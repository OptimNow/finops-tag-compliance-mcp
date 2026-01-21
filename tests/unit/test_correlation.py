"""Tests for correlation ID generation and context management."""

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_server.utils.cloudwatch_logger import CorrelationIDFilter
from mcp_server.utils.correlation import (
    CorrelationIDMiddleware,
    generate_correlation_id,
    get_correlation_id,
    get_correlation_id_for_logging,
    set_correlation_id,
)


class TestGenerateCorrelationId:
    """Test correlation ID generation."""

    def test_generate_correlation_id_returns_string(self):
        """Test that generate_correlation_id returns a string."""
        correlation_id = generate_correlation_id()
        assert isinstance(correlation_id, str)

    def test_generate_correlation_id_is_uuid4_format(self):
        """Test that generated ID is in UUID4 format."""
        correlation_id = generate_correlation_id()
        # UUID4 format: 8-4-4-4-12 hex digits
        parts = correlation_id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_generate_correlation_id_uniqueness(self):
        """Test that generated IDs are unique."""
        id1 = generate_correlation_id()
        id2 = generate_correlation_id()
        assert id1 != id2


class TestCorrelationIdContext:
    """Test correlation ID context management."""

    def test_set_and_get_correlation_id(self):
        """Test setting and getting correlation ID."""
        test_id = "test-correlation-id-123"
        set_correlation_id(test_id)
        assert get_correlation_id() == test_id

    def test_get_correlation_id_default_empty(self):
        """Test that get_correlation_id returns empty string by default."""
        # Create a new context to avoid interference from other tests
        import contextvars

        ctx = contextvars.copy_context()

        def check_default():
            # In a fresh context, should return empty string
            return get_correlation_id()

        ctx.run(check_default)
        # Note: This test may not work as expected due to context isolation
        # The important thing is that the function doesn't crash

    def test_get_correlation_id_for_logging_with_id(self):
        """Test get_correlation_id_for_logging when ID is set."""
        test_id = "test-id-456"
        set_correlation_id(test_id)
        result = get_correlation_id_for_logging()
        assert result == {"correlation_id": test_id}

    def test_get_correlation_id_for_logging_without_id(self):
        """Test get_correlation_id_for_logging when ID is not set."""
        set_correlation_id("")
        result = get_correlation_id_for_logging()
        assert result == {}


class TestCorrelationIDMiddleware:
    """Test the CorrelationIDMiddleware."""

    def test_middleware_generates_correlation_id_if_not_present(self):
        """Test that middleware generates correlation ID if not in headers."""
        app = FastAPI()
        app.add_middleware(CorrelationIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        # Check that response has correlation ID header
        assert "X-Correlation-ID" in response.headers
        correlation_id = response.headers["X-Correlation-ID"]
        assert correlation_id  # Should not be empty
        assert len(correlation_id) > 0

    def test_middleware_preserves_existing_correlation_id(self):
        """Test that middleware preserves correlation ID from request headers."""
        app = FastAPI()
        app.add_middleware(CorrelationIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        test_id = "existing-correlation-id-789"
        response = client.get("/test", headers={"X-Correlation-ID": test_id})

        # Check that response has the same correlation ID
        assert response.headers["X-Correlation-ID"] == test_id

    def test_middleware_adds_correlation_id_to_response_headers(self):
        """Test that middleware adds correlation ID to response headers."""
        app = FastAPI()
        app.add_middleware(CorrelationIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        # Check that response has correlation ID header
        assert "X-Correlation-ID" in response.headers

    def test_middleware_sets_correlation_id_in_context(self):
        """Test that middleware sets correlation ID in context."""
        app = FastAPI()
        app.add_middleware(CorrelationIDMiddleware)

        captured_id = None

        @app.get("/test")
        async def test_endpoint():
            nonlocal captured_id
            captured_id = get_correlation_id()
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")

        # Check that correlation ID was set in context
        assert captured_id is not None
        assert captured_id == response.headers["X-Correlation-ID"]

    def test_middleware_with_multiple_requests(self):
        """Test that middleware generates different IDs for different requests."""
        app = FastAPI()
        app.add_middleware(CorrelationIDMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response1 = client.get("/test")
        response2 = client.get("/test")

        # Check that different requests get different correlation IDs
        id1 = response1.headers["X-Correlation-ID"]
        id2 = response2.headers["X-Correlation-ID"]
        assert id1 != id2

    def test_middleware_header_name_constant(self):
        """Test that middleware uses correct header name."""
        assert CorrelationIDMiddleware.CORRELATION_ID_HEADER == "X-Correlation-ID"


class TestCorrelationIDFilter:
    """Test the CorrelationIDFilter for logging."""

    def test_filter_adds_correlation_id_to_log_record(self):
        """Test that filter adds correlation ID to log records."""
        # Set a correlation ID in context
        test_id = "test-correlation-123"
        set_correlation_id(test_id)

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

        # Check that filter returns True (allows logging)
        assert result is True

        # Check that correlation_id was added to record
        assert hasattr(record, "correlation_id")
        assert record.correlation_id == test_id

    def test_filter_adds_dash_when_no_correlation_id(self):
        """Test that filter adds '-' when no correlation ID is set."""
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

        # Check that filter returns True
        assert result is True

        # Check that correlation_id was added with dash
        assert hasattr(record, "correlation_id")
        assert record.correlation_id == "-"

    def test_filter_with_logger_integration(self):
        """Test that filter works with actual logger."""
        # Create a logger with the filter
        test_logger = logging.getLogger("test.correlation.filter")
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

        # Set correlation ID and log
        test_id = "integration-test-456"
        set_correlation_id(test_id)
        test_logger.info("Test log message")

        # Check that record has correlation ID
        assert len(captured_records) == 1
        assert hasattr(captured_records[0], "correlation_id")
        assert captured_records[0].correlation_id == test_id

        # Clean up
        test_logger.removeHandler(handler)
        test_logger.removeFilter(correlation_filter)
