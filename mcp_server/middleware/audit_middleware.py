# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Audit logging middleware for MCP tools."""

import functools
import time
from typing import Any, Callable, TypeVar, ParamSpec

from ..models.audit import AuditStatus
from ..services.audit_service import AuditService
from ..utils.correlation import get_correlation_id


# Type variables for generic decorator
P = ParamSpec("P")
R = TypeVar("R")


def audit_tool(tool_func: Callable[P, R]) -> Callable[P, R]:
    """
    Decorator to audit tool invocations.

    Logs every tool invocation with timestamp, tool name, parameters,
    result status, and errors if any.

    Args:
        tool_func: The tool function to wrap

    Returns:
        Wrapped function that logs invocations
    """

    @functools.wraps(tool_func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        audit_service = AuditService()
        tool_name = tool_func.__name__
        start_time = time.time()

        # Capture parameters (combine args and kwargs)
        parameters = {
            "args": args,
            "kwargs": kwargs,
        }

        # Capture correlation ID from context
        correlation_id = get_correlation_id() or None

        try:
            # Execute the tool
            result = await tool_func(*args, **kwargs)

            # Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000

            # Log successful invocation
            audit_service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
                execution_time_ms=execution_time_ms,
                correlation_id=correlation_id,
            )

            return result

        except Exception as e:
            # Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000

            # Log failed invocation
            audit_service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.FAILURE,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
                correlation_id=correlation_id,
            )

            # Re-raise the exception
            raise

    return wrapper


def audit_tool_sync(tool_func: Callable[P, R]) -> Callable[P, R]:
    """
    Decorator to audit synchronous tool invocations.

    Logs every tool invocation with timestamp, tool name, parameters,
    result status, and errors if any.

    Args:
        tool_func: The synchronous tool function to wrap

    Returns:
        Wrapped function that logs invocations
    """

    @functools.wraps(tool_func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        audit_service = AuditService()
        tool_name = tool_func.__name__
        start_time = time.time()

        # Capture parameters (combine args and kwargs)
        parameters = {
            "args": args,
            "kwargs": kwargs,
        }

        # Capture correlation ID from context
        correlation_id = get_correlation_id() or None

        try:
            # Execute the tool
            result = tool_func(*args, **kwargs)

            # Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000

            # Log successful invocation
            audit_service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
                execution_time_ms=execution_time_ms,
                correlation_id=correlation_id,
            )

            return result

        except Exception as e:
            # Calculate execution time
            execution_time_ms = (time.time() - start_time) * 1000

            # Log failed invocation
            audit_service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.FAILURE,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
                correlation_id=correlation_id,
            )

            # Re-raise the exception
            raise

    return wrapper
