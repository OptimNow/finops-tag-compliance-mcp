"""Unit tests for error message sanitization utility.

Tests verify that sensitive information is properly redacted from error messages
while preserving useful information for debugging.

Requirements: 16.5
"""

from mcp_server.utils.error_sanitization import (
    SanitizedError,
    create_safe_error_response,
    detect_sensitive_info,
    handle_aws_error,
    handle_database_error,
    redact_sensitive_info,
    sanitize_error_response,
    sanitize_exception,
)


class TestDetectSensitiveInfo:
    """Tests for detecting sensitive information in text."""

    def test_detects_file_paths(self):
        """Test detection of file paths."""
        text = "Error in /home/user/app/main.py at line 42"
        result = detect_sensitive_info(text)
        assert "file_path" in result
        assert len(result["file_path"]) > 0

    def test_detects_aws_access_key(self):
        """Test detection of AWS access keys."""
        text = "Using AWS key AKIAIOSFODNN7EXAMPLE"
        result = detect_sensitive_info(text)
        assert "credentials" in result

    def test_detects_password_patterns(self):
        """Test detection of password patterns."""
        text = 'password = "super_secret_password_123"'
        result = detect_sensitive_info(text)
        assert "credentials" in result

    def test_detects_connection_strings(self):
        """Test detection of database connection strings."""
        text = "mysql://user:password@localhost:3306/database"
        result = detect_sensitive_info(text)
        assert "connection_string" in result

    def test_detects_internal_ips(self):
        """Test detection of internal IP addresses."""
        text = "Connected to 192.168.1.100"
        result = detect_sensitive_info(text)
        assert "internal_ip" in result

    def test_detects_stack_traces(self):
        """Test detection of stack traces."""
        text = 'File "/app/service.py", line 123, in process'
        result = detect_sensitive_info(text)
        assert "stack_trace" in result or "file_path" in result

    def test_no_sensitive_info_in_clean_text(self):
        """Test that clean text is not flagged."""
        text = "The operation completed successfully"
        result = detect_sensitive_info(text)
        assert len(result) == 0


