# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""FastAPI application entry point for FinOps Tag Compliance MCP Server.

This module creates the FastAPI application with MCP protocol support,
registers all 8 tools, configures CORS and middleware, and sets up
error handling.

Requirements: 14.2, 14.5
"""

import logging
from contextlib import asynccontextmanager
from datetime import timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from . import __version__
from .http_config import settings
from .container import ServiceContainer
from .mcp_handler import MCPHandler
from .middleware.budget_middleware import set_budget_tracker
from .models import HealthStatus
from .models.audit import AuditStatus
from .utils.cloudwatch_logger import CorrelationIDFilter, configure_cloudwatch_logging
from .middleware.correlation_middleware import CorrelationIDMiddleware
from .utils.correlation import get_correlation_id
from .utils.loop_detection import set_loop_detector
from .services.security_service import set_security_service

# Configure logging with correlation ID support
# Create a handler with correlation ID format
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s"
)
handler.setFormatter(formatter)

# Add correlation ID filter to the handler
correlation_filter = CorrelationIDFilter()
handler.addFilter(correlation_filter)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(handler)

logger = logging.getLogger(__name__)

# Configure CloudWatch logging if enabled
configure_cloudwatch_logging()

# Global container and MCP handler
_container: ServiceContainer | None = None
_mcp_handler: MCPHandler | None = None


# Request/Response models for MCP protocol
class MCPToolCallRequest(BaseModel):
    """Request model for MCP tool invocation."""

    name: str
    arguments: dict = {}


class MCPToolCallResponse(BaseModel):
    """Response model for MCP tool invocation."""

    content: list[dict]
    is_error: bool = False


class MCPListToolsResponse(BaseModel):
    """Response model for listing available tools."""

    tools: list[dict]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle - startup and shutdown.

    Uses ServiceContainer to initialize all services in dependency order.
    Also sets legacy global singletons for backwards compatibility with
    code that still uses get_budget_tracker() / get_loop_detector() /
    get_security_service().

    Requirements: 14.2
    """
    global _container, _mcp_handler

    # Startup
    logger.info("Starting FinOps Tag Compliance MCP Server")

    app_settings = settings()

    # Initialize all services via ServiceContainer
    _container = ServiceContainer(settings=app_settings)
    await _container.initialize()

    # Bridge: set legacy global singletons so that mcp_handler.py and
    # other code that still uses get_budget_tracker() etc. keeps working.
    if _container.budget_tracker:
        set_budget_tracker(_container.budget_tracker)
    if _container.loop_detector:
        set_loop_detector(_container.loop_detector)
    if _container.security_service:
        set_security_service(_container.security_service)

    # Initialize MCP handler with services from the container
    _mcp_handler = MCPHandler(
        aws_client=_container.aws_client,
        policy_service=_container.policy_service,
        compliance_service=_container.compliance_service,
        redis_cache=_container.redis_cache,
        audit_service=_container.audit_service,
        history_service=_container.history_service,
        multi_region_scanner=_container.multi_region_scanner,
    )
    logger.info("MCP handler initialized with 8 tools")

    logger.info(f"MCP Server v{__version__} started successfully on port {app_settings.port}")

    yield

    # Shutdown
    logger.info("Shutting down FinOps Tag Compliance MCP Server")
    await _container.shutdown()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="FinOps Tag Compliance MCP Server",
    description=(
        "AWS resource tagging validation and compliance checking via MCP. "
        "Exposes 8 tools for checking compliance, finding untagged resources, "
        "validating tags, analyzing cost attribution gaps, suggesting tags, "
        "retrieving policies, generating reports, and tracking history."
    ),
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware for cross-origin requests
# This allows AI assistants like Claude Desktop to communicate with the server
# Requirements: 20.1, 20.2, 20.4, 20.5, 20.6
def get_cors_origins() -> list[str]:
    """
    Get CORS allowed origins from settings.

    Returns a list of allowed origins. In production, this should be
    restricted to specific trusted domains.

    Requirements: 20.1, 20.4
    """
    app_settings = settings()
    origins_str = app_settings.cors_allowed_origins

    # Handle wildcard for development
    if origins_str == "*":
        return ["*"]

    # Parse comma-separated list
    origins = [o.strip() for o in origins_str.split(",") if o.strip()]

    # Default to empty list (block all) if not configured
    return origins if origins else []


