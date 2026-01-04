# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Request sanitization middleware for the MCP server.

This module provides middleware for sanitizing and validating incoming requests
to prevent security vulnerabilities like header injection, oversized requests,
and malicious input.

Requirements: 16.2, 16.5
"""

import logging
import re
from typing import Optional
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers

from ..services.security_service import get_security_service
from ..utils.correlation import get_correlation_id

logger = logging.getLogger(__name__)

# Security patterns for detecting malicious input
SUSPICIOUS_PATTERNS = [
    # SQL injection patterns
    r"(\bUNION\b.*\bSELECT\b)",
    r"(\bDROP\b.*\bTABLE\b)",
    r"(\bINSERT\b.*\bINTO\b)",
    r"(\bDELETE\b.*\bFROM\b)",
    r"(\bUPDATE\b.*\bSET\b)",
    # Command injection patterns
    r"[;&|`$]",
    r"(\.\./)+",  # Path traversal
    # Script injection patterns
    r"<script[^>]*>",
    r"javascript:",
    r"onerror\s*=",
    r"onload\s*=",
    # Header injection patterns (CRLF)
    r"[\r\n]",
]

# Compile patterns for performance
COMPILED_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in SUSPICIOUS_PATTERNS]

# Dangerous header names that should not be accepted from clients
DANGEROUS_HEADERS = {
    "x-forwarded-host",
    "x-forwarded-server",
    "x-original-url",
    "x-rewrite-url",
}

# Maximum sizes
MAX_REQUEST_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_HEADER_SIZE_BYTES = 8 * 1024  # 8 KB
MAX_HEADER_COUNT = 50
MAX_QUERY_STRING_LENGTH = 4096
MAX_PATH_LENGTH = 2048


class RequestSanitizationError(Exception):
    """Raised when request sanitization fails."""
    pass


def sanitize_string(value: str, field_name: str = "input") -> str:
    """
    Sanitize a string value by checking for suspicious patterns.
    
    Args:
        value: String value to sanitize
        field_name: Name of the field being sanitized (for logging)
    
    Returns:
        The original value if safe
    
    Raises:
        RequestSanitizationError: If suspicious patterns are detected
    
    Requirements: 16.2, 16.5
    """
    if not value:
        return value
    
    # Check for suspicious patterns
    for pattern in COMPILED_PATTERNS:
        if pattern.search(value):
            raise RequestSanitizationError(
                f"Suspicious pattern detected in {field_name}"
            )
    
    return value


def validate_headers(headers: Headers) -> None:
    """
    Validate request headers for security issues.
    
    Checks for:
    - Header injection (CRLF characters)
    - Dangerous header names
    - Excessive header count
    - Oversized headers
    
    Args:
        headers: Request headers to validate
    
    Raises:
        RequestSanitizationError: If headers fail validation
    
    Requirements: 16.2, 16.5
    """
    # Check header count
    if len(headers) > MAX_HEADER_COUNT:
        raise RequestSanitizationError(
            f"Too many headers: {len(headers)} (max: {MAX_HEADER_COUNT})"
        )
    
    # Calculate total header size
    total_size = sum(len(k) + len(v) for k, v in headers.items())
    if total_size > MAX_HEADER_SIZE_BYTES:
        raise RequestSanitizationError(
            f"Headers too large: {total_size} bytes (max: {MAX_HEADER_SIZE_BYTES})"
        )
    
    # Check each header
    for name, value in headers.items():
        name_lower = name.lower()
        
        # Check for dangerous headers
        if name_lower in DANGEROUS_HEADERS:
            raise RequestSanitizationError(
                f"Dangerous header not allowed: {name}"
            )
        
        # Check for CRLF injection in header values
        if "\r" in value or "\n" in value:
            raise RequestSanitizationError(
                f"Header injection detected in {name}"
            )
        
        # Check for null bytes
        if "\x00" in name or "\x00" in value:
            raise RequestSanitizationError(
                f"Null byte detected in header {name}"
            )


def validate_request_size(content_length: Optional[int]) -> None:
    """
    Validate request body size.
    
    Args:
        content_length: Content-Length header value
    
    Raises:
        RequestSanitizationError: If request is too large
    
    Requirements: 16.2
    """
    if content_length is not None and content_length > MAX_REQUEST_SIZE_BYTES:
        raise RequestSanitizationError(
            f"Request too large: {content_length} bytes (max: {MAX_REQUEST_SIZE_BYTES})"
        )


def validate_url(url: str) -> None:
    """
    Validate request URL for security issues.
    
    Args:
        url: Request URL to validate
    
    Raises:
        RequestSanitizationError: If URL fails validation
    
    Requirements: 16.2, 16.5
    """
    # Check for path traversal attempts first (security critical)
    if "../" in url or "..\\" in url:
        raise RequestSanitizationError(
            "Path traversal attempt detected in URL"
        )
    
    # Check for null bytes
    if "\x00" in url:
        raise RequestSanitizationError(
            "Null byte detected in URL"
        )
    
    # Check query string length if present (before path length to be more specific)
    if "?" in url:
        query_string = url.split("?", 1)[1]
        if len(query_string) > MAX_QUERY_STRING_LENGTH:
            raise RequestSanitizationError(
                f"Query string too long: {len(query_string)} (max: {MAX_QUERY_STRING_LENGTH})"
            )
    
    # Check path length
    if len(url) > MAX_PATH_LENGTH:
        raise RequestSanitizationError(
            f"URL path too long: {len(url)} (max: {MAX_PATH_LENGTH})"
        )


class RequestSanitizationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for sanitizing and validating incoming requests.
    
    This middleware performs security checks on all incoming requests:
    - Validates request headers
    - Enforces request size limits
    - Validates URL structure
    - Logs security violations
    
    Requirements: 16.2, 16.5
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Process incoming request with security validation.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain
        
        Returns:
            HTTP response
        
        Requirements: 16.2, 16.5
        """
        correlation_id = get_correlation_id()
        security_service = get_security_service()
        
        try:
            # Validate headers
            validate_headers(request.headers)
            
            # Validate request size
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    validate_request_size(int(content_length))
                except ValueError:
                    raise RequestSanitizationError(
                        "Invalid Content-Length header"
                    )
            
            # Validate URL
            validate_url(str(request.url.path))
            
            # Log successful validation
            logger.debug(
                f"Request sanitization passed for {request.method} {request.url.path}",
                extra={"correlation_id": correlation_id}
            )
            
            # Continue to next middleware/handler
            response = await call_next(request)
            return response
        
        except RequestSanitizationError as e:
            # Log security violation
            logger.warning(
                f"Request sanitization failed: {str(e)}",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": str(request.url.path),
                    "client_host": request.client.host if request.client else None,
                }
            )
            
            # Log to security service if available
            if security_service:
                await security_service.log_security_event(
                    event_type="request_sanitization_failure",
                    severity="high",
                    message=f"Request sanitization failed: {str(e)}",
                    details={
                        "method": request.method,
                        "path": str(request.url.path),
                        "client_host": request.client.host if request.client else None,
                        "error": str(e),
                    },
                    session_id=correlation_id,
                )
            
            # Return error response without exposing internal details
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Bad Request",
                    "message": "Request validation failed",
                },
            )
        
        except Exception as e:
            # Log unexpected errors
            logger.error(
                f"Unexpected error in request sanitization: {str(e)}",
                exc_info=True,
                extra={"correlation_id": correlation_id}
            )
            
            # Return generic error without exposing details
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": "An error occurred processing your request",
                },
            )


