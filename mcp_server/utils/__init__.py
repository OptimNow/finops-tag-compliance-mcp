"""Utility modules for FinOps Tag Compliance MCP Server."""

from .cloudwatch_logger import CloudWatchHandler, configure_cloudwatch_logging
from .correlation import (
    CorrelationIDMiddleware,
    generate_correlation_id,
    get_correlation_id,
    get_correlation_id_for_logging,
    set_correlation_id,
)
from .error_sanitization import (
    SanitizedError,
    create_safe_error_response,
    detect_sensitive_info,
    handle_aws_error,
    handle_database_error,
    log_error_safely,
    redact_sensitive_info,
    sanitize_error_response,
    sanitize_exception,
)
from .input_validation import InputValidator, SecurityViolationError, ValidationError
from .resource_utils import extract_account_from_arn, fetch_resources_by_type

__all__ = [
    "CloudWatchHandler",
    "configure_cloudwatch_logging",
    "fetch_resources_by_type",
    "extract_account_from_arn",
    "generate_correlation_id",
    "set_correlation_id",
    "get_correlation_id",
    "get_correlation_id_for_logging",
    "CorrelationIDMiddleware",
    "InputValidator",
    "ValidationError",
    "SecurityViolationError",
    "detect_sensitive_info",
    "redact_sensitive_info",
    "sanitize_exception",
    "sanitize_error_response",
    "create_safe_error_response",
    "SanitizedError",
    "handle_aws_error",
    "handle_database_error",
    "log_error_safely",
]