cors_origins = get_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,  # Disabled - MCP doesn't use cookies/credentials
    allow_methods=["POST", "OPTIONS"] if cors_origins != ["*"] else ["GET", "POST"],  # Req 20.5
    allow_headers=["Content-Type", "Authorization", "X-Correlation-ID"] if cors_origins != ["*"] else ["*"],  # Req 20.6
)

# Add request sanitization middleware for security (Requirements: 16.2, 16.5)
# This validates headers, enforces size limits, and prevents injection attacks
from .middleware.sanitization_middleware import RequestSanitizationMiddleware

app.add_middleware(RequestSanitizationMiddleware)

# Add API key authentication middleware (Requirements: 19.1, 19.2, 19.3)
# This middleware validates Bearer tokens in Authorization header
# Authentication is disabled by default (AUTH_ENABLED=false)
from .middleware.auth_middleware import APIKeyAuthMiddleware, parse_api_keys

_auth_settings = settings()
if _auth_settings.auth_enabled:
    _api_keys = parse_api_keys(_auth_settings.api_keys)
    if _api_keys:
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_keys=_api_keys,
            enabled=True,
            realm=_auth_settings.auth_realm,
        )
        logger.info(f"API key authentication enabled with {len(_api_keys)} configured keys")
    else:
        logger.warning("AUTH_ENABLED=true but no API_KEYS configured - authentication disabled")

# Add CORS logging middleware for security monitoring (Requirements: 20.3, 23.3)
# This logs requests from non-allowed origins to the security service
from .middleware.cors_middleware import CORSLoggingMiddleware

if cors_origins != ["*"]:
    app.add_middleware(
        CORSLoggingMiddleware,
        allowed_origins=cors_origins,
        enabled=True,
    )
    logger.info(f"CORS logging enabled for {len(cors_origins)} allowed origins")

