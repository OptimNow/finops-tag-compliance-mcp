# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Correlation ID generation and context management for request tracing.

This module provides utilities for generating unique correlation IDs
and managing them in request context for end-to-end tracing across
logs, audit records, and trace spans.

No HTTP dependencies — the HTTP middleware (CorrelationIDMiddleware) has
been extracted to ``mcp_server.middleware.correlation_middleware``.

Requirements: 15.1
"""

import contextvars
import logging
import uuid

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
