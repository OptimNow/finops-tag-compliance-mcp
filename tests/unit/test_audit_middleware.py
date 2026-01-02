"""Unit tests for audit middleware."""

import os
import tempfile

import pytest

from mcp_server.middleware.audit_middleware import audit_tool, audit_tool_sync
from mcp_server.models.audit import AuditStatus
from mcp_server.services.audit_service import AuditService
from mcp_server.utils.correlation import set_correlation_id


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture(autouse=True)
def setup_audit_db(temp_db, monkeypatch):
    """Set up audit service to use temporary database."""
    # Monkey patch the AuditService to use temp db
    original_init = AuditService.__init__
    
    def patched_init(self, db_path=None):
        original_init(self, db_path=temp_db)
    
    monkeypatch.setattr(AuditService, "__init__", patched_init)
    yield temp_db


@pytest.mark.asyncio
async def test_audit_tool_success(setup_audit_db):
    """Test that audit_tool logs successful invocations."""
    
    @audit_tool
    async def sample_tool(param1: str, param2: int = 10) -> str:
        return f"Result: {param1}-{param2}"
    
    # Call the decorated function
    result = await sample_tool("test", param2=20)
    
    assert result == "Result: test-20"
    
    # Check audit log
    audit_service = AuditService()
    logs = audit_service.get_logs()
    
    assert len(logs) == 1
    assert logs[0].tool_name == "sample_tool"
    assert logs[0].status == AuditStatus.SUCCESS
    assert logs[0].error_message is None
    assert logs[0].execution_time_ms is not None
    assert logs[0].execution_time_ms > 0


@pytest.mark.asyncio
async def test_audit_tool_failure(setup_audit_db):
    """Test that audit_tool logs failed invocations."""
    
    @audit_tool
    async def failing_tool(should_fail: bool) -> str:
        if should_fail:
            raise ValueError("Tool failed intentionally")
        return "Success"
    
    # Call the decorated function with failure
    with pytest.raises(ValueError, match="Tool failed intentionally"):
        await failing_tool(True)
    
    # Check audit log
    audit_service = AuditService()
    logs = audit_service.get_logs()
    
    assert len(logs) == 1
    assert logs[0].tool_name == "failing_tool"
    assert logs[0].status == AuditStatus.FAILURE
    assert logs[0].error_message == "Tool failed intentionally"
    assert logs[0].execution_time_ms is not None


@pytest.mark.asyncio
async def test_audit_tool_captures_parameters(setup_audit_db):
    """Test that audit_tool captures function parameters."""
    
    @audit_tool
    async def tool_with_params(
        resource_types: list[str],
        filters: dict | None = None,
        severity: str = "all"
    ) -> dict:
        return {"result": "ok"}
    
    # Call with various parameters
    await tool_with_params(
        resource_types=["ec2:instance", "rds:db"],
        filters={"region": "us-east-1"},
        severity="errors_only"
    )
    
    # Check audit log
    audit_service = AuditService()
    logs = audit_service.get_logs()
    
    assert len(logs) == 1
    assert logs[0].tool_name == "tool_with_params"
    # Parameters should be captured
    assert "kwargs" in logs[0].parameters


def test_audit_tool_sync_success(setup_audit_db):
    """Test that audit_tool_sync logs successful synchronous invocations."""
    
    @audit_tool_sync
    def sync_tool(value: int) -> int:
        return value * 2
    
    # Call the decorated function
    result = sync_tool(5)
    
    assert result == 10
    
    # Check audit log
    audit_service = AuditService()
    logs = audit_service.get_logs()
    
    assert len(logs) == 1
    assert logs[0].tool_name == "sync_tool"
    assert logs[0].status == AuditStatus.SUCCESS
    assert logs[0].error_message is None


def test_audit_tool_sync_failure(setup_audit_db):
    """Test that audit_tool_sync logs failed synchronous invocations."""
    
    @audit_tool_sync
    def failing_sync_tool() -> None:
        raise RuntimeError("Sync tool failed")
    
    # Call the decorated function
    with pytest.raises(RuntimeError, match="Sync tool failed"):
        failing_sync_tool()
    
    # Check audit log
    audit_service = AuditService()
    logs = audit_service.get_logs()
    
    assert len(logs) == 1
    assert logs[0].tool_name == "failing_sync_tool"
    assert logs[0].status == AuditStatus.FAILURE
    assert logs[0].error_message == "Sync tool failed"


