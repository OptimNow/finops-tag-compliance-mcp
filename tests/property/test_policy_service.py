"""
Property-based tests for PolicyService.

Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
Validates: Requirements 6.1, 6.2, 6.3, 6.4

Property 7 states:
*For any* tagging policy returned, the policy SHALL include:
- version
- last updated timestamp
- required tags list
- optional tags list

Each required tag SHALL include:
- name
- description
- applies_to list

Each tag with value restrictions SHALL include:
- allowed_values or validation_regex
"""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from mcp_server.models import (
    TagNamingRules,
)
from mcp_server.services.policy_service import (
    PolicyNotFoundError,
    PolicyService,
    PolicyValidationError,
)

# =============================================================================
# Strategies for generating test data
# =============================================================================

# Valid AWS resource types
RESOURCE_TYPES = ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]

# Strategy for non-empty strings
non_empty_string = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=50,
).filter(lambda x: x.strip() and x[0].isalpha())

# Strategy for version strings
version_strategy = st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}(\.[0-9]{1,3})?", fullmatch=True)

# Strategy for resource types
resource_type_strategy = st.sampled_from(RESOURCE_TYPES)

# Strategy for lists of resource types
resource_types_list_strategy = st.lists(resource_type_strategy, min_size=1, max_size=5, unique=True)

# Strategy for allowed values lists
allowed_values_strategy = st.lists(
    st.text(min_size=1, max_size=30).filter(lambda x: x.strip()),
    min_size=1,
    max_size=10,
    unique=True,
)

# Strategy for regex patterns (simple valid patterns)
regex_strategy = st.sampled_from(
    [
        r"^[a-z]+$",
        r"^[A-Za-z0-9]+$",
        r"^[a-z][a-z0-9-]{2,63}$",
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    ]
)


# =============================================================================
# Strategy for generating complete valid policies
# =============================================================================


@st.composite
def required_tag_strategy(draw):
    """Generate a valid RequiredTag."""
    name = draw(non_empty_string)
    description = draw(st.text(min_size=5, max_size=100).filter(lambda x: x.strip()))
    applies_to = draw(resource_types_list_strategy)

    # Randomly decide if we have allowed_values, regex, or neither
    restriction_type = draw(st.sampled_from(["allowed_values", "regex", "none"]))

    allowed_values = None
    validation_regex = None

    if restriction_type == "allowed_values":
        allowed_values = draw(allowed_values_strategy)
    elif restriction_type == "regex":
        validation_regex = draw(regex_strategy)

    return {
        "name": name,
        "description": description,
        "allowed_values": allowed_values,
        "validation_regex": validation_regex,
        "applies_to": applies_to,
    }


@st.composite
def optional_tag_strategy(draw):
    """Generate a valid OptionalTag."""
    name = draw(non_empty_string)
    description = draw(st.text(min_size=5, max_size=100).filter(lambda x: x.strip()))

    # Optionally include allowed_values
    has_allowed = draw(st.booleans())
    allowed_values = draw(allowed_values_strategy) if has_allowed else None

    return {
        "name": name,
        "description": description,
        "allowed_values": allowed_values,
    }


@st.composite
def tag_naming_rules_strategy(draw):
    """Generate valid TagNamingRules."""
    return {
        "case_sensitivity": draw(st.booleans()),
        "allow_special_characters": draw(st.booleans()),
        "max_key_length": draw(st.integers(min_value=1, max_value=256)),
        "max_value_length": draw(st.integers(min_value=1, max_value=512)),
    }


@st.composite
def valid_policy_strategy(draw):
    """Generate a complete valid policy dictionary."""
    version = draw(version_strategy)

    # Generate required tags (1-5)
    num_required = draw(st.integers(min_value=1, max_value=5))
    required_tags = []
    used_names = set()

    for _ in range(num_required):
        tag = draw(required_tag_strategy())
        # Ensure unique names
        while tag["name"] in used_names:
            tag["name"] = tag["name"] + draw(st.text(alphabet="0123456789", min_size=1, max_size=3))
        used_names.add(tag["name"])
        required_tags.append(tag)

    # Generate optional tags (0-3)
    num_optional = draw(st.integers(min_value=0, max_value=3))
    optional_tags = []

    for _ in range(num_optional):
        tag = draw(optional_tag_strategy())
        # Ensure unique names
        while tag["name"] in used_names:
            tag["name"] = tag["name"] + draw(st.text(alphabet="0123456789", min_size=1, max_size=3))
        used_names.add(tag["name"])
        optional_tags.append(tag)

    naming_rules = draw(tag_naming_rules_strategy())

    return {
        "version": version,
        "last_updated": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "required_tags": required_tags,
        "optional_tags": optional_tags,
        "tag_naming_rules": naming_rules,
    }


