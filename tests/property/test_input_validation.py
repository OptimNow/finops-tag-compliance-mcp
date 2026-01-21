"""Property-based tests for input validation.

Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
Validates: Requirements 16.3

Property 17: Input Schema Validation
*For any* tool invocation, the input parameters SHALL be validated against
the tool's defined JSON schema before execution. Invalid inputs SHALL be
rejected with a clear error message indicating which parameter failed
validation and why.
"""

import re
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from mcp_server.utils.input_validation import (
    InputValidator,
    SecurityViolationError,
    ValidationError,
)

# =============================================================================
# Strategies for generating test data
# =============================================================================

# Valid resource types
valid_resource_types = st.sampled_from(
    [
        "ec2:instance",
        "rds:db",
        "s3:bucket",
        "lambda:function",
        "ecs:service",
    ]
)

# Invalid resource types (strings that are not in the valid set)
invalid_resource_type = st.text(min_size=1, max_size=50).filter(
    lambda x: x not in InputValidator.VALID_RESOURCE_TYPES and x.strip() != ""
)

# Valid AWS regions
valid_region = st.sampled_from(list(InputValidator.VALID_AWS_REGIONS))

# Invalid AWS regions
invalid_region = st.text(min_size=1, max_size=30).filter(
    lambda x: x not in InputValidator.VALID_AWS_REGIONS and x.strip() != ""
)

# Valid severity levels
valid_severity = st.sampled_from(["all", "errors_only", "warnings_only"])

# Invalid severity levels
invalid_severity = st.text(min_size=1, max_size=30).filter(
    lambda x: x not in InputValidator.VALID_SEVERITIES and x.strip() != ""
)

# Valid report formats
valid_format = st.sampled_from(["json", "csv", "markdown"])

# Invalid report formats
invalid_format = st.text(min_size=1, max_size=30).filter(
    lambda x: x not in InputValidator.VALID_REPORT_FORMATS and x.strip() != ""
)

# Valid 12-digit AWS account IDs
valid_account_id = st.from_regex(r"^\d{12}$", fullmatch=True)

# Invalid account IDs (not 12 digits)
invalid_account_id = st.one_of(
    st.text(min_size=1, max_size=11).filter(lambda x: not x.isdigit() or len(x) != 12),
    st.text(min_size=13, max_size=20).filter(lambda x: not x.isdigit() or len(x) != 12),
)

# Valid ARN pattern
valid_arn = st.builds(
    lambda service, region, account, resource: f"arn:aws:{service}:{region}:{account}:{resource}",
    service=st.sampled_from(["ec2", "rds", "s3", "lambda", "ecs"]),
    region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]),
    account=st.from_regex(r"^\d{12}$", fullmatch=True),
    resource=st.from_regex(r"^[a-z0-9\-/:._]+$", fullmatch=True).filter(
        lambda x: len(x) > 0 and len(x) < 100
    ),
)

# Invalid ARN (doesn't match pattern)
invalid_arn = st.text(min_size=1, max_size=100).filter(
    lambda x: not x.startswith("arn:aws:") and x.strip() != ""
)

# Valid date strings (YYYY-MM-DD)
valid_date = st.dates().map(lambda d: d.strftime("%Y-%m-%d"))

# Invalid date strings
invalid_date = st.one_of(
    st.from_regex(r"^\d{2}/\d{2}/\d{4}$", fullmatch=True),  # MM/DD/YYYY
    st.from_regex(r"^\d{2}-\d{2}-\d{4}$", fullmatch=True),  # DD-MM-YYYY
    st.text(min_size=1, max_size=20).filter(lambda x: not re.match(r"^\d{4}-\d{2}-\d{2}$", x)),
)

