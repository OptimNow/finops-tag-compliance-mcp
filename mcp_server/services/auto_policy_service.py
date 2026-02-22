# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Auto-policy detection and loading service.

On server startup, this service determines the tagging policy source:
1. Existing policy file → use as-is
2. AWS Organizations tag policy → import and convert
3. Fallback → create a sensible default policy

Phase 2.4: Auto-Policy Detection on Startup
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Default tagging policy when no other source is available
DEFAULT_POLICY: dict[str, Any] = {
    "version": "1.0",
    "required_tags": [
        {
            "name": "Owner",
            "description": "Team or individual responsible for the resource",
            "allowed_values": None,
            "validation_regex": None,
            "applies_to": [],
        },
        {
            "name": "Environment",
            "description": "Deployment environment (production, staging, development, test)",
            "allowed_values": ["production", "staging", "development", "test"],
            "validation_regex": None,
            "applies_to": [],
        },
        {
            "name": "Application",
            "description": "Application or service name this resource belongs to",
            "allowed_values": None,
            "validation_regex": None,
            "applies_to": [],
        },
    ],
    "optional_tags": [
        {
            "name": "Project",
            "description": "Project or initiative name",
            "allowed_values": None,
            "validation_regex": None,
            "applies_to": [],
        },
        {
            "name": "CostCenter",
            "description": "Cost center for financial attribution",
            "allowed_values": None,
            "validation_regex": None,
            "applies_to": [],
        },
    ],
    "tag_naming_rules": {
        "case_sensitivity": False,
        "max_key_length": 128,
        "max_value_length": 256,
    },
    "metadata": {
        "source": "default",
        "created_at": None,  # Will be filled at creation time
        "description": "Default tagging policy - customize to match your organization's requirements",
    },
}

# Service-to-resource-type mappings for ALL_SUPPORTED expansion
# Duplicated from import_aws_tag_policy.py to avoid circular imports
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


class AutoPolicyResult:
    """Result of the auto-policy detection process."""

    def __init__(
        self,
        source: str,
        policy_path: str,
        success: bool,
        message: str,
        aws_policy_id: Optional[str] = None,
    ):
        self.source = source  # "existing_file", "aws_organizations", "default"
        self.policy_path = policy_path
        self.success = success
        self.message = message
        self.aws_policy_id = aws_policy_id


