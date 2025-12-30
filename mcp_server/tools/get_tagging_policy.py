"""MCP tool for retrieving the tagging policy configuration."""

import logging

from ..models.policy import TagPolicy
from ..services.policy_service import PolicyService

logger = logging.getLogger(__name__)


class GetTaggingPolicyResult:
    """Result from the get_tagging_policy tool."""
    
    def __init__(self, policy: TagPolicy):
        self.policy = policy
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.policy.version,
            "last_updated": self.policy.last_updated.isoformat(),
            "required_tags": [
                {
                    "name": tag.name,
                    "description": tag.description,
                    "allowed_values": tag.allowed_values,
                    "validation_regex": tag.validation_regex,
                    "applies_to": tag.applies_to,
                }
                for tag in self.policy.required_tags
            ],
            "optional_tags": [
                {
                    "name": tag.name,
                    "description": tag.description,
                    "allowed_values": tag.allowed_values,
                }
                for tag in self.policy.optional_tags
            ],
            "tag_naming_rules": {
                "case_sensitivity": self.policy.tag_naming_rules.case_sensitivity,
                "allow_special_characters": self.policy.tag_naming_rules.allow_special_characters,
                "max_key_length": self.policy.tag_naming_rules.max_key_length,
                "max_value_length": self.policy.tag_naming_rules.max_value_length,
            },
            "required_tag_count": len(self.policy.required_tags),
            "optional_tag_count": len(self.policy.optional_tags),
        }


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
        >>> print(f"Policy version: {result.policy.version}")
        >>> print(f"Required tags: {len(result.policy.required_tags)}")
        >>> for tag in result.policy.required_tags:
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
    
    return GetTaggingPolicyResult(policy=policy)
