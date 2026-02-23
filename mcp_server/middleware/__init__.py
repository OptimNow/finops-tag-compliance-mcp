"""Middleware for MCP server."""

from .audit_middleware import audit_tool, audit_tool_sync
from .correlation_middleware import CorrelationIDMiddleware
from .auth_middleware import (
    APIKeyAuthMiddleware,
    AuthenticationError,
    hash_api_key,
    parse_api_keys,
)
from .budget_middleware import (
    DEFAULT_MAX_TOOL_CALLS_PER_SESSION,
    DEFAULT_SESSION_TTL_SECONDS,
    BudgetExhaustedError,
    BudgetTracker,
    check_and_consume_budget,
    get_budget_tracker,
    set_budget_tracker,
)
from .cors_middleware import (
    CORSLoggingMiddleware,
    get_cors_config,
    parse_cors_origins,
)
from .sanitization_middleware import (
    RequestSanitizationError,
    RequestSanitizationMiddleware,
    RequestSizeLimits,
    sanitize_json_value,
    sanitize_string,
    validate_headers,
    validate_request_size,
    validate_url,
)

__all__ = [
    "audit_tool",
    "audit_tool_sync",
    "CorrelationIDMiddleware",
    "APIKeyAuthMiddleware",
    "AuthenticationError",
    "hash_api_key",
    "parse_api_keys",
    "CORSLoggingMiddleware",
    "get_cors_config",
    "parse_cors_origins",
    "BudgetTracker",
    "BudgetExhaustedError",
    "get_budget_tracker",
    "set_budget_tracker",
    "check_and_consume_budget",
    "DEFAULT_MAX_TOOL_CALLS_PER_SESSION",
    "DEFAULT_SESSION_TTL_SECONDS",
    "RequestSanitizationMiddleware",
    "RequestSanitizationError",
    "sanitize_string",
    "sanitize_json_value",
    "validate_headers",
    "validate_request_size",
    "validate_url",
    "RequestSizeLimits",
]
