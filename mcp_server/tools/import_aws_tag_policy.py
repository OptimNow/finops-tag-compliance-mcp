# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for importing and converting AWS Organizations tag policies at runtime."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from pydantic import BaseModel, Field

from ..clients.aws_client import AWSClient

logger = logging.getLogger(__name__)

# Service-to-resource-type mappings for ALL_SUPPORTED expansion
SERVICE_RESOURCE_MAPPINGS: dict[str, list[str]] = {
    "ec2": ["ec2:instance", "ec2:volume"],
    "s3": ["s3:bucket"],
    "rds": ["rds:db"],
    "lambda": ["lambda:function"],
    "ecs": ["ecs:service", "ecs:cluster"],
    "eks": ["eks:cluster"],
    "secretsmanager": ["secretsmanager:secret"],
    "dynamodb": ["dynamodb:table"],
    "elasticache": ["elasticache:cluster"],
    "redshift": ["redshift:cluster"],
    "sagemaker": ["sagemaker:endpoint", "sagemaker:notebook-instance"],
    "opensearch": ["opensearch:domain"],
    "sns": ["sns:topic"],
    "sqs": ["sqs:queue"],
    "kms": ["kms:key"],
    "logs": ["logs:log-group"],
    "ecr": ["ecr:repository"],
    "kinesis": ["kinesis:stream"],
    "glue": ["glue:job", "glue:crawler", "glue:database"],
    "athena": ["athena:workgroup"],
}


class PolicySummary(BaseModel):
    """Summary of the converted policy."""

    required_tags_count: int = Field(0, description="Number of required tags")
    optional_tags_count: int = Field(0, description="Number of optional tags")
    enforced_services: list[str] = Field(
        default_factory=list, description="Services with enforced tags"
    )


class AvailablePolicy(BaseModel):
    """An available AWS Organizations tag policy."""

    policy_id: str = Field(..., description="AWS policy ID")
    policy_name: str = Field(..., description="Policy name")
    description: str = Field("", description="Policy description")


class ImportAwsTagPolicyResult(BaseModel):
    """Result from the import_aws_tag_policy tool."""

    status: str = Field(
        ..., description="Status: 'success', 'saved', 'listed', or 'error'"
    )
    policy: dict | None = Field(
        None, description="Converted policy in MCP format (when status is success/saved)"
    )
    saved_to: str | None = Field(
        None, description="File path where policy was saved (when save_to_file=True)"
    )
    summary: PolicySummary | None = Field(
        None, description="Quick summary of the converted policy"
    )
    available_policies: list[AvailablePolicy] | None = Field(
        None, description="List of available policies (when listing)"
    )
    message: str = Field("", description="Human-readable status message")
    conversion_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the conversion was performed",
    )