# =============================================================================
# Property 7: Policy Structure Completeness - Policy Loading Tests
# =============================================================================


class TestPolicyStructureCompleteness:
    """
    Property 7: Policy Structure Completeness

    For any tagging policy returned, the policy SHALL include:
    - version
    - last updated timestamp
    - required tags list
    - optional tags list

    Each required tag SHALL include:
    - name
    - description
    - applies_to list

    Each tag with value restrictions SHALL include:
    - allowed_values or validation_regex
    """

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=100)
    def test_loaded_policy_has_complete_structure(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.1, 6.2, 6.3, 6.4

        For any valid policy JSON, loading it SHALL return a policy with
        all required structural elements present.
        """
        # Write policy to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            # Load policy using PolicyService
            service = PolicyService(policy_path=temp_path)
            policy = service.load_policy()

            # Verify complete structure (Requirements 6.1)
            assert policy.version is not None
            assert policy.version == policy_data["version"]
            assert policy.last_updated is not None
            assert isinstance(policy.required_tags, list)
            assert isinstance(policy.optional_tags, list)
            assert isinstance(policy.tag_naming_rules, TagNamingRules)

            # Verify required tags structure (Requirements 6.2, 6.4)
            for i, tag in enumerate(policy.required_tags):
                assert tag.name is not None
                assert tag.name == policy_data["required_tags"][i]["name"]
                assert tag.description is not None
                assert tag.applies_to is not None
                assert len(tag.applies_to) > 0

            # Verify optional tags structure (Requirements 6.3)
            for i, tag in enumerate(policy.optional_tags):
                assert tag.name is not None
                assert tag.name == policy_data["optional_tags"][i]["name"]
                assert tag.description is not None
        finally:
            Path(temp_path).unlink()

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=100)
    def test_required_tags_have_applies_to(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.4

        Each required tag SHALL include applies_to list indicating
        which resource types the tag applies to.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            policy = service.load_policy()

            # Every required tag must have applies_to
            for tag in policy.required_tags:
                assert tag.applies_to is not None, f"Tag {tag.name} missing applies_to"
                assert isinstance(tag.applies_to, list)
                assert len(tag.applies_to) > 0, f"Tag {tag.name} has empty applies_to"

                # Each applies_to entry should be a valid resource type string
                for resource_type in tag.applies_to:
                    assert isinstance(resource_type, str)
                    assert len(resource_type) > 0
        finally:
            Path(temp_path).unlink()

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=100)
    def test_tags_with_restrictions_have_validation_rules(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.2

        Each tag with value restrictions SHALL include allowed_values
        or validation_regex.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            policy = service.load_policy()

            # Check required tags
            for i, tag in enumerate(policy.required_tags):
                original = policy_data["required_tags"][i]

                # If original had allowed_values, loaded tag should too
                if original.get("allowed_values"):
                    assert tag.allowed_values is not None
                    assert tag.allowed_values == original["allowed_values"]

                # If original had validation_regex, loaded tag should too
                if original.get("validation_regex"):
                    assert tag.validation_regex is not None
                    assert tag.validation_regex == original["validation_regex"]

            # Check optional tags
            for i, tag in enumerate(policy.optional_tags):
                original = policy_data["optional_tags"][i]

                if original.get("allowed_values"):
                    assert tag.allowed_values is not None
                    assert tag.allowed_values == original["allowed_values"]
        finally:
            Path(temp_path).unlink()

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=100)
    def test_get_policy_returns_cached_policy(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.1

        get_policy() SHALL return the complete policy configuration,
        and subsequent calls should return the same cached policy.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)

            # First call loads the policy
            policy1 = service.get_policy()

            # Second call should return same cached policy
            policy2 = service.get_policy()

            # Both should be complete and identical
            assert policy1.version == policy2.version
            assert len(policy1.required_tags) == len(policy2.required_tags)
            assert len(policy1.optional_tags) == len(policy2.optional_tags)
        finally:
            Path(temp_path).unlink()

    @given(
        policy_data=valid_policy_strategy(),
        resource_type=resource_type_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_get_required_tags_filters_by_resource_type(
        self, policy_data: dict, resource_type: str
    ):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.4

        get_required_tags(resource_type) SHALL return only tags that
        apply to the specified resource type.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Get filtered tags
            filtered_tags = service.get_required_tags(resource_type)

            # All returned tags should apply to the resource type
            for tag in filtered_tags:
                assert resource_type in tag.applies_to, (
                    f"Tag {tag.name} returned for {resource_type} "
                    f"but applies_to is {tag.applies_to}"
                )

            # Count expected tags
            expected_count = sum(
                1 for t in policy_data["required_tags"] if resource_type in t["applies_to"]
            )
            assert len(filtered_tags) == expected_count
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Policy Loading Error Handling Tests
# =============================================================================


class TestPolicyLoadingErrors:
    """Tests for policy loading error handling."""

    def test_missing_policy_file_raises_error(self):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 9.1

        Loading a non-existent policy file SHALL raise PolicyNotFoundError.
        """
        service = PolicyService(policy_path="/nonexistent/path/policy.json")

        with pytest.raises(PolicyNotFoundError):
            service.load_policy()

    def test_invalid_json_raises_error(self):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 9.1

        Loading invalid JSON SHALL raise PolicyValidationError.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)

            with pytest.raises(PolicyValidationError):
                service.load_policy()
        finally:
            Path(temp_path).unlink()

    def test_missing_required_fields_raises_error(self):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.1

        Policy missing required fields SHALL raise PolicyValidationError.
        """
        # Policy missing version
        invalid_policy = {
            "required_tags": [],
            "optional_tags": [],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(invalid_policy, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)

            with pytest.raises(PolicyValidationError):
                service.load_policy()
        finally:
            Path(temp_path).unlink()

    def test_required_tag_missing_applies_to_raises_error(self):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.4

        Required tag without applies_to SHALL raise PolicyValidationError.
        """
        invalid_policy = {
            "version": "1.0",
            "required_tags": [
                {
                    "name": "CostCenter",
                    "description": "Cost allocation tag",
                    # Missing applies_to
                }
            ],
            "optional_tags": [],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(invalid_policy, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)

            with pytest.raises(PolicyValidationError):
                service.load_policy()
        finally:
            Path(temp_path).unlink()


# =============================================================================
# Policy Retrieval Interface Tests
# =============================================================================


class TestPolicyRetrievalInterface:
    """Tests for policy retrieval methods."""

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=50)
    def test_get_optional_tags_returns_all_optional(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.3

        get_optional_tags() SHALL return all optional tags with descriptions.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            optional_tags = service.get_optional_tags()

            assert len(optional_tags) == len(policy_data["optional_tags"])

            for tag in optional_tags:
                assert tag.name is not None
                assert tag.description is not None
        finally:
            Path(temp_path).unlink()

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=50)
    def test_get_tag_by_name_finds_required_tags(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.2

        get_tag_by_name() SHALL find required tags by name.
        """
        assume(len(policy_data["required_tags"]) > 0)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Look up each required tag by name
            for expected in policy_data["required_tags"]:
                tag = service.get_tag_by_name(expected["name"])
                assert tag is not None
                assert tag.name == expected["name"]
                assert tag.description == expected["description"]
        finally:
            Path(temp_path).unlink()

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=50)
    def test_get_tag_by_name_returns_none_for_unknown(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.2

        get_tag_by_name() SHALL return None for unknown tag names.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Unknown tag should return None
            tag = service.get_tag_by_name("NonExistentTagName12345")
            assert tag is None
        finally:
            Path(temp_path).unlink()

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=50)
    def test_validate_policy_structure_accepts_valid(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.1

        validate_policy_structure() SHALL return (True, None) for valid policies.
        """
        service = PolicyService()

        is_valid, error = service.validate_policy_structure(policy_data)

        assert is_valid is True
        assert error is None

    def test_validate_policy_structure_rejects_invalid(self):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.1

        validate_policy_structure() SHALL return (False, error_message) for invalid policies.
        """
        service = PolicyService()

        # Missing version
        invalid_policy = {"required_tags": [], "optional_tags": []}

        is_valid, error = service.validate_policy_structure(invalid_policy)

        assert is_valid is False
        assert error is not None
        assert len(error) > 0


# =============================================================================
# Property 10: Policy Validation Correctness
# =============================================================================


# Strategy for generating tag values that match a regex pattern
def value_matching_regex(pattern: str) -> st.SearchStrategy[str]:
    """Generate values that match a given regex pattern."""
    # Map common patterns to strategies that generate matching values
    pattern_strategies = {
        r"^[a-z]+$": st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20),
        r"^[A-Za-z0-9]+$": st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            min_size=1,
            max_size=20,
        ),
        r"^[a-z][a-z0-9-]{2,63}$": st.from_regex(r"^[a-z][a-z0-9-]{2,63}$", fullmatch=True),
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$": st.from_regex(
            r"^[a-z]{3,8}@example\.com$", fullmatch=True
        ),
    }
    return pattern_strategies.get(pattern, st.text(min_size=1, max_size=20))


# Strategy for generating tag values that DON'T match a regex pattern
def value_not_matching_regex(pattern: str) -> st.SearchStrategy[str]:
    """Generate values that don't match a given regex pattern."""
    # Generate values that are guaranteed to not match common patterns
    pattern_non_matching = {
        r"^[a-z]+$": st.text(alphabet="0123456789!@#$%", min_size=1, max_size=10),
        r"^[A-Za-z0-9]+$": st.text(
            alphabet="!@#$%^&*()_+-=[]{}|;':\",./<>?", min_size=1, max_size=10
        ),
        r"^[a-z][a-z0-9-]{2,63}$": st.sampled_from(["A", "1abc", "-abc", "ab", "ABC123"]),
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$": st.sampled_from(
            ["notanemail", "missing@domain", "@nodomain.com", "spaces in@email.com"]
        ),
    }
    return pattern_non_matching.get(pattern, st.sampled_from(["!@#$%", "   ", ""]))