@pytest.mark.asyncio
async def test_multiple_tool_invocations(setup_audit_db):
    """Test logging multiple tool invocations."""
    
    @audit_tool
    async def tool1() -> str:
        return "tool1"
    
    @audit_tool
    async def tool2() -> str:
        return "tool2"
    
    # Call both tools
    await tool1()
    await tool2()
    await tool1()
    
    # Check audit logs
    audit_service = AuditService()
    logs = audit_service.get_logs()
    
    assert len(logs) == 3
    # Most recent first
    assert logs[0].tool_name == "tool1"
    assert logs[1].tool_name == "tool2"
    assert logs[2].tool_name == "tool1"


@pytest.mark.asyncio
async def test_audit_preserves_function_metadata(setup_audit_db):
    """Test that the decorator preserves function metadata."""
    
    @audit_tool
    async def documented_tool(param: str) -> str:
        """This is a documented tool."""
        return param
    
    # Check that metadata is preserved
    assert documented_tool.__name__ == "documented_tool"
    assert documented_tool.__doc__ == "This is a documented tool."


@pytest.mark.asyncio
async def test_audit_tool_captures_correlation_id_from_context(setup_audit_db):
    """Test that audit_tool captures correlation ID from context."""
    correlation_id = "test-correlation-123"
    
    @audit_tool
    async def tool_with_correlation() -> str:
        return "result"
    
    # Set correlation ID in context
    set_correlation_id(correlation_id)
    
    try:
        await tool_with_correlation()
        
        # Check audit log
        audit_service = AuditService()
        logs = audit_service.get_logs()
        
        assert len(logs) == 1
        assert logs[0].correlation_id == correlation_id
        assert logs[0].tool_name == "tool_with_correlation"
    finally:
        # Clean up context
        set_correlation_id("")


@pytest.mark.asyncio
async def test_audit_tool_without_correlation_id(setup_audit_db):
    """Test that audit_tool works when no correlation ID is set."""
    
    @audit_tool
    async def tool_without_correlation() -> str:
        return "result"
    
    # Ensure no correlation ID in context
    set_correlation_id("")
    
    await tool_without_correlation()
    
    # Check audit log
    audit_service = AuditService()
    logs = audit_service.get_logs()
    
    assert len(logs) == 1
    assert logs[0].correlation_id is None
    assert logs[0].tool_name == "tool_without_correlation"


def test_audit_tool_sync_captures_correlation_id(setup_audit_db):
    """Test that audit_tool_sync captures correlation ID from context."""
    correlation_id = "sync-correlation-456"
    
    @audit_tool_sync
    def sync_tool_with_correlation(value: int) -> int:
        return value * 2
    
    # Set correlation ID in context
    set_correlation_id(correlation_id)
    
    try:
        result = sync_tool_with_correlation(5)
        
        assert result == 10
        
        # Check audit log
        audit_service = AuditService()
        logs = audit_service.get_logs()
        
        assert len(logs) == 1
        assert logs[0].correlation_id == correlation_id
        assert logs[0].tool_name == "sync_tool_with_correlation"
    finally:
        # Clean up context
        set_correlation_id("")


@pytest.mark.asyncio
async def test_audit_tool_correlation_id_on_failure(setup_audit_db):
    """Test that correlation ID is captured even when tool fails."""
    correlation_id = "failure-correlation-789"
    
    @audit_tool
    async def failing_tool_with_correlation() -> str:
        raise ValueError("Tool failed")
    
    # Set correlation ID in context
    set_correlation_id(correlation_id)
    
    try:
        with pytest.raises(ValueError, match="Tool failed"):
            await failing_tool_with_correlation()
        
        # Check audit log
        audit_service = AuditService()
        logs = audit_service.get_logs()
        
        assert len(logs) == 1
        assert logs[0].correlation_id == correlation_id
        assert logs[0].status == AuditStatus.FAILURE
        assert logs[0].error_message == "Tool failed"
    finally:
        # Clean up context
        set_correlation_id("")
