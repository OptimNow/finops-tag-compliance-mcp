# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""API Key authentication middleware for the MCP server.

This module provides middleware for validating Bearer tokens in the
Authorization header against a configured list of valid API keys.

Requirements: 19.1, 19.2, 19.3, 19.5, 19.7
"""

import hashlib
import logging
from datetime import datetime

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..clients.cache import RedisCache
from ..services.security_service import get_security_service
from ..utils.cloudwatch_logger import emit_auth_failure_metric
from ..utils.correlation import get_correlation_id

logger = logging.getLogger(__name__)

# Endpoints that bypass authentication
PUBLIC_ENDPOINTS = {
    "/health",
    "/",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for safe logging.

    We never log the full API key, only a hash for correlation.

    Args:
        api_key: The API key to hash

    Returns:
        First 8 characters of SHA256 hash
    """
    return hashlib.sha256(api_key.encode()).hexdigest()[:8]


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware for validating Bearer tokens in Authorization header.

    This middleware:
    - Extracts the Authorization header from incoming requests
    - Validates the format: "Bearer <api_key>"
    - Checks the api_key against a configured list of valid keys
    - Returns 401 Unauthorized with WWW-Authenticate header on failure
    - Skips authentication for public endpoints (e.g., /health)

    Requirements: 19.1, 19.2, 19.3, 19.5, 19.7
    """

    def __init__(
        self,
        app,
        api_keys: set[str],
        redis_cache: RedisCache | None = None,
        enabled: bool = True,
        realm: str = "mcp-server",
        resource_metadata_url: str | None = None,
    ):
        """
        Initialize the authentication middleware.

        Args:
            app: The FastAPI application
            api_keys: Set of valid API keys
            redis_cache: Optional Redis cache for dynamic key loading
            enabled: Whether authentication is enabled (default: True)
            realm: The authentication realm for WWW-Authenticate header
            resource_metadata_url: URL to resource metadata (for WWW-Authenticate)
        """
        super().__init__(app)
        self.api_keys = api_keys
        self.redis_cache = redis_cache
        self.enabled = enabled
        self.realm = realm
        self.resource_metadata_url = resource_metadata_url

        # Redis key for dynamic API keys
        self._redis_api_keys_key = "auth:api_keys"

    async def dispatch(self, request: Request, call_next):
        """
        Process incoming request with authentication validation.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response

        Requirements: 19.1, 19.2, 19.3, 19.5, 19.7
        """
        correlation_id = get_correlation_id()

        # Skip authentication if disabled
        if not self.enabled:
            return await call_next(request)

        # Skip authentication for public endpoints
        path = request.url.path.rstrip("/")
        if path in PUBLIC_ENDPOINTS or path == "":
            return await call_next(request)

        # Extract and validate Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            await self._log_auth_failure(
                request,
                correlation_id,
                "missing_header",
                "No Authorization header provided",
            )
            return self._unauthorized_response("missing_token")

        # Validate Bearer token format
        if not auth_header.startswith("Bearer "):
            await self._log_auth_failure(
                request,
                correlation_id,
                "invalid_format",
                "Authorization header must use Bearer scheme",
            )
            return self._unauthorized_response("invalid_request")

        # Extract the API key
        api_key = auth_header[7:]  # Remove "Bearer " prefix

        if not api_key:
            await self._log_auth_failure(
                request,
                correlation_id,
                "empty_token",
                "Bearer token is empty",
            )
            return self._unauthorized_response("invalid_token")

        # Validate the API key
        if not await self._validate_key(api_key):
            await self._log_auth_failure(
                request,
                correlation_id,
                "invalid_key",
                f"Invalid API key (hash: {hash_api_key(api_key)})",
            )
            return self._unauthorized_response("invalid_token")

        # Authentication successful
        logger.debug(
            f"Authentication successful for {request.method} {request.url.path}",
            extra={"correlation_id": correlation_id},
        )

        return await call_next(request)

    async def _validate_key(self, api_key: str) -> bool:
        """
        Validate an API key against configured keys.

        Checks in-memory keys first, then falls back to Redis for
        dynamically loaded keys.

        Args:
            api_key: The API key to validate

        Returns:
            True if the key is valid, False otherwise

        Requirements: 19.2, 19.6
        """
        # Check in-memory keys first
        if api_key in self.api_keys:
            return True

        # Check Redis for dynamically loaded keys
        if self.redis_cache:
            try:
                redis_keys = await self.redis_cache.smembers(self._redis_api_keys_key)
                if redis_keys and api_key in redis_keys:
                    return True
            except Exception as e:
                logger.warning(f"Failed to check Redis for API keys: {e}")

        return False

    async def _log_auth_failure(
        self,
        request: Request,
        correlation_id: str,
        failure_type: str,
        message: str,
    ) -> None:
        """
        Log an authentication failure.

        Logs to both the application logger and the security service.

        Args:
            request: The HTTP request
            correlation_id: Request correlation ID
            failure_type: Type of authentication failure
            message: Failure message

        Requirements: 19.5, 23.1
        """
        client_ip = request.client.host if request.client else "unknown"
        timestamp = datetime.utcnow().isoformat()

        # Log to application logger
        logger.warning(
            f"Authentication failure: {failure_type}",
            extra={
                "correlation_id": correlation_id,
                "client_ip": client_ip,
                "timestamp": timestamp,
                "method": request.method,
                "path": str(request.url.path),
                "failure_type": failure_type,
            },
        )

        # Log to security service if available
        security_service = get_security_service()
        if security_service:
            await security_service.log_security_event(
                event_type="authentication_failure",
                severity="medium",
                message=message,
                details={
                    "failure_type": failure_type,
                    "client_ip": client_ip,
                    "method": request.method,
                    "path": str(request.url.path),
                    "timestamp": timestamp,
                },
                session_id=correlation_id,
            )

        # Emit CloudWatch metric for alerting (Requirement 23.2)
        emit_auth_failure_metric(failure_type=failure_type, client_ip=client_ip)

    def _unauthorized_response(self, error_code: str) -> JSONResponse:
        """
        Build a 401 Unauthorized response with proper headers.

        Per RFC 6750, the response includes:
        - WWW-Authenticate header with Bearer scheme
        - Error code in the WWW-Authenticate header
        - JSON body with error details

        Args:
            error_code: OAuth 2.0 error code (invalid_token, invalid_request, etc.)

        Returns:
            JSONResponse with 401 status

        Requirements: 19.3, 19.7
        """
        # Build WWW-Authenticate header per RFC 6750
        www_auth_parts = [f'Bearer realm="{self.realm}"']

        if self.resource_metadata_url:
            www_auth_parts.append(f'resource_metadata="{self.resource_metadata_url}"')

        www_auth_parts.append(f'error="{error_code}"')

        # Map error codes to descriptions
        error_descriptions = {
            "missing_token": "No access token provided",
            "invalid_token": "The access token is invalid or expired",
            "invalid_request": "The request is missing a required parameter",
            "insufficient_scope": "The access token has insufficient scope",
        }
        description = error_descriptions.get(error_code, "Authentication failed")
        www_auth_parts.append(f'error_description="{description}"')

        www_authenticate = ", ".join(www_auth_parts)

        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": description,
                "error_code": error_code,
            },
            headers={"WWW-Authenticate": www_authenticate},
        )


def parse_api_keys(api_keys_str: str) -> set[str]:
    """
    Parse a comma-separated string of API keys.

    Args:
        api_keys_str: Comma-separated list of API keys

    Returns:
        Set of API keys (empty strings filtered out)
    """
    if not api_keys_str:
        return set()

    keys = [k.strip() for k in api_keys_str.split(",")]
    return {k for k in keys if k}
