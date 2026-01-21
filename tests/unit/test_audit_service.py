"""Unit tests for AuditService."""

import os
import tempfile
from datetime import datetime

import pytest

from mcp_server.models.audit import AuditLogEntry, AuditStatus
from mcp_server.services.audit_service import AuditService
from mcp_server.utils.correlation import set_correlation_id, get_correlation_id


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def audit_service(temp_db):
    """Create an AuditService instance with a temporary database."""
    return AuditService(db_path=temp_db)


def test_audit_service_initialization(audit_service):
    """Test that AuditService initializes the database correctly."""
    # The database should be created and initialized
    assert os.path.exists(audit_service.db_path)


def test_log_successful_invocation(audit_service):
    """Test logging a successful tool invocation."""
    tool_name = "check_tag_compliance"
    parameters = {"resource_types": ["ec2:instance"], "severity": "all"}

    entry = audit_service.log_invocation(
        tool_name=tool_name,
        parameters=parameters,
        status=AuditStatus.SUCCESS,
        execution_time_ms=123.45,
    )

    assert entry.id is not None
    assert entry.tool_name == tool_name
    assert entry.parameters == parameters
    assert entry.status == AuditStatus.SUCCESS
    assert entry.error_message is None
    assert entry.execution_time_ms == 123.45
    assert isinstance(entry.timestamp, datetime)


def test_log_failed_invocation(audit_service):
    """Test logging a failed tool invocation."""
    tool_name = "find_untagged_resources"
    parameters = {"min_cost_threshold": 100}
    error_msg = "AWS API rate limit exceeded"

    entry = audit_service.log_invocation(
        tool_name=tool_name,
        parameters=parameters,
        status=AuditStatus.FAILURE,
        error_message=error_msg,
        execution_time_ms=50.0,
    )

    assert entry.id is not None
    assert entry.tool_name == tool_name
    assert entry.parameters == parameters
    assert entry.status == AuditStatus.FAILURE
    assert entry.error_message == error_msg
    assert entry.execution_time_ms == 50.0


def test_get_logs_all(audit_service):
    """Test retrieving all audit logs."""
    # Log multiple invocations
    audit_service.log_invocation(
        tool_name="tool1",
        parameters={"param": "value1"},
        status=AuditStatus.SUCCESS,
    )
    audit_service.log_invocation(
        tool_name="tool2",
        parameters={"param": "value2"},
        status=AuditStatus.FAILURE,
        error_message="Error occurred",
    )

    logs = audit_service.get_logs()

    assert len(logs) == 2
    # Logs should be in reverse chronological order
    assert logs[0].tool_name == "tool2"
    assert logs[1].tool_name == "tool1"


def test_get_logs_filter_by_tool_name(audit_service):
    """Test filtering logs by tool name."""
    audit_service.log_invocation(
        tool_name="check_tag_compliance",
        parameters={},
        status=AuditStatus.SUCCESS,
    )
    audit_service.log_invocation(
        tool_name="find_untagged_resources",
        parameters={},
        status=AuditStatus.SUCCESS,
    )
    audit_service.log_invocation(
        tool_name="check_tag_compliance",
        parameters={},
        status=AuditStatus.FAILURE,
        error_message="Error",
    )

    logs = audit_service.get_logs(tool_name="check_tag_compliance")

    assert len(logs) == 2
    assert all(log.tool_name == "check_tag_compliance" for log in logs)


def test_get_logs_filter_by_status(audit_service):
    """Test filtering logs by status."""
    audit_service.log_invocation(
        tool_name="tool1",
        parameters={},
        status=AuditStatus.SUCCESS,
    )
    audit_service.log_invocation(
        tool_name="tool2",
        parameters={},
        status=AuditStatus.FAILURE,
        error_message="Error 1",
    )
    audit_service.log_invocation(
        tool_name="tool3",
        parameters={},
        status=AuditStatus.FAILURE,
        error_message="Error 2",
    )

    logs = audit_service.get_logs(status=AuditStatus.FAILURE)

    assert len(logs) == 2
    assert all(log.status == AuditStatus.FAILURE for log in logs)
    assert all(log.error_message is not None for log in logs)


def test_get_logs_with_limit(audit_service):
    """Test limiting the number of logs returned."""
    # Log 10 invocations
    for i in range(10):
        audit_service.log_invocation(
            tool_name=f"tool{i}",
            parameters={"index": i},
            status=AuditStatus.SUCCESS,
        )

    logs = audit_service.get_logs(limit=5)

    assert len(logs) == 5


def test_get_logs_combined_filters(audit_service):
    """Test combining multiple filters."""
    audit_service.log_invocation(
        tool_name="check_tag_compliance",
        parameters={},
        status=AuditStatus.SUCCESS,
    )
    audit_service.log_invocation(
        tool_name="check_tag_compliance",
        parameters={},
        status=AuditStatus.FAILURE,
        error_message="Error",
    )
    audit_service.log_invocation(
        tool_name="find_untagged_resources",
        parameters={},
        status=AuditStatus.FAILURE,
        error_message="Error",
    )

    logs = audit_service.get_logs(
        tool_name="check_tag_compliance",
        status=AuditStatus.FAILURE,
    )

    assert len(logs) == 1
    assert logs[0].tool_name == "check_tag_compliance"
    assert logs[0].status == AuditStatus.FAILURE