async def import_aws_tag_policy(
    aws_client: AWSClient,
    policy_id: str | None = None,
    save_to_file: bool = True,
    output_path: str = "policies/tagging_policy.json",
) -> ImportAwsTagPolicyResult:
    """
    Fetch and convert an AWS Organizations tag policy to MCP format.

    Connects to AWS Organizations to retrieve tag policies and converts
    them to the MCP server's tagging policy format. If no policy_id is
    provided, lists all available tag policies.

    Args:
        aws_client: AWSClient for AWS API calls
        policy_id: AWS Organizations policy ID (e.g., "p-xxxxxxxx").
            If None, lists all available tag policies instead of importing.
        save_to_file: Whether to save the converted policy to a file.
            Default: True
        output_path: File path to save the converted policy.
            Default: "policies/tagging_policy.json"

    Returns:
        ImportAwsTagPolicyResult containing:
        - status: "success"/"saved"/"listed"/"error"
        - policy: The converted policy dict (when importing)
        - saved_to: File path (when saving)
        - summary: Quick stats about the policy
        - available_policies: List of policies (when listing)
        - message: Human-readable description

    Raises:
        ValueError: If the AWS policy format is invalid

    Example:
        >>> # List available policies
        >>> result = await import_aws_tag_policy(aws_client=client)
        >>> for p in result.available_policies:
        ...     print(f"{p.policy_id}: {p.policy_name}")
        >>>
        >>> # Import a specific policy
        >>> result = await import_aws_tag_policy(
        ...     aws_client=client,
        ...     policy_id="p-abc12345",
        ... )
        >>> print(f"Imported {result.summary.required_tags_count} required tags")
    """
    logger.info(f"Import AWS tag policy: policy_id={policy_id}")

    # If no policy_id, list available policies
    if not policy_id:
        return await _list_available_policies(aws_client)

    # Fetch the policy from AWS Organizations
    try:
        policy_content = await _fetch_policy(aws_client, policy_id)
    except Exception as e:
        error_msg = str(e)
        if "AccessDenied" in error_msg or "not authorized" in error_msg.lower():
            return ImportAwsTagPolicyResult(
                status="error",
                message=(
                    f"Insufficient permissions to access AWS Organizations policy. "
                    f"Required IAM permissions: organizations:DescribePolicy, "
                    f"organizations:ListPolicies. Error: {error_msg}"
                ),
            )
        raise

    # Convert the AWS policy to MCP format
    converted = _convert_aws_policy(policy_content)

    # Build summary
    enforced_services = set()
    for tag in converted.get("required_tags", []):
        for applies_to in tag.get("applies_to", []):
            service = applies_to.split(":")[0] if ":" in applies_to else applies_to
            enforced_services.add(service)

    summary = PolicySummary(
        required_tags_count=len(converted.get("required_tags", [])),
        optional_tags_count=len(converted.get("optional_tags", [])),
        enforced_services=sorted(enforced_services),
    )

    # Save to file if requested
    saved_to = None
    if save_to_file:
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(converted, f, indent=2, default=str)
            saved_to = str(output_file)
            logger.info(f"Policy saved to {saved_to}")
        except Exception as e:
            logger.error(f"Failed to save policy to {output_path}: {e}")
            return ImportAwsTagPolicyResult(
                status="error",
                policy=converted,
                summary=summary,
                message=f"Policy converted successfully but failed to save: {e}",
            )

    status = "saved" if saved_to else "success"
    message = (
        f"Successfully imported AWS tag policy '{policy_id}'. "
        f"Found {summary.required_tags_count} required tags and "
        f"{summary.optional_tags_count} optional tags."
    )
    if saved_to:
        message += f" Saved to {saved_to}."

    return ImportAwsTagPolicyResult(
        status=status,
        policy=converted,
        saved_to=saved_to,
        summary=summary,
        message=message,
    )


async def _list_available_policies(aws_client: AWSClient) -> ImportAwsTagPolicyResult:
    """List available AWS Organizations tag policies.

    Args:
        aws_client: AWSClient for API calls

    Returns:
        ImportAwsTagPolicyResult with available_policies populated
    """
    try:
        organizations_client = await asyncio.to_thread(
            boto3.client, "organizations", region_name=aws_client.region
        )
        response = await asyncio.to_thread(
            organizations_client.list_policies,
            Filter="TAG_POLICY",
        )

        policies = []
        for p in response.get("Policies", []):
            policies.append(
                AvailablePolicy(
                    policy_id=p.get("Id", ""),
                    policy_name=p.get("Name", ""),
                    description=p.get("Description", ""),
                )
            )

        if policies:
            message = f"Found {len(policies)} AWS Organizations tag policies."
        else:
            message = (
                "No tag policies found in AWS Organizations. "
                "Tag policies may not be enabled or you may lack permissions. "
                "Required: organizations:ListPolicies"
            )

        return ImportAwsTagPolicyResult(
            status="listed",
            available_policies=policies,
            message=message,
        )

    except Exception as e:
        error_msg = str(e)
        if "AccessDenied" in error_msg or "not authorized" in error_msg.lower():
            return ImportAwsTagPolicyResult(
                status="error",
                message=(
                    "Insufficient permissions to list AWS Organizations policies. "
                    "Required: organizations:ListPolicies. "
                    f"Error: {error_msg}"
                ),
            )
        return ImportAwsTagPolicyResult(
            status="error",
            message=f"Error listing policies: {error_msg}",
        )


