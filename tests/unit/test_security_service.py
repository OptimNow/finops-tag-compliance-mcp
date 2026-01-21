"""Unit tests for SecurityService.

Tests security event logging, rate limiting, and metrics collection.

Requirements: 16.4
"""

import pytest
from datetime import datetime
from mcp_server.services.security_service import (
    SecurityService,
    SecurityEvent,
    configure_security_logging,
)


class TestSecurityEvent:
    """Test SecurityEvent model."""

    def test_create_security_event(self):
        """Test creating a security event."""
        event = SecurityEvent(
            event_type="unknown_tool_attempt",
            severity="medium",
            tool_name="invalid_tool",
            session_id="test-session",
            message="Unknown tool attempted",
        )

        assert event.event_type == "unknown_tool_attempt"
        assert event.severity == "medium"
        assert event.tool_name == "invalid_tool"
        assert event.session_id == "test-session"
        assert event.message == "Unknown tool attempted"
        assert isinstance(event.timestamp, datetime)

    def test_security_event_with_details(self):
        """Test security event with additional details."""
        event = SecurityEvent(
            event_type="injection_attempt",
            severity="high",
            tool_name="check_tag_compliance",
            session_id="test-session",
            message="SQL injection detected",
            details={"field": "resource_types", "pattern": "DROP TABLE"},
        )

        assert event.details == {"field": "resource_types", "pattern": "DROP TABLE"}

    def test_security_event_to_dict(self):
        """Test converting security event to dictionary."""
        event = SecurityEvent(
            event_type="unknown_tool_attempt",
            severity="medium",
            tool_name="invalid_tool",
            session_id="test-session",
            message="Unknown tool attempted",
            details={"key": "value"},
        )

        event_dict = event.to_dict()

        assert event_dict["event_type"] == "unknown_tool_attempt"
        assert event_dict["severity"] == "medium"
        assert event_dict["tool_name"] == "invalid_tool"
        assert event_dict["session_id"] == "test-session"
        assert event_dict["message"] == "Unknown tool attempted"
        assert event_dict["details"] == {"key": "value"}
        assert "timestamp" in event_dict


class TestConfigureSecurityLogging:
    """Test configure_security_logging function."""

    def test_configure_security_logging_default(self):
        """Test configuring security logging with defaults."""
        # Should not raise any exceptions
        configure_security_logging()

    def test_configure_security_logging_custom_params(self):
        """Test configuring security logging with custom parameters."""
        # Should not raise any exceptions
        configure_security_logging(
            log_group="/test/log-group",
            log_stream="test-security",
            region="us-west-2",
        )


