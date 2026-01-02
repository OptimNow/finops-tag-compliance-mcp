"""Property-based tests for unknown tool rejection.

Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
Validates: Requirements 16.1, 16.4

Property 18: Unknown Tool Rejection
*For any* request to invoke a tool that is not registered in the MCP Server,
the request SHALL be rejected with an error response. The rejection SHALL be
logged with the attempted tool name for security monitoring.
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import AsyncMock, MagicMock, patch
import json
from typing import Optional

from mcp_server.mcp_handler import MCPHandler, MCPToolResult


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Known registered tool names (these should NOT be used as unknown tools)
REGISTERED_TOOLS = {
    "check_tag_compliance",
    "find_untagged_resources",
    "validate_resource_tags",
    "get_cost_attribution_gap",
    "suggest_tags",
    "get_tagging_policy",
    "generate_compliance_report",
    "get_violation_history",
}

# Strategy for generating unknown tool names (not in registered tools)
unknown_tool_name = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="_-",
    ),
    min_size=1,
    max_size=100,
).filter(
    lambda x: x.strip() != "" and x not in REGISTERED_TOOLS
)

# Strategy for generating random tool parameters
random_parameters = st.dictionaries(
    keys=st.text(min_size=1, max_size=30).filter(lambda x: x.strip() != ""),
    values=st.one_of(
        st.text(max_size=100),
        st.integers(),
        st.booleans(),
        st.lists(st.text(max_size=20), max_size=5),
    ),
    max_size=5,
)

# Strategy for generating session IDs
session_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
    min_size=8,
    max_size=64,
).filter(lambda x: x.strip() != "")


# =============================================================================
# Property Tests for Unknown Tool Rejection
# =============================================================================

class TestUnknownToolRejectionProperty:
    """Property tests for unknown tool rejection (Property 18)."""

    @pytest.fixture
    def mcp_handler(self):
        """Create an MCPHandler instance for testing."""
        return MCPHandler()

    @given(tool_name=unknown_tool_name, parameters=random_parameters)
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_18_unknown_tool_rejected_with_error(
        self,
        tool_name: str,
        parameters: dict,
    ):
        """
        Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
        Validates: Requirements 16.1, 16.4
        
        For any request to invoke a tool that is not registered in the MCP Server,
        the request SHALL be rejected with an error response.
        """
        handler = MCPHandler()
        
        # Mock the security service to avoid side effects
        with patch("mcp_server.mcp_handler.get_security_service") as mock_get_security:
            mock_security = AsyncMock()
            mock_security.log_unknown_tool_attempt = AsyncMock()
            mock_security.check_unknown_tool_rate_limit = AsyncMock(
                return_value=(False, 1, 10)  # Not blocked
            )
            mock_get_security.return_value = mock_security
            
            # Mock correlation ID
            with patch("mcp_server.mcp_handler.get_correlation_id") as mock_corr:
                mock_corr.return_value = "test-session-id"
                
                result = await handler.invoke_tool(tool_name, parameters)
        
        # Verify the result is an error
        assert isinstance(result, MCPToolResult)
        assert result.is_error is True
        
        # Verify the error content
        assert len(result.content) > 0
        content = result.content[0]
        assert content["type"] == "text"
        
        # Parse the error response
        error_data = json.loads(content["text"])
        assert "error" in error_data
        assert error_data["error"] == "Unknown tool"
        assert "message" in error_data
        assert tool_name in error_data["message"]

    @given(tool_name=unknown_tool_name, parameters=random_parameters)
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_18_unknown_tool_logged_for_security(
        self,
        tool_name: str,
        parameters: dict,
    ):
        """
        Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
        Validates: Requirements 16.1, 16.4
        
        For any unknown tool rejection, the tool name SHALL be logged
        for security monitoring.
        """
        handler = MCPHandler()
        
        # Mock the security service to capture the logging call
        with patch("mcp_server.mcp_handler.get_security_service") as mock_get_security:
            mock_security = AsyncMock()
            mock_security.log_unknown_tool_attempt = AsyncMock()
            mock_security.check_unknown_tool_rate_limit = AsyncMock(
                return_value=(False, 1, 10)  # Not blocked
            )
            mock_get_security.return_value = mock_security
            
            # Mock correlation ID
            with patch("mcp_server.mcp_handler.get_correlation_id") as mock_corr:
                mock_corr.return_value = "test-session-id"
                
                await handler.invoke_tool(tool_name, parameters)
        
        # Verify log_unknown_tool_attempt was called with the tool name
        mock_security.log_unknown_tool_attempt.assert_called_once()
        call_kwargs = mock_security.log_unknown_tool_attempt.call_args
        
        # Check that tool_name was passed
        assert call_kwargs.kwargs.get("tool_name") == tool_name or \
               (call_kwargs.args and call_kwargs.args[0] == tool_name)

    @given(tool_name=unknown_tool_name)
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_18_error_response_includes_registered_tools(
        self,
        tool_name: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
        Validates: Requirements 16.1, 16.4
        
        For any unknown tool rejection, the error response SHALL include
        the list of registered tools to help the user.
        """
        handler = MCPHandler()
        
        # Mock the security service
        with patch("mcp_server.mcp_handler.get_security_service") as mock_get_security:
            mock_security = AsyncMock()
            mock_security.log_unknown_tool_attempt = AsyncMock()
            mock_security.check_unknown_tool_rate_limit = AsyncMock(
                return_value=(False, 1, 10)
            )
            mock_get_security.return_value = mock_security
            
            with patch("mcp_server.mcp_handler.get_correlation_id") as mock_corr:
                mock_corr.return_value = "test-session-id"
                
                result = await handler.invoke_tool(tool_name, {})
        
        # Parse the error response
        error_data = json.loads(result.content[0]["text"])
        
        # Verify registered_tools is included
        assert "registered_tools" in error_data
        registered = set(error_data["registered_tools"])
        
        # Verify all 8 registered tools are listed
        assert registered == REGISTERED_TOOLS


