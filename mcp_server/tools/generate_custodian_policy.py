# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for generating Cloud Custodian policies from compliance violations."""

import logging
from typing import Any

import yaml
from pydantic import BaseModel, Field

from ..services.compliance_service import ComplianceService
from ..services.policy_service import PolicyService

logger = logging.getLogger(__name__)

# Mapping from our internal resource types to Cloud Custodian resource names
CUSTODIAN_RESOURCE_MAP: dict[str, str] = {
    "ec2:instance": "ec2",
    "ec2:volume": "ebs",
    "rds:db": "rds",
    "s3:bucket": "s3",
    "lambda:function": "lambda",
    "ecs:service": "ecs-service",
    "ecs:cluster": "ecs",
    "ecs:task-definition": "ecs-task-definition",
    "eks:cluster": "eks",
    "eks:nodegroup": "eks-nodegroup",
    "elasticloadbalancing:loadbalancer": "elb",
    "elasticloadbalancing:targetgroup": "app-elb-target-group",
    "dynamodb:table": "dynamodb-table",
    "elasticache:cluster": "cache-cluster",
    "redshift:cluster": "redshift",
    "sagemaker:endpoint": "sagemaker-endpoint",
    "sagemaker:notebook-instance": "sagemaker-notebook",
    "opensearch:domain": "opensearch",
    "sns:topic": "sns",
    "sqs:queue": "sqs",
    "kms:key": "kms-key",
    "logs:log-group": "log-group",
    "secretsmanager:secret": "secrets-manager",
    "ecr:repository": "ecr",
    "kinesis:stream": "kinesis",
    "glue:job": "glue-job",
    "glue:crawler": "glue-crawler",
    "glue:database": "glue-database",
    "athena:workgroup": "athena-workgroup",
    "cognito-idp:userpool": "cognito-user-pool",
    "cloudwatch:alarm": "alarm",
    "elasticfilesystem:file-system": "efs",
    "fsx:file-system": "fsx",
    "ec2:natgateway": "nat-gateway",
    "ec2:vpc": "vpc",
    "ec2:subnet": "subnet",
    "ec2:security-group": "security-group",
    "bedrock:agent": "bedrock-agent-alias",
    "bedrock:knowledge-base": "bedrock-knowledge-base",
}


class CustodianPolicyOutput(BaseModel):
    """A single generated Cloud Custodian policy."""

    name: str = Field(..., description="Policy name")
    resource_type: str = Field(..., description="Cloud Custodian resource type")
    yaml_content: str = Field(..., description="Complete YAML policy content")
    description: str = Field(..., description="Human-readable description")
    filter_count: int = Field(0, description="Number of tag filters in policy")
    action_type: str = Field(
        ..., description="Action type: 'tag' for enforcement, 'notify' for dry-run"
    )


class GenerateCustodianPolicyResult(BaseModel):
    """Result from the generate_custodian_policy tool."""

    policies: list[CustodianPolicyOutput] = Field(
        default_factory=list, description="Generated Cloud Custodian policies"
    )
    combined_yaml: str = Field(
        "", description="All policies combined into a single YAML document"
    )
    total_policies: int = Field(0, description="Number of policies generated")
    resource_types_covered: list[str] = Field(
        default_factory=list, description="Resource types covered by policies"
    )
    dry_run: bool = Field(
        False, description="Whether policies use notify (dry-run) or tag (enforce) actions"
    )
    target_tags: list[str] = Field(
        default_factory=list, description="Tags targeted for enforcement"
    )

    def model_post_init(self, __context) -> None:
        """Compute total_policies after initialization."""
        object.__setattr__(self, "total_policies", len(self.policies))