class AutoPolicyService:
    """Detects and loads tagging policy automatically on startup.

    Decision flow:
    1. Check if policy file exists → use it
    2. If auto_import enabled → try AWS Organizations
    3. Fallback → create default policy

    Usage::

        service = AutoPolicyService(
            policy_path="policies/tagging_policy.json",
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=boto3_session)
        # result.source tells you what happened
    """

    def __init__(
        self,
        policy_path: str = "policies/tagging_policy.json",
        auto_import: bool = True,
        aws_policy_id: Optional[str] = None,
        fallback_to_default: bool = True,
    ):
        self._policy_path = Path(policy_path)
        self._auto_import = auto_import
        self._aws_policy_id = aws_policy_id
        self._fallback_to_default = fallback_to_default

    async def detect_and_load(
        self, aws_session: Optional[Any] = None
    ) -> AutoPolicyResult:
        """Run the full auto-detection flow.

        Args:
            aws_session: A boto3 Session. Required for AWS Organizations import.
                        If None, AWS import is skipped.

        Returns:
            AutoPolicyResult describing what happened.
        """
        # Step 1: Check if policy file already exists
        if self._policy_path.exists():
            logger.info(
                f"AutoPolicy: existing policy file found at {self._policy_path}"
            )
            return AutoPolicyResult(
                source="existing_file",
                policy_path=str(self._policy_path),
                success=True,
                message=f"Using existing policy file: {self._policy_path}",
            )

        logger.info(
            f"AutoPolicy: no policy file at {self._policy_path}, "
            f"starting auto-detection"
        )

        # Step 2: Try AWS Organizations import
        if self._auto_import and aws_session is not None:
            result = await self._try_aws_import(aws_session)
            if result is not None:
                return result

        # Step 3: Fallback to default policy
        if self._fallback_to_default:
            return await self._create_default_policy()

        # No fallback allowed
        return AutoPolicyResult(
            source="none",
            policy_path=str(self._policy_path),
            success=False,
            message=(
                f"No policy file found at {self._policy_path} and "
                f"auto-import failed or disabled. "
                f"Create a policy file manually."
            ),
        )

    async def _try_aws_import(
        self, aws_session: Any
    ) -> Optional[AutoPolicyResult]:
        """Try to import a tag policy from AWS Organizations.

        Returns AutoPolicyResult on success, None on failure (so caller falls through).
        """
        try:
            logger.info("AutoPolicy: attempting AWS Organizations tag policy import")

            # Create Organizations client
            org_client = await asyncio.to_thread(
                aws_session.client, "organizations"
            )

            # List tag policies
            if self._aws_policy_id:
                # User specified a specific policy ID
                policy_id = self._aws_policy_id
                logger.info(
                    f"AutoPolicy: using specified policy ID: {policy_id}"
                )
            else:
                # Auto-detect: find the first tag policy
                response = await asyncio.to_thread(
                    org_client.list_policies, Filter="TAG_POLICY"
                )
                policies = response.get("Policies", [])

                if not policies:
                    logger.info(
                        "AutoPolicy: no tag policies found in AWS Organizations"
                    )
                    return None

                policy_id = policies[0]["Id"]
                logger.info(
                    f"AutoPolicy: found {len(policies)} tag policies, "
                    f"using first: {policy_id} "
                    f"({policies[0].get('Name', 'unnamed')})"
                )

            # Fetch the policy content
            describe_response = await asyncio.to_thread(
                org_client.describe_policy, PolicyId=policy_id
            )
            content_str = describe_response["Policy"]["Content"]
            aws_policy = json.loads(content_str)

            # Convert to MCP format
            mcp_policy = _convert_aws_policy(aws_policy)

            # Save to file
            await self._save_policy(mcp_policy)

            logger.info(
                f"AutoPolicy: imported AWS Organizations tag policy "
                f"({policy_id}) and saved to {self._policy_path}"
            )

            return AutoPolicyResult(
                source="aws_organizations",
                policy_path=str(self._policy_path),
                success=True,
                message=(
                    f"Imported tag policy from AWS Organizations "
                    f"(policy_id={policy_id}) and saved to {self._policy_path}"
                ),
                aws_policy_id=policy_id,
            )

        except Exception as e:
            error_str = str(e)
            if "AccessDenied" in error_str or "not authorized" in error_str.lower():
                logger.warning(
                    f"AutoPolicy: insufficient permissions for AWS Organizations: {e}"
                )
            elif "AWSOrganizationsNotInUse" in error_str:
                logger.info(
                    "AutoPolicy: AWS Organizations is not enabled in this account"
                )
            else:
                logger.warning(
                    f"AutoPolicy: failed to import from AWS Organizations: {e}"
                )
            return None

    async def _create_default_policy(self) -> AutoPolicyResult:
        """Create and save the default policy."""
        policy = DEFAULT_POLICY.copy()
        # Deep copy nested structures
        policy["required_tags"] = [t.copy() for t in DEFAULT_POLICY["required_tags"]]
        policy["optional_tags"] = [t.copy() for t in DEFAULT_POLICY["optional_tags"]]
        policy["tag_naming_rules"] = DEFAULT_POLICY["tag_naming_rules"].copy()
        policy["metadata"] = DEFAULT_POLICY["metadata"].copy()
        policy["metadata"]["created_at"] = datetime.now(timezone.utc).isoformat()
        policy["metadata"]["source"] = "default"

        try:
            await self._save_policy(policy)
            logger.info(
                f"AutoPolicy: created default policy at {self._policy_path}"
            )
            return AutoPolicyResult(
                source="default",
                policy_path=str(self._policy_path),
                success=True,
                message=(
                    f"Created default tagging policy at {self._policy_path}. "
                    f"Customize it to match your organization's tagging standards."
                ),
            )
        except Exception as e:
            logger.error(f"AutoPolicy: failed to create default policy: {e}")
            return AutoPolicyResult(
                source="default",
                policy_path=str(self._policy_path),
                success=False,
                message=f"Failed to create default policy: {e}",
            )

    async def _save_policy(self, policy: dict) -> None:
        """Save policy to the configured path, creating directories if needed."""
        # Ensure parent directory exists
        self._policy_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self._policy_path, "w", encoding="utf-8") as f:
            json.dump(policy, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# AWS Policy Conversion (shared logic with import_aws_tag_policy.py)
# ---------------------------------------------------------------------------


def _convert_aws_policy(aws_policy: dict) -> dict:
    """Convert AWS Organizations tag policy format to MCP format.

    AWS Organizations format:
        {
            "tags": {
                "Environment": {
                    "tag_key": {"@@assign": "Environment"},
                    "tag_value": {"@@assign": ["production", "staging"]},
                    "enforced_for": {"@@assign": ["ec2:instance"]}
                }
            }
        }

    MCP format:
        {
            "version": "1.0",
            "required_tags": [...],
            "optional_tags": [...],
            "metadata": {...}
        }
    """
    required_tags: list[dict] = []
    optional_tags: list[dict] = []

    tags_section = aws_policy.get("tags", {})

    for tag_key, tag_config in tags_section.items():
        if not isinstance(tag_config, dict):
            continue

        # Extract tag name
        tag_key_obj = tag_config.get("tag_key", {})
        if isinstance(tag_key_obj, dict):
            name = tag_key_obj.get("@@assign", tag_key)
        else:
            name = tag_key

        # Extract allowed values
        tag_value = tag_config.get("tag_value")
        allowed_values = _extract_tag_values(tag_value)

        # Extract enforced resource types
        enforced_for = tag_config.get("enforced_for")
        applies_to = _parse_enforced_for(enforced_for)

        # Build tag entry
        tag_entry = {
            "name": name,
            "description": f"Imported from AWS Organizations tag policy: {name}",
            "allowed_values": allowed_values,
            "validation_regex": None,
            "applies_to": applies_to,
        }

        # Tags with enforced_for are required; others are optional
        if applies_to:
            required_tags.append(tag_entry)
        else:
            optional_tags.append(tag_entry)

    return {
        "version": "1.0",
        "required_tags": required_tags,
        "optional_tags": optional_tags,
        "tag_naming_rules": {
            "case_sensitivity": False,
            "max_key_length": 128,
            "max_value_length": 256,
        },
        "metadata": {
            "source": "aws_organizations",
            "imported_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _extract_tag_values(tag_value: Any) -> Optional[list[str]]:
    """Extract allowed values from AWS tag policy tag_value field."""
    if tag_value is None:
        return None

    if isinstance(tag_value, dict):
        values = tag_value.get("@@assign", [])
    elif isinstance(tag_value, list):
        values = tag_value
    else:
        return None

    if not values:
        return None

    # Clean up wildcard entries
    cleaned = []
    for v in values:
        if not isinstance(v, str):
            continue
        v = v.rstrip("*")
        if v:
            cleaned.append(v)

    return cleaned if cleaned else None


def _parse_enforced_for(enforced_for: Any) -> list[str]:
    """Parse the enforced_for section to get resource type list."""
    if enforced_for is None:
        return []

    if isinstance(enforced_for, dict):
        resources = enforced_for.get("@@assign", [])
    elif isinstance(enforced_for, list):
        resources = enforced_for
    else:
        return []

    result: list[str] = []
    for resource in resources:
        if not isinstance(resource, str):
            continue

        # Handle ALL_SUPPORTED and wildcard patterns
        if ":ALL_SUPPORTED" in resource or ":*" in resource:
            service = resource.split(":")[0]
            if service in SERVICE_RESOURCE_MAPPINGS:
                result.extend(SERVICE_RESOURCE_MAPPINGS[service])
            else:
                result.append(f"{service}:resource")
        else:
            result.append(resource)

    return result
