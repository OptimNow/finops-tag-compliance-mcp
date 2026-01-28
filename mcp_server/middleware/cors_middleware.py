# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""CORS middleware with violation logging for the MCP server.

This module provides a CORS middleware wrapper that logs requests from
non-allowed origins to the security service.

Requirements: 20.1, 20.2, 20.3, 23.3
"""

import logging
from datetime import datetime

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..services.security_service import get_security_service
from ..utils.cloudwatch_logger import emit_cors_violation_metric
from ..utils.correlation import get_correlation_id

logger = logging.getLogger(__name__)


class CORSLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs CORS violations to the security service.

    This middleware runs before the actual CORS middleware and logs
    requests from non-allowed origins. It doesn't enforce CORS itself -
    that's handled by Starlette's CORSMiddleware.

    Requirements: 20.3, 23.3
    """

    def __init__(
        self,
        app,
        allowed_origins: list[str],
        enabled: bool = True,
    ):
        """
        Initialize the CORS logging middleware.

        Args:
            app: The FastAPI application
            allowed_origins: List of allowed origins (empty list = block all)
            enabled: Whether logging is enabled
        """
        super().__init__(app)
        self.allowed_origins = set(allowed_origins)
        self.allow_all = "*" in allowed_origins
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and log CORS violations.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response

        Requirements: 20.3, 23.3
        """
        if not self.enabled:
            return await call_next(request)

        # Get the Origin header
        origin = request.headers.get("Origin")

        # If no Origin header, this is not a CORS request
        if not origin:
            return await call_next(request)

        # Check if origin is allowed
        is_allowed = self._is_origin_allowed(origin)

        if not is_allowed:
            await self._log_cors_violation(request, origin)

        # Continue with request (actual CORS enforcement is done by CORSMiddleware)
        return await call_next(request)

    def _is_origin_allowed(self, origin: str) -> bool:
        """
        Check if an origin is allowed.

        Args:
            origin: The Origin header value

        Returns:
            True if allowed, False otherwise
        """
        if self.allow_all:
            return True

        if not self.allowed_origins:
            return False

        return origin in self.allowed_origins

    async def _log_cors_violation(self, request: Request, origin: str) -> None:
        """
        Log a CORS violation to the security service.

        Args:
            request: The HTTP request
            origin: The non-allowed origin

        Requirements: 23.3
        """
        correlation_id = get_correlation_id()
        client_ip = request.client.host if request.client else "unknown"
        timestamp = datetime.utcnow().isoformat()

        # Log to application logger
        logger.warning(
            f"CORS violation: request from non-allowed origin",
            extra={
                "correlation_id": correlation_id,
                "origin": origin,
                "client_ip": client_ip,
                "method": request.method,
                "path": str(request.url.path),
                "timestamp": timestamp,
            },
        )

        # Log to security service if available
        security_service = get_security_service()
        if security_service:
            await security_service.log_security_event(
                event_type="cors_violation",
                severity="medium",
                message=f"Request from non-allowed origin: {origin}",
                details={
                    "origin": origin,
                    "client_ip": client_ip,
                    "method": request.method,
                    "path": str(request.url.path),
                    "timestamp": timestamp,
                    "allowed_origins": list(self.allowed_origins) if not self.allow_all else ["*"],
                },
                session_id=correlation_id,
            )

        # Emit CloudWatch metric for alerting (Requirement 23.5)
        emit_cors_violation_metric(origin=origin, path=str(request.url.path))


def get_cors_config(allowed_origins: list[str]) -> dict:
    """
    Build CORS configuration from allowed origins.

    Args:
        allowed_origins: List of allowed origins

    Returns:
        Dictionary of CORS configuration

    Requirements: 20.1, 20.2, 20.4, 20.5, 20.6
    """
    is_wildcard = "*" in allowed_origins or allowed_origins == ["*"]

    return {
        "allow_origins": allowed_origins,
        "allow_credentials": False,
        # Requirement 20.5: Restrict methods to POST only for MCP tool calls
        "allow_methods": ["GET", "POST"] if is_wildcard else ["POST", "OPTIONS"],
        # Requirement 20.6: Restrict headers
        "allow_headers": (
            ["*"]
            if is_wildcard
            else ["Content-Type", "Authorization", "X-Correlation-ID"]
        ),
    }


def parse_cors_origins(origins_str: str) -> list[str]:
    """
    Parse a comma-separated string of CORS origins.

    Args:
        origins_str: Comma-separated list of origins or "*"

    Returns:
        List of origins (empty list if none configured)

    Requirements: 20.4
    """
    if not origins_str:
        return []

    # Handle wildcard
    if origins_str.strip() == "*":
        return ["*"]

    # Parse comma-separated list
    origins = [o.strip() for o in origins_str.split(",") if o.strip()]
    return origins