def test_log_invocation_with_complex_parameters(audit_service):
    """Test logging with complex nested parameters."""
    complex_params = {
        "resource_types": ["ec2:instance", "rds:db"],
        "filters": {
            "region": "us-east-1",
            "account_id": "123456789012",
        },
        "severity": "errors_only",
        "nested": {
            "deep": {
                "value": [1, 2, 3],
            }
        },
    }

    entry = audit_service.log_invocation(
        tool_name="check_tag_compliance",
        parameters=complex_params,
        status=AuditStatus.SUCCESS,
    )

    assert entry.parameters == complex_params


def test_multiple_audit_service_instances(temp_db):
    """Test that multiple instances can access the same database."""
    service1 = AuditService(db_path=temp_db)
    service2 = AuditService(db_path=temp_db)

    # Log with first instance
    service1.log_invocation(
        tool_name="tool1",
        parameters={},
        status=AuditStatus.SUCCESS,
    )

    # Retrieve with second instance
    logs = service2.get_logs()

    assert len(logs) == 1
    assert logs[0].tool_name == "tool1"


def test_log_invocation_with_explicit_correlation_id(audit_service):
    """Test logging with an explicitly provided correlation ID."""
    correlation_id = "test-correlation-123"

    entry = audit_service.log_invocation(
        tool_name="check_tag_compliance",
        parameters={"resource_types": ["ec2:instance"]},
        status=AuditStatus.SUCCESS,
        correlation_id=correlation_id,
    )

    assert entry.correlation_id == correlation_id


def test_log_invocation_captures_correlation_id_from_context(audit_service):
    """Test that correlation ID is automatically captured from context."""
    correlation_id = "context-correlation-456"

    # Set correlation ID in context
    set_correlation_id(correlation_id)

    try:
        entry = audit_service.log_invocation(
            tool_name="find_untagged_resources",
            parameters={"min_cost_threshold": 100},
            status=AuditStatus.SUCCESS,
        )

        assert entry.correlation_id == correlation_id
    finally:
        # Clean up context
        set_correlation_id("")


def test_log_invocation_without_correlation_id(audit_service):
    """Test logging when no correlation ID is available."""
    # Ensure no correlation ID in context
    set_correlation_id("")

    entry = audit_service.log_invocation(
        tool_name="validate_resource_tags",
        parameters={
            "resource_arns": ["arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"]
        },
        status=AuditStatus.SUCCESS,
    )

    assert entry.correlation_id is None


def test_get_logs_filter_by_correlation_id(audit_service):
    """Test filtering logs by correlation ID."""
    correlation_id_1 = "correlation-1"
    correlation_id_2 = "correlation-2"

    # Log with different correlation IDs
    audit_service.log_invocation(
        tool_name="tool1",
        parameters={},
        status=AuditStatus.SUCCESS,
        correlation_id=correlation_id_1,
    )
    audit_service.log_invocation(
        tool_name="tool2",
        parameters={},
        status=AuditStatus.SUCCESS,
        correlation_id=correlation_id_2,
    )
    audit_service.log_invocation(
        tool_name="tool3",
        parameters={},
        status=AuditStatus.FAILURE,
        error_message="Error",
        correlation_id=correlation_id_1,
    )

    # Filter by correlation_id_1
    logs = audit_service.get_logs(correlation_id=correlation_id_1)

    assert len(logs) == 2
    assert all(log.correlation_id == correlation_id_1 for log in logs)
    assert {log.tool_name for log in logs} == {"tool1", "tool3"}


def test_get_logs_combined_filters_with_correlation_id(audit_service):
    """Test combining correlation ID filter with other filters."""
    correlation_id = "test-correlation"

    audit_service.log_invocation(
        tool_name="check_tag_compliance",
        parameters={},
        status=AuditStatus.SUCCESS,
        correlation_id=correlation_id,
    )
    audit_service.log_invocation(
        tool_name="check_tag_compliance",
        parameters={},
        status=AuditStatus.FAILURE,
        error_message="Error",
        correlation_id=correlation_id,
    )
    audit_service.log_invocation(
        tool_name="find_untagged_resources",
        parameters={},
        status=AuditStatus.FAILURE,
        error_message="Error",
        correlation_id=correlation_id,
    )
    audit_service.log_invocation(
        tool_name="check_tag_compliance",
        parameters={},
        status=AuditStatus.FAILURE,
        error_message="Error",
        correlation_id="different-correlation",
    )

    # Filter by tool name, status, and correlation ID
    logs = audit_service.get_logs(
        tool_name="check_tag_compliance",
        status=AuditStatus.FAILURE,
        correlation_id=correlation_id,
    )

    assert len(logs) == 1
    assert logs[0].tool_name == "check_tag_compliance"
    assert logs[0].status == AuditStatus.FAILURE
    assert logs[0].correlation_id == correlation_id


def test_correlation_id_persists_across_queries(audit_service):
    """Test that correlation ID is properly stored and retrieved."""
    correlation_id = "persistent-correlation-789"

    # Log an entry
    audit_service.log_invocation(
        tool_name="suggest_tags",
        parameters={"resource_arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-test"},
        status=AuditStatus.SUCCESS,
        execution_time_ms=250.5,
        correlation_id=correlation_id,
    )

    # Retrieve all logs
    logs = audit_service.get_logs()

    assert len(logs) == 1
    assert logs[0].correlation_id == correlation_id
    assert logs[0].tool_name == "suggest_tags"
    assert logs[0].execution_time_ms == 250.5
