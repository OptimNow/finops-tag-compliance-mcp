# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Error message sanitization utility for the MCP server.

This module provides utilities for sanitizing error messages to prevent
exposure of sensitive information like internal paths, credentials, and
stack traces.

Requirements: 16.5
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Patterns for detecting sensitive information in error messages
SENSITIVE_PATTERNS = {
    # File paths (absolute and relative)
    "file_path": [
        r"[/\\](?:home|root|var|etc|opt|srv|usr|tmp)[/\\][\w\-./\\]+",
        r"[A-Za-z]:\\[\w\-./\\]+",  # Windows paths
        r"/[\w\-./]+\.py",  # Python files
        r"/[\w\-./]+\.json",  # JSON files
        r"/[\w\-./]+\.yaml",  # YAML files
    ],
    # AWS credentials and keys
    "credentials": [
        r"AKIA[0-9A-Z]{16}",  # AWS Access Key ID
        r"(?i)aws_secret_access_key['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}",
        r"(?i)password['\"]?\s*[:=]\s*['\"]?[^\s'\"]+",
        r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"]?[^\s'\"]+",
        r"(?i)token['\"]?\s*[:=]\s*['\"]?[^\s'\"]+",
        r"(?i)secret['\"]?\s*[:=]\s*['\"]?[^\s'\"]+",
    ],
    # Database connection strings
    "connection_string": [
        r"(?i)(?:mysql|postgres|mongodb|redis)://[^\s]+",
        r"(?i)(?:user|username)['\"]?\s*[:=]\s*['\"]?[^\s'\"]+",
        r"(?i)(?:host|server)['\"]?\s*[:=]\s*[^\s'\"]+",
    ],
    # Email addresses
    "email": [
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    ],
    # IP addresses (internal networks)
    "internal_ip": [
        r"(?:10|172\.(?:1[6-9]|2[0-9]|3[01])|192\.168)\.\d{1,3}\.\d{1,3}",
        r"127\.0\.0\.1",
        r"localhost",
    ],
    # Stack traces and internal details
    "stack_trace": [
        r"(?i)traceback|File \"[^\"]+\", line \d+",
        r"(?i)at [\w.]+\(\)",
    ],
    # Docker/container paths
    "container_path": [
        r"/app/[\w\-./]+",
        r"/src/[\w\-./]+",
        r"/workspace/[\w\-./]+",
    ],
}

# Compile patterns for performance
COMPILED_PATTERNS = {
    category: [re.compile(pattern) for pattern in patterns]
    for category, patterns in SENSITIVE_PATTERNS.items()
}