async def generate_custodian_policy(
    policy_service: PolicyService,
    resource_types: list[str],
    violation_types: list[str] | None = None,
    target_tags: list[str] | None = None,
    dry_run: bool = True,
    compliance_service: ComplianceService | None = None,
) -> GenerateCustodianPolicyResult:
    """
    Generate Cloud Custodian YAML policies from compliance violations.

    Creates ready-to-execute Cloud Custodian policies that enforce tag
    compliance based on the organization's tagging policy. Supports tag
    enforcement, tag normalization, and missing tag remediation.

    Args:
        policy_service: PolicyService for retrieving tagging policy configuration
        resource_types: List of resource types to generate policies for
            (e.g., ["ec2:instance", "rds:db"]). Does not support "all".
        violation_types: Types of violations to address. Options:
            - "missing_tag": Tags that are absent from resources
            - "invalid_value": Tags with values not in the allowed list
            If None, addresses all violation types.
        target_tags: Specific tag keys to include in policies.
            If None, uses all required tags from the tagging policy.
        dry_run: If True, generates 'notify' actions (safe preview).
            If False, generates 'tag' actions (actual enforcement).
            Default: True.
        compliance_service: Optional ComplianceService (unused currently,
            reserved for future violation-driven generation).

    Returns:
        GenerateCustodianPolicyResult containing:
        - policies: List of individual policy objects with YAML content
        - combined_yaml: All policies in a single YAML document
        - total_policies: Number of policies generated
        - resource_types_covered: Which resource types have policies
        - dry_run: Whether dry-run mode was used
        - target_tags: Which tags are being enforced

    Raises:
        ValueError: If resource_types is empty or contains unsupported types

    Example:
        >>> result = await generate_custodian_policy(
        ...     policy_service=policy,
        ...     resource_types=["ec2:instance", "rds:db"],
        ...     dry_run=True,
        ... )
        >>> print(result.combined_yaml)
    """
    if not resource_types:
        raise ValueError("resource_types cannot be empty")

    # Validate violation_types if provided
    valid_violation_types = {"missing_tag", "invalid_value"}
    if violation_types:
        for vt in violation_types:
            if vt not in valid_violation_types:
                raise ValueError(
                    f"Invalid violation_type '{vt}'. Must be one of: {valid_violation_types}"
                )
    else:
        violation_types = list(valid_violation_types)

    logger.info(
        f"Generating Cloud Custodian policies for resource_types={resource_types}, "
        f"violation_types={violation_types}, dry_run={dry_run}"
    )

    # Get the tagging policy to know which tags are required
    policy = policy_service.get_policy()

    # Determine which tags to enforce
    if target_tags:
        tags_to_enforce = [
            tag for tag in policy.required_tags if tag.name in target_tags
        ]
        if not tags_to_enforce:
            # If no required tags match, check if user provided names that exist
            # as optional tags, and warn
            raise ValueError(
                f"None of the target_tags {target_tags} match required tags in the policy. "
                f"Available required tags: {[t.name for t in policy.required_tags]}"
            )
    else:
        tags_to_enforce = policy.required_tags
        target_tags = [t.name for t in tags_to_enforce]

    policies: list[CustodianPolicyOutput] = []
    resource_types_covered: list[str] = []

    for resource_type in resource_types:
        custodian_resource = CUSTODIAN_RESOURCE_MAP.get(resource_type)
        if not custodian_resource:
            logger.warning(
                f"No Cloud Custodian mapping for resource type '{resource_type}', skipping"
            )
            continue

        # Filter tags that apply to this resource type
        applicable_tags = []
        for tag in tags_to_enforce:
            if not tag.applies_to or resource_type in tag.applies_to:
                applicable_tags.append(tag)

        if not applicable_tags:
            logger.info(f"No applicable tags for {resource_type}, skipping")
            continue

        # Build the Cloud Custodian policy
        custodian_policy = _build_custodian_policy(
            resource_type=resource_type,
            custodian_resource=custodian_resource,
            tags=applicable_tags,
            violation_types=violation_types,
            dry_run=dry_run,
        )

        if custodian_policy:
            yaml_content = yaml.dump(
                {"policies": [custodian_policy]},
                default_flow_style=False,
                sort_keys=False,
            )

            # Count filters
            filters = custodian_policy.get("filters", [])
            filter_count = 0
            for f in filters:
                if isinstance(f, dict) and "or" in f:
                    filter_count = len(f["or"])
                elif isinstance(f, str) or isinstance(f, dict):
                    filter_count += 1

            policies.append(
                CustodianPolicyOutput(
                    name=custodian_policy["name"],
                    resource_type=custodian_resource,
                    yaml_content=yaml_content,
                    description=custodian_policy.get("description", ""),
                    filter_count=filter_count,
                    action_type="notify" if dry_run else "tag",
                )
            )
            resource_types_covered.append(resource_type)

    # Build combined YAML
    combined_policies = []
    for p in policies:
        # Parse back the individual YAML to combine
        parsed = yaml.safe_load(p.yaml_content)
        combined_policies.extend(parsed.get("policies", []))

    combined_yaml = ""
    if combined_policies:
        combined_yaml = yaml.dump(
            {"policies": combined_policies},
            default_flow_style=False,
            sort_keys=False,
        )

    logger.info(f"Generated {len(policies)} Cloud Custodian policies")

    return GenerateCustodianPolicyResult(
        policies=policies,
        combined_yaml=combined_yaml,
        resource_types_covered=resource_types_covered,
        dry_run=dry_run,
        target_tags=target_tags,
    )


