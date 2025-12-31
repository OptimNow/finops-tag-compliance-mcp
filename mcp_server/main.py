"""FastAPI application entry point for FinOps Tag Compliance MCP Server.

This module creates the FastAPI application with MCP protocol support,
registers all 8 tools, configures CORS and middleware, and sets up
error handling.

Requirements: 14.2, 14.5
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import __version__
from .config import settings
from .models import HealthStatus
from .models.audit import AuditStatus
from .clients.aws_client import AWSClient
from .clients.cache import RedisCache
from .services.audit_service import AuditService
from .services.policy_service import PolicyService
from .services.compliance_service import ComplianceService
from .mcp_handler import MCPHandler, MCPToolResult
from .utils.cloudwatch_logger import configure_cloudwatch_logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configure CloudWatch logging if enabled
configure_cloudwatch_logging()

# Global instances
redis_cache: Optional[RedisCache] = None
audit_service: Optional[AuditService] = None
aws_client: Optional[AWSClient] = None
policy_service: Optional[PolicyService] = None
compliance_service: Optional[ComplianceService] = None
mcp_handler: Optional[MCPHandler] = None


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
    
    Initializes all services on startup:
    - Redis cache for caching compliance data
    - Audit service for logging tool invocations
    - AWS client for AWS API calls
    - Policy service for tagging policy management
    - Compliance service for compliance checking
    - MCP handler for tool registration and invocation
    
    Cleans up on shutdown.
    
    Requirements: 14.2
    """
    global redis_cache, audit_service, aws_client, policy_service
    global compliance_service, mcp_handler
    
    # Startup
    logger.info("Starting FinOps Tag Compliance MCP Server")
    
    # Get settings instance
    app_settings = settings()
    
    # Initialize Redis cache
    try:
        redis_cache = await RedisCache.create(redis_url=app_settings.redis_url)
        logger.info("Redis cache initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize Redis cache: {e}")
        redis_cache = None
    
    # Initialize audit service
    try:
        audit_service = AuditService(db_path=app_settings.audit_db_path)
        logger.info("Audit service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize audit service: {e}")
        audit_service = None
    
    # Initialize AWS client
    try:
        aws_client = AWSClient(region=app_settings.aws_region)
        logger.info(f"AWS client initialized for region {app_settings.aws_region}")
    except Exception as e:
        logger.warning(f"Failed to initialize AWS client: {e}")
        aws_client = None
    
    # Initialize policy service
    try:
        policy_service = PolicyService(policy_path=app_settings.policy_path)
        logger.info(f"Policy service initialized from {app_settings.policy_path}")
    except Exception as e:
        logger.warning(f"Failed to initialize policy service: {e}")
        policy_service = None
    
    # Initialize compliance service
    if aws_client and policy_service:
        try:
            compliance_service = ComplianceService(
                aws_client=aws_client,
                policy_service=policy_service,
                cache=redis_cache,
            )
            logger.info("Compliance service initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize compliance service: {e}")
            compliance_service = None
    
    # Initialize MCP handler with all services
    mcp_handler = MCPHandler(
        aws_client=aws_client,
        policy_service=policy_service,
        compliance_service=compliance_service,
        redis_cache=redis_cache,
        audit_service=audit_service,
    )
    logger.info("MCP handler initialized with 8 tools")
    
    logger.info(f"MCP Server v{__version__} started successfully on port {app_settings.port}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down FinOps Tag Compliance MCP Server")
    if redis_cache:
        await redis_cache.close()
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for MCP protocol
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler for unhandled errors.
    
    Logs the error and returns a structured error response.
    """
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    # Log to audit service if available
    if audit_service:
        audit_service.log_invocation(
            tool_name="unknown",
            parameters={"path": str(request.url.path)},
            status=AuditStatus.FAILURE,
            error_message=str(exc),
        )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
        },
    )


@app.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """
    Health check endpoint for monitoring server status.
    
    Returns:
        HealthStatus with server status, version, and connectivity information
    
    Requirements: 13.1, 13.2
    """
    # Check Redis connectivity
    redis_connected = False
    if redis_cache:
        redis_connected = await redis_cache.is_connected()
    
    # Check SQLite connectivity
    sqlite_connected = False
    if audit_service:
        try:
            # Try to query the audit database
            import sqlite3
            conn = sqlite3.connect(audit_service.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            sqlite_connected = True
        except Exception as e:
            logger.warning(f"SQLite connectivity check failed: {e}")
            sqlite_connected = False
    
    # Determine overall status
    # Server is healthy if core services are available
    # Degraded if some optional services (Redis) are unavailable
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
    )


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "FinOps Tag Compliance MCP Server",
        "version": __version__,
        "description": "AWS resource tagging validation and compliance checking via MCP",
        "health_check": "/health",
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
    if not mcp_handler:
        raise HTTPException(
            status_code=503,
            detail="MCP handler not initialized",
        )
    
    tools = mcp_handler.get_tool_definitions()
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
    if not mcp_handler:
        raise HTTPException(
            status_code=503,
            detail="MCP handler not initialized",
        )
    
    logger.info(f"MCP tool call: {request.name} with args: {request.arguments}")
    
    result = await mcp_handler.invoke_tool(
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
    filters: Optional[dict] = None,
    severity: str = "all",
):
    """
    Direct API endpoint for compliance checking.
    
    This provides an alternative to the MCP protocol for direct HTTP access.
    """
    if not mcp_handler:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await mcp_handler.invoke_tool(
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
    if not mcp_handler:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await mcp_handler.invoke_tool(
        name="get_tagging_policy",
        arguments={},
    )
    
    if result.is_error:
        raise HTTPException(status_code=400, detail=result.content[0]["text"])
    
    return JSONResponse(content={"result": result.content[0]["text"]})
