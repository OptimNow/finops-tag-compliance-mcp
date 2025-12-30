"""Unit tests for AuditService."""

import os
import tempfile
from datetime import datetime

import pytest

from mcp_server.models.audit import AuditLogEntry, AuditStatus
from mcp_server.services.audit_service import AuditService


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
