"""End-to-end integration tests for MCP Server.

These tests verify the MCP protocol communication and tool invocation flow.

Requirements: 14.5
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from mcp_server.clients.aws_client import AWSClient
from mcp_server.clients.cache import RedisCache
from mcp_server.main import app
from mcp_server.mcp_handler import MCPHandler, MCPToolResult
from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.enums import Severity, ViolationType
from mcp_server.models.violations import Violation
from mcp_server.services.compliance_service import ComplianceService
from mcp_server.services.policy_service import PolicyService


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    client = MagicMock(spec=AWSClient)
    client.get_ec2_instances = AsyncMock(return_value=[])
    client.get_rds_instances = AsyncMock(return_value=[])
    client.get_s3_buckets = AsyncMock(return_value=[])
    client.get_lambda_functions = AsyncMock(return_value=[])
    client.get_ecs_services = AsyncMock(return_value=[])
    client.get_cost_data = AsyncMock(return_value={})
    return client


@pytest.fixture
def mock_policy_service():
    """Create a mock policy service."""
    service = MagicMock(spec=PolicyService)
    service.validate_resource_tags = MagicMock(return_value=[])

    # Mock get_policy to return a valid policy object
    from mcp_server.models.policy import OptionalTag, RequiredTag, TagNamingRules, TagPolicy

    mock_policy = TagPolicy(
        version="1.0",
        last_updated=datetime.now(timezone.utc),
        required_tags=[
            RequiredTag(
                name="CostCenter",
                description="Cost center for billing",
                allowed_values=["Engineering", "Marketing", "Sales"],
                applies_to=["ec2:instance", "rds:db", "s3:bucket"],
            ),
            RequiredTag(
                name="Environment",
                description="Deployment environment",
                allowed_values=["production", "staging", "development"],
                applies_to=["ec2:instance", "rds:db", "lambda:function"],
            ),
        ],
        optional_tags=[
            OptionalTag(
                name="Project",
                description="Project name",
            ),
        ],
        tag_naming_rules=TagNamingRules(
            case_sensitivity=False,
            allow_special_characters=False,
            max_key_length=128,
            max_value_length=256,
        ),
    )
    service.get_policy = MagicMock(return_value=mock_policy)

    return service


@pytest.fixture
def mock_redis_cache():
    """Create a mock Redis cache."""
    cache = MagicMock(spec=RedisCache)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.is_connected = MagicMock(return_value=True)
    cache.close = AsyncMock()
    return cache


@pytest.fixture
def mock_compliance_service(mock_aws_client, mock_policy_service, mock_redis_cache):
    """Create a mock compliance service."""
    service = MagicMock(spec=ComplianceService)

    # Default compliance result
    service.check_compliance = AsyncMock(
        return_value=ComplianceResult(
            compliance_score=0.85,
            total_resources=10,
            compliant_resources=8,
            violations=[
                Violation(
                    resource_id="i-123",
                    resource_type="ec2:instance",
                    region="us-east-1",
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=Severity.ERROR,
                    cost_impact_monthly=100.0,
                ),
                Violation(
                    resource_id="i-456",
                    resource_type="ec2:instance",
                    region="us-east-1",
                    violation_type=ViolationType.INVALID_VALUE,
                    tag_name="Environment",
                    severity=Severity.WARNING,
                    current_value="prod",
                    allowed_values=["production", "staging", "development"],
                    cost_impact_monthly=50.0,
                ),
            ],
            cost_attribution_gap=150.0,
            scan_timestamp=datetime.now(timezone.utc),
        )
    )

    return service


@pytest.fixture
def mcp_handler(mock_aws_client, mock_policy_service, mock_compliance_service, mock_redis_cache):
    """Create an MCP handler with mocked dependencies."""
    return MCPHandler(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        compliance_service=mock_compliance_service,
        redis_cache=mock_redis_cache,
        audit_service=None,
    )


@pytest.mark.integration
class TestMCPServerEndpoints:
    """Test MCP server HTTP endpoints."""

    def test_root_endpoint(self, test_client):
        """Test the root endpoint returns API information."""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert "name" in data
        assert data["name"] == "FinOps Tag Compliance MCP Server"
        assert "version" in data
        assert "mcp_endpoints" in data
        assert data["tools_count"] == 8

    def test_health_endpoint(self, test_client):
        """Test the health check endpoint."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "version" in data
        assert "cloud_providers" in data
        assert "aws" in data["cloud_providers"]