def _build_custodian_policy(
    resource_type: str,
    custodian_resource: str,
    tags: list,
    violation_types: list[str],
    dry_run: bool,
) -> dict[str, Any] | None:
    """Build a single Cloud Custodian policy dict.

    Args:
        resource_type: Internal resource type (e.g., "ec2:instance")
        custodian_resource: Cloud Custodian resource name (e.g., "ec2")
        tags: List of RequiredTag objects to enforce
        violation_types: Which violation types to address
        dry_run: Whether to use notify vs tag actions

    Returns:
        Cloud Custodian policy dict, or None if no filters apply
    """
    safe_name = resource_type.replace(":", "-").replace("_", "-")
    policy_name = f"enforce-required-tags-{safe_name}"

    filters: list[dict[str, Any] | str] = []

    # Build filters based on violation types
    if "missing_tag" in violation_types:
        absent_filters = []
        for tag in tags:
            absent_filters.append({f"tag:{tag.name}": "absent"})
        if absent_filters:
            if len(absent_filters) == 1:
                filters.extend(absent_filters)
            else:
                filters.append({"or": absent_filters})

    if "invalid_value" in violation_types:
        for tag in tags:
            if tag.allowed_values:
                # Filter for tags present but with invalid values
                filters.append(
                    {
                        "type": "value",
                        "key": f"tag:{tag.name}",
                        "op": "not-in",
                        "value": tag.allowed_values,
                    }
                )

    if not filters:
        return None

    # Build actions
    actions: list[dict[str, Any]] = []
    if dry_run:
        actions.append(
            {
                "type": "notify",
                "template": "default.html",
                "subject": f"Tag Compliance Violation - {resource_type}",
                "violation_desc": (
                    f"Resources of type {resource_type} are missing required tags "
                    f"or have invalid tag values."
                ),
                "to": ["resource-owner"],
                "transport": {
                    "type": "sqs",
                    "queue": "https://sqs.{region}.amazonaws.com/{account_id}/custodian-mailer",
                },
            }
        )
    else:
        # Build default tag values for missing tags
        default_tags: dict[str, str] = {}
        for tag in tags:
            if tag.allowed_values:
                default_tags[tag.name] = tag.allowed_values[0]
            else:
                default_tags[tag.name] = "unassigned"

        actions.append({"type": "tag", "tags": default_tags})

    tag_names = [t.name for t in tags]
    description = (
        f"Enforce required tags ({', '.join(tag_names)}) "
        f"on {resource_type} resources."
    )
    if dry_run:
        description += " [DRY RUN - notify only]"

    return {
        "name": policy_name,
        "description": description,
        "resource": custodian_resource,
        "filters": filters,
        "actions": actions,
    }
