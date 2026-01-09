"""Unit tests for input validation utilities.

Requirements: 16.3
"""

import pytest
import re
from mcp_server.utils.input_validation import (
    InputValidator,
    ValidationError,
    SecurityViolationError,
)


class TestSanitizeString:
    """Test string sanitization."""
    
    def test_sanitize_valid_string(self):
        """Test sanitization passes for valid strings."""
        result = InputValidator.sanitize_string("valid-string_123")
        assert result == "valid-string_123"
    
    def test_sanitize_string_with_newlines(self):
        """Test sanitization allows newlines."""
        result = InputValidator.sanitize_string("line1\nline2")
        assert result == "line1\nline2"
    
    def test_sanitize_string_with_tabs(self):
        """Test sanitization allows tabs."""
        result = InputValidator.sanitize_string("col1\tcol2")
        assert result == "col1\tcol2"
    
    def test_sanitize_string_too_long(self):
        """Test sanitization rejects strings that are too long."""
        long_string = "a" * 2000
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.sanitize_string(long_string, max_length=1024)
        
        assert exc_info.value.field == "string"
        assert "too long" in exc_info.value.message.lower()
    
    def test_sanitize_string_with_null_bytes(self):
        """Test sanitization rejects null bytes."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.sanitize_string("test\x00injection", field_name="test_field")
        
        assert exc_info.value.violation_type == "null_byte_injection"
        assert "null bytes" in exc_info.value.message.lower()
    
    def test_sanitize_string_with_control_chars(self):
        """Test sanitization rejects dangerous control characters."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.sanitize_string("test\x01control", field_name="test_field")
        
        assert exc_info.value.violation_type == "control_character"
        assert "control character" in exc_info.value.message.lower()


