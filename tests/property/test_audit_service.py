"""
Property-based tests for AuditService.

Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
Validates: Requirements 12.1, 12.3, 12.4

Property 12 states:
*For any* tool invocation, an audit log entry SHALL be created containing:
timestamp, tool name, parameters, and result status (success/failure).
When an error occurs, the error message SHALL be included in the log entry.
"""

import os
import tempfile
import re
from datetime import datetime, timezone
from hypothesis import given, strategies as st, settings
import pytest

from mcp_server.models.audit import AuditLogEntry, AuditStatus
from mcp_server.services.audit_service import AuditService


# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def tool_name_strategy(draw):
    """Generate valid tool names."""
    # Tool names should be valid Python identifiers
    first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz_"))
    rest = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_", min_size=0, max_size=50))
    return first_char + rest


@st.composite
def parameters_strategy(draw):
    """Generate valid parameter dictionaries."""
    # Generate simple parameter dictionaries with safe values
    num_params = draw(st.integers(min_value=0, max_value=5))
    params = {}
    for i in range(num_params):
        key = f"param_{i}"
        value_type = draw(st.sampled_from(["string", "int", "bool", "none"]))
        if value_type == "string":
            # Use ASCII-only strings to avoid encoding issues
            params[key] = draw(
                st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=0, max_size=20)
            )
        elif value_type == "int":
            params[key] = draw(st.integers(min_value=-1000, max_value=1000))
        elif value_type == "bool":
            params[key] = draw(st.booleans())
        else:
            params[key] = None
    return params


@st.composite
def error_message_strategy(draw):
    """Generate valid error messages."""
    # Use ASCII-only strings to avoid encoding issues
    return draw(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 .,!?-_", min_size=1, max_size=100)
    )


@st.composite
def execution_time_strategy(draw):
    """Generate valid execution times in milliseconds."""
    return draw(st.floats(min_value=0.0, max_value=60000.0, allow_nan=False, allow_infinity=False))


# =============================================================================
# Helper function to create temp database
# =============================================================================


