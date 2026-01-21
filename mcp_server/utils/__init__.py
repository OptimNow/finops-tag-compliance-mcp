"""Utility modules for FinOps Tag Compliance MCP Server."""

from .cloudwatch_logger import CloudWatchHandler, configure_cloudwatch_logging
from .resource_utils import fetch_resources_by_type, extract_account_from_arn
from .correlation import (
    generate_correlation_id,
    set_correlation_id,
    get_correlation_id,
    get_correlation_id_for_logging,
    CorrelationIDMiddleware,
)
from .input_validation import InputValidator, ValidationError, SecurityViolationError
from .error_sanitization import (
    detect_sensitive_info,
    redact_sensitive_info,
    sanitize_exception,
    sanitize_error_response,
    create_safe_error_response,
    SanitizedError,
    handle_aws_error,
    handle_database_error,
    log_error_safely,
)

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
