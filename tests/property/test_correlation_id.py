# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""
Property-based tests for Correlation ID Propagation.

Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
Validates: Requirements 15.1

Property 16 states:
*For any* tool invocation, a unique correlation ID SHALL be generated and included
in all log entries, audit records, and trace spans related to that invocation.
The correlation ID SHALL be returned in the response headers or metadata.
"""

import logging
import os
import re
import tempfile

from hypothesis import given, settings
from hypothesis import strategies as st

from mcp_server.models.audit import AuditStatus
from mcp_server.services.audit_service import AuditService
from mcp_server.utils.cloudwatch_logger import CorrelationIDFilter
from mcp_server.utils.correlation import (
    generate_correlation_id,
    get_correlation_id,
    get_correlation_id_for_logging,
    set_correlation_id,
)

# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def uuid4_strategy(draw):
    """Generate valid UUID4 strings."""
    # UUID4 format: 8-4-4-4-12 hex digits
    hex_chars = "0123456789abcdef"
    part1 = draw(st.text(alphabet=hex_chars, min_size=8, max_size=8))
    part2 = draw(st.text(alphabet=hex_chars, min_size=4, max_size=4))
    # UUID4 version indicator (4xxx)
    part3 = "4" + draw(st.text(alphabet=hex_chars, min_size=3, max_size=3))
    # UUID4 variant indicator (8, 9, a, or b followed by 3 hex chars)
    variant = draw(st.sampled_from(["8", "9", "a", "b"]))
    part4 = variant + draw(st.text(alphabet=hex_chars, min_size=3, max_size=3))
    part5 = draw(st.text(alphabet=hex_chars, min_size=12, max_size=12))
    return f"{part1}-{part2}-{part3}-{part4}-{part5}"


@st.composite
def tool_name_strategy(draw):
    """Generate valid tool names."""
    first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz_"))
    rest = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_", min_size=0, max_size=30))
    return first_char + rest


@st.composite
def parameters_strategy(draw):
    """Generate valid parameter dictionaries."""
    num_params = draw(st.integers(min_value=0, max_value=5))
    params = {}
    for i in range(num_params):
        key = f"param_{i}"
        value_type = draw(st.sampled_from(["string", "int", "bool", "none"]))
        if value_type == "string":
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


# =============================================================================
# Helper functions
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


def is_valid_uuid4(value: str) -> bool:
    """Check if a string is a valid UUID4 format."""
    uuid4_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE
    )
    return bool(uuid4_pattern.match(value))


# =============================================================================
# Property 16: Correlation ID Propagation
# =============================================================================


class TestCorrelationIDGeneration:
    """
    Property 16: Correlation ID Propagation - Generation Tests

    For any tool invocation, a unique correlation ID SHALL be generated.

    Validates: Requirements 15.1
    """

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=100, deadline=None)
    def test_generated_correlation_ids_are_unique(self, count: int):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any number of generated correlation IDs, all IDs SHALL be unique.
        """
        ids = [generate_correlation_id() for _ in range(count)]

        # All IDs should be unique
        assert len(ids) == len(
            set(ids)
        ), f"Generated {count} IDs but only {len(set(ids))} are unique"

    @given(st.data())
    @settings(max_examples=100, deadline=None)
    def test_generated_correlation_id_is_valid_uuid4(self, data):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any generated correlation ID, it SHALL be in valid UUID4 format.
        """
        correlation_id = generate_correlation_id()

        # Must be a string
        assert isinstance(correlation_id, str), "Correlation ID must be a string"

        # Must be valid UUID4 format
        assert is_valid_uuid4(
            correlation_id
        ), f"Correlation ID '{correlation_id}' is not valid UUID4 format"


class TestCorrelationIDContextPropagation:
    """
    Property 16: Correlation ID Propagation - Context Tests

    The correlation ID SHALL be propagated through the request context.

    Validates: Requirements 15.1
    """

    @given(correlation_id=uuid4_strategy())
    @settings(max_examples=100, deadline=None)
    def test_correlation_id_set_and_get_consistency(self, correlation_id: str):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any correlation ID set in context, getting it SHALL return the same value.
        """
        set_correlation_id(correlation_id)
        retrieved = get_correlation_id()

        assert retrieved == correlation_id, f"Set '{correlation_id}' but got '{retrieved}'"

    @given(correlation_id=uuid4_strategy())
    @settings(max_examples=100, deadline=None)
    def test_correlation_id_for_logging_contains_id(self, correlation_id: str):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any correlation ID set in context, get_correlation_id_for_logging
        SHALL return a dict containing that ID.
        """
        set_correlation_id(correlation_id)
        result = get_correlation_id_for_logging()

        assert isinstance(result, dict), "Result must be a dictionary"
        assert "correlation_id" in result, "Result must contain 'correlation_id' key"
        assert (
            result["correlation_id"] == correlation_id
        ), f"Expected '{correlation_id}' but got '{result['correlation_id']}'"


class TestCorrelationIDInAuditLogs:
    """
    Property 16: Correlation ID Propagation - Audit Log Tests

    The correlation ID SHALL be included in all audit records.

    Validates: Requirements 15.1
    """

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
        correlation_id=uuid4_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_log_includes_correlation_id(
        self,
        tool_name: str,
        parameters: dict,
        correlation_id: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any tool invocation with a correlation ID, the audit log entry
        SHALL include that correlation ID.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
                correlation_id=correlation_id,
            )

            # Entry must have the correlation ID
            assert entry.correlation_id is not None, "Audit entry must have correlation_id"
            assert (
                entry.correlation_id == correlation_id
            ), f"Expected '{correlation_id}' but got '{entry.correlation_id}'"
        finally:
            cleanup_temp_db(temp_db)

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
        correlation_id=uuid4_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_log_correlation_id_persisted_and_retrievable(
        self,
        tool_name: str,
        parameters: dict,
        correlation_id: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any audit log entry with a correlation ID, retrieving logs
        SHALL return entries with the same correlation ID.
        """
        temp_db = create_temp_db()
        try:
            service = AuditService(db_path=temp_db)

            # Log the invocation
            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
                correlation_id=correlation_id,
            )

            # Retrieve logs by correlation ID
            logs = service.get_logs(correlation_id=correlation_id)

            # Should find the logged entry
            assert len(logs) >= 1, "Should have at least one log entry"

            # Find our entry
            found = False
            for log in logs:
                if log.id == entry.id:
                    found = True
                    assert (
                        log.correlation_id == correlation_id
                    ), f"Retrieved log has wrong correlation ID: {log.correlation_id}"
                    break

            assert found, f"Could not find logged entry with id {entry.id}"
        finally:
            cleanup_temp_db(temp_db)

    @given(
        tool_name=tool_name_strategy(),
        parameters=parameters_strategy(),
        correlation_id=uuid4_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_audit_log_captures_correlation_id_from_context(
        self,
        tool_name: str,
        parameters: dict,
        correlation_id: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any tool invocation, if correlation ID is set in context,
        the audit service SHALL automatically capture it.
        """
        temp_db = create_temp_db()
        try:
            # Set correlation ID in context
            set_correlation_id(correlation_id)

            service = AuditService(db_path=temp_db)

            # Log without explicitly passing correlation_id
            entry = service.log_invocation(
                tool_name=tool_name,
                parameters=parameters,
                status=AuditStatus.SUCCESS,
                # correlation_id not passed - should be captured from context
            )

            # Entry must have the correlation ID from context
            assert (
                entry.correlation_id == correlation_id
            ), f"Expected '{correlation_id}' from context but got '{entry.correlation_id}'"
        finally:
            cleanup_temp_db(temp_db)


class TestCorrelationIDInLogRecords:
    """
    Property 16: Correlation ID Propagation - Log Record Tests

    The correlation ID SHALL be included in all log entries.

    Validates: Requirements 15.1
    """

    @given(correlation_id=uuid4_strategy())
    @settings(max_examples=100, deadline=None)
    def test_correlation_id_filter_adds_id_to_log_record(self, correlation_id: str):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any log record when correlation ID is set in context,
        the CorrelationIDFilter SHALL add the correlation ID to the record.
        """
        # Set correlation ID in context
        set_correlation_id(correlation_id)

        # Create a log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Apply the filter
        correlation_filter = CorrelationIDFilter()
        result = correlation_filter.filter(record)

        # Filter should allow the record
        assert result is True, "Filter should return True"

        # Record should have correlation_id attribute
        assert hasattr(record, "correlation_id"), "Log record must have correlation_id attribute"
        assert (
            record.correlation_id == correlation_id
        ), f"Expected '{correlation_id}' but got '{record.correlation_id}'"

    @given(st.data())
    @settings(max_examples=100, deadline=None)
    def test_correlation_id_filter_adds_dash_when_not_set(self, data):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any log record when correlation ID is not set in context,
        the CorrelationIDFilter SHALL add a dash placeholder.
        """
        # Clear correlation ID
        set_correlation_id("")

        # Create a log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Apply the filter
        correlation_filter = CorrelationIDFilter()
        result = correlation_filter.filter(record)

        # Filter should allow the record
        assert result is True, "Filter should return True"

        # Record should have correlation_id as dash
        assert hasattr(record, "correlation_id"), "Log record must have correlation_id attribute"
        assert record.correlation_id == "-", f"Expected '-' but got '{record.correlation_id}'"

    @given(
        correlation_id=uuid4_strategy(),
        log_message=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789 ", min_size=1, max_size=50
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_correlation_id_propagates_through_logger(
        self,
        correlation_id: str,
        log_message: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 16: Correlation ID Propagation
        Validates: Requirements 15.1

        For any log message when correlation ID is set, the correlation ID
        SHALL be available in the log record captured by handlers.
        """
        # Set correlation ID in context
        set_correlation_id(correlation_id)

        # Create a logger with the filter
        test_logger = logging.getLogger(f"test.correlation.{correlation_id[:8]}")
        test_logger.setLevel(logging.INFO)

        # Add filter
        correlation_filter = CorrelationIDFilter()
        test_logger.addFilter(correlation_filter)

        # Add a handler to capture log records
        captured_records = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                captured_records.append(record)

        handler = CaptureHandler()
        test_logger.addHandler(handler)

        try:
            # Log a message
            test_logger.info(log_message)

            # Check that record has correlation ID
            assert len(captured_records) == 1, "Should have captured one log record"
            assert hasattr(
                captured_records[0], "correlation_id"
            ), "Log record must have correlation_id attribute"
            assert (
                captured_records[0].correlation_id == correlation_id
            ), f"Expected '{correlation_id}' but got '{captured_records[0].correlation_id}'"
        finally:
            # Clean up
            test_logger.removeHandler(handler)
            test_logger.removeFilter(correlation_filter)