def create_temp_db():
    """Create a temporary database file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return path


def cleanup_temp_db(path):
    """Clean up a temporary database file."""
    if os.path.exists(path):
        os.unlink(path)


# =============================================================================
# Property 12: Audit Log Completeness
# =============================================================================


class TestAuditLogCompleteness:
    """
    Property 12: Audit Log Completeness

    For any tool invocation, an audit log entry SHALL be created containing:
    timestamp, tool name, parameters, and result status (success/failure).
    When an error occurs, the error message SHALL be included in the log entry.

    Validates: Requirements 12.1, 12.3, 12.4
    """

    # -------------------------------------------------------------------------
    # Timestamp Tests (Requirement 12.1)
    # -------------------------------------------------------------------------

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_entry_contains_timestamp(
        self,
        tool_name: str,
        parameters: dict,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1

        Every audit log entry SHALL contain a timestamp.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            before_log = datetime.now(timezone.utc)

            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
            )

            after_log = datetime.now(timezone.utc)

            # Entry must have a timestamp
            assert entry.timestamp is not None, "Audit entry must have a timestamp"
            assert isinstance(entry.timestamp, datetime), "Timestamp must be a datetime object"

            # Timestamp should be between before and after the log call
            entry_ts = entry.timestamp.replace(tzinfo=None)
            before_ts = before_log.replace(tzinfo=None)
            after_ts = after_log.replace(tzinfo=None)

            assert (
                before_ts <= entry_ts <= after_ts
            ), f"Timestamp {entry_ts} should be between {before_ts} and {after_ts}"
        finally:
            cleanup_temp_db(temp_db)

    # -------------------------------------------------------------------------
    # Tool Name Tests (Requirement 12.1)
    # -------------------------------------------------------------------------

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_entry_contains_tool_name(
        self,
        tool_name: str,
        parameters: dict,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1

        Every audit log entry SHALL contain the tool name.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
            )

            # Entry must have the correct tool name
            assert entry.tool_name is not None, "Audit entry must have a tool name"
            assert (
                entry.tool_name == tool_name
            ), f"Tool name should be '{tool_name}', got '{entry.tool_name}'"
        finally:
            cleanup_temp_db(temp_db)

    # -------------------------------------------------------------------------
    # Parameters Tests (Requirement 12.1)
    # -------------------------------------------------------------------------

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_entry_contains_parameters(
        self,
        tool_name: str,
        parameters: dict,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1

        Every audit log entry SHALL contain the parameters passed to the tool.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
            )

            # Entry must have parameters
            assert entry.parameters is not None, "Audit entry must have parameters"
            assert (
                entry.parameters == parameters
            ), f"Parameters should be '{parameters}', got '{entry.parameters}'"
        finally:
            cleanup_temp_db(temp_db)

    # -------------------------------------------------------------------------
    # Status Tests (Requirement 12.3)
    # -------------------------------------------------------------------------

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
        status=st.sampled_from([AuditStatus.SUCCESS, AuditStatus.FAILURE]),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_entry_contains_status(
        self,
        tool_name: str,
        parameters: dict,
        status: AuditStatus,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.3

        Every audit log entry SHALL contain the result status (success/failure).
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            error_message = "Test error" if status == AuditStatus.FAILURE else None

            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=status,
                error_message=error_message,
            )

            # Entry must have the correct status
            assert entry.status is not None, "Audit entry must have a status"
            assert entry.status == status, f"Status should be '{status}', got '{entry.status}'"
        finally:
            cleanup_temp_db(temp_db)

    # -------------------------------------------------------------------------
    # Error Message Tests (Requirement 12.4)
    # -------------------------------------------------------------------------

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
        error_message=error_message_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_entry_contains_error_message_on_failure(
        self,
        tool_name: str,
        parameters: dict,
        error_message: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.4

        When an error occurs, the error message SHALL be included in the log entry.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.FAILURE,
                error_message=error_message,
            )

            # Entry must have the error message
            assert (
                entry.error_message is not None
            ), "Audit entry for failure must have an error message"
            assert (
                entry.error_message == error_message
            ), f"Error message should be '{error_message}', got '{entry.error_message}'"
        finally:
            cleanup_temp_db(temp_db)

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_entry_no_error_message_on_success(
        self,
        tool_name: str,
        parameters: dict,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.3, 12.4

        When a tool succeeds, the error message SHALL be None.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
            )

            # Entry should not have an error message on success
            assert (
                entry.error_message is None
            ), f"Audit entry for success should not have error message, got '{entry.error_message}'"
        finally:
            cleanup_temp_db(temp_db)

    # -------------------------------------------------------------------------
    # Persistence Tests (Requirement 12.2)
    # -------------------------------------------------------------------------

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
        status=st.sampled_from([AuditStatus.SUCCESS, AuditStatus.FAILURE]),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_entry_persisted_to_database(
        self,
        tool_name: str,
        parameters: dict,
        status: AuditStatus,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1, 12.2

        Audit log entries SHALL be stored in SQLite database and retrievable.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            error_message = "Test error" if status == AuditStatus.FAILURE else None

            # Log the invocation
            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=status,
                error_message=error_message,
            )

            # Retrieve logs
            logs = service.get_logs(tool_name=tool_name)

            # Should find the logged entry
            assert len(logs) >= 1, "Should have at least one log entry"

            # Find our entry
            found = False
            for log in logs:
                if log.id == entry.id:
                    found = True
                    assert log.tool_name == tool_name
                    assert log.parameters == parameters
                    assert log.status == status
                    if status == AuditStatus.FAILURE:
                        assert log.error_message == error_message
                    break

            assert found, f"Could not find logged entry with id {entry.id}"
        finally:
            cleanup_temp_db(temp_db)

    # -------------------------------------------------------------------------
    # Complete Entry Tests (All Requirements)
    # -------------------------------------------------------------------------

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
        execution_time=execution_time_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_successful_invocation_complete_entry(
        self,
        tool_name: str,
        parameters: dict,
        execution_time: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1, 12.3

        For any successful tool invocation, the audit log entry SHALL contain:
        timestamp, tool name, parameters, and success status.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
                execution_time_ms=execution_time,
            )

            # Verify all required fields are present
            assert entry.timestamp is not None, "Must have timestamp"
            assert entry.tool_name == tool_name, "Must have correct tool name"
            assert entry.parameters == parameters, "Must have correct parameters"
            assert entry.status == AuditStatus.SUCCESS, "Must have success status"
            assert entry.error_message is None, "Success should not have error message"
            assert entry.execution_time_ms == execution_time, "Must have execution time"
        finally:
            cleanup_temp_db(temp_db)

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
        error_message=error_message_strategy(),
        execution_time=execution_time_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_failed_invocation_complete_entry(
        self,
        tool_name: str,
        parameters: dict,
        error_message: str,
        execution_time: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1, 12.3, 12.4

        For any failed tool invocation, the audit log entry SHALL contain:
        timestamp, tool name, parameters, failure status, and error message.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.FAILURE,
                error_message=error_message,
                execution_time_ms=execution_time,
            )

            # Verify all required fields are present
            assert entry.timestamp is not None, "Must have timestamp"
            assert entry.tool_name == tool_name, "Must have correct tool name"
            assert entry.parameters == parameters, "Must have correct parameters"
            assert entry.status == AuditStatus.FAILURE, "Must have failure status"
            assert entry.error_message == error_message, "Must have error message"
            assert entry.execution_time_ms == execution_time, "Must have execution time"
        finally:
            cleanup_temp_db(temp_db)

    # -------------------------------------------------------------------------
    # Middleware Integration Tests
    # -------------------------------------------------------------------------

    @given(
        return_value=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=0, max_size=50
        ),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_audit_middleware_logs_successful_async_invocation(
        self,
        return_value: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1, 12.3

        The audit middleware SHALL log successful async tool invocations
        with all required fields.
        """
        import functools
        import time

        temp_db = create_temp_db()
        try:
            # Create a custom audit_tool decorator that uses our temp db
            def custom_audit_tool(tool_func):
                @functools.wraps(tool_func)
                async def wrapper(*args, **kwargs):
                    audit_service = AuditService(db_path=temp_db)
                    tool_name = tool_func.__name__
                    start_time = time.time()

                    parameters = {"args": args, "kwargs": kwargs}

                    try:
                        result = await tool_func(*args, **kwargs)
                        execution_time_ms = (time.time() - start_time) * 1000

                        audit_service.log_invocation(
                            tool_name=tool_name,
                            parameters=parameters,
                            status=AuditStatus.SUCCESS,
                            execution_time_ms=execution_time_ms,
                        )
                        return result
                    except Exception as e:
                        execution_time_ms = (time.time() - start_time) * 1000
                        audit_service.log_invocation(
                            tool_name=tool_name,
                            parameters=parameters,
                            status=AuditStatus.FAILURE,
                            error_message=str(e),
                            execution_time_ms=execution_time_ms,
                        )
                        raise

                return wrapper

            @custom_audit_tool
            async def test_async_tool(value: str) -> str:
                return value

            # Call the decorated function
            result = await test_async_tool(return_value)

            assert result == return_value

            # Check audit log
            service = AuditService(db_path=temp_db)
            logs = service.get_logs()

            assert len(logs) >= 1, "Should have at least one log entry"

            log = logs[0]
            assert log.tool_name == "test_async_tool"
            assert log.status == AuditStatus.SUCCESS
            assert log.timestamp is not None
            assert log.parameters is not None
            assert log.error_message is None
        finally:
            cleanup_temp_db(temp_db)

    @given(
        error_msg=error_message_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_audit_middleware_logs_failed_async_invocation(
        self,
        error_msg: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1, 12.3, 12.4

        The audit middleware SHALL log failed async tool invocations
        with all required fields including error message.
        """
        import functools
        import time

        temp_db = create_temp_db()
        try:
            # Create a custom audit_tool decorator that uses our temp db
            def custom_audit_tool(tool_func):
                @functools.wraps(tool_func)
                async def wrapper(*args, **kwargs):
                    audit_service = AuditService(db_path=temp_db)
                    tool_name = tool_func.__name__
                    start_time = time.time()

                    parameters = {"args": args, "kwargs": kwargs}

                    try:
                        result = await tool_func(*args, **kwargs)
                        execution_time_ms = (time.time() - start_time) * 1000

                        audit_service.log_invocation(
                            tool_name=tool_name,
                            parameters=parameters,
                            status=AuditStatus.SUCCESS,
                            execution_time_ms=execution_time_ms,
                        )
                        return result
                    except Exception as e:
                        execution_time_ms = (time.time() - start_time) * 1000
                        audit_service.log_invocation(
                            tool_name=tool_name,
                            parameters=parameters,
                            status=AuditStatus.FAILURE,
                            error_message=str(e),
                            execution_time_ms=execution_time_ms,
                        )
                        raise

                return wrapper

            @custom_audit_tool
            async def failing_async_tool() -> str:
                raise ValueError(error_msg)

            # Call the decorated function
            with pytest.raises(ValueError, match=re.escape(error_msg)):
                await failing_async_tool()

            # Check audit log
            service = AuditService(db_path=temp_db)
            logs = service.get_logs()

            assert len(logs) >= 1, "Should have at least one log entry"

            log = logs[0]
            assert log.tool_name == "failing_async_tool"
            assert log.status == AuditStatus.FAILURE
            assert log.timestamp is not None
            assert log.parameters is not None
            assert log.error_message == error_msg
        finally:
            cleanup_temp_db(temp_db)

    @given(
        return_value=st.integers(min_value=-1000, max_value=1000),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_middleware_logs_successful_sync_invocation(
        self,
        return_value: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1, 12.3

        The audit middleware SHALL log successful sync tool invocations
        with all required fields.
        """
        import functools
        import time

        temp_db = create_temp_db()
        try:
            # Create a custom audit_tool_sync decorator that uses our temp db
            def custom_audit_tool_sync(tool_func):
                @functools.wraps(tool_func)
                def wrapper(*args, **kwargs):
                    audit_service = AuditService(db_path=temp_db)
                    tool_name = tool_func.__name__
                    start_time = time.time()

                    parameters = {"args": args, "kwargs": kwargs}

                    try:
                        result = tool_func(*args, **kwargs)
                        execution_time_ms = (time.time() - start_time) * 1000

                        audit_service.log_invocation(
                            tool_name=tool_name,
                            parameters=parameters,
                            status=AuditStatus.SUCCESS,
                            execution_time_ms=execution_time_ms,
                        )
                        return result
                    except Exception as e:
                        execution_time_ms = (time.time() - start_time) * 1000
                        audit_service.log_invocation(
                            tool_name=tool_name,
                            parameters=parameters,
                            status=AuditStatus.FAILURE,
                            error_message=str(e),
                            execution_time_ms=execution_time_ms,
                        )
                        raise

                return wrapper

            @custom_audit_tool_sync
            def test_sync_tool(value: int) -> int:
                return value * 2

            # Call the decorated function
            result = test_sync_tool(return_value)

            assert result == return_value * 2

            # Check audit log
            service = AuditService(db_path=temp_db)
            logs = service.get_logs()

            assert len(logs) >= 1, "Should have at least one log entry"

            log = logs[0]
            assert log.tool_name == "test_sync_tool"
            assert log.status == AuditStatus.SUCCESS
            assert log.timestamp is not None
            assert log.parameters is not None
            assert log.error_message is None
        finally:
            cleanup_temp_db(temp_db)

    @given(
        error_msg=error_message_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_middleware_logs_failed_sync_invocation(
        self,
        error_msg: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1, 12.3, 12.4

        The audit middleware SHALL log failed sync tool invocations
        with all required fields including error message.
        """
        import functools
        import time

        temp_db = create_temp_db()
        try:
            # Create a custom audit_tool_sync decorator that uses our temp db
            def custom_audit_tool_sync(tool_func):
                @functools.wraps(tool_func)
                def wrapper(*args, **kwargs):
                    audit_service = AuditService(db_path=temp_db)
                    tool_name = tool_func.__name__
                    start_time = time.time()

                    parameters = {"args": args, "kwargs": kwargs}

                    try:
                        result = tool_func(*args, **kwargs)
                        execution_time_ms = (time.time() - start_time) * 1000

                        audit_service.log_invocation(
                            tool_name=tool_name,
                            parameters=parameters,
                            status=AuditStatus.SUCCESS,
                            execution_time_ms=execution_time_ms,
                        )
                        return result
                    except Exception as e:
                        execution_time_ms = (time.time() - start_time) * 1000
                        audit_service.log_invocation(
                            tool_name=tool_name,
                            parameters=parameters,
                            status=AuditStatus.FAILURE,
                            error_message=str(e),
                            execution_time_ms=execution_time_ms,
                        )
                        raise

                return wrapper

            @custom_audit_tool_sync
            def failing_sync_tool() -> str:
                raise RuntimeError(error_msg)

            # Call the decorated function
            with pytest.raises(RuntimeError, match=re.escape(error_msg)):
                failing_sync_tool()

            # Check audit log
            service = AuditService(db_path=temp_db)
            logs = service.get_logs()

            assert len(logs) >= 1, "Should have at least one log entry"

            log = logs[0]
            assert log.tool_name == "failing_sync_tool"
            assert log.status == AuditStatus.FAILURE
            assert log.timestamp is not None
            assert log.parameters is not None
            assert log.error_message == error_msg
        finally:
            cleanup_temp_db(temp_db)

    # -------------------------------------------------------------------------
    # Multiple Invocations Tests
    # -------------------------------------------------------------------------

    @given(
        num_invocations=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=50, deadline=None)
    def test_multiple_invocations_all_logged(
        self,
        num_invocations: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 12: Audit Log Completeness
        Validates: Requirements 12.1

        For any number of tool invocations, each SHALL create a separate
        audit log entry.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            # Log multiple invocations
            for i in range(num_invocations):
                service.log_invocation(
                    tool_name=f"tool_{i}",
                    parameters={"index": i},
                    status=AuditStatus.SUCCESS if i % 2 == 0 else AuditStatus.FAILURE,
                    error_message=f"Error {i}" if i % 2 != 0 else None,
                )

            # Retrieve all logs
            logs = service.get_logs(limit=num_invocations + 10)

            # Should have exactly num_invocations entries
            assert (
                len(logs) == num_invocations
            ), f"Expected {num_invocations} log entries, got {len(logs)}"
        finally:
            cleanup_temp_db(temp_db)
