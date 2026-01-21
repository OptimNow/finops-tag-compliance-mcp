# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for retrieving the tagging policy configuration."""

import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, computed_field

from ..models.policy import TagPolicy, RequiredTag, OptionalTag, TagNamingRules
from ..services.policy_service import PolicyService

logger = logging.getLogger(__name__)


class RequiredTagInfo(BaseModel):
    """Information about a required tag."""

    name: str
    description: Optional[str] = None
    allowed_values: Optional[list[str]] = None
    validation_regex: Optional[str] = None
    applies_to: list[str] = Field(default_factory=list)


class OptionalTagInfo(BaseModel):
    """Information about an optional tag."""

    name: str
    description: Optional[str] = None
    allowed_values: Optional[list[str]] = None


class TagNamingRulesInfo(BaseModel):
    """Information about tag naming rules."""

    case_sensitivity: bool = False
    allow_special_characters: bool = False
    max_key_length: int = 128
    max_value_length: int = 256


class GetTaggingPolicyResult(BaseModel):
    """Result from the get_tagging_policy tool."""

    version: str = Field(..., description="Policy version string")
    last_updated: datetime = Field(..., description="When policy was last updated")
    required_tags: list[RequiredTagInfo] = Field(
        default_factory=list, description="Required tags with configuration"
    )
    optional_tags: list[OptionalTagInfo] = Field(
        default_factory=list, description="Optional tags with descriptions"
    )
    tag_naming_rules: TagNamingRulesInfo = Field(
        default_factory=TagNamingRulesInfo, description="Rules for tag naming"
    )

    @computed_field
    @property
    def required_tag_count(self) -> int:
        """Number of required tags."""
        return len(self.required_tags)

    @computed_field
    @property
    def optional_tag_count(self) -> int:
        """Number of optional tags."""
        return len(self.optional_tags)

    @classmethod
    def from_policy(cls, policy: TagPolicy) -> "GetTaggingPolicyResult":
        """Create result from a TagPolicy instance."""
        return cls(
            version=policy.version,
            last_updated=policy.last_updated,
            required_tags=[
                RequiredTagInfo(
                    name=tag.name,
                    description=tag.description,
                    allowed_values=tag.allowed_values,
                    validation_regex=tag.validation_regex,
                    applies_to=tag.applies_to or [],
                )
                for tag in policy.required_tags
            ],
            optional_tags=[
                OptionalTagInfo(
                    name=tag.name,
                    description=tag.description,
                    allowed_values=tag.allowed_values,
                )
                for tag in policy.optional_tags
            ],
            tag_naming_rules=TagNamingRulesInfo(
                case_sensitivity=policy.tag_naming_rules.case_sensitivity,
                allow_special_characters=policy.tag_naming_rules.allow_special_characters,
                max_key_length=policy.tag_naming_rules.max_key_length,
                max_value_length=policy.tag_naming_rules.max_value_length,
            ),
        )


async def get_tagging_policy(
    policy_service: PolicyService,
) -> GetTaggingPolicyResult:
    """
    Retrieve the complete tagging policy configuration.

    This tool returns the organization's tagging policy, including:
    - Required tags with their descriptions, allowed values, and validation rules
    - Optional tags with their descriptions
    - Tag naming rules and conventions
    - Which resource types each tag applies to

    Args:
        policy_service: PolicyService instance for accessing the policy

    Returns:
        GetTaggingPolicyResult containing:
        - version: Policy version string
        - last_updated: Timestamp when policy was last updated
        - required_tags: List of required tags with full configuration
        - optional_tags: List of optional tags with descriptions
        - tag_naming_rules: Rules for tag naming conventions
        - required_tag_count: Number of required tags
        - optional_tag_count: Number of optional tags

    Requirements: 6.1, 6.2, 6.3, 6.4

    Example:
        >>> result = await get_tagging_policy(policy_service=policy)
        >>> print(f"Policy version: {result.version}")
        >>> print(f"Required tags: {result.required_tag_count}")
        >>> for tag in result.required_tags:
        ...     print(f"  - {tag.name}: {tag.description}")
        ...     if tag.allowed_values:
        ...         print(f"    Allowed values: {', '.join(tag.allowed_values)}")
        ...     print(f"    Applies to: {', '.join(tag.applies_to)}")
    """
    logger.info("Retrieving tagging policy configuration")

    # Get the policy from the service
    policy = policy_service.get_policy()

    logger.info(
        f"Retrieved policy version {policy.version} with "
        f"{len(policy.required_tags)} required tags and "
        f"{len(policy.optional_tags)} optional tags"
    )

    return GetTaggingPolicyResult.from_policy(policy)