@pytest.mark.integration
class TestMCPToolDefinitions:
    """Test MCP tool definitions and listing."""

    def test_list_tools_returns_8_tools(self, mcp_handler):
        """Test that all 8 tools are registered."""
        tools = mcp_handler.get_tool_definitions()

        assert len(tools) == 8

        # Verify all expected tools are present
        tool_names = {tool["name"] for tool in tools}
        expected_tools = {
            "check_tag_compliance",
            "find_untagged_resources",
            "validate_resource_tags",
            "get_cost_attribution_gap",
            "suggest_tags",
            "get_tagging_policy",
            "generate_compliance_report",
            "get_violation_history",
        }

        assert tool_names == expected_tools

    def test_tool_definitions_have_required_fields(self, mcp_handler):
        """Test that each tool definition has required fields."""
        tools = mcp_handler.get_tool_definitions()

        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

            # Verify input schema structure
            schema = tool["inputSchema"]
            assert "type" in schema
            assert schema["type"] == "object"
            assert "properties" in schema

    def test_check_tag_compliance_schema(self, mcp_handler):
        """Test check_tag_compliance tool schema."""
        tools = mcp_handler.get_tool_definitions()
        tool = next(t for t in tools if t["name"] == "check_tag_compliance")

        schema = tool["inputSchema"]
        props = schema["properties"]

        assert "resource_types" in props
        assert props["resource_types"]["type"] == "array"

        assert "filters" in props
        assert "severity" in props

        assert "required" in schema
        assert "resource_types" in schema["required"]

    def test_suggest_tags_schema(self, mcp_handler):
        """Test suggest_tags tool schema."""
        tools = mcp_handler.get_tool_definitions()
        tool = next(t for t in tools if t["name"] == "suggest_tags")

        schema = tool["inputSchema"]
        props = schema["properties"]

        assert "resource_arn" in props
        assert props["resource_arn"]["type"] == "string"

        assert "required" in schema
        assert "resource_arn" in schema["required"]


@pytest.mark.integration
class TestMCPToolInvocation:
    """Test MCP tool invocation flow."""

    @pytest.mark.asyncio
    async def test_invoke_check_tag_compliance(self, mcp_handler):
        """Test invoking check_tag_compliance tool."""
        result = await mcp_handler.invoke_tool(
            name="check_tag_compliance",
            arguments={
                "resource_types": ["ec2:instance"],
                "severity": "all",
            },
        )

        assert isinstance(result, MCPToolResult)
        assert not result.is_error
        assert len(result.content) == 1
        assert result.content[0]["type"] == "text"

        # Parse the JSON response
        response_data = json.loads(result.content[0]["text"])

        assert "compliance_score" in response_data
        assert "total_resources" in response_data
        assert "violations" in response_data
        assert response_data["compliance_score"] == 0.85
        assert response_data["total_resources"] == 10

    @pytest.mark.asyncio
    async def test_invoke_get_tagging_policy(self, mcp_handler):
        """Test invoking get_tagging_policy tool."""
        result = await mcp_handler.invoke_tool(
            name="get_tagging_policy",
            arguments={},
        )

        assert isinstance(result, MCPToolResult)
        assert not result.is_error

        # Parse the JSON response
        response_data = json.loads(result.content[0]["text"])

        assert "version" in response_data
        assert "required_tags" in response_data
        assert "optional_tags" in response_data
        assert len(response_data["required_tags"]) == 2

    @pytest.mark.asyncio
    async def test_invoke_unknown_tool_returns_error(self, mcp_handler):
        """Test invoking an unknown tool returns an error."""
        result = await mcp_handler.invoke_tool(
            name="unknown_tool",
            arguments={},
        )

        assert isinstance(result, MCPToolResult)
        assert result.is_error
        assert "Unknown tool" in result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_invoke_tool_with_invalid_arguments(self, mcp_handler):
        """Test invoking a tool with invalid arguments returns an error."""
        result = await mcp_handler.invoke_tool(
            name="check_tag_compliance",
            arguments={
                "resource_types": [],  # Empty list should cause error
            },
        )

        assert isinstance(result, MCPToolResult)
        assert result.is_error
        # Check for error in response (case-insensitive)
        assert "error" in result.content[0]["text"].lower()