class TestUnknownToolRateLimiting:
    """Property tests for rate limiting of unknown tool attempts."""

    @given(
        tool_name=unknown_tool_name,
        current_count=st.integers(min_value=11, max_value=100),
        max_attempts=st.integers(min_value=5, max_value=10),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_18_rate_limit_blocks_after_threshold(
        self,
        tool_name: str,
        current_count: int,
        max_attempts: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
        Validates: Requirements 16.4
        
        For any session that exceeds the rate limit for unknown tool attempts,
        subsequent requests SHALL be blocked with a rate limit error.
        """
        assume(current_count > max_attempts)
        
        handler = MCPHandler()
        
        # Mock the security service to simulate rate limit exceeded
        with patch("mcp_server.mcp_handler.get_security_service") as mock_get_security:
            mock_security = AsyncMock()
            mock_security.log_unknown_tool_attempt = AsyncMock()
            mock_security.check_unknown_tool_rate_limit = AsyncMock(
                return_value=(True, current_count, max_attempts)  # Blocked
            )
            mock_security.window_seconds = 60
            mock_get_security.return_value = mock_security
            
            with patch("mcp_server.mcp_handler.get_correlation_id") as mock_corr:
                mock_corr.return_value = "test-session-id"
                
                result = await handler.invoke_tool(tool_name, {})
        
        # Verify the result is an error
        assert result.is_error is True
        
        # Parse the error response
        error_data = json.loads(result.content[0]["text"])
        
        # Verify rate limit error
        assert error_data["error"] == "Rate limit exceeded"
        assert "details" in error_data
        assert error_data["details"]["attempts"] == current_count
        assert error_data["details"]["max_attempts"] == max_attempts

    @given(
        tool_name=unknown_tool_name,
        current_count=st.integers(min_value=1, max_value=5),
        max_attempts=st.integers(min_value=10, max_value=20),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_18_rate_limit_allows_under_threshold(
        self,
        tool_name: str,
        current_count: int,
        max_attempts: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
        Validates: Requirements 16.4
        
        For any session under the rate limit threshold, unknown tool
        requests SHALL be rejected but not rate-limited.
        """
        assume(current_count < max_attempts)
        
        handler = MCPHandler()
        
        # Mock the security service to simulate under rate limit
        with patch("mcp_server.mcp_handler.get_security_service") as mock_get_security:
            mock_security = AsyncMock()
            mock_security.log_unknown_tool_attempt = AsyncMock()
            mock_security.check_unknown_tool_rate_limit = AsyncMock(
                return_value=(False, current_count, max_attempts)  # Not blocked
            )
            mock_get_security.return_value = mock_security
            
            with patch("mcp_server.mcp_handler.get_correlation_id") as mock_corr:
                mock_corr.return_value = "test-session-id"
                
                result = await handler.invoke_tool(tool_name, {})
        
        # Verify the result is an error (unknown tool) but NOT rate limited
        assert result.is_error is True
        
        # Parse the error response
        error_data = json.loads(result.content[0]["text"])
        
        # Should be "Unknown tool" error, not "Rate limit exceeded"
        assert error_data["error"] == "Unknown tool"


class TestUnknownToolAuditLogging:
    """Property tests for audit logging of unknown tool attempts."""

    @given(tool_name=unknown_tool_name, parameters=random_parameters)
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_18_unknown_tool_audit_logged(
        self,
        tool_name: str,
        parameters: dict,
    ):
        """
        Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
        Validates: Requirements 16.4
        
        For any unknown tool rejection, an audit log entry SHALL be created
        with the tool name and failure status.
        """
        # Create mock audit service
        mock_audit = MagicMock()
        mock_audit.log_invocation = MagicMock()
        
        handler = MCPHandler(audit_service=mock_audit)
        
        # Mock the security service
        with patch("mcp_server.mcp_handler.get_security_service") as mock_get_security:
            mock_security = AsyncMock()
            mock_security.log_unknown_tool_attempt = AsyncMock()
            mock_security.check_unknown_tool_rate_limit = AsyncMock(
                return_value=(False, 1, 10)
            )
            mock_get_security.return_value = mock_security
            
            with patch("mcp_server.mcp_handler.get_correlation_id") as mock_corr:
                mock_corr.return_value = "test-session-id"
                
                await handler.invoke_tool(tool_name, parameters)
        
        # Verify audit log was called
        mock_audit.log_invocation.assert_called_once()
        call_kwargs = mock_audit.log_invocation.call_args.kwargs
        
        # Verify the audit log contains the tool name
        assert call_kwargs["tool_name"] == tool_name
        # Verify the status is FAILURE
        assert call_kwargs["status"].value == "failure"
        # Verify error message mentions unknown tool
        assert "Unknown tool" in call_kwargs["error_message"]


class TestRegisteredToolsAccepted:
    """Property tests ensuring registered tools are NOT rejected as unknown."""

    @given(
        tool_name=st.sampled_from(list(REGISTERED_TOOLS)),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_18_registered_tools_not_rejected_as_unknown(
        self,
        tool_name: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
        Validates: Requirements 16.1
        
        For any registered tool, the request SHALL NOT be rejected as unknown.
        (It may fail for other reasons like missing parameters, but not as unknown.)
        """
        handler = MCPHandler()
        
        # Mock the security service
        with patch("mcp_server.mcp_handler.get_security_service") as mock_get_security:
            mock_security = AsyncMock()
            mock_security.log_unknown_tool_attempt = AsyncMock()
            mock_get_security.return_value = mock_security
            
            with patch("mcp_server.mcp_handler.get_correlation_id") as mock_corr:
                mock_corr.return_value = "test-session-id"
                
                # Invoke with empty parameters (will likely fail validation)
                result = await handler.invoke_tool(tool_name, {})
        
        # If there's an error, it should NOT be "Unknown tool"
        if result.is_error:
            content_text = result.content[0]["text"]
            # Try to parse as JSON, but handle plain error strings too
            try:
                error_data = json.loads(content_text)
                # The error should be something other than "Unknown tool"
                # (e.g., validation error, missing required parameter)
                assert error_data.get("error") != "Unknown tool"
            except json.JSONDecodeError:
                # Plain error string (e.g., "Error: PolicyService not initialized")
                # This is fine - it's not an "Unknown tool" error
                assert "Unknown tool" not in content_text
        
        # log_unknown_tool_attempt should NOT have been called
        mock_security.log_unknown_tool_attempt.assert_not_called()


class TestUnknownToolEdgeCases:
    """Property tests for edge cases in unknown tool handling."""

    @given(
        prefix=st.sampled_from(list(REGISTERED_TOOLS)),
        suffix=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() != ""),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_18_similar_tool_names_rejected(
        self,
        prefix: str,
        suffix: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
        Validates: Requirements 16.1, 16.4
        
        For any tool name that is similar to but not exactly a registered tool,
        the request SHALL be rejected as unknown.
        """
        # Create a tool name that's similar but not exact
        similar_name = f"{prefix}_{suffix}"
        assume(similar_name not in REGISTERED_TOOLS)
        
        handler = MCPHandler()
        
        with patch("mcp_server.mcp_handler.get_security_service") as mock_get_security:
            mock_security = AsyncMock()
            mock_security.log_unknown_tool_attempt = AsyncMock()
            mock_security.check_unknown_tool_rate_limit = AsyncMock(
                return_value=(False, 1, 10)
            )
            mock_get_security.return_value = mock_security
            
            with patch("mcp_server.mcp_handler.get_correlation_id") as mock_corr:
                mock_corr.return_value = "test-session-id"
                
                result = await handler.invoke_tool(similar_name, {})
        
        # Should be rejected as unknown
        assert result.is_error is True
        error_data = json.loads(result.content[0]["text"])
        assert error_data["error"] == "Unknown tool"

    @given(
        tool_name=st.sampled_from(list(REGISTERED_TOOLS)),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_18_case_sensitive_tool_names(
        self,
        tool_name: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 18: Unknown Tool Rejection
        Validates: Requirements 16.1, 16.4
        
        Tool names SHALL be case-sensitive. A tool name with different
        casing SHALL be rejected as unknown.
        """
        # Create variations with different casing
        variations = [
            tool_name.upper(),
            tool_name.capitalize(),
            tool_name.swapcase(),
        ]
        
        handler = MCPHandler()
        
        for variant in variations:
            if variant == tool_name:
                continue  # Skip if it happens to match
            
            with patch("mcp_server.mcp_handler.get_security_service") as mock_get_security:
                mock_security = AsyncMock()
                mock_security.log_unknown_tool_attempt = AsyncMock()
                mock_security.check_unknown_tool_rate_limit = AsyncMock(
                    return_value=(False, 1, 10)
                )
                mock_get_security.return_value = mock_security
                
                with patch("mcp_server.mcp_handler.get_correlation_id") as mock_corr:
                    mock_corr.return_value = "test-session-id"
                    
                    result = await handler.invoke_tool(variant, {})
            
            # Should be rejected as unknown
            assert result.is_error is True
            error_data = json.loads(result.content[0]["text"])
            assert error_data["error"] == "Unknown tool"