# Injection patterns for security testing
injection_patterns = st.sampled_from(
    [
        "<script>alert('xss')</script>",
        "javascript:alert('xss')",
        "<img onerror='alert(1)'>",
        "eval(malicious_code)",
        "exec(malicious_code)",
        "__import__('os').system('rm -rf /')",
        "${malicious_code}",
        "{{malicious_code}}",
        "../../etc/passwd",
        "..\\..\\windows\\system32",
        "/etc/passwd",
        "cmd.exe /c dir",
        "/bin/sh -c 'ls'",
        "; rm -rf /",
        "; drop table users",
    ]
)

# Safe strings that should pass validation
safe_string = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        blacklist_characters="\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f"
        "\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f",
    ),
    min_size=1,
    max_size=100,
).filter(
    lambda x: x.strip() != "" and not any(p.search(x) for p in InputValidator.SUSPICIOUS_PATTERNS)
)


# =============================================================================
# Property Tests for Input Schema Validation
# =============================================================================


class TestInputSchemaValidationProperty:
    """Property tests for input schema validation (Property 17)."""

    @given(resource_types=st.lists(valid_resource_types, min_size=1, max_size=5, unique=True))
    @settings(max_examples=100, deadline=None)
    def test_property_17_valid_resource_types_accepted(
        self,
        resource_types: list[str],
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid resource types, validation SHALL accept them.
        """
        result = InputValidator.validate_resource_types(resource_types)
        assert result == resource_types
        assert all(rt in InputValidator.VALID_RESOURCE_TYPES for rt in result)

    @given(
        valid_types=st.lists(valid_resource_types, min_size=0, max_size=3, unique=True),
        invalid_type=invalid_resource_type,
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_invalid_resource_types_rejected_with_message(
        self,
        valid_types: list[str],
        invalid_type: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any invalid resource type, validation SHALL reject with a clear
        error message indicating which parameter failed and why.
        """
        # Combine valid and invalid types
        resource_types = valid_types + [invalid_type]

        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_types(resource_types)

        error = exc_info.value
        # Error message should indicate the field name
        assert error.field == "resource_types"
        # Error message should mention the invalid value
        assert "invalid" in error.message.lower()
        # Error message should list valid options
        assert "valid" in error.message.lower()

    @given(
        region=valid_region,
        account_id=valid_account_id,
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_valid_filters_accepted(
        self,
        region: str,
        account_id: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid filter values, validation SHALL accept them.
        """
        filters = {"region": region, "account_id": account_id}
        result = InputValidator.validate_filters(filters)
        assert result == filters

    @given(
        invalid_key=st.text(min_size=1, max_size=30).filter(
            lambda x: x not in {"region", "account_id"} and x.strip() != ""
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_invalid_filter_keys_rejected_with_message(
        self,
        invalid_key: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any invalid filter key, validation SHALL reject with a clear
        error message indicating which parameter failed and why.
        """
        filters = {invalid_key: "some_value"}

        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_filters(filters)

        error = exc_info.value
        assert error.field == "filters"
        assert "invalid" in error.message.lower()
        assert invalid_key in str(error.message) or "keys" in error.message.lower()

    @given(severity=valid_severity)
    @settings(max_examples=100, deadline=None)
    def test_property_17_valid_severity_accepted(self, severity: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid severity value, validation SHALL accept it.
        """
        result = InputValidator.validate_severity(severity)
        assert result == severity

    @given(severity=invalid_severity)
    @settings(max_examples=100, deadline=None)
    def test_property_17_invalid_severity_rejected_with_message(self, severity: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any invalid severity value, validation SHALL reject with a clear
        error message indicating which parameter failed and why.
        """
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_severity(severity)

        error = exc_info.value
        assert error.field == "severity"
        assert "invalid" in error.message.lower()
        assert severity in error.message

    @given(severity=valid_severity)
    @settings(max_examples=100, deadline=None)
    def test_property_17_severity_array_unwrapping(self, severity: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid severity value wrapped in a single-element array,
        validation SHALL auto-unwrap and accept it (AI agent tolerance).
        """
        # AI agents sometimes wrap values in arrays - we should be forgiving
        result = InputValidator.validate_severity([severity])
        assert result == severity

    @given(arns=st.lists(valid_arn, min_size=1, max_size=10, unique=True))
    @settings(max_examples=100, deadline=None)
    def test_property_17_valid_arns_accepted(self, arns: list[str]):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid ARNs, validation SHALL accept them.
        """
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns

    @given(
        valid_arns=st.lists(valid_arn, min_size=0, max_size=3, unique=True),
        invalid_arn_val=invalid_arn,
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_invalid_arns_rejected_with_message(
        self,
        valid_arns: list[str],
        invalid_arn_val: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any invalid ARN, validation SHALL reject with a clear
        error message indicating which parameter failed and why.
        Both ValidationError (for format issues) and SecurityViolationError
        (for control characters, null bytes, etc.) are valid rejection responses.
        """
        arns = valid_arns + [invalid_arn_val]

        # Both ValidationError and SecurityViolationError are valid rejections
        # - ValidationError: for invalid ARN format
        # - SecurityViolationError: for control characters, null bytes, injection attempts
        with pytest.raises((ValidationError, SecurityViolationError)) as exc_info:
            InputValidator.validate_resource_arns(arns)

        error = exc_info.value
        # Error should have a meaningful message
        if isinstance(error, ValidationError):
            assert error.field == "resource_arns"
            assert "invalid" in error.message.lower() or "arn" in error.message.lower()
        else:
            # SecurityViolationError - should have violation type and message
            assert error.violation_type is not None
            assert len(error.message) > 0


class TestInputValidationErrorMessages:
    """Property tests ensuring error messages are clear and informative."""

    @given(
        wrong_type=st.one_of(
            st.integers(),
            st.floats(allow_nan=False),
            st.booleans(),
            st.dictionaries(st.text(max_size=10), st.text(max_size=10), max_size=3),
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_type_mismatch_error_includes_expected_type(
        self,
        wrong_type: Any,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any type mismatch, the error message SHALL indicate the expected type.
        """
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_types(wrong_type)

        error = exc_info.value
        assert error.field == "resource_types"
        # Should mention expected type (array/list)
        assert "array" in error.message.lower() or "list" in error.message.lower()
        # Should mention actual type
        assert type(wrong_type).__name__.lower() in error.message.lower()

    @given(
        field_name=st.text(min_size=1, max_size=30).filter(lambda x: x.strip() != ""),
        value=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_validation_error_includes_field_name(
        self,
        field_name: str,
        value: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any validation error, the error SHALL include the field name.
        """
        error = ValidationError(field_name, "Test error message", value)

        assert error.field == field_name
        assert field_name in str(error)

    @given(
        min_val=st.integers(min_value=1, max_value=100),
        max_val=st.integers(min_value=101, max_value=200),
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_range_error_includes_bounds(
        self,
        min_val: int,
        max_val: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any range validation error, the error SHALL include the valid bounds.
        """
        # Test minimum bound
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(min_val - 1, "test_field", minimum=min_val)

        error = exc_info.value
        assert str(min_val) in error.message

        # Test maximum bound
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(max_val + 1, "test_field", maximum=max_val)

        error = exc_info.value
        assert str(max_val) in error.message


class TestSecurityValidation:
    """Property tests for security-related validation."""

    @given(injection=injection_patterns)
    @settings(max_examples=100, deadline=None)
    def test_property_17_injection_attempts_rejected(self, injection: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any injection attempt, validation SHALL reject with a security error.
        """
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(injection, "test_field")

        error = exc_info.value
        assert error.violation_type == "injection_attempt"
        assert "suspicious" in error.message.lower() or "malicious" in error.message.lower()

    @given(
        depth=st.integers(min_value=6, max_value=10),
    )
    @settings(max_examples=50, deadline=None)
    def test_property_17_excessive_nesting_rejected(self, depth: int):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any excessively nested structure, validation SHALL reject.
        """
        # Build nested structure
        data: dict = {"value": "leaf"}
        for i in range(depth):
            data = {f"level{i}": data}

        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.check_parameter_size_limits(data)

        error = exc_info.value
        assert error.violation_type == "excessive_nesting"
        assert "nesting" in error.message.lower()

    @given(
        length=st.integers(
            min_value=InputValidator.MAX_STRING_LENGTH + 1,
            max_value=InputValidator.MAX_STRING_LENGTH + 1000,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_property_17_excessive_string_length_rejected(self, length: int):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any string exceeding max length, validation SHALL reject.
        """
        long_string = "a" * length

        with pytest.raises((ValidationError, SecurityViolationError)) as exc_info:
            InputValidator.sanitize_string(long_string, field_name="test_field")

        error = exc_info.value
        assert "too long" in error.message.lower() or "string" in error.message.lower()

    @given(
        num_keys=st.integers(
            min_value=InputValidator.MAX_DICT_KEYS + 1,
            max_value=InputValidator.MAX_DICT_KEYS + 50,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_property_17_excessive_dict_keys_rejected(self, num_keys: int):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any dict with too many keys, validation SHALL reject.
        """
        data = {f"key{i}": f"value{i}" for i in range(num_keys)}

        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.check_parameter_size_limits(data)

        error = exc_info.value
        assert error.violation_type == "excessive_keys"

    @given(
        num_items=st.integers(
            min_value=InputValidator.MAX_ARRAY_LENGTH + 1,
            max_value=InputValidator.MAX_ARRAY_LENGTH + 500,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_property_17_excessive_array_length_rejected(self, num_items: int):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any array exceeding max length, validation SHALL reject.
        """
        data = ["item"] * num_items

        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.check_parameter_size_limits(data)

        error = exc_info.value
        assert error.violation_type == "excessive_array_length"


class TestTimePeriodValidation:
    """Property tests for time period validation."""

    @given(
        start_date=st.dates(),
        days_diff=st.integers(min_value=1, max_value=365),
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_valid_time_period_accepted(
        self,
        start_date,
        days_diff: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid time period (end after start, within 365 days),
        validation SHALL accept it.
        """
        from datetime import timedelta

        end_date = start_date + timedelta(days=days_diff)
        time_period = {
            "Start": start_date.strftime("%Y-%m-%d"),
            "End": end_date.strftime("%Y-%m-%d"),
        }

        result = InputValidator.validate_time_period(time_period)
        assert result == time_period

    @given(
        start_date=st.dates(),
        days_before=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_end_before_start_rejected(
        self,
        start_date,
        days_before: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any time period where end is before start, validation SHALL reject.
        """
        from datetime import timedelta

        end_date = start_date - timedelta(days=days_before)
        time_period = {
            "Start": start_date.strftime("%Y-%m-%d"),
            "End": end_date.strftime("%Y-%m-%d"),
        }

        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_time_period(time_period)

        error = exc_info.value
        assert "after" in error.message.lower() or "before" in error.message.lower()

    @given(
        start_date=st.dates(),
        days_diff=st.integers(min_value=366, max_value=730),
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_time_period_too_large_rejected(
        self,
        start_date,
        days_diff: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any time period exceeding 365 days, validation SHALL reject.
        """
        from datetime import timedelta

        end_date = start_date + timedelta(days=days_diff)
        time_period = {
            "Start": start_date.strftime("%Y-%m-%d"),
            "End": end_date.strftime("%Y-%m-%d"),
        }

        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_time_period(time_period)

        error = exc_info.value
        assert "too large" in error.message.lower() or "365" in error.message


class TestRequiredFieldValidation:
    """Property tests for required field validation."""

    @given(field_name=st.text(min_size=1, max_size=30).filter(lambda x: x.strip() != ""))
    @settings(max_examples=100, deadline=None)
    def test_property_17_required_field_missing_rejected(self, field_name: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any required field that is None, validation SHALL reject
        with a clear message indicating the field is required.
        """
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_types(None, field_name=field_name, required=True)

        error = exc_info.value
        assert error.field == field_name
        assert "required" in error.message.lower()

    @given(field_name=st.text(min_size=1, max_size=30).filter(lambda x: x.strip() != ""))
    @settings(max_examples=100, deadline=None)
    def test_property_17_optional_field_none_accepted(self, field_name: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any optional field that is None, validation SHALL accept it.
        """
        result = InputValidator.validate_filters(None, field_name=field_name, required=False)
        assert result is None


class TestIntegerValidation:
    """Property tests for integer validation."""

    @given(
        value=st.integers(min_value=-1000, max_value=1000),
        minimum=st.integers(min_value=-500, max_value=0),
        maximum=st.integers(min_value=500, max_value=1000),
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_integer_in_range_accepted(
        self,
        value: int,
        minimum: int,
        maximum: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any integer within the specified range, validation SHALL accept it.
        """
        assume(minimum <= value <= maximum)

        result = InputValidator.validate_integer(
            value, "test_field", minimum=minimum, maximum=maximum
        )
        assert result == value

    @given(value=st.booleans())
    @settings(max_examples=100, deadline=None)
    def test_property_17_boolean_not_accepted_as_integer(self, value: bool):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any boolean value, integer validation SHALL reject it
        (even though bool is a subclass of int in Python).
        """
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(value, "test_field")

        error = exc_info.value
        assert "integer" in error.message.lower()


class TestCostThresholdValidation:
    """Property tests for cost threshold validation."""

    @given(threshold=st.floats(min_value=0.0, max_value=1_000_000.0, allow_nan=False))
    @settings(max_examples=100, deadline=None)
    def test_property_17_valid_cost_threshold_accepted(self, threshold: float):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid cost threshold (0 to 1,000,000), validation SHALL accept it.
        """
        result = InputValidator.validate_min_cost_threshold(threshold)
        assert result == threshold

    @given(threshold=st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, deadline=None)
    def test_property_17_negative_cost_threshold_rejected(self, threshold: float):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any negative cost threshold, validation SHALL reject it.
        """
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_min_cost_threshold(threshold)

        error = exc_info.value
        assert "non-negative" in error.message.lower() or "negative" in error.message.lower()

    @given(threshold=st.floats(min_value=1_000_001.0, max_value=10_000_000.0, allow_nan=False))
    @settings(max_examples=100, deadline=None)
    def test_property_17_excessive_cost_threshold_rejected(self, threshold: float):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any cost threshold exceeding $1,000,000, validation SHALL reject it.
        """
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_min_cost_threshold(threshold)

        error = exc_info.value
        assert "unreasonably large" in error.message.lower() or "1,000,000" in error.message


class TestArnFormatValidationProperty:
    """Property tests for comprehensive ARN format validation.

    Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
    Validates: Requirements 16.3

    These tests verify that the ARN validation correctly handles all AWS service
    ARN formats including global services, S3 buckets, and various partitions.
    """

    # Strategy for generating valid standard ARNs (with region and account)
    standard_arn = st.builds(
        lambda partition, service, region, account, resource: f"arn:{partition}:{service}:{region}:{account}:{resource}",
        partition=st.sampled_from(["aws", "aws-cn", "aws-us-gov"]),
        service=st.sampled_from(
            ["ec2", "rds", "lambda", "ecs", "dynamodb", "sns", "sqs", "kinesis"]
        ),
        region=st.sampled_from(
            ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1", "cn-north-1", "us-gov-west-1"]
        ),
        account=st.from_regex(r"^\d{12}$", fullmatch=True),
        resource=st.from_regex(r"^[a-z][a-z0-9\-/_:.]+$", fullmatch=True).filter(
            lambda x: 1 < len(x) < 100
        ),
    )

    # Strategy for generating valid global service ARNs (empty region)
    global_service_arn = st.builds(
        lambda partition, service, account, resource: f"arn:{partition}:{service}::{account}:{resource}",
        partition=st.sampled_from(["aws", "aws-cn", "aws-us-gov"]),
        service=st.sampled_from(["iam", "route53", "cloudfront", "waf"]),
        account=st.from_regex(r"^\d{12}$", fullmatch=True),
        resource=st.from_regex(r"^[a-z][a-z0-9\-/_:.]+$", fullmatch=True).filter(
            lambda x: 1 < len(x) < 100
        ),
    )

    # Strategy for generating valid S3 bucket ARNs (empty region AND account)
    s3_bucket_arn = st.builds(
        lambda partition, bucket: f"arn:{partition}:s3:::{bucket}",
        partition=st.sampled_from(["aws", "aws-cn", "aws-us-gov"]),
        bucket=st.from_regex(r"^[a-z0-9][a-z0-9\-._]{2,62}$", fullmatch=True),
    )

    # Combined strategy for any valid ARN
    any_valid_arn = st.one_of(standard_arn, global_service_arn, s3_bucket_arn)

    @given(arn=standard_arn)
    @settings(max_examples=100, deadline=None)
    def test_property_17_standard_arns_accepted(self, arn: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid standard ARN (with region and account), validation SHALL accept it.
        """
        result = InputValidator.validate_resource_arns([arn])
        assert result == [arn]

    @given(arn=global_service_arn)
    @settings(max_examples=100, deadline=None)
    def test_property_17_global_service_arns_accepted(self, arn: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid global service ARN (empty region), validation SHALL accept it.
        """
        result = InputValidator.validate_resource_arns([arn])
        assert result == [arn]

    @given(arn=s3_bucket_arn)
    @settings(max_examples=100, deadline=None)
    def test_property_17_s3_bucket_arns_accepted(self, arn: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any valid S3 bucket ARN (empty region and account), validation SHALL accept it.
        """
        result = InputValidator.validate_resource_arns([arn])
        assert result == [arn]

    @given(arns=st.lists(any_valid_arn, min_size=1, max_size=10, unique=True))
    @settings(max_examples=100, deadline=None)
    def test_property_17_mixed_arn_types_accepted(self, arns: list[str]):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any list of valid ARNs (mixed types), validation SHALL accept all of them.
        """
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns

    @given(
        partition=st.text(min_size=1, max_size=20).filter(
            lambda x: x not in ["aws", "aws-cn", "aws-us-gov"] and x.strip() != ""
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_invalid_partition_rejected(self, partition: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any ARN with invalid partition, validation SHALL reject it.
        """
        arn = f"arn:{partition}:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"

        with pytest.raises((ValidationError, SecurityViolationError)):
            InputValidator.validate_resource_arns([arn])

    @given(
        account=st.text(min_size=1, max_size=20).filter(
            lambda x: not (x.isdigit() and len(x) == 12) and x != "" and x.strip() != ""
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_invalid_account_id_rejected(self, account: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any ARN with invalid account ID (not 12 digits and not empty),
        validation SHALL reject it.
        """
        # Skip if account contains characters that would trigger security violations
        try:
            InputValidator.detect_injection_attempt(account, "test")
        except SecurityViolationError:
            assume(False)  # Skip this test case

        arn = f"arn:aws:ec2:us-east-1:{account}:instance/i-1234567890abcdef0"

        with pytest.raises((ValidationError, SecurityViolationError)):
            InputValidator.validate_resource_arns([arn])

    @given(
        prefix=st.text(min_size=1, max_size=50).filter(
            lambda x: not x.startswith("arn:") and x.strip() != ""
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_17_non_arn_strings_rejected(self, prefix: str):
        """
        Feature: phase-1-aws-mvp, Property 17: Input Schema Validation
        Validates: Requirements 16.3

        For any string that doesn't start with 'arn:', validation SHALL reject it.
        """
        # Skip if prefix contains characters that would trigger security violations
        try:
            InputValidator.detect_injection_attempt(prefix, "test")
        except SecurityViolationError:
            assume(False)  # Skip this test case

        with pytest.raises((ValidationError, SecurityViolationError)):
            InputValidator.validate_resource_arns([prefix])