class SanitizedError:
    """Represents a sanitized error message with metadata."""

    def __init__(
        self,
        user_message: str,
        internal_message: str | None = None,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """
        Initialize a sanitized error.

        Args:
            user_message: Safe message to show to users
            internal_message: Full error message for internal logging
            error_code: Machine-readable error code
            details: Additional safe details to include
        """
        self.user_message = user_message
        self.internal_message = internal_message
        self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        result = {
            "error": self.error_code or "internal_error",
            "message": self.user_message,
        }
        if self.details:
            result["details"] = self.details
        return result

    def to_json_string(self) -> str:
        """Convert to JSON string."""
        import json

        return json.dumps(self.to_dict())


def detect_sensitive_info(text: str) -> dict[str, list]:
    """
    Detect sensitive information in text.

    Args:
        text: Text to scan for sensitive information

    Returns:
        Dictionary mapping sensitivity categories to found patterns

    Requirements: 16.5
    """
    if not text:
        return {}

    found = {}

    for category, patterns in COMPILED_PATTERNS.items():
        matches = []
        for pattern in patterns:
            for match in pattern.finditer(text):
                matches.append(
                    {
                        "pattern": pattern.pattern,
                        "match": match.group(0),
                        "position": match.start(),
                    }
                )

        if matches:
            found[category] = matches

    return found


def redact_sensitive_info(text: str, replacement: str = "[REDACTED]") -> str:
    """
    Redact sensitive information from text.

    Args:
        text: Text to redact
        replacement: String to use for redacted content

    Returns:
        Text with sensitive information redacted

    Requirements: 16.5
    """
    if not text:
        return text

    result = text

    for category, patterns in COMPILED_PATTERNS.items():
        for pattern in patterns:
            result = pattern.sub(replacement, result)

    return result


def sanitize_exception(
    exc: Exception,
    include_type: bool = True,
    include_message: bool = True,
) -> SanitizedError:
    """
    Sanitize an exception into a user-safe error message.

    Args:
        exc: Exception to sanitize
        include_type: Whether to include exception type in message
        include_message: Whether to include exception message

    Returns:
        SanitizedError with sanitized message

    Requirements: 16.5
    """
    exc_type = type(exc).__name__
    exc_message = str(exc)

    # Log the full exception internally
    logger.debug(
        f"Sanitizing exception: {exc_type}: {exc_message}",
        exc_info=True,
    )

    # Detect sensitive information
    sensitive_info = detect_sensitive_info(exc_message)

    if sensitive_info:
        logger.warning(
            f"Sensitive information detected in exception message: {list(sensitive_info.keys())}",
            extra={"sensitive_categories": list(sensitive_info.keys())},
        )

    # Redact sensitive information
    safe_message = redact_sensitive_info(exc_message)

    # Map exception types to user-friendly messages
    error_code = _get_error_code(exc)
    user_message = _get_user_message(exc, error_code, safe_message)

    return SanitizedError(
        user_message=user_message,
        internal_message=exc_message,
        error_code=error_code,
    )


def sanitize_error_response(
    error: Any,
    status_code: int = 500,
) -> dict[str, Any]:
    """
    Sanitize an error into a safe response dictionary.

    Args:
        error: Error to sanitize (Exception, string, or dict)
        status_code: HTTP status code

    Returns:
        Safe error response dictionary

    Requirements: 16.5
    """
    if isinstance(error, Exception):
        sanitized = sanitize_exception(error)
        return {
            "error": sanitized.error_code,
            "message": sanitized.user_message,
            "status_code": status_code,
        }
    elif isinstance(error, str):
        # Redact any sensitive info from string errors
        safe_message = redact_sensitive_info(error)
        return {
            "error": "error",
            "message": safe_message,
            "status_code": status_code,
        }
    elif isinstance(error, dict):
        # Redact sensitive info from dict errors
        safe_error = {}
        for key, value in error.items():
            if isinstance(value, str):
                safe_error[key] = redact_sensitive_info(value)
            else:
                safe_error[key] = value
        safe_error["status_code"] = status_code
        return safe_error
    else:
        # Unknown error type
        return {
            "error": "internal_error",
            "message": "An unexpected error occurred",
            "status_code": status_code,
        }


def _get_error_code(exc: Exception) -> str:
    """
    Map exception type to error code.

    Args:
        exc: Exception to map

    Returns:
        Error code string
    """
    exc_type = type(exc).__name__

    # Map common exceptions to error codes
    error_code_map = {
        "ValueError": "invalid_input",
        "TypeError": "invalid_type",
        "KeyError": "not_found",
        "FileNotFoundError": "not_found",
        "PermissionError": "permission_denied",
        "TimeoutError": "timeout",
        "ConnectionError": "connection_error",
        "RuntimeError": "runtime_error",
        "NotImplementedError": "not_implemented",
        "ValidationError": "validation_error",
        "SecurityViolationError": "security_violation",
        "BudgetExhaustedError": "budget_exceeded",
        "LoopDetectedError": "loop_detected",
    }

    return error_code_map.get(exc_type, "internal_error")


def _get_user_message(
    exc: Exception,
    error_code: str,
    safe_message: str,
) -> str:
    """
    Generate a user-friendly error message.

    Args:
        exc: Original exception
        error_code: Error code
        safe_message: Sanitized exception message

    Returns:
        User-friendly message
    """
    # Map error codes to user-friendly messages
    message_map = {
        "invalid_input": "The provided input is invalid. Please check your parameters and try again.",
        "invalid_type": "The provided value has an invalid type. Please check the parameter type.",
        "not_found": "The requested resource was not found.",
        "permission_denied": "You do not have permission to perform this action.",
        "timeout": "The request took too long to complete. Please try again.",
        "connection_error": "Failed to connect to a required service. Please try again later.",
        "runtime_error": "An error occurred while processing your request.",
        "not_implemented": "This feature is not yet implemented.",
        "validation_error": "The provided data failed validation. Please check your input.",
        "security_violation": "Your request was rejected due to a security policy violation.",
        "budget_exceeded": "The tool call budget for this session has been exceeded.",
        "loop_detected": "A repeated tool call pattern was detected. Please try a different approach.",
        "internal_error": "An unexpected error occurred. Please try again later.",
    }

    # Return mapped message or safe message
    return message_map.get(error_code, safe_message or "An error occurred")


def create_safe_error_response(
    error_code: str,
    user_message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a safe error response with guaranteed no sensitive info.

    Args:
        error_code: Machine-readable error code
        user_message: User-friendly message (should already be safe)
        details: Additional safe details

    Returns:
        Safe error response dictionary

    Requirements: 16.5
    """
    # Double-check that user_message doesn't contain sensitive info
    if detect_sensitive_info(user_message):
        logger.warning(
            "User message contains sensitive information, redacting",
            extra={"error_code": error_code},
        )
        user_message = redact_sensitive_info(user_message)

    response = {
        "error": error_code,
        "message": user_message,
    }

    if details:
        # Redact any sensitive info from details
        safe_details = {}
        for key, value in details.items():
            if isinstance(value, str):
                safe_details[key] = redact_sensitive_info(value)
            else:
                safe_details[key] = value
        response["details"] = safe_details

    return response


def log_error_safely(
    error: Exception,
    context: dict[str, Any] | None = None,
    logger_instance: logging.Logger | None = None,
) -> None:
    """
    Log an error with full details internally while sanitizing for external use.

    Args:
        error: Exception to log
        context: Additional context to log
        logger_instance: Logger to use (defaults to module logger)

    Requirements: 16.5
    """
    if logger_instance is None:
        logger_instance = logger

    # Log full error internally
    logger_instance.error(
        f"Error occurred: {type(error).__name__}: {str(error)}",
        exc_info=True,
        extra=context or {},
    )


# Utility function for common error scenarios


def handle_aws_error(exc: Exception) -> SanitizedError:
    """
    Handle AWS-specific errors with appropriate sanitization.

    Args:
        exc: AWS exception

    Returns:
        SanitizedError with appropriate message

    Requirements: 16.5
    """
    exc_message = str(exc)

    # Detect AWS-specific error patterns
    if (
        "AccessDenied" in exc_message
        or "UnauthorizedOperation" in exc_message
        or "not authorized" in exc_message.lower()
    ):
        return SanitizedError(
            user_message="You do not have permission to access this AWS resource.",
            internal_message=exc_message,
            error_code="permission_denied",
        )
    elif "InvalidParameterValue" in exc_message:
        return SanitizedError(
            user_message="Invalid parameter provided to AWS API.",
            internal_message=exc_message,
            error_code="invalid_input",
        )
    elif "ThrottlingException" in exc_message or "RequestLimitExceeded" in exc_message:
        return SanitizedError(
            user_message="AWS API rate limit exceeded. Please try again later.",
            internal_message=exc_message,
            error_code="rate_limit",
        )
    elif "ServiceUnavailable" in exc_message:
        return SanitizedError(
            user_message="The AWS service is temporarily unavailable. Please try again later.",
            internal_message=exc_message,
            error_code="service_unavailable",
        )
    else:
        # Generic AWS error
        return SanitizedError(
            user_message="An error occurred while accessing AWS resources.",
            internal_message=exc_message,
            error_code="aws_error",
        )


def handle_database_error(exc: Exception) -> SanitizedError:
    """
    Handle database-specific errors with appropriate sanitization.

    Args:
        exc: Database exception

    Returns:
        SanitizedError with appropriate message

    Requirements: 16.5
    """
    exc_message = str(exc)

    # Detect database-specific error patterns
    if "UNIQUE constraint failed" in exc_message or "duplicate key" in exc_message.lower():
        return SanitizedError(
            user_message="A record with this value already exists.",
            internal_message=exc_message,
            error_code="duplicate_entry",
        )
    elif "no such table" in exc_message.lower() or "table does not exist" in exc_message.lower():
        return SanitizedError(
            user_message="Database table not found.",
            internal_message=exc_message,
            error_code="not_found",
        )
    elif "database is locked" in exc_message.lower():
        return SanitizedError(
            user_message="Database is temporarily locked. Please try again.",
            internal_message=exc_message,
            error_code="database_locked",
        )
    else:
        # Generic database error
        return SanitizedError(
            user_message="A database error occurred.",
            internal_message=exc_message,
            error_code="database_error",
        )
