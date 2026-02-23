# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""HTTP middleware for correlation ID propagation.

Extracts the CorrelationIDMiddleware that was previously in
``mcp_server.utils.correlation`` — this class depends on FastAPI/Starlette
and belongs in the middleware (HTTP-only) layer.

Requirements: 15.1
"""

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..utils.correlation import generate_correlation_id, set_correlation_id

logger = logging.getLogger(__name__)


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
