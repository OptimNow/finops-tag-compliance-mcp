# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Policy service for loading and managing tagging policies."""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..models import TagPolicy, RequiredTag, OptionalTag, Violation, ViolationType, Severity


class PolicyValidationError(Exception):
    """Raised when policy configuration is invalid."""

    pass


class PolicyNotFoundError(Exception):
    """Raised when policy file is not found."""

    pass


class PolicyService:
    """
    Service for loading and managing tagging policies.

    This service handles:
    - Loading policy from JSON file
    - Validating policy structure on load
    - Providing policy retrieval interface
    - Caching loaded policy for performance

    Requirements: 6.1, 6.2, 6.3, 6.4, 9.1
    """

    def __init__(self, policy_path: str | Path | None = None):
        """
        Initialize the PolicyService.

        Args:
            policy_path: Path to the policy JSON file. If None, uses default path.
        """
        self._policy: TagPolicy | None = None
        self._policy_path = (
            Path(policy_path) if policy_path else Path("policies/tagging_policy.json")
        )

    def load_policy(self, policy_path: str | Path | None = None) -> TagPolicy:
        """
        Load tagging policy from JSON file.

        This method:
        1. Reads the JSON file from disk
        2. Validates the structure using Pydantic models
        3. Caches the policy for future retrieval

        Args:
            policy_path: Optional path to policy file. If None, uses instance path.

        Returns:
            TagPolicy: The loaded and validated policy

        Raises:
            PolicyNotFoundError: If the policy file doesn't exist
            PolicyValidationError: If the policy structure is invalid

        Requirements: 9.1 - Load tagging policy from JSON configuration file
        """
        path = Path(policy_path) if policy_path else self._policy_path

        # Check if file exists
        if not path.exists():
            raise PolicyNotFoundError(
                f"Policy file not found: {path}. " f"Please create a policy file at this location."
            )

        # Read and parse JSON
        try:
            with open(path, "r", encoding="utf-8") as f:
                policy_data = json.load(f)
        except json.JSONDecodeError as e:
            raise PolicyValidationError(f"Invalid JSON in policy file {path}: {e}") from e
        except Exception as e:
            raise PolicyValidationError(f"Error reading policy file {path}: {e}") from e

        # Validate structure using Pydantic
        try:
            self._policy = TagPolicy(**policy_data)
        except ValidationError as e:
            raise PolicyValidationError(f"Invalid policy structure in {path}: {e}") from e

        return self._policy

    def get_policy(self) -> TagPolicy:
        """
        Get the currently loaded policy.

        If no policy is loaded, attempts to load from the default path.

        Returns:
            TagPolicy: The current policy

        Raises:
            PolicyNotFoundError: If no policy is loaded and default file doesn't exist
            PolicyValidationError: If policy validation fails

        Requirements: 6.1 - Return complete policy configuration
        """
        if self._policy is None:
            self.load_policy()

        return self._policy

    def get_required_tags(self, resource_type: str | None = None) -> list[RequiredTag]:
        """
        Get required tags, optionally filtered by resource type.

        Args:
            resource_type: Optional resource type to filter by (e.g., "ec2:instance")

        Returns:
            List of required tags (filtered if resource_type provided)

        Requirements: 6.2 - Return required tags with descriptions, allowed values, and validation rules
        Requirements: 6.4 - Indicate which resource types each tag applies to
        """
        policy = self.get_policy()

        if resource_type is None:
            return policy.required_tags

        # Filter tags that apply to the specified resource type
        # None or empty applies_to means applies to ALL resource types
        return [tag for tag in policy.required_tags if tag.applies_to_resource(resource_type)]

    def get_optional_tags(self) -> list[OptionalTag]:
        """
        Get optional tags from the policy.

        Returns:
            List of optional tags

        Requirements: 6.3 - Return optional tags with their descriptions
        """
        policy = self.get_policy()
        return policy.optional_tags

    def get_tag_by_name(self, tag_name: str) -> RequiredTag | OptionalTag | None:
        """
        Get a specific tag by name (searches both required and optional).

        Args:
            tag_name: Name of the tag to find

        Returns:
            The tag if found, None otherwise
        """
        policy = self.get_policy()

        # Search required tags
        for tag in policy.required_tags:
            if tag.name == tag_name:
                return tag

        # Search optional tags
        for tag in policy.optional_tags:
            if tag.name == tag_name:
                return tag

        return None

    def is_tag_required(self, tag_name: str, resource_type: str) -> bool:
        """
        Check if a tag is required for a specific resource type.

        Args:
            tag_name: Name of the tag
            resource_type: Resource type (e.g., "ec2:instance")

        Returns:
            True if the tag is required for this resource type

        Requirements: 9.5 - Apply tag requirements only to applicable resource types
        """
        required_tags = self.get_required_tags(resource_type)
        return any(tag.name == tag_name for tag in required_tags)

    def get_allowed_values(self, tag_name: str) -> list[str] | None:
        """
        Get allowed values for a tag.

        Args:
            tag_name: Name of the tag

        Returns:
            List of allowed values if defined, None otherwise

        Requirements: 9.3 - Validate tag values against allowed value lists
        """
        tag = self.get_tag_by_name(tag_name)
        if tag is None:
            return None

        return tag.allowed_values

    def get_validation_regex(self, tag_name: str) -> str | None:
        """
        Get validation regex pattern for a tag.

        Args:
            tag_name: Name of the tag

        Returns:
            Regex pattern if defined, None otherwise

        Requirements: 9.4 - Validate tag values against regex patterns
        """
        tag = self.get_tag_by_name(tag_name)
        if tag is None or not isinstance(tag, RequiredTag):
            return None

        return tag.validation_regex

    def reload_policy(self) -> TagPolicy:
        """
        Reload the policy from disk.

        Useful for picking up changes to the policy file without restarting.

        Returns:
            The newly loaded policy

        Raises:
            PolicyNotFoundError: If the policy file doesn't exist
            PolicyValidationError: If policy validation fails
        """
        return self.load_policy()

    def validate_policy_structure(self, policy_data: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate policy structure without loading it.

        Useful for pre-validation before saving a policy file.

        Args:
            policy_data: Dictionary containing policy data

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            TagPolicy(**policy_data)
            return True, None
        except ValidationError as e:
            return False, str(e)

    def validate_resource_tags(
        self,
        resource_id: str,
        resource_type: str,
        region: str,
        tags: dict[str, str],
        cost_impact: float = 0.0,
    ) -> list[Violation]:
        """
        Validate a resource's tags against the policy.

        This method checks:
        1. Required tag presence (9.2)
        2. Tag values against allowed value lists (9.3)
        3. Tag values against regex patterns (9.4)
        4. Only applies rules to applicable resource types (9.5)

        Args:
            resource_id: AWS resource identifier (ARN or ID)
            resource_type: Type of resource (e.g., "ec2:instance")
            region: AWS region
            tags: Dictionary of current tags on the resource
            cost_impact: Monthly cost impact for this resource

        Returns:
            List of Violation objects (empty if compliant)

        Requirements: 9.2, 9.3, 9.4, 9.5
        """
        violations: list[Violation] = []

        # Get required tags for this resource type
        required_tags = self.get_required_tags(resource_type)

        # Check each required tag
        for required_tag in required_tags:
            tag_name = required_tag.name

            # Check if tag is present (9.2)
            if tag_name not in tags:
                violations.append(
                    Violation(
                        resource_id=resource_id,
                        resource_type=resource_type,
                        region=region,
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        tag_name=tag_name,
                        severity=Severity.ERROR,
                        current_value=None,
                        allowed_values=required_tag.allowed_values,
                        cost_impact_monthly=cost_impact,
                    )
                )
                continue

            # Tag is present, validate its value
            tag_value = tags[tag_name]

            # Validate against allowed values list (9.3)
            if required_tag.allowed_values is not None:
                if tag_value not in required_tag.allowed_values:
                    violations.append(
                        Violation(
                            resource_id=resource_id,
                            resource_type=resource_type,
                            region=region,
                            violation_type=ViolationType.INVALID_VALUE,
                            tag_name=tag_name,
                            severity=Severity.ERROR,
                            current_value=tag_value,
                            allowed_values=required_tag.allowed_values,
                            cost_impact_monthly=cost_impact,
                        )
                    )
                    continue

            # Validate against regex pattern (9.4)
            if required_tag.validation_regex is not None:
                try:
                    pattern = re.compile(required_tag.validation_regex)
                    if not pattern.match(tag_value):
                        violations.append(
                            Violation(
                                resource_id=resource_id,
                                resource_type=resource_type,
                                region=region,
                                violation_type=ViolationType.INVALID_FORMAT,
                                tag_name=tag_name,
                                severity=Severity.ERROR,
                                current_value=tag_value,
                                allowed_values=None,
                                cost_impact_monthly=cost_impact,
                            )
                        )
                except re.error:
                    # Invalid regex pattern in policy - this shouldn't happen
                    # if policy validation is working correctly
                    pass

        return violations

    def is_resource_compliant(
        self,
        resource_type: str,
        tags: dict[str, str],
    ) -> bool:
        """
        Check if a resource is compliant with the policy.

        Args:
            resource_type: Type of resource (e.g., "ec2:instance")
            tags: Dictionary of current tags on the resource

        Returns:
            True if compliant, False if any violations exist

        Requirements: 9.2, 9.3, 9.4, 9.5
        """
        # Use a dummy resource_id and region for validation
        violations = self.validate_resource_tags(
            resource_id="dummy",
            resource_type=resource_type,
            region="us-east-1",
            tags=tags,
        )
        return len(violations) == 0

    def check_tag_presence(
        self,
        resource_type: str,
        tags: dict[str, str],
    ) -> list[str]:
        """
        Check which required tags are missing for a resource.

        Args:
            resource_type: Type of resource (e.g., "ec2:instance")
            tags: Dictionary of current tags on the resource

        Returns:
            List of missing required tag names

        Requirements: 9.2 - Validate tag presence for required tags
        """
        required_tags = self.get_required_tags(resource_type)
        missing_tags = []

        for tag in required_tags:
            if tag.name not in tags:
                missing_tags.append(tag.name)

        return missing_tags

    def validate_tag_value(
        self,
        tag_name: str,
        tag_value: str,
    ) -> tuple[bool, str | None]:
        """
        Validate a tag value against policy rules.

        Args:
            tag_name: Name of the tag
            tag_value: Value to validate

        Returns:
            Tuple of (is_valid, error_message)

        Requirements: 9.3, 9.4 - Validate against allowed values and regex
        """
        tag = self.get_tag_by_name(tag_name)
        if tag is None:
            # Tag not in policy, so it's valid by default
            return True, None

        # Check allowed values (9.3)
        if tag.allowed_values is not None:
            if tag_value not in tag.allowed_values:
                return False, f"Value '{tag_value}' not in allowed values: {tag.allowed_values}"

        # Check regex pattern (9.4)
        if isinstance(tag, RequiredTag) and tag.validation_regex is not None:
            try:
                pattern = re.compile(tag.validation_regex)
                if not pattern.match(tag_value):
                    return (
                        False,
                        f"Value '{tag_value}' does not match required pattern: {tag.validation_regex}",
                    )
            except re.error as e:
                return False, f"Invalid regex pattern in policy: {e}"

        return True, None