class TestRedactSensitiveInfo:
    """Tests for redacting sensitive information."""

    def test_redacts_file_paths(self):
        """Test redaction of file paths."""
        text = "Error in /home/user/app/main.py at line 42"
        result = redact_sensitive_info(text)
        assert "/home/user/app/main.py" not in result
        assert "[REDACTED]" in result

    def test_redacts_aws_keys(self):
        """Test redaction of AWS keys."""
        text = "Using AWS key AKIAIOSFODNN7EXAMPLE"
        result = redact_sensitive_info(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result
        assert "[REDACTED]" in result

    def test_redacts_passwords(self):
        """Test redaction of passwords."""
        text = 'password = "super_secret_password_123"'
        result = redact_sensitive_info(text)
        assert "super_secret_password_123" not in result
        assert "[REDACTED]" in result

    def test_preserves_non_sensitive_text(self):
        """Test that non-sensitive text is preserved."""
        text = "The operation completed successfully"
        result = redact_sensitive_info(text)
        assert result == text

    def test_custom_replacement_string(self):
        """Test using custom replacement string."""
        text = "Error in /home/user/app/main.py"
        result = redact_sensitive_info(text, replacement="***")
        assert "/home/user/app/main.py" not in result
        assert "***" in result


class TestSanitizeException:
    """Tests for sanitizing exceptions."""

    def test_sanitizes_value_error(self):
        """Test sanitization of ValueError."""
        exc = ValueError("Invalid value: /home/user/secret.key")
        result = sanitize_exception(exc)

        assert isinstance(result, SanitizedError)
        assert result.error_code == "invalid_input"
        assert "/home/user/secret.key" not in result.user_message
        assert "Invalid" in result.user_message or "invalid" in result.user_message.lower()

    def test_sanitizes_permission_error(self):
        """Test sanitization of PermissionError."""
        exc = PermissionError("Access denied to /etc/passwd")
        result = sanitize_exception(exc)

        assert result.error_code == "permission_denied"
        assert "/etc/passwd" not in result.user_message

    def test_sanitizes_file_not_found_error(self):
        """Test sanitization of FileNotFoundError."""
        exc = FileNotFoundError("File not found: /app/config.json")
        result = sanitize_exception(exc)

        assert result.error_code == "not_found"
        assert "/app/config.json" not in result.user_message

    def test_sanitizes_timeout_error(self):
        """Test sanitization of TimeoutError."""
        exc = TimeoutError("Request to 192.168.1.100 timed out")
        result = sanitize_exception(exc)

        assert result.error_code == "timeout"
        assert "192.168.1.100" not in result.user_message

    def test_preserves_internal_message(self):
        """Test that internal message is preserved."""
        exc = ValueError("Invalid value: /home/user/secret.key")
        result = sanitize_exception(exc)

        assert result.internal_message == str(exc)

    def test_to_dict_conversion(self):
        """Test conversion to dictionary."""
        exc = ValueError("Invalid input")
        result = sanitize_exception(exc)

        result_dict = result.to_dict()
        assert "error" in result_dict
        assert "message" in result_dict
        assert result_dict["error"] == "invalid_input"


class TestSanitizeErrorResponse:
    """Tests for sanitizing error responses."""

    def test_sanitizes_exception_response(self):
        """Test sanitization of exception in response."""
        exc = ValueError("Invalid: /home/user/secret.key")
        result = sanitize_error_response(exc, status_code=400)

        assert result["status_code"] == 400
        assert "/home/user/secret.key" not in result["message"]
        assert "error" in result

    def test_sanitizes_string_error(self):
        """Test sanitization of string error."""
        error = "Error accessing /etc/passwd with key AKIAIOSFODNN7EXAMPLE"
        result = sanitize_error_response(error, status_code=500)

        assert "/etc/passwd" not in result["message"]
        assert "AKIAIOSFODNN7EXAMPLE" not in result["message"]

    def test_sanitizes_dict_error(self):
        """Test sanitization of dict error."""
        error = {
            "error": "database_error",
            "message": "Connection failed to 192.168.1.100:5432",
            "details": "User: admin, Password: secret123",
        }
        result = sanitize_error_response(error, status_code=500)

        assert "192.168.1.100" not in result["message"]
        assert "secret123" not in result["details"]

    def test_handles_unknown_error_type(self):
        """Test handling of unknown error type."""
        result = sanitize_error_response(12345, status_code=500)

        assert result["status_code"] == 500
        assert "error" in result
        assert "message" in result


class TestCreateSafeErrorResponse:
    """Tests for creating safe error responses."""

    def test_creates_safe_response(self):
        """Test creation of safe error response."""
        result = create_safe_error_response(
            error_code="invalid_input",
            user_message="The provided input is invalid",
        )

        assert result["error"] == "invalid_input"
        assert result["message"] == "The provided input is invalid"

    def test_redacts_sensitive_user_message(self):
        """Test that sensitive info in user message is redacted."""
        result = create_safe_error_response(
            error_code="error",
            user_message="Error accessing /home/user/secret.key",
        )

        assert "/home/user/secret.key" not in result["message"]

    def test_includes_safe_details(self):
        """Test inclusion of safe details."""
        result = create_safe_error_response(
            error_code="validation_error",
            user_message="Validation failed",
            details={"field": "email", "reason": "invalid format"},
        )

        assert "details" in result
        assert result["details"]["field"] == "email"

    def test_redacts_sensitive_details(self):
        """Test that sensitive info in details is redacted."""
        result = create_safe_error_response(
            error_code="error",
            user_message="Error occurred",
            details={"path": "/home/user/secret.key", "key": "AKIAIOSFODNN7EXAMPLE"},
        )

        assert "/home/user/secret.key" not in result["details"]["path"]
        assert "AKIAIOSFODNN7EXAMPLE" not in result["details"]["key"]


class TestHandleAWSError:
    """Tests for handling AWS-specific errors."""

    def test_handles_access_denied_error(self):
        """Test handling of AccessDenied error."""
        exc = Exception(
            "User: arn:aws:iam::123456789012:user/admin is not authorized to perform: ec2:DescribeInstances"
        )
        result = handle_aws_error(exc)

        assert result.error_code == "permission_denied"
        assert "not authorized" not in result.user_message

    def test_handles_invalid_parameter_error(self):
        """Test handling of InvalidParameterValue error."""
        exc = Exception("InvalidParameterValue: Invalid value for parameter InstanceType")
        result = handle_aws_error(exc)

        assert result.error_code == "invalid_input"

    def test_handles_throttling_error(self):
        """Test handling of throttling error."""
        exc = Exception("ThrottlingException: Rate exceeded")
        result = handle_aws_error(exc)

        assert result.error_code == "rate_limit"

    def test_handles_service_unavailable_error(self):
        """Test handling of ServiceUnavailable error."""
        exc = Exception("ServiceUnavailable: The service is temporarily unavailable")
        result = handle_aws_error(exc)

        assert result.error_code == "service_unavailable"

    def test_handles_generic_aws_error(self):
        """Test handling of generic AWS error."""
        exc = Exception("Some AWS error occurred")
        result = handle_aws_error(exc)

        assert result.error_code == "aws_error"


class TestHandleDatabaseError:
    """Tests for handling database-specific errors."""

    def test_handles_unique_constraint_error(self):
        """Test handling of UNIQUE constraint error."""
        exc = Exception("UNIQUE constraint failed: users.email")
        result = handle_database_error(exc)

        assert result.error_code == "duplicate_entry"

    def test_handles_table_not_found_error(self):
        """Test handling of table not found error."""
        exc = Exception("no such table: users")
        result = handle_database_error(exc)

        assert result.error_code == "not_found"

    def test_handles_database_locked_error(self):
        """Test handling of database locked error."""
        exc = Exception("database is locked")
        result = handle_database_error(exc)

        assert result.error_code == "database_locked"

    def test_handles_generic_database_error(self):
        """Test handling of generic database error."""
        exc = Exception("Some database error occurred")
        result = handle_database_error(exc)

        assert result.error_code == "database_error"


class TestErrorSanitizationIntegration:
    """Integration tests for error sanitization."""

    def test_full_error_flow_with_sensitive_info(self):
        """Test complete error flow with sensitive information."""
        # Create an exception with multiple types of sensitive info
        exc = ValueError(
            "Failed to connect to database at 192.168.1.100:5432 "
            "with user admin and password secret123. "
            "Error in /app/database.py line 42. "
            "AWS key: AKIAIOSFODNN7EXAMPLE"
        )

        # Sanitize the exception
        result = sanitize_exception(exc)

        # Verify all sensitive info is redacted
        assert "192.168.1.100" not in result.user_message
        assert "secret123" not in result.user_message
        assert "/app/database.py" not in result.user_message
        assert "AKIAIOSFODNN7EXAMPLE" not in result.user_message

        # Verify internal message is preserved
        assert "192.168.1.100" in result.internal_message
        assert "secret123" in result.internal_message

    def test_error_response_json_serialization(self):
        """Test that sanitized error can be JSON serialized."""
        import json

        exc = ValueError("Invalid: /home/user/secret.key")
        result = sanitize_exception(exc)

        # Should be JSON serializable
        json_str = result.to_json_string()
        parsed = json.loads(json_str)

        assert "error" in parsed
        assert "message" in parsed
        assert "/home/user/secret.key" not in parsed["message"]