async def _fetch_policy(aws_client: AWSClient, policy_id: str) -> dict:
    """Fetch a specific policy from AWS Organizations.

    Args:
        aws_client: AWSClient for API calls
        policy_id: The AWS policy ID

    Returns:
        Parsed policy content dict

    Raises:
        Exception: If the API call fails
    """
    organizations_client = await asyncio.to_thread(
        boto3.client, "organizations", region_name=aws_client.region
    )
    response = await asyncio.to_thread(
        organizations_client.describe_policy,
        PolicyId=policy_id,
    )

    policy = response.get("Policy", {})
    content_str = policy.get("Content", "{}")
    return json.loads(content_str)


def _convert_aws_policy(aws_policy: dict) -> dict[str, Any]:
    """Convert an AWS Organizations tag policy to MCP format.

    AWS format:
    {
        "tags": {
            "Environment": {
                "tag_key": {"@@assign": "Environment"},
                "tag_value": {"@@assign": ["production", "staging", "development"]},
                "enforced_for": {"@@assign": ["ec2:instance", "s3:*"]}
            }
        }
    }

    MCP format:
    {
        "required_tags": [
            {
                "name": "Environment",
                "description": "Imported from AWS Organizations",
                "allowed_values": ["production", "staging", "development"],
                "validation_regex": null,
                "applies_to": ["ec2:instance", "s3:bucket"]
            }
        ],
        "optional_tags": []
    }

    Args:
        aws_policy: Parsed AWS tag policy dict

    Returns:
        MCP format policy dict
    """
    required_tags: list[dict[str, Any]] = []
    optional_tags: list[dict[str, Any]] = []

    tags_config = aws_policy.get("tags", {})

    for tag_key, tag_config in tags_config.items():
        # Extract tag key name (use @@assign if present)
        tag_key_config = tag_config.get("tag_key", {})
        if isinstance(tag_key_config, dict):
            name = tag_key_config.get("@@assign", tag_key)
        else:
            name = tag_key

        # Extract allowed values
        tag_value_config = tag_config.get("tag_value", {})
        allowed_values = _extract_tag_values(tag_value_config)

        # Extract enforced_for (which resource types this applies to)
        enforced_config = tag_config.get("enforced_for", {})
        applies_to = _parse_enforced_for(enforced_config)

        # Determine if required or optional
        # Tags with enforced_for are required; others are optional
        tag_entry = {
            "name": name,
            "description": f"Imported from AWS Organizations tag policy",
            "allowed_values": allowed_values,
            "validation_regex": None,
            "applies_to": applies_to,
        }

        if applies_to:
            required_tags.append(tag_entry)
        else:
            optional_tags.append(tag_entry)

    return {
        "version": "1.0",
        "required_tags": required_tags,
        "optional_tags": optional_tags,
        "metadata": {
            "source": "aws_organizations",
            "imported_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _extract_tag_values(tag_value_config: Any) -> list[str] | None:
    """Extract allowed values from AWS policy format.

    Args:
        tag_value_config: The tag_value section of an AWS tag policy

    Returns:
        List of allowed values, or None if unrestricted
    """
    if not tag_value_config:
        return None

    if isinstance(tag_value_config, dict):
        values = tag_value_config.get("@@assign", [])
    elif isinstance(tag_value_config, list):
        values = tag_value_config
    else:
        return None

    # Clean values: remove wildcards (not supported)
    clean_values = []
    for val in values:
        if isinstance(val, str):
            # Remove trailing wildcards
            cleaned = val.rstrip("*")
            if cleaned:
                clean_values.append(cleaned)

    return clean_values if clean_values else None


def _parse_enforced_for(enforced_config: Any) -> list[str]:
    """Convert AWS enforced_for to our applies_to format.

    Args:
        enforced_config: The enforced_for section of an AWS tag policy

    Returns:
        List of resource type strings
    """
    if not enforced_config:
        return []

    if isinstance(enforced_config, dict):
        resources = enforced_config.get("@@assign", [])
    elif isinstance(enforced_config, list):
        resources = enforced_config
    else:
        return []

    applies_to = []
    for resource in resources:
        if not isinstance(resource, str):
            continue

        if ":ALL_SUPPORTED" in resource or resource.endswith(":*"):
            # Expand ALL_SUPPORTED to known resource types
            service = resource.split(":")[0]
            mapped = SERVICE_RESOURCE_MAPPINGS.get(service, [f"{service}:resource"])
            applies_to.extend(mapped)
        else:
            applies_to.append(resource)

    return applies_to