class TestValidateResourceTypes:
    """Test resource_types validation."""
    
    def test_valid_resource_types(self):
        """Test validation passes for valid resource types."""
        result = InputValidator.validate_resource_types(
            ["ec2:instance", "s3:bucket"]
        )
        assert result == ["ec2:instance", "s3:bucket"]
    
    def test_resource_types_required(self):
        """Test validation fails when required field is missing."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_types(None, required=True)
        
        assert exc_info.value.field == "resource_types"
        assert "required" in exc_info.value.message.lower()
    
    def test_resource_types_not_list(self):
        """Test validation fails for non-list input."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_types("ec2:instance")
        
        assert exc_info.value.field == "resource_types"
        assert "array" in exc_info.value.message.lower()
    
    def test_resource_types_empty(self):
        """Test validation fails for empty list."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_types([])
        
        assert exc_info.value.field == "resource_types"
        assert "empty" in exc_info.value.message.lower()
    
    def test_resource_types_too_many(self):
        """Test validation fails when too many types provided."""
        too_many = ["ec2:instance"] * 15
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_types(too_many)
        
        assert exc_info.value.field == "resource_types"
        assert "too many" in exc_info.value.message.lower()
    
    def test_resource_types_duplicates(self):
        """Test validation fails for duplicate values."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_types(
                ["ec2:instance", "ec2:instance"]
            )
        
        assert exc_info.value.field == "resource_types"
        assert "duplicate" in exc_info.value.message.lower()
    
    def test_resource_types_invalid_type(self):
        """Test validation fails for invalid resource type."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_types(
                ["ec2:instance", "invalid:type"]
            )
        
        assert exc_info.value.field == "resource_types"
        assert "invalid" in exc_info.value.message.lower()
        assert "invalid:type" in exc_info.value.message


class TestValidateResourceArns:
    """Test resource_arns validation."""
    
    def test_valid_arns(self):
        """Test validation passes for valid ARNs."""
        arns = [
            "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            "arn:aws:s3:::my-bucket-name",  # S3 buckets have empty region/account
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_arns_required(self):
        """Test validation fails when required field is missing."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_arns(None, required=True)
        
        assert exc_info.value.field == "resource_arns"
        assert "required" in exc_info.value.message.lower()
    
    def test_arns_not_list(self):
        """Test validation fails for non-list input."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_arns("arn:aws:ec2:...")
        
        assert exc_info.value.field == "resource_arns"
        assert "array" in exc_info.value.message.lower()
    
    def test_arns_empty(self):
        """Test validation fails for empty list."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_arns([])
        
        assert exc_info.value.field == "resource_arns"
        assert "empty" in exc_info.value.message.lower()
    
    def test_arns_too_many(self):
        """Test validation fails when too many ARNs provided."""
        too_many = ["arn:aws:ec2:us-east-1:123456789012:instance/i-123"] * 150
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_arns(too_many)
        
        assert exc_info.value.field == "resource_arns"
        assert "too many" in exc_info.value.message.lower()
    
    def test_arns_invalid_format(self):
        """Test validation fails for invalid ARN format."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_resource_arns(
                ["not-an-arn", "arn:aws:ec2:us-east-1:123456789012:instance/i-123"]
            )
        
        assert exc_info.value.field == "resource_arns"
        assert "invalid arn" in exc_info.value.message.lower()
    
    def test_arns_with_injection_attempt(self):
        """Test validation rejects ARNs with null bytes."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.validate_resource_arns(
                ["arn:aws:ec2:us-east-1:123456789012:instance/i-123\x00injection"]
            )
        
        assert exc_info.value.violation_type == "null_byte_injection"
        assert "null bytes" in exc_info.value.message.lower()
    
    def test_s3_bucket_arn_with_empty_region_and_account(self):
        """Test validation passes for S3 bucket ARNs with empty region and account."""
        arns = [
            "arn:aws:s3:::zombiescan-cur-zs551762956371",
            "arn:aws:s3:::my-bucket",
            "arn:aws:s3:::bucket-with-dots.example.com",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_iam_arn_with_empty_region(self):
        """Test validation passes for IAM ARNs with empty region."""
        arns = [
            "arn:aws:iam::123456789012:user/johndoe",
            "arn:aws:iam::123456789012:role/admin-role",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns


class TestValidateRegions:
    """Test regions validation."""
    
    def test_valid_regions(self):
        """Test validation passes for valid regions."""
        result = InputValidator.validate_regions(["us-east-1", "eu-west-1"])
        assert result == ["us-east-1", "eu-west-1"]
    
    def test_regions_optional(self):
        """Test validation passes when optional field is None."""
        result = InputValidator.validate_regions(None, required=False)
        assert result is None
    
    def test_regions_invalid(self):
        """Test validation fails for invalid regions."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_regions(["us-east-1", "invalid-region"])
        
        assert exc_info.value.field == "regions"
        assert "invalid" in exc_info.value.message.lower()


class TestValidateFilters:
    """Test filters validation."""
    
    def test_valid_filters(self):
        """Test validation passes for valid filters."""
        filters = {"region": "us-east-1", "account_id": "123456789012"}
        result = InputValidator.validate_filters(filters)
        assert result == filters
    
    def test_filters_optional(self):
        """Test validation passes when optional field is None."""
        result = InputValidator.validate_filters(None, required=False)
        assert result is None
    
    def test_filters_invalid_keys(self):
        """Test validation fails for invalid filter keys."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_filters({"invalid_key": "value"})
        
        assert exc_info.value.field == "filters"
        assert "invalid" in exc_info.value.message.lower()
    
    def test_filters_invalid_account_id(self):
        """Test validation fails for invalid account ID."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_filters({"account_id": "invalid"})
        
        assert "account_id" in exc_info.value.field
        assert "12-digit" in exc_info.value.message.lower()


class TestValidateTimePeriod:
    """Test time_period validation."""
    
    def test_valid_time_period(self):
        """Test validation passes for valid time period."""
        time_period = {"Start": "2024-01-01", "End": "2024-01-31"}
        result = InputValidator.validate_time_period(time_period)
        assert result == time_period
    
    def test_time_period_optional(self):
        """Test validation passes when optional field is None."""
        result = InputValidator.validate_time_period(None, required=False)
        assert result is None
    
    def test_time_period_missing_keys(self):
        """Test validation fails when required keys are missing."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_time_period({"Start": "2024-01-01"})
        
        assert exc_info.value.field == "time_period"
        assert "missing" in exc_info.value.message.lower()
    
    def test_time_period_invalid_date_format(self):
        """Test validation fails for invalid date format."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_time_period(
                {"Start": "01/01/2024", "End": "2024-01-31"}
            )
        
        assert "Start" in exc_info.value.field
        assert "YYYY-MM-DD" in exc_info.value.message
    
    def test_time_period_end_before_start(self):
        """Test validation fails when end date is before start date."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_time_period(
                {"Start": "2024-01-31", "End": "2024-01-01"}
            )
        
        assert exc_info.value.field == "time_period"
        assert "after" in exc_info.value.message.lower()
    
    def test_time_period_too_large(self):
        """Test validation fails when date range is too large."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_time_period(
                {"Start": "2023-01-01", "End": "2024-12-31"}
            )
        
        assert exc_info.value.field == "time_period"
        assert "too large" in exc_info.value.message.lower()


class TestValidateInteger:
    """Test integer validation."""
    
    def test_valid_integer(self):
        """Test validation passes for valid integer."""
        result = InputValidator.validate_integer(42, "test_field")
        assert result == 42
    
    def test_integer_with_minimum(self):
        """Test validation enforces minimum value."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(0, "test_field", minimum=1)
        
        assert exc_info.value.field == "test_field"
        assert "at least" in exc_info.value.message.lower()
    
    def test_integer_with_maximum(self):
        """Test validation enforces maximum value."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(100, "test_field", maximum=90)
        
        assert exc_info.value.field == "test_field"
        assert "at most" in exc_info.value.message.lower()
    
    def test_integer_rejects_boolean(self):
        """Test validation rejects boolean values."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(True, "test_field")
        
        assert exc_info.value.field == "test_field"
        assert "integer" in exc_info.value.message.lower()


class TestValidateString:
    """Test string validation."""
    
    def test_valid_string(self):
        """Test validation passes for valid string."""
        result = InputValidator.validate_string("test", "test_field")
        assert result == "test"
    
    def test_string_with_pattern(self):
        """Test validation enforces pattern matching."""
        pattern = re.compile(r'^\d{3}$')
        
        result = InputValidator.validate_string(
            "123", "test_field", pattern=pattern
        )
        assert result == "123"
        
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_string(
                "abc", "test_field", pattern=pattern
            )
        
        assert exc_info.value.field == "test_field"
        assert "pattern" in exc_info.value.message.lower()
    
    def test_string_sanitization(self):
        """Test string sanitization is applied."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.validate_string(
                "test\x00injection", "test_field"
            )
        
        assert exc_info.value.violation_type == "null_byte_injection"
        assert "null bytes" in exc_info.value.message.lower()


class TestInjectionDetection:
    """Test injection attempt detection."""
    
    def test_detect_xss_script_tag(self):
        """Test detection of XSS script tags."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(
                "<script>alert('xss')</script>", "test_field"
            )
        
        assert exc_info.value.violation_type == "injection_attempt"
        assert "suspicious pattern" in exc_info.value.message.lower()
    
    def test_detect_javascript_protocol(self):
        """Test detection of javascript: protocol."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(
                "javascript:alert('xss')", "test_field"
            )
        
        assert exc_info.value.violation_type == "injection_attempt"
    
    def test_detect_event_handlers(self):
        """Test detection of event handlers."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(
                "<img onerror='alert(1)'>", "test_field"
            )
        
        assert exc_info.value.violation_type == "injection_attempt"
    
    def test_detect_eval_calls(self):
        """Test detection of eval() calls."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(
                "eval(malicious_code)", "test_field"
            )
        
        assert exc_info.value.violation_type == "injection_attempt"
    
    def test_detect_template_injection(self):
        """Test detection of template injection patterns."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(
                "${malicious_code}", "test_field"
            )
        
        assert exc_info.value.violation_type == "injection_attempt"
    
    def test_detect_path_traversal(self):
        """Test detection of path traversal attempts."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(
                "../../etc/passwd", "test_field"
            )
        
        assert exc_info.value.violation_type == "injection_attempt"
    
    def test_detect_system_file_access(self):
        """Test detection of system file access attempts."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(
                "cat /etc/passwd", "test_field"
            )
        
        assert exc_info.value.violation_type == "injection_attempt"
    
    def test_detect_command_execution(self):
        """Test detection of command execution attempts."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(
                "cmd.exe /c dir", "test_field"
            )
        
        assert exc_info.value.violation_type == "injection_attempt"
    
    def test_detect_destructive_commands(self):
        """Test detection of destructive commands."""
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.detect_injection_attempt(
                "; rm -rf /", "test_field"
            )
        
        assert exc_info.value.violation_type == "injection_attempt"
    
    def test_safe_strings_pass(self):
        """Test that safe strings pass injection detection."""
        # These should not raise exceptions
        InputValidator.detect_injection_attempt("normal text", "test_field")
        InputValidator.detect_injection_attempt("arn:aws:ec2:us-east-1:123456789012:instance/i-123", "test_field")
        InputValidator.detect_injection_attempt("CostCenter=Engineering", "test_field")


class TestParameterSizeLimits:
    """Test parameter size limit enforcement."""
    
    def test_check_excessive_nesting(self):
        """Test detection of excessive nesting depth."""
        # Create deeply nested structure
        data = {"level1": {"level2": {"level3": {"level4": {"level5": {"level6": "too deep"}}}}}}
        
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.check_parameter_size_limits(data)
        
        assert exc_info.value.violation_type == "excessive_nesting"
        assert "nesting too deep" in exc_info.value.message.lower()
    
    def test_check_excessive_dict_keys(self):
        """Test detection of excessive dictionary keys."""
        # Create dict with too many keys
        data = {f"key{i}": f"value{i}" for i in range(100)}
        
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.check_parameter_size_limits(data)
        
        assert exc_info.value.violation_type == "excessive_keys"
        assert "too many dictionary keys" in exc_info.value.message.lower()
    
    def test_check_excessive_array_length(self):
        """Test detection of excessive array length."""
        # Create array that's too long
        data = ["item"] * 2000
        
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.check_parameter_size_limits(data)
        
        assert exc_info.value.violation_type == "excessive_array_length"
        assert "array too long" in exc_info.value.message.lower()
    
    def test_check_excessive_string_length(self):
        """Test detection of excessive string length."""
        # Create string that's too long
        data = {"field": "a" * 2000}
        
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.check_parameter_size_limits(data)
        
        assert exc_info.value.violation_type == "excessive_string_length"
        assert "string too long" in exc_info.value.message.lower()
    
    def test_check_excessive_key_length(self):
        """Test detection of excessive key length."""
        # Create dict with key that's too long
        long_key = "k" * 2000
        data = {long_key: "value"}
        
        with pytest.raises(SecurityViolationError) as exc_info:
            InputValidator.check_parameter_size_limits(data)
        
        assert exc_info.value.violation_type == "excessive_key_length"
        assert "key too long" in exc_info.value.message.lower()
    
    def test_check_normal_parameters_pass(self):
        """Test that normal parameters pass size checks."""
        # These should not raise exceptions
        data = {
            "resource_types": ["ec2:instance", "s3:bucket"],
            "filters": {"region": "us-east-1"},
            "severity": "all",
        }
        InputValidator.check_parameter_size_limits(data)
    
    def test_check_nested_arrays_and_dicts(self):
        """Test size checking works with nested structures."""
        data = {
            "level1": {
                "array": ["item1", "item2"],
                "nested": {
                    "field": "value"
                }
            }
        }
        # Should not raise exception
        InputValidator.check_parameter_size_limits(data)


class TestArnPatternValidation:
    """Test ARN pattern validation for various AWS resource types.
    
    Requirements: 16.3
    """
    
    def test_s3_bucket_arn_empty_region_and_account(self):
        """Test S3 bucket ARNs with empty region and account fields pass validation."""
        # S3 bucket ARNs have format: arn:aws:s3:::bucket-name
        arns = [
            "arn:aws:s3:::zombiescan-cur-zs551762956371",
            "arn:aws:s3:::my-bucket",
            "arn:aws:s3:::bucket-with-dots.example.com",
            "arn:aws:s3:::bucket_with_underscores",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_iam_arn_empty_region(self):
        """Test IAM ARNs with empty region field pass validation."""
        # IAM ARNs have format: arn:aws:iam::account-id:resource
        arns = [
            "arn:aws:iam::123456789012:user/johndoe",
            "arn:aws:iam::123456789012:role/admin-role",
            "arn:aws:iam::123456789012:policy/my-policy",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_ec2_arn_with_region_and_account(self):
        """Test EC2 ARNs with region and account pass validation."""
        arns = [
            "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            "arn:aws:ec2:eu-west-1:123456789012:volume/vol-1234567890abcdef0",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_lambda_arn_with_function_name(self):
        """Test Lambda function ARNs pass validation."""
        arns = [
            "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "arn:aws:lambda:us-west-2:123456789012:function:another-function",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_rds_arn_with_db_identifier(self):
        """Test RDS ARNs pass validation."""
        arns = [
            "arn:aws:rds:us-east-1:123456789012:db:my-database",
            "arn:aws:rds:eu-central-1:123456789012:cluster:my-cluster",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_invalid_arn_format_rejected(self):
        """Test invalid ARN formats are rejected."""
        invalid_arns = [
            "not-an-arn",
            "arn:invalid",
            "arn:aws:ec2",  # Too few parts
            "",
        ]
        for arn in invalid_arns:
            with pytest.raises(ValidationError) as exc_info:
                InputValidator.validate_resource_arns([arn])
            assert "invalid arn" in exc_info.value.message.lower()


class TestArnPatternComprehensive:
    """Comprehensive ARN pattern tests for all supported AWS services.
    
    Requirements: 16.3
    """
    
    # =========================================================================
    # Global Services (Empty Region)
    # =========================================================================
    
    def test_iam_user_arn(self):
        """Test IAM user ARNs pass validation."""
        arns = [
            "arn:aws:iam::123456789012:user/johndoe",
            "arn:aws:iam::123456789012:user/path/to/user",
            "arn:aws:iam::123456789012:user/user_with_underscore",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_iam_role_arn(self):
        """Test IAM role ARNs pass validation."""
        arns = [
            "arn:aws:iam::123456789012:role/admin-role",
            "arn:aws:iam::123456789012:role/service-role/AWSLambdaBasicExecutionRole",
            "arn:aws:iam::123456789012:role/aws-service-role/ecs.amazonaws.com/AWSServiceRoleForECS",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_iam_policy_arn(self):
        """Test IAM policy ARNs pass validation."""
        arns = [
            "arn:aws:iam::123456789012:policy/my-custom-policy",
            "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess",  # AWS managed policy
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_iam_instance_profile_arn(self):
        """Test IAM instance profile ARNs pass validation."""
        arns = [
            "arn:aws:iam::123456789012:instance-profile/my-profile",
            "arn:aws:iam::123456789012:instance-profile/path/to/profile",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_route53_hosted_zone_arn(self):
        """Test Route53 hosted zone ARNs pass validation."""
        arns = [
            "arn:aws:route53::123456789012:hostedzone/Z1234567890ABC",
            "arn:aws:route53::123456789012:healthcheck/abc123-def456",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_cloudfront_distribution_arn(self):
        """Test CloudFront distribution ARNs pass validation."""
        arns = [
            "arn:aws:cloudfront::123456789012:distribution/E1234567890ABC",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    # =========================================================================
    # S3 (Empty Region AND Account for Buckets)
    # =========================================================================
    
    def test_s3_bucket_arn_various_names(self):
        """Test S3 bucket ARNs with various naming conventions."""
        arns = [
            "arn:aws:s3:::simple-bucket",
            "arn:aws:s3:::bucket.with.dots",
            "arn:aws:s3:::bucket_with_underscores",
            "arn:aws:s3:::bucket-with-numbers-123",
            "arn:aws:s3:::123-starts-with-number",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_s3_object_arn(self):
        """Test S3 object ARNs pass validation."""
        arns = [
            "arn:aws:s3:::my-bucket/path/to/object.txt",
            "arn:aws:s3:::my-bucket/folder/subfolder/file.json",
            "arn:aws:s3:::my-bucket/*",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_s3_access_point_arn(self):
        """Test S3 access point ARNs (with region and account) pass validation."""
        arns = [
            "arn:aws:s3:us-east-1:123456789012:accesspoint/my-access-point",
            "arn:aws:s3:eu-west-1:123456789012:accesspoint/another-ap",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    # =========================================================================
    # EC2 Resources
    # =========================================================================
    
    def test_ec2_instance_arn(self):
        """Test EC2 instance ARNs pass validation."""
        arns = [
            "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            "arn:aws:ec2:ap-southeast-1:123456789012:instance/i-abcdef1234567890",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_ec2_volume_arn(self):
        """Test EC2 volume ARNs pass validation."""
        arns = [
            "arn:aws:ec2:us-east-1:123456789012:volume/vol-1234567890abcdef0",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_ec2_snapshot_arn(self):
        """Test EC2 snapshot ARNs pass validation."""
        arns = [
            "arn:aws:ec2:us-east-1:123456789012:snapshot/snap-1234567890abcdef0",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_ec2_security_group_arn(self):
        """Test EC2 security group ARNs pass validation."""
        arns = [
            "arn:aws:ec2:us-east-1:123456789012:security-group/sg-1234567890abcdef0",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_ec2_vpc_arn(self):
        """Test EC2 VPC ARNs pass validation."""
        arns = [
            "arn:aws:ec2:us-east-1:123456789012:vpc/vpc-1234567890abcdef0",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    # =========================================================================
    # Lambda Resources
    # =========================================================================
    
    def test_lambda_function_arn_with_alias(self):
        """Test Lambda function ARNs with alias pass validation."""
        arns = [
            "arn:aws:lambda:us-east-1:123456789012:function:my-function:prod",
            "arn:aws:lambda:us-east-1:123456789012:function:my-function:$LATEST",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_lambda_layer_arn(self):
        """Test Lambda layer ARNs pass validation."""
        arns = [
            "arn:aws:lambda:us-east-1:123456789012:layer:my-layer:1",
            "arn:aws:lambda:us-east-1:123456789012:layer:my-layer:42",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    # =========================================================================
    # RDS Resources
    # =========================================================================
    
    def test_rds_db_instance_arn(self):
        """Test RDS DB instance ARNs pass validation."""
        arns = [
            "arn:aws:rds:us-east-1:123456789012:db:my-database",
            "arn:aws:rds:eu-west-1:123456789012:db:production-db",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_rds_cluster_arn(self):
        """Test RDS cluster ARNs pass validation."""
        arns = [
            "arn:aws:rds:us-east-1:123456789012:cluster:my-aurora-cluster",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_rds_snapshot_arn(self):
        """Test RDS snapshot ARNs pass validation."""
        arns = [
            "arn:aws:rds:us-east-1:123456789012:snapshot:my-snapshot",
            "arn:aws:rds:us-east-1:123456789012:cluster-snapshot:my-cluster-snapshot",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    # =========================================================================
    # ECS Resources
    # =========================================================================
    
    def test_ecs_cluster_arn(self):
        """Test ECS cluster ARNs pass validation."""
        arns = [
            "arn:aws:ecs:us-east-1:123456789012:cluster/my-cluster",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_ecs_service_arn(self):
        """Test ECS service ARNs pass validation."""
        arns = [
            "arn:aws:ecs:us-east-1:123456789012:service/my-cluster/my-service",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_ecs_task_arn(self):
        """Test ECS task ARNs pass validation."""
        arns = [
            "arn:aws:ecs:us-east-1:123456789012:task/my-cluster/abc123def456",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_ecs_task_definition_arn(self):
        """Test ECS task definition ARNs pass validation."""
        arns = [
            "arn:aws:ecs:us-east-1:123456789012:task-definition/my-task:1",
            "arn:aws:ecs:us-east-1:123456789012:task-definition/my-task:42",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    # =========================================================================
    # OpenSearch / Elasticsearch
    # =========================================================================
    
    def test_opensearch_domain_arn(self):
        """Test OpenSearch domain ARNs pass validation."""
        arns = [
            "arn:aws:es:us-east-1:123456789012:domain/my-search-domain",
            "arn:aws:opensearch:us-west-2:123456789012:domain/my-opensearch",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    # =========================================================================
    # Other Services
    # =========================================================================
    
    def test_sns_topic_arn(self):
        """Test SNS topic ARNs pass validation."""
        arns = [
            "arn:aws:sns:us-east-1:123456789012:my-topic",
            "arn:aws:sns:us-east-1:123456789012:my-topic.fifo",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_sqs_queue_arn(self):
        """Test SQS queue ARNs pass validation."""
        arns = [
            "arn:aws:sqs:us-east-1:123456789012:my-queue",
            "arn:aws:sqs:us-east-1:123456789012:my-queue.fifo",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_dynamodb_table_arn(self):
        """Test DynamoDB table ARNs pass validation."""
        arns = [
            "arn:aws:dynamodb:us-east-1:123456789012:table/my-table",
            "arn:aws:dynamodb:us-east-1:123456789012:table/my-table/index/my-index",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_kinesis_stream_arn(self):
        """Test Kinesis stream ARNs pass validation."""
        arns = [
            "arn:aws:kinesis:us-east-1:123456789012:stream/my-stream",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_secrets_manager_arn(self):
        """Test Secrets Manager ARNs pass validation."""
        arns = [
            "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-abc123",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_kms_key_arn(self):
        """Test KMS key ARNs pass validation."""
        arns = [
            "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012",
            "arn:aws:kms:us-east-1:123456789012:alias/my-key-alias",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_step_functions_arn(self):
        """Test Step Functions state machine ARNs pass validation."""
        arns = [
            "arn:aws:states:us-east-1:123456789012:stateMachine:my-state-machine",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_cloudwatch_logs_arn(self):
        """Test CloudWatch Logs ARNs pass validation."""
        arns = [
            "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/my-function",
            "arn:aws:logs:us-east-1:123456789012:log-group:my-log-group:*",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_elb_arn(self):
        """Test Elastic Load Balancing ARNs pass validation."""
        arns = [
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/1234567890abcdef",
            "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/my-tg/1234567890abcdef",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_elasticache_arn(self):
        """Test ElastiCache ARNs pass validation."""
        arns = [
            "arn:aws:elasticache:us-east-1:123456789012:cluster:my-redis-cluster",
            "arn:aws:elasticache:us-east-1:123456789012:replicationgroup:my-replication-group",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_redshift_arn(self):
        """Test Redshift ARNs pass validation."""
        arns = [
            "arn:aws:redshift:us-east-1:123456789012:cluster:my-redshift-cluster",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_glue_arn(self):
        """Test Glue ARNs pass validation."""
        arns = [
            "arn:aws:glue:us-east-1:123456789012:database/my-database",
            "arn:aws:glue:us-east-1:123456789012:table/my-database/my-table",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    # =========================================================================
    # AWS Partitions (China, GovCloud)
    # =========================================================================
    
    def test_aws_china_partition_arn(self):
        """Test ARNs with aws-cn partition pass validation."""
        arns = [
            "arn:aws-cn:ec2:cn-north-1:123456789012:instance/i-1234567890abcdef0",
            "arn:aws-cn:s3:::my-china-bucket",
            "arn:aws-cn:iam::123456789012:user/johndoe",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_aws_govcloud_partition_arn(self):
        """Test ARNs with aws-us-gov partition pass validation."""
        arns = [
            "arn:aws-us-gov:ec2:us-gov-west-1:123456789012:instance/i-1234567890abcdef0",
            "arn:aws-us-gov:s3:::my-govcloud-bucket",
            "arn:aws-us-gov:iam::123456789012:role/admin-role",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    # =========================================================================
    # Edge Cases
    # =========================================================================
    
    def test_arn_with_special_characters_in_resource(self):
        """Test ARNs with special characters in resource pass validation."""
        arns = [
            "arn:aws:s3:::bucket/path/to/file@2024.txt",
            "arn:aws:lambda:us-east-1:123456789012:function:my-function:$LATEST",
            "arn:aws:logs:us-east-1:123456789012:log-group:/aws/lambda/my-function:*",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns
    
    def test_mixed_arn_types_in_single_request(self):
        """Test validation passes for mixed ARN types in a single request."""
        arns = [
            "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            "arn:aws:s3:::my-bucket",
            "arn:aws:iam::123456789012:role/admin-role",
            "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            "arn:aws:rds:us-east-1:123456789012:db:my-database",
        ]
        result = InputValidator.validate_resource_arns(arns)
        assert result == arns


# =============================================================================
# Array Unwrapping Tests (AI Agent Compatibility)
# =============================================================================

class TestArrayUnwrapping:
    """Test automatic array unwrapping for AI agent compatibility.
    
    AI agents often wrap single values in arrays (e.g., ["resource_type"] instead
    of "resource_type"). These tests verify that validators handle this gracefully.
    """
    
    def test_validate_severity_unwraps_single_element_array(self):
        """Test that severity validator unwraps single-element arrays."""
        result = InputValidator.validate_severity(["all"])
        assert result == "all"
        
        result = InputValidator.validate_severity(["errors_only"])
        assert result == "errors_only"
    
    def test_validate_severity_rejects_multi_element_array(self):
        """Test that severity validator rejects multi-element arrays."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_severity(["all", "errors_only"])
        assert "Must be a string" in str(exc_info.value)
    
    def test_validate_group_by_unwraps_single_element_array(self):
        """Test that group_by validator unwraps single-element arrays."""
        result = InputValidator.validate_group_by(["resource_type"])
        assert result == "resource_type"
        
        result = InputValidator.validate_group_by(["region"])
        assert result == "region"
    
    def test_validate_group_by_unwraps_json_string_array(self):
        """Test that group_by validator unwraps JSON string arrays.
        
        AI agents sometimes pass '["resource_type"]' as a string instead of
        an actual array. This test ensures we handle that case.
        """
        result = InputValidator.validate_group_by('["resource_type"]')
        assert result == "resource_type"
        
        result = InputValidator.validate_group_by('["region"]')
        assert result == "region"
        
        result = InputValidator.validate_group_by('["service"]')
        assert result == "service"
    
    def test_validate_group_by_rejects_multi_element_array(self):
        """Test that group_by validator rejects multi-element arrays."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_group_by(["resource_type", "region"])
        assert "Must be a string" in str(exc_info.value)
    
    def test_validate_format_unwraps_single_element_array(self):
        """Test that format validator unwraps single-element arrays."""
        result = InputValidator.validate_format(["json"])
        assert result == "json"
        
        result = InputValidator.validate_format(["markdown"])
        assert result == "markdown"
    
    def test_validate_format_rejects_multi_element_array(self):
        """Test that format validator rejects multi-element arrays."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_format(["json", "csv"])
        assert "Must be a string" in str(exc_info.value)
    
    def test_validate_string_unwraps_single_element_array(self):
        """Test that string validator unwraps single-element arrays."""
        result = InputValidator.validate_string(["test_value"], "test_field")
        assert result == "test_value"
    
    def test_validate_string_rejects_multi_element_array(self):
        """Test that string validator rejects multi-element arrays."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_string(["value1", "value2"], "test_field")
        assert "Must be a string" in str(exc_info.value)
    
    def test_validate_integer_unwraps_single_element_array(self):
        """Test that integer validator unwraps single-element arrays."""
        result = InputValidator.validate_integer([30], "days_back")
        assert result == 30
        
        result = InputValidator.validate_integer([90], "days_back", maximum=90)
        assert result == 90
    
    def test_validate_integer_rejects_multi_element_array(self):
        """Test that integer validator rejects multi-element arrays."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer([30, 60], "days_back")
        assert "Must be an integer" in str(exc_info.value)
    
    def test_validate_integer_rejects_array_of_non_integers(self):
        """Test that integer validator rejects arrays of non-integers."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(["30"], "days_back")
        assert "Must be an integer" in str(exc_info.value)
    
    def test_validate_boolean_unwraps_single_element_array(self):
        """Test that boolean validator unwraps single-element arrays."""
        result = InputValidator.validate_boolean([True], "include_costs")
        assert result is True
        
        result = InputValidator.validate_boolean([False], "include_costs")
        assert result is False
    
    def test_validate_boolean_rejects_multi_element_array(self):
        """Test that boolean validator rejects multi-element arrays."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_boolean([True, False], "include_costs")
        assert "Must be a boolean" in str(exc_info.value)
    
    def test_validate_boolean_rejects_array_of_non_booleans(self):
        """Test that boolean validator rejects arrays of non-booleans."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_boolean(["true"], "include_costs")
        assert "Must be a boolean" in str(exc_info.value)
    
    def test_validate_min_cost_threshold_unwraps_single_element_array(self):
        """Test that min_cost_threshold validator unwraps single-element arrays."""
        result = InputValidator.validate_min_cost_threshold([100.0])
        assert result == 100.0
        
        result = InputValidator.validate_min_cost_threshold([50])
        assert result == 50.0
    
    def test_validate_min_cost_threshold_rejects_multi_element_array(self):
        """Test that min_cost_threshold validator rejects multi-element arrays."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_min_cost_threshold([100.0, 200.0])
        assert "Must be a number" in str(exc_info.value)
    
    def test_validate_min_cost_threshold_rejects_array_of_non_numbers(self):
        """Test that min_cost_threshold validator rejects arrays of non-numbers."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_min_cost_threshold(["100"])
        assert "Must be a number" in str(exc_info.value)
    
    def test_unwrapped_values_still_validated(self):
        """Test that unwrapped values are still validated against allowed values."""
        # Invalid severity value should still fail after unwrapping
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_severity(["invalid_severity"])
        assert "Invalid severity" in str(exc_info.value)
        
        # Invalid group_by value should still fail after unwrapping
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_group_by(["invalid_group"])
        assert "Invalid value" in str(exc_info.value)
        
        # Invalid format value should still fail after unwrapping
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_format(["invalid_format"])
        assert "Invalid format" in str(exc_info.value)