# Add correlation ID middleware for request tracing
# This must be added after CORS middleware so it wraps the request
app.add_middleware(CorrelationIDMiddleware)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors.

    Logs the full error internally and returns a sanitized error response
    that does not expose sensitive information like paths, credentials, or
    stack traces.

    Requirements: 16.5
    """
    from .utils.error_sanitization import log_error_safely, sanitize_exception

    # Log the full error internally with all details
    log_error_safely(
        exc,
        context={
            "path": str(request.url.path),
            "method": request.method,
            "correlation_id": get_correlation_id(),
        },
        logger_instance=logger,
    )

    # Sanitize the error for user response
    sanitized_error = sanitize_exception(exc)

    # Log to audit service if available
    if _container and _container.audit_service:
        _container.audit_service.log_invocation(
            tool_name="unknown",
            parameters={"path": str(request.url.path)},
            status=AuditStatus.FAILURE,
            error_message=sanitized_error.internal_message,
        )

    return JSONResponse(
        status_code=500,
        content={
            "error": sanitized_error.error_code,
            "message": sanitized_error.user_message,
        },
    )


@app.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """
    Health check endpoint for monitoring server status.

    Returns:
        HealthStatus with server status, version, connectivity, budget info, loop detection info, and security info

    Requirements: 13.1, 13.2, 15.3, 15.4, 16.4
    """
    from .models.health import BudgetHealthInfo, LoopDetectionHealthInfo, SecurityHealthInfo

    app_settings = settings()

    # Check Redis connectivity
    redis_connected = False
    if _container and _container.redis_cache:
        redis_connected = await _container.redis_cache.is_connected()

    # Check SQLite connectivity
    sqlite_connected = False
    if _container and _container.audit_service:
        try:
            import sqlite3

            conn = sqlite3.connect(_container.audit_service.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            sqlite_connected = True
        except Exception as e:
            logger.warning(f"SQLite connectivity check failed: {e}")
            sqlite_connected = False

    # Get budget tracking info (Requirement 15.3)
    budget_info = None
    budget_tracker = _container.budget_tracker if _container else None

    if budget_tracker:
        try:
            active_sessions = await budget_tracker.get_active_session_count()
            budget_info = BudgetHealthInfo(
                enabled=True,
                max_calls_per_session=budget_tracker.max_calls_per_session,
                session_ttl_seconds=budget_tracker.session_ttl_seconds,
                active_sessions=active_sessions,
            )
        except Exception as e:
            logger.warning(f"Failed to get budget tracking info: {e}")
            budget_info = BudgetHealthInfo(
                enabled=True,
                max_calls_per_session=app_settings.max_tool_calls_per_session,
                session_ttl_seconds=app_settings.session_budget_ttl_seconds,
                active_sessions=0,
            )
    elif app_settings.budget_tracking_enabled:
        budget_info = BudgetHealthInfo(
            enabled=True,
            max_calls_per_session=app_settings.max_tool_calls_per_session,
            session_ttl_seconds=app_settings.session_budget_ttl_seconds,
            active_sessions=0,
        )
    else:
        budget_info = BudgetHealthInfo(
            enabled=False,
            max_calls_per_session=0,
            session_ttl_seconds=0,
            active_sessions=0,
        )

    # Get loop detection info (Requirement 15.4)
    loop_detection_info = None
    loop_detector = _container.loop_detector if _container else None

    if loop_detector:
        try:
            stats = await loop_detector.get_loop_detection_stats()
            loop_detection_info = LoopDetectionHealthInfo(
                enabled=True,
                max_identical_calls=loop_detector.max_identical_calls,
                sliding_window_seconds=loop_detector.sliding_window_seconds,
                active_sessions=stats.get("active_sessions", 0),
                loops_detected_total=stats.get("loops_detected_total", 0),
                loops_by_tool=stats.get("loops_by_tool", {}),
                last_loop_detected_at=stats.get("last_loop_detected_at"),
                last_loop_tool_name=stats.get("last_loop_tool_name"),
            )
        except Exception as e:
            logger.warning(f"Failed to get loop detection info: {e}")
            loop_detection_info = LoopDetectionHealthInfo(
                enabled=True,
                max_identical_calls=app_settings.max_identical_calls,
                sliding_window_seconds=app_settings.loop_detection_window_seconds,
                active_sessions=0,
                loops_detected_total=0,
                loops_by_tool={},
            )
    elif app_settings.loop_detection_enabled:
        loop_detection_info = LoopDetectionHealthInfo(
            enabled=True,
            max_identical_calls=app_settings.max_identical_calls,
            sliding_window_seconds=app_settings.loop_detection_window_seconds,
            active_sessions=0,
            loops_detected_total=0,
            loops_by_tool={},
        )
    else:
        loop_detection_info = LoopDetectionHealthInfo(
            enabled=False,
            max_identical_calls=0,
            sliding_window_seconds=0,
            active_sessions=0,
            loops_detected_total=0,
            loops_by_tool={},
        )

    # Get security monitoring info (Requirement 16.4)
    security_info = None
    security_svc = _container.security_service if _container else None

    if security_svc:
        try:
            metrics = await security_svc.get_security_metrics()
            security_info = SecurityHealthInfo(
                enabled=True,
                max_unknown_tool_attempts=security_svc.max_unknown_tool_attempts,
                window_seconds=security_svc.window_seconds,
                total_events=metrics.get("total_events", 0),
                events_by_type=metrics.get("events_by_type", {}),
                events_by_severity=metrics.get("events_by_severity", {}),
                recent_events_count=metrics.get("recent_events_count", 0),
                redis_enabled=metrics.get("redis_enabled", False),
            )
        except Exception as e:
            logger.warning(f"Failed to get security monitoring info: {e}")
            security_info = SecurityHealthInfo(
                enabled=True,
                max_unknown_tool_attempts=app_settings.max_unknown_tool_attempts,
                window_seconds=app_settings.security_event_window_seconds,
                total_events=0,
                events_by_type={},
                events_by_severity={},
                recent_events_count=0,
                redis_enabled=False,
            )
    elif app_settings.security_monitoring_enabled:
        security_info = SecurityHealthInfo(
            enabled=True,
            max_unknown_tool_attempts=app_settings.max_unknown_tool_attempts,
            window_seconds=app_settings.security_event_window_seconds,
            total_events=0,
            events_by_type={},
            events_by_severity={},
            recent_events_count=0,
            redis_enabled=False,
        )
    else:
        security_info = SecurityHealthInfo(
            enabled=False,
            max_unknown_tool_attempts=0,
            window_seconds=0,
            total_events=0,
            events_by_type={},
            events_by_severity={},
            recent_events_count=0,
            redis_enabled=False,
        )

    # Determine overall status
    policy_service = _container.policy_service if _container else None
    audit_service = _container.audit_service if _container else None
    if policy_service and audit_service:
        status = "healthy" if redis_connected else "degraded"
    else:
        status = "unhealthy"

    return HealthStatus(
        status=status,
        version=__version__,
        cloud_providers=["aws"],
        redis_connected=redis_connected,
        sqlite_connected=sqlite_connected,
        budget_tracking=budget_info,
        loop_detection=loop_detection_info,
        security_monitoring=security_info,
    )


@app.get("/metrics")
async def metrics_endpoint() -> Response:
    """
    Prometheus-compatible metrics endpoint for observability.

    Returns metrics in Prometheus text format including:
    - Tool call counts and execution times
    - Error rates by tool
    - Budget utilization metrics
    - Loop detection metrics
    - Session metrics

    Requirements: 15.2
    """
    from datetime import datetime

    from .services.metrics_service import MetricsService

    if not _container or not _container.audit_service:
        return Response(
            content="# No metrics available - audit service not initialized\n",
            media_type="text/plain; charset=utf-8",
        )

    # Create metrics service instance
    metrics_service = MetricsService(
        audit_service=_container.audit_service,
        budget_tracker=_container.budget_tracker,
        loop_detector=_container.loop_detector,
    )

    # Get global metrics
    global_metrics = await metrics_service.get_global_metrics()

    # Build Prometheus format output
    lines = []
    lines.append("# HELP mcp_server_uptime_seconds Server uptime in seconds")
    lines.append("# TYPE mcp_server_uptime_seconds gauge")
    lines.append(f"mcp_server_uptime_seconds {global_metrics.uptime_seconds}")

    lines.append("# HELP mcp_server_total_sessions Total number of sessions created")
    lines.append("# TYPE mcp_server_total_sessions counter")
    lines.append(f"mcp_server_total_sessions {global_metrics.total_sessions}")

    lines.append("# HELP mcp_server_active_sessions Number of currently active sessions")
    lines.append("# TYPE mcp_server_active_sessions gauge")
    lines.append(f"mcp_server_active_sessions {global_metrics.active_sessions}")

    lines.append("# HELP mcp_tool_invocations_total Total number of tool invocations")
    lines.append("# TYPE mcp_tool_invocations_total counter")
    lines.append(f"mcp_tool_invocations_total {global_metrics.total_tool_invocations}")

    lines.append("# HELP mcp_tool_successes_total Total number of successful tool invocations")
    lines.append("# TYPE mcp_tool_successes_total counter")
    lines.append(f"mcp_tool_successes_total {global_metrics.total_tool_successes}")

    lines.append("# HELP mcp_tool_failures_total Total number of failed tool invocations")
    lines.append("# TYPE mcp_tool_failures_total counter")
    lines.append(f"mcp_tool_failures_total {global_metrics.total_tool_failures}")

    lines.append("# HELP mcp_tool_error_rate Overall error rate as a fraction")
    lines.append("# TYPE mcp_tool_error_rate gauge")
    lines.append(f"mcp_tool_error_rate {global_metrics.overall_error_rate}")

    lines.append("# HELP mcp_tool_execution_time_ms_total Total execution time in milliseconds")
    lines.append("# TYPE mcp_tool_execution_time_ms_total counter")
    lines.append(f"mcp_tool_execution_time_ms_total {global_metrics.total_execution_time_ms}")

    lines.append("# HELP mcp_tool_execution_time_ms_average Average execution time in milliseconds")
    lines.append("# TYPE mcp_tool_execution_time_ms_average gauge")
    lines.append(f"mcp_tool_execution_time_ms_average {global_metrics.average_execution_time_ms}")

    # Per-tool metrics
    lines.append("# HELP mcp_tool_invocations Tool invocation count by tool name")
    lines.append("# TYPE mcp_tool_invocations counter")
    for tool_stat in global_metrics.tool_stats:
        lines.append(
            f'mcp_tool_invocations{{tool="{tool_stat.tool_name}"}} {tool_stat.invocation_count}'
        )

    lines.append("# HELP mcp_tool_successes Tool success count by tool name")
    lines.append("# TYPE mcp_tool_successes counter")
    for tool_stat in global_metrics.tool_stats:
        lines.append(
            f'mcp_tool_successes{{tool="{tool_stat.tool_name}"}} {tool_stat.success_count}'
        )

    lines.append("# HELP mcp_tool_failures Tool failure count by tool name")
    lines.append("# TYPE mcp_tool_failures counter")
    for tool_stat in global_metrics.tool_stats:
        lines.append(f'mcp_tool_failures{{tool="{tool_stat.tool_name}"}} {tool_stat.failure_count}')

    lines.append("# HELP mcp_tool_error_rate_by_tool Error rate by tool name")
    lines.append("# TYPE mcp_tool_error_rate_by_tool gauge")
    for tool_stat in global_metrics.tool_stats:
        lines.append(
            f'mcp_tool_error_rate_by_tool{{tool="{tool_stat.tool_name}"}} {tool_stat.error_rate}'
        )

    lines.append(
        "# HELP mcp_tool_execution_time_ms_average_by_tool Average execution time by tool name"
    )
    lines.append("# TYPE mcp_tool_execution_time_ms_average_by_tool gauge")
    for tool_stat in global_metrics.tool_stats:
        lines.append(
            f'mcp_tool_execution_time_ms_average_by_tool{{tool="{tool_stat.tool_name}"}} {tool_stat.average_execution_time_ms}'
        )

    # Budget metrics
    if global_metrics.budget_metrics:
        lines.append("# HELP mcp_budget_max_calls_per_session Maximum tool calls per session")
        lines.append("# TYPE mcp_budget_max_calls_per_session gauge")
        lines.append(f"mcp_budget_max_calls_per_session {global_metrics.budget_metrics.max_budget}")

        lines.append(
            "# HELP mcp_budget_active_sessions Number of active sessions with budget tracking"
        )
        lines.append("# TYPE mcp_budget_active_sessions gauge")
        lines.append(
            f"mcp_budget_active_sessions {global_metrics.budget_metrics.active_sessions_count}"
        )

        lines.append(
            "# HELP mcp_budget_sessions_exhausted Number of sessions that exhausted their budget"
        )
        lines.append("# TYPE mcp_budget_sessions_exhausted counter")
        lines.append(
            f"mcp_budget_sessions_exhausted {global_metrics.budget_metrics.sessions_exhausted_count}"
        )

    # Loop detection metrics
    if global_metrics.loop_detection_metrics:
        lines.append("# HELP mcp_loop_detection_total Total loops detected")
        lines.append("# TYPE mcp_loop_detection_total counter")
        lines.append(
            f"mcp_loop_detection_total {global_metrics.loop_detection_metrics.total_loops_detected}"
        )

        lines.append("# HELP mcp_loop_detection_active_sessions Active sessions with loop tracking")
        lines.append("# TYPE mcp_loop_detection_active_sessions gauge")
        lines.append(
            f"mcp_loop_detection_active_sessions {global_metrics.loop_detection_metrics.active_sessions_with_loops}"
        )

        lines.append("# HELP mcp_loop_detection_by_tool Loops detected by tool name")
        lines.append("# TYPE mcp_loop_detection_by_tool counter")
        for tool_name, count in global_metrics.loop_detection_metrics.loops_by_tool.items():
            lines.append(f'mcp_loop_detection_by_tool{{tool="{tool_name}"}} {count}')

        lines.append(
            "# HELP mcp_loop_detection_max_identical_calls_threshold Max identical calls threshold"
        )
        lines.append("# TYPE mcp_loop_detection_max_identical_calls_threshold gauge")
        lines.append(
            f"mcp_loop_detection_max_identical_calls_threshold {global_metrics.loop_detection_metrics.max_identical_calls_threshold}"
        )

    # Error metrics
    if global_metrics.error_metrics:
        lines.append("# HELP mcp_error_trend Error trend direction")
        lines.append("# TYPE mcp_error_trend gauge")
        trend_value = {"improving": 1, "stable": 0, "declining": -1}.get(
            global_metrics.error_metrics.error_trend, 0
        )
        lines.append(f"mcp_error_trend {trend_value}")

        lines.append("# HELP mcp_errors_by_type Error count by error type")
        lines.append("# TYPE mcp_errors_by_type counter")
        for error_type, count in global_metrics.error_metrics.errors_by_type.items():
            lines.append(f'mcp_errors_by_type{{type="{error_type}"}} {count}')

        lines.append("# HELP mcp_errors_by_tool Error count by tool name")
        lines.append("# TYPE mcp_errors_by_tool counter")
        for tool_name, count in global_metrics.error_metrics.errors_by_tool.items():
            lines.append(f'mcp_errors_by_tool{{tool="{tool_name}"}} {count}')

    # Add timestamp
    lines.append(f"# Generated at {datetime.now(timezone.utc).isoformat()}")

    return Response(content="\n".join(lines) + "\n", media_type="text/plain; charset=utf-8")


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "FinOps Tag Compliance MCP Server",
        "version": __version__,
        "description": "AWS resource tagging validation and compliance checking via MCP",
        "health_check": "/health",
        "metrics": "/metrics",
        "mcp_endpoints": {
            "list_tools": "/mcp/tools",
            "call_tool": "/mcp/tools/call",
        },
        "tools_count": 8,
    }


# MCP Protocol Endpoints


@app.get("/mcp/tools", response_model=MCPListToolsResponse)
async def list_tools() -> MCPListToolsResponse:
    """
    List all available MCP tools.

    Returns the definitions of all 8 registered tools including
    their names, descriptions, and input schemas.

    Requirements: 14.5
    """
    if not _mcp_handler:
        raise HTTPException(
            status_code=503,
            detail="MCP handler not initialized",
        )

    tools = _mcp_handler.get_tool_definitions()
    return MCPListToolsResponse(tools=tools)


@app.post("/mcp/tools/call", response_model=MCPToolCallResponse)
async def call_tool(request: MCPToolCallRequest) -> MCPToolCallResponse:
    """
    Invoke an MCP tool by name.

    This endpoint handles tool invocations from AI assistants.
    It validates the tool name, invokes the appropriate handler,
    and returns the result.

    Args:
        request: MCPToolCallRequest with tool name and arguments

    Returns:
        MCPToolCallResponse with tool output or error

    Requirements: 14.5
    """
    if not _mcp_handler:
        raise HTTPException(
            status_code=503,
            detail="MCP handler not initialized",
        )

    logger.info(f"MCP tool call: {request.name} with args: {request.arguments}")

    result = await _mcp_handler.invoke_tool(
        name=request.name,
        arguments=request.arguments,
    )

    return MCPToolCallResponse(
        content=result.content,
        is_error=result.is_error,
    )


# Tool-specific endpoints for direct HTTP access (optional)


@app.post("/api/v1/compliance/check")
async def api_check_compliance(
    resource_types: list[str],
    filters: dict | None = None,
    severity: str = "all",
):
    """
    Direct API endpoint for compliance checking.

    This provides an alternative to the MCP protocol for direct HTTP access.
    """
    if not _mcp_handler:
        raise HTTPException(status_code=503, detail="Service not initialized")

    result = await _mcp_handler.invoke_tool(
        name="check_tag_compliance",
        arguments={
            "resource_types": resource_types,
            "filters": filters,
            "severity": severity,
        },
    )

    if result.is_error:
        raise HTTPException(status_code=400, detail=result.content[0]["text"])

    return JSONResponse(content={"result": result.content[0]["text"]})


@app.get("/api/v1/policy")
async def api_get_policy():
    """
    Direct API endpoint for retrieving the tagging policy.
    """
    if not _mcp_handler:
        raise HTTPException(status_code=503, detail="Service not initialized")

    result = await _mcp_handler.invoke_tool(
        name="get_tagging_policy",
        arguments={},
    )

    if result.is_error:
        raise HTTPException(status_code=400, detail=result.content[0]["text"])

    return JSONResponse(content={"result": result.content[0]["text"]})