def sanitize_json_value(value, field_path: str = "root") -> any:
    """
    Recursively sanitize JSON values.
    
    Args:
        value: Value to sanitize (can be dict, list, str, etc.)
        field_path: Path to current field (for error messages)
    
    Returns:
        Sanitized value
    
    Raises:
        RequestSanitizationError: If suspicious patterns are detected
    
    Requirements: 16.2, 16.5
    """
    if isinstance(value, str):
        return sanitize_string(value, field_path)
    elif isinstance(value, dict):
        return {
            k: sanitize_json_value(v, f"{field_path}.{k}")
            for k, v in value.items()
        }
    elif isinstance(value, list):
        return [
            sanitize_json_value(item, f"{field_path}[{i}]")
            for i, item in enumerate(value)
        ]
    else:
        # Numbers, booleans, None are safe
        return value


# Configuration for request size limits
class RequestSizeLimits:
    """Configuration for request size limits."""
    
    MAX_REQUEST_SIZE_BYTES = MAX_REQUEST_SIZE_BYTES
    MAX_HEADER_SIZE_BYTES = MAX_HEADER_SIZE_BYTES
    MAX_HEADER_COUNT = MAX_HEADER_COUNT
    MAX_QUERY_STRING_LENGTH = MAX_QUERY_STRING_LENGTH
    MAX_PATH_LENGTH = MAX_PATH_LENGTH
    
    @classmethod
    def from_env(cls):
        """Load limits from environment variables."""
        import os
        
        cls.MAX_REQUEST_SIZE_BYTES = int(
            os.getenv("MAX_REQUEST_SIZE_BYTES", MAX_REQUEST_SIZE_BYTES)
        )
        cls.MAX_HEADER_SIZE_BYTES = int(
            os.getenv("MAX_HEADER_SIZE_BYTES", MAX_HEADER_SIZE_BYTES)
        )
        cls.MAX_HEADER_COUNT = int(
            os.getenv("MAX_HEADER_COUNT", MAX_HEADER_COUNT)
        )
        cls.MAX_QUERY_STRING_LENGTH = int(
            os.getenv("MAX_QUERY_STRING_LENGTH", MAX_QUERY_STRING_LENGTH)
        )
        cls.MAX_PATH_LENGTH = int(
            os.getenv("MAX_PATH_LENGTH", MAX_PATH_LENGTH)
        )