class TestPolicyValidationCorrectness:
    """
    Property 10: Policy Validation Correctness

    For any resource validated against a policy:
    - Missing required tags SHALL be detected (9.2)
    - Invalid values (not in allowed list) SHALL be detected (9.3)
    - Values not matching regex patterns SHALL be detected (9.4)
    - Tag requirements SHALL only apply to resource types listed in applies_to (9.5)

    Validates: Requirements 9.2, 9.3, 9.4, 9.5
    """

    @given(
        policy_data=valid_policy_strategy(),
        resource_type=resource_type_strategy,
        resource_id=st.text(min_size=5, max_size=50).filter(lambda x: x.strip()),
        region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_required_tags_detected(
        self, policy_data: dict, resource_type: str, resource_id: str, region: str
    ):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.2

        For any resource with missing required tags, the validation SHALL
        detect and report each missing tag as a MISSING_REQUIRED_TAG violation.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Get required tags for this resource type
            required_tags = service.get_required_tags(resource_type)

            # Validate with empty tags (all required tags missing)
            violations = service.validate_resource_tags(
                resource_id=resource_id,
                resource_type=resource_type,
                region=region,
                tags={},  # No tags provided
            )

            # Should have one violation per required tag for this resource type
            missing_violations = [
                v for v in violations if v.violation_type == ViolationType.MISSING_REQUIRED_TAG
            ]

            assert len(missing_violations) == len(required_tags), (
                f"Expected {len(required_tags)} missing tag violations, "
                f"got {len(missing_violations)}"
            )

            # Each violation should reference a required tag
            violation_tag_names = {v.tag_name for v in missing_violations}
            required_tag_names = {t.name for t in required_tags}

            assert violation_tag_names == required_tag_names, (
                f"Violation tags {violation_tag_names} don't match "
                f"required tags {required_tag_names}"
            )

            # Each violation should have correct metadata
            for v in missing_violations:
                assert v.resource_id == resource_id
                assert v.resource_type == resource_type
                assert v.region == region
                assert v.severity == Severity.ERROR
                assert v.current_value is None  # Tag is missing
        finally:
            Path(temp_path).unlink()

    @given(
        policy_data=valid_policy_strategy(),
        resource_type=resource_type_strategy,
        resource_id=st.text(min_size=5, max_size=50).filter(lambda x: x.strip()),
        region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_values_detected(
        self, policy_data: dict, resource_type: str, resource_id: str, region: str
    ):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.3

        For any tag with an invalid value (not in allowed list), the validation
        SHALL detect and report it as an INVALID_VALUE violation with the
        current value and allowed values included.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Get required tags for this resource type that have allowed_values
            required_tags = service.get_required_tags(resource_type)
            tags_with_allowed_values = [
                t
                for t in required_tags
                if t.allowed_values is not None and len(t.allowed_values) > 0
            ]

            # Skip if no tags have allowed_values restrictions
            assume(len(tags_with_allowed_values) > 0)

            # Build tags dict with invalid values for tags that have allowed_values
            tags = {}
            for tag in required_tags:
                if tag.allowed_values is not None and len(tag.allowed_values) > 0:
                    # Use a value that's definitely not in allowed_values
                    tags[tag.name] = "INVALID_VALUE_NOT_IN_LIST_12345"
                elif tag.validation_regex is not None:
                    # For regex tags, provide a valid-looking value
                    tags[tag.name] = "valid@example.com"
                else:
                    # For tags with no restrictions, any value works
                    tags[tag.name] = "any_value"

            violations = service.validate_resource_tags(
                resource_id=resource_id,
                resource_type=resource_type,
                region=region,
                tags=tags,
            )

            # Should have INVALID_VALUE violations for tags with allowed_values
            invalid_value_violations = [
                v for v in violations if v.violation_type == ViolationType.INVALID_VALUE
            ]

            assert len(invalid_value_violations) == len(tags_with_allowed_values), (
                f"Expected {len(tags_with_allowed_values)} invalid value violations, "
                f"got {len(invalid_value_violations)}"
            )

            # Each violation should include current_value and allowed_values
            for v in invalid_value_violations:
                assert v.current_value is not None, "Violation should include current_value"
                assert v.current_value == "INVALID_VALUE_NOT_IN_LIST_12345"
                assert v.allowed_values is not None, "Violation should include allowed_values"
                assert len(v.allowed_values) > 0
        finally:
            Path(temp_path).unlink()

    @given(
        policy_data=valid_policy_strategy(),
        resource_type=resource_type_strategy,
        resource_id=st.text(min_size=5, max_size=50).filter(lambda x: x.strip()),
        region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_format_detected(
        self, policy_data: dict, resource_type: str, resource_id: str, region: str
    ):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.4

        For any tag value that doesn't match the required regex pattern,
        the validation SHALL detect and report it as an INVALID_FORMAT violation.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Get required tags for this resource type that have validation_regex
            required_tags = service.get_required_tags(resource_type)
            tags_with_regex = [t for t in required_tags if t.validation_regex is not None]

            # Skip if no tags have regex validation
            assume(len(tags_with_regex) > 0)

            # Build tags dict with values that don't match regex patterns
            tags = {}
            for tag in required_tags:
                if tag.validation_regex is not None:
                    # Use a value that won't match any of our regex patterns
                    tags[tag.name] = "!!!INVALID_FORMAT!!!"
                elif tag.allowed_values is not None and len(tag.allowed_values) > 0:
                    # For allowed_values tags, use a valid value
                    tags[tag.name] = tag.allowed_values[0]
                else:
                    # For tags with no restrictions, any value works
                    tags[tag.name] = "any_value"

            violations = service.validate_resource_tags(
                resource_id=resource_id,
                resource_type=resource_type,
                region=region,
                tags=tags,
            )

            # Should have INVALID_FORMAT violations for tags with regex
            invalid_format_violations = [
                v for v in violations if v.violation_type == ViolationType.INVALID_FORMAT
            ]

            assert len(invalid_format_violations) == len(tags_with_regex), (
                f"Expected {len(tags_with_regex)} invalid format violations, "
                f"got {len(invalid_format_violations)}"
            )

            # Each violation should include current_value
            for v in invalid_format_violations:
                assert v.current_value is not None, "Violation should include current_value"
                assert v.current_value == "!!!INVALID_FORMAT!!!"
        finally:
            Path(temp_path).unlink()

    @given(
        policy_data=valid_policy_strategy(),
        resource_id=st.text(min_size=5, max_size=50).filter(lambda x: x.strip()),
        region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_tag_requirements_only_apply_to_applicable_resource_types(
        self, policy_data: dict, resource_id: str, region: str
    ):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.5

        Tag requirements SHALL only apply to resource types listed in the
        tag's applies_to field. A resource type not in applies_to SHALL NOT
        generate violations for that tag.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            policy = service.load_policy()

            # For each resource type, validate with empty tags
            for resource_type in RESOURCE_TYPES:
                violations = service.validate_resource_tags(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    tags={},  # No tags
                )

                # Get tags that should apply to this resource type
                applicable_tags = [t for t in policy.required_tags if resource_type in t.applies_to]

                # Get tags that should NOT apply to this resource type
                non_applicable_tags = [
                    t for t in policy.required_tags if resource_type not in t.applies_to
                ]

                # Violations should only be for applicable tags
                violation_tag_names = {v.tag_name for v in violations}
                applicable_tag_names = {t.name for t in applicable_tags}
                non_applicable_tag_names = {t.name for t in non_applicable_tags}

                # All violations should be for applicable tags
                assert violation_tag_names.issubset(applicable_tag_names), (
                    f"Violations {violation_tag_names} include non-applicable tags. "
                    f"Applicable: {applicable_tag_names}"
                )

                # No violations should be for non-applicable tags
                assert violation_tag_names.isdisjoint(non_applicable_tag_names), (
                    f"Violations {violation_tag_names} include non-applicable tags "
                    f"{non_applicable_tag_names}"
                )
        finally:
            Path(temp_path).unlink()

    @given(
        policy_data=valid_policy_strategy(),
        resource_type=resource_type_strategy,
        resource_id=st.text(min_size=5, max_size=50).filter(lambda x: x.strip()),
        region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_compliant_resource_has_no_violations(
        self, policy_data: dict, resource_type: str, resource_id: str, region: str
    ):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.2, 9.3, 9.4, 9.5

        For any resource with all required tags present and valid values,
        the validation SHALL return an empty list of violations.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Get required tags for this resource type
            required_tags = service.get_required_tags(resource_type)

            # Build a fully compliant tags dict
            tags = {}
            for tag in required_tags:
                if tag.allowed_values is not None and len(tag.allowed_values) > 0:
                    # Use first allowed value
                    tags[tag.name] = tag.allowed_values[0]
                elif tag.validation_regex is not None:
                    # Generate a value that matches the regex
                    if tag.validation_regex == r"^[a-z]+$":
                        tags[tag.name] = "validvalue"
                    elif tag.validation_regex == r"^[A-Za-z0-9]+$":
                        tags[tag.name] = "ValidValue123"
                    elif tag.validation_regex == r"^[a-z][a-z0-9-]{2,63}$":
                        tags[tag.name] = "valid-app-name"
                    elif "email" in tag.validation_regex.lower() or "@" in tag.validation_regex:
                        tags[tag.name] = "user@example.com"
                    else:
                        # Default: try a simple alphanumeric value
                        tags[tag.name] = "validvalue"
                else:
                    # No restrictions, any value works
                    tags[tag.name] = "any_valid_value"

            violations = service.validate_resource_tags(
                resource_id=resource_id,
                resource_type=resource_type,
                region=region,
                tags=tags,
            )

            # Should have no violations for compliant resource
            assert len(violations) == 0, (
                f"Expected 0 violations for compliant resource, got {len(violations)}: "
                f"{[v.tag_name + ':' + str(v.violation_type) for v in violations]}"
            )
        finally:
            Path(temp_path).unlink()

    @given(
        policy_data=valid_policy_strategy(),
        resource_type=resource_type_strategy,
        resource_id=st.text(min_size=5, max_size=50).filter(lambda x: x.strip()),
        region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_is_resource_compliant_matches_violations(
        self, policy_data: dict, resource_type: str, resource_id: str, region: str
    ):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.2, 9.3, 9.4, 9.5

        is_resource_compliant() SHALL return True if and only if
        validate_resource_tags() returns an empty list of violations.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Test with empty tags
            violations = service.validate_resource_tags(
                resource_id=resource_id,
                resource_type=resource_type,
                region=region,
                tags={},
            )
            is_compliant = service.is_resource_compliant(resource_type, {})

            # is_compliant should be True iff no violations
            assert is_compliant == (
                len(violations) == 0
            ), f"is_resource_compliant={is_compliant} but violations={len(violations)}"

            # Test with some tags
            required_tags = service.get_required_tags(resource_type)
            if len(required_tags) > 0:
                # Provide just one tag (likely still non-compliant if multiple required)
                partial_tags = {required_tags[0].name: "some_value"}

                violations2 = service.validate_resource_tags(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    tags=partial_tags,
                )
                is_compliant2 = service.is_resource_compliant(resource_type, partial_tags)

                assert is_compliant2 == (len(violations2) == 0)
        finally:
            Path(temp_path).unlink()

    @given(
        policy_data=valid_policy_strategy(),
        resource_type=resource_type_strategy,
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_check_tag_presence_returns_missing_tags(self, policy_data: dict, resource_type: str):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.2

        check_tag_presence() SHALL return the list of required tag names
        that are missing from the provided tags dictionary.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            required_tags = service.get_required_tags(resource_type)
            required_tag_names = {t.name for t in required_tags}

            # Test with empty tags - all should be missing
            missing = service.check_tag_presence(resource_type, {})
            assert set(missing) == required_tag_names

            # Test with all tags present - none should be missing
            all_tags = {t.name: "value" for t in required_tags}
            missing2 = service.check_tag_presence(resource_type, all_tags)
            assert len(missing2) == 0

            # Test with partial tags
            if len(required_tags) > 1:
                partial_tags = {required_tags[0].name: "value"}
                missing3 = service.check_tag_presence(resource_type, partial_tags)
                expected_missing = required_tag_names - {required_tags[0].name}
                assert set(missing3) == expected_missing
        finally:
            Path(temp_path).unlink()

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_validate_tag_value_checks_allowed_values(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.3

        validate_tag_value() SHALL return (False, error) when the value
        is not in the allowed_values list.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Find tags with allowed_values
            for tag_data in policy_data["required_tags"]:
                if tag_data.get("allowed_values"):
                    tag_name = tag_data["name"]
                    allowed = tag_data["allowed_values"]

                    # Valid value should pass
                    is_valid, error = service.validate_tag_value(tag_name, allowed[0])
                    assert is_valid is True
                    assert error is None

                    # Invalid value should fail
                    is_valid2, error2 = service.validate_tag_value(
                        tag_name, "DEFINITELY_NOT_ALLOWED_VALUE"
                    )
                    assert is_valid2 is False
                    assert error2 is not None
                    assert "not in allowed values" in error2.lower()
        finally:
            Path(temp_path).unlink()

    @given(policy_data=valid_policy_strategy())
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_validate_tag_value_checks_regex(self, policy_data: dict):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.4

        validate_tag_value() SHALL return (False, error) when the value
        does not match the validation_regex pattern.
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(policy_data, f)
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Find tags with validation_regex
            for tag_data in policy_data["required_tags"]:
                if tag_data.get("validation_regex"):
                    tag_name = tag_data["name"]

                    # Invalid format should fail
                    is_valid, error = service.validate_tag_value(tag_name, "!!!INVALID_FORMAT!!!")
                    assert is_valid is False
                    assert error is not None
                    assert "does not match" in error.lower() or "pattern" in error.lower()
        finally:
            Path(temp_path).unlink()

    def test_validate_tag_value_unknown_tag_is_valid(self):
        """
        Feature: phase-1-aws-mvp, Property 10: Policy Validation Correctness
        Validates: Requirements 9.3, 9.4

        validate_tag_value() SHALL return (True, None) for tags not
        defined in the policy (unknown tags are valid by default).
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "version": "1.0",
                    "required_tags": [],
                    "optional_tags": [],
                },
                f,
            )
            temp_path = f.name

        try:
            service = PolicyService(policy_path=temp_path)
            service.load_policy()

            # Unknown tag should be valid
            is_valid, error = service.validate_tag_value("UnknownTag", "any_value")
            assert is_valid is True
            assert error is None
        finally:
            Path(temp_path).unlink()


# Import ViolationType and Severity for the new tests
from mcp_server.models import Severity, ViolationType