@pytest.mark.asyncio
class TestSecurityService:
    """Test SecurityService functionality."""

    async def test_log_security_event(self):
        """Test logging a security event."""
        service = SecurityService()

        event = await service.log_security_event(
            event_type="unknown_tool_attempt",
            severity="medium",
            tool_name="invalid_tool",
            session_id="test-session",
            message="Unknown tool attempted",
        )

        assert event.event_type == "unknown_tool_attempt"
        assert event.severity == "medium"
        assert event.tool_name == "invalid_tool"

    async def test_log_unknown_tool_attempt(self):
        """Test logging unknown tool attempt."""
        service = SecurityService()

        event = await service.log_unknown_tool_attempt(
            tool_name="invalid_tool",
            session_id="test-session",
            parameters={"arg1": "value1"},
        )

        assert event.event_type == "unknown_tool_attempt"
        assert event.severity == "medium"
        assert event.tool_name == "invalid_tool"
        assert "invalid_tool" in event.message

    async def test_log_injection_attempt(self):
        """Test logging injection attempt."""
        service = SecurityService()

        event = await service.log_injection_attempt(
            tool_name="check_tag_compliance",
            violation_type="sql_injection",
            field_name="resource_types",
            session_id="test-session",
        )

        assert event.event_type == "injection_attempt"
        assert event.severity == "high"
        assert event.tool_name == "check_tag_compliance"
        assert event.details["violation_type"] == "sql_injection"
        assert event.details["field_name"] == "resource_types"

    async def test_log_validation_bypass_attempt(self):
        """Test logging validation bypass attempt."""
        service = SecurityService()

        event = await service.log_validation_bypass_attempt(
            tool_name="validate_resource_tags",
            violation_type="excessive_nesting",
            session_id="test-session",
        )

        assert event.event_type == "validation_bypass_attempt"
        assert event.severity == "high"
        assert event.tool_name == "validate_resource_tags"
        assert event.details["violation_type"] == "excessive_nesting"

    async def test_check_unknown_tool_rate_limit_not_blocked(self):
        """Test rate limit check when under limit."""
        service = SecurityService(max_unknown_tool_attempts=3)

        # First attempt
        is_blocked, count, max_attempts = await service.check_unknown_tool_rate_limit(
            session_id="test-session",
            tool_name="invalid_tool",
        )

        assert not is_blocked
        assert count == 1
        assert max_attempts == 3

    async def test_check_unknown_tool_rate_limit_blocked(self):
        """Test rate limit check when limit exceeded."""
        service = SecurityService(max_unknown_tool_attempts=2)

        # Make multiple attempts
        for _ in range(2):
            await service.check_unknown_tool_rate_limit(
                session_id="test-session",
                tool_name="invalid_tool",
            )

        # Third attempt should be blocked
        is_blocked, count, max_attempts = await service.check_unknown_tool_rate_limit(
            session_id="test-session",
            tool_name="invalid_tool",
        )

        assert is_blocked
        assert count == 3
        assert max_attempts == 2

    async def test_get_security_metrics(self):
        """Test getting security metrics."""
        service = SecurityService()

        # Log some events
        await service.log_unknown_tool_attempt("tool1", "session1")
        await service.log_unknown_tool_attempt("tool2", "session1")
        await service.log_injection_attempt("tool3", "sql_injection", "field1", "session2")

        metrics = await service.get_security_metrics()

        assert metrics["total_events"] == 3
        assert metrics["events_by_type"]["unknown_tool_attempt"] == 2
        assert metrics["events_by_type"]["injection_attempt"] == 1
        assert metrics["events_by_severity"]["medium"] == 2
        assert metrics["events_by_severity"]["high"] == 1

    async def test_get_recent_events(self):
        """Test getting recent security events."""
        service = SecurityService()

        # Log some events
        await service.log_unknown_tool_attempt("tool1", "session1")
        await service.log_injection_attempt("tool2", "sql_injection", "field1", "session1")

        events = await service.get_recent_events(limit=10)

        assert len(events) == 2
        assert events[0]["event_type"] == "injection_attempt"
        assert events[1]["event_type"] == "unknown_tool_attempt"

    async def test_get_recent_events_with_limit(self):
        """Test getting recent events with limit."""
        service = SecurityService()

        # Log multiple events
        for i in range(5):
            await service.log_unknown_tool_attempt(f"tool{i}", "session1")

        events = await service.get_recent_events(limit=3)

        assert len(events) == 3

    async def test_get_recent_events_by_type(self):
        """Test filtering recent events by type."""
        service = SecurityService()

        # Log different types of events
        await service.log_unknown_tool_attempt("tool1", "session1")
        await service.log_injection_attempt("tool2", "sql_injection", "field1", "session1")
        await service.log_unknown_tool_attempt("tool3", "session1")

        events = await service.get_recent_events(
            limit=10,
            event_type="unknown_tool_attempt",
        )

        assert len(events) == 2
        assert all(e["event_type"] == "unknown_tool_attempt" for e in events)

    async def test_get_recent_events_by_session(self):
        """Test filtering recent events by session."""
        service = SecurityService()

        # Log events for different sessions
        await service.log_unknown_tool_attempt("tool1", "session1")
        await service.log_unknown_tool_attempt("tool2", "session2")
        await service.log_unknown_tool_attempt("tool3", "session1")

        events = await service.get_recent_events(
            limit=10,
            session_id="session1",
        )

        assert len(events) == 2
        assert all(e["session_id"] == "session1" for e in events)

    async def test_reset_session(self):
        """Test resetting rate limiting for a session."""
        service = SecurityService(max_unknown_tool_attempts=2)

        # Make some attempts
        await service.check_unknown_tool_rate_limit("test-session", "tool1")
        await service.check_unknown_tool_rate_limit("test-session", "tool2")

        # Reset the session
        await service.reset_session("test-session")

        # Should be able to make attempts again
        is_blocked, count, _ = await service.check_unknown_tool_rate_limit("test-session", "tool3")

        assert not is_blocked
        assert count == 1

    async def test_security_metrics_rate_limit_config(self):
        """Test that security metrics include rate limit configuration."""
        service = SecurityService(
            max_unknown_tool_attempts=5,
            window_seconds=120,
        )

        metrics = await service.get_security_metrics()

        assert metrics["rate_limit_config"]["max_unknown_tool_attempts"] == 5
        assert metrics["rate_limit_config"]["window_seconds"] == 120
        assert "redis_enabled" in metrics