@pytest.mark.integration
class TestMCPProtocolCommunication:
    """Test MCP protocol communication patterns."""

    @pytest.mark.asyncio
    async def test_tool_call_request_response_cycle(self, mcp_handler):
        """Test complete request-response cycle for tool calls."""
        # Simulate MCP protocol request
        request = {
            "name": "check_tag_compliance",
            "arguments": {
                "resource_types": ["ec2:instance", "rds:db"],
                "filters": {"region": "us-east-1"},
                "severity": "errors_only",
            },
        }

        # Invoke the tool
        result = await mcp_handler.invoke_tool(
            name=request["name"],
            arguments=request["arguments"],
        )

        # Verify response structure matches MCP protocol
        assert hasattr(result, "content")
        assert hasattr(result, "is_error")
        assert isinstance(result.content, list)

        # Each content item should have type and text
        for item in result.content:
            assert "type" in item
            assert "text" in item

    @pytest.mark.asyncio
    async def test_multiple_sequential_tool_calls(self, mcp_handler):
        """Test multiple sequential tool calls work correctly."""
        # First call: get policy
        result1 = await mcp_handler.invoke_tool(
            name="get_tagging_policy",
            arguments={},
        )
        assert not result1.is_error

        # Second call: check compliance
        result2 = await mcp_handler.invoke_tool(
            name="check_tag_compliance",
            arguments={"resource_types": ["ec2:instance"]},
        )
        assert not result2.is_error

        # Third call: get policy again (should still work)
        result3 = await mcp_handler.invoke_tool(
            name="get_tagging_policy",
            arguments={},
        )
        assert not result3.is_error

        # Verify responses are consistent
        policy1 = json.loads(result1.content[0]["text"])
        policy3 = json.loads(result3.content[0]["text"])
        assert policy1["version"] == policy3["version"]

    @pytest.mark.asyncio
    async def test_tool_call_with_all_parameters(self, mcp_handler):
        """Test tool call with all optional parameters specified."""
        result = await mcp_handler.invoke_tool(
            name="check_tag_compliance",
            arguments={
                "resource_types": ["ec2:instance", "rds:db", "s3:bucket"],
                "filters": {
                    "region": "us-east-1",
                    "account_id": "123456789012",
                },
                "severity": "errors_only",
            },
        )

        assert not result.is_error
        response_data = json.loads(result.content[0]["text"])
        assert "compliance_score" in response_data


@pytest.mark.integration
class TestMCPErrorHandling:
    """Test MCP error handling scenarios."""

    @pytest.mark.asyncio
    async def test_service_not_initialized_error(self):
        """Test error when service is not initialized.

        Errors are now sanitized to prevent information leakage.
        The raw error message is logged internally but not exposed to clients.
        """
        # Create handler without compliance service
        handler = MCPHandler(
            aws_client=None,
            policy_service=None,
            compliance_service=None,
            redis_cache=None,
            audit_service=None,
        )

        result = await handler.invoke_tool(
            name="check_tag_compliance",
            arguments={"resource_types": ["ec2:instance"]},
        )

        assert result.is_error
        # Error is now sanitized - should return generic error message
        # instead of exposing internal details like "not initialized"
        error_data = json.loads(result.content[0]["text"])
        assert "error" in error_data
        assert "message" in error_data
        # Should NOT contain internal details
        assert "not initialized" not in result.content[0]["text"]

    @pytest.mark.asyncio
    async def test_validation_error_returns_meaningful_message(self, mcp_handler):
        """Test that validation errors return meaningful messages."""
        result = await mcp_handler.invoke_tool(
            name="check_tag_compliance",
            arguments={
                "resource_types": ["invalid:type"],
            },
        )

        assert result.is_error
        error_text = result.content[0]["text"]
        assert "Invalid resource types" in error_text or "Error" in error_text


@pytest.mark.integration
class TestMCPResponseFormat:
    """Test MCP response format compliance."""

    @pytest.mark.asyncio
    async def test_compliance_result_format(self, mcp_handler):
        """Test compliance result has correct format."""
        result = await mcp_handler.invoke_tool(
            name="check_tag_compliance",
            arguments={"resource_types": ["ec2:instance"]},
        )

        response_data = json.loads(result.content[0]["text"])

        # Verify required fields
        assert "compliance_score" in response_data
        assert "total_resources" in response_data
        assert "compliant_resources" in response_data
        assert "violations" in response_data
        assert "cost_attribution_gap" in response_data
        assert "scan_timestamp" in response_data

        # Verify violation format
        for violation in response_data["violations"]:
            assert "resource_id" in violation
            assert "resource_type" in violation
            assert "violation_type" in violation
            assert "tag_name" in violation
            assert "severity" in violation

    @pytest.mark.asyncio
    async def test_policy_result_format(self, mcp_handler):
        """Test policy result has correct format."""
        result = await mcp_handler.invoke_tool(
            name="get_tagging_policy",
            arguments={},
        )

        response_data = json.loads(result.content[0]["text"])

        # Verify required fields
        assert "version" in response_data
        assert "last_updated" in response_data
        assert "required_tags" in response_data
        assert "optional_tags" in response_data
        assert "tag_naming_rules" in response_data

        # Verify required tag format
        for tag in response_data["required_tags"]:
            assert "name" in tag
            assert "description" in tag
            assert "applies_to" in tag
