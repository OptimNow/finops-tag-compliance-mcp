# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Correlation ID generation and context management for request tracing.

This module provides utilities for generating unique correlation IDs
and managing them in request context for end-to-end tracing across
logs, audit records, and trace spans.

Requirements: 15.1
"""

import contextvars
import logging
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Context variable to store correlation ID per request
_correlation_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def generate_correlation_id() -> str:
    """
    Generate a unique correlation ID using UUID4.

    Returns:
        A unique correlation ID string in UUID4 format
    """
    return str(uuid.uuid4())


def set_correlation_id(correlation_id: str) -> None:
    """
    Set the correlation ID in the current context.

    Args:
        correlation_id: The correlation ID to set
    """
    _correlation_id_context.set(correlation_id)


def get_correlation_id() -> str:
    """
    Get the correlation ID from the current context.

    Returns:
        The correlation ID if set, or an empty string if not set
    """
    return _correlation_id_context.get()


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that generates and manages correlation IDs.

    This middleware:
    1. Checks for an existing correlation ID in request headers
    2. Generates a new one if not present
    3. Sets it in the request context for use throughout the request
    4. Adds it to the response headers for client tracking

    Requirements: 15.1
    """

    CORRELATION_ID_HEADER = "X-Correlation-ID"

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        """
        Process the request and add correlation ID tracking.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware/handler in the chain

        Returns:
            The response with correlation ID in headers
        """
        # Check if correlation ID is already in request headers
        correlation_id = request.headers.get(self.CORRELATION_ID_HEADER, None)

        # Generate new correlation ID if not present
        if not correlation_id:
            correlation_id = generate_correlation_id()

        # Set correlation ID in context for this request
        set_correlation_id(correlation_id)

        # Log the correlation ID for this request
        logger.debug(
            f"Request started with correlation ID: {correlation_id}",
            extra={"correlation_id": correlation_id},
        )

        # Process the request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers[self.CORRELATION_ID_HEADER] = correlation_id

        # Log the correlation ID for response
        logger.debug(
            f"Request completed with correlation ID: {correlation_id}",
            extra={"correlation_id": correlation_id},
        )

        return response


def get_correlation_id_for_logging() -> dict:
    """
    Get correlation ID as a dictionary for use in logging extra fields.

    This is useful for structured logging where you want to include
    the correlation ID in log records.

    Returns:
        Dictionary with correlation_id key, or empty dict if not set
    """
    correlation_id = get_correlation_id()
    if correlation_id:
        return {"correlation_id": correlation_id}
    return {}
