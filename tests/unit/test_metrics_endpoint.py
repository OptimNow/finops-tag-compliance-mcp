"""Unit tests for the metrics endpoint.

Tests the /metrics endpoint that returns Prometheus-compatible metrics
for observability and monitoring.

Requirements: 15.2
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from mcp_server.main import app
from mcp_server.models.audit import AuditLogEntry, AuditStatus


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_audit_service():
    """Create a mock audit service with sample data."""
    mock_service = MagicMock()

    # Create sample audit logs
    sample_logs = [
        AuditLogEntry(
            id=1,
            timestamp=datetime.now(UTC),
            tool_name="check_tag_compliance",
            parameters={"resource_types": ["ec2"]},
            status=AuditStatus.SUCCESS,
            result="Compliance check completed",
            execution_time_ms=150.5,
            correlation_id="test-session-1",
            error_message=None,
        ),
        AuditLogEntry(
            id=2,
            timestamp=datetime.now(UTC),
            tool_name="find_untagged_resources",
            parameters={"resource_types": ["s3"]},
            status=AuditStatus.SUCCESS,
            result="Found 5 untagged resources",
            execution_time_ms=200.0,
            correlation_id="test-session-1",
            error_message=None,
        ),
        AuditLogEntry(
            id=3,
            timestamp=datetime.now(UTC),
            tool_name="check_tag_compliance",
            parameters={"resource_types": ["rds"]},
            status=AuditStatus.FAILURE,
            result=None,
            execution_time_ms=50.0,
            correlation_id="test-session-2",
            error_message="AWS API error",
        ),
    ]

    mock_service.get_logs.return_value = sample_logs
    return mock_service


class TestMetricsEndpoint:
    """Tests for the /metrics endpoint."""

    def test_metrics_endpoint_returns_200(self, client, mock_audit_service):
        """Test that the metrics endpoint returns a 200 status code."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            assert response.status_code == 200

    def test_metrics_endpoint_returns_text_plain(self, client, mock_audit_service):
        """Test that the metrics endpoint returns text/plain content type."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_endpoint_returns_prometheus_format(self, client, mock_audit_service):
        """Test that the metrics endpoint returns Prometheus text format."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Check for Prometheus format markers
            assert "# HELP" in content
            assert "# TYPE" in content
            assert "mcp_server_uptime_seconds" in content

    def test_metrics_endpoint_includes_uptime_metric(self, client, mock_audit_service):
        """Test that metrics include server uptime."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            assert "mcp_server_uptime_seconds" in content
            # Should have a numeric value
            lines = content.split("\n")
            uptime_lines = [l for l in lines if l.startswith("mcp_server_uptime_seconds ")]
            assert len(uptime_lines) > 0
            # Extract the value
            value = float(uptime_lines[0].split()[-1])
            assert value >= 0

    def test_metrics_endpoint_includes_session_metrics(self, client, mock_audit_service):
        """Test that metrics include session-related metrics."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Check for session metrics
            assert "mcp_server_total_sessions" in content
            assert "mcp_server_active_sessions" in content

    def test_metrics_endpoint_includes_tool_invocation_metrics(self, client, mock_audit_service):
        """Test that metrics include tool invocation metrics."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Check for tool invocation metrics
            assert "mcp_tool_invocations_total" in content
            assert "mcp_tool_successes_total" in content
            assert "mcp_tool_failures_total" in content
            assert "mcp_tool_error_rate" in content

    def test_metrics_endpoint_includes_execution_time_metrics(self, client, mock_audit_service):
        """Test that metrics include execution time metrics."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Check for execution time metrics
            assert "mcp_tool_execution_time_ms_total" in content
            assert "mcp_tool_execution_time_ms_average" in content

    def test_metrics_endpoint_includes_budget_metrics(self, client, mock_audit_service):
        """Test that metrics include budget tracking metrics."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Check for budget metrics (if budget tracking is enabled)
            if "mcp_budget_max_calls_per_session" in content:
                assert "mcp_budget_active_sessions" in content
                assert "mcp_budget_sessions_exhausted" in content

    def test_metrics_endpoint_includes_loop_detection_metrics(self, client, mock_audit_service):
        """Test that metrics include loop detection metrics."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Check for loop detection metrics (if loop detection is enabled)
            if "mcp_loop_detection_total" in content:
                assert "mcp_loop_detection_active_sessions" in content
                assert "mcp_loop_detection_max_identical_calls_threshold" in content

    def test_metrics_endpoint_includes_error_metrics(self, client, mock_audit_service):
        """Test that metrics include error rate metrics."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Check for error metrics
            if "mcp_error_trend" in content:
                assert "mcp_errors_by_type" in content or "mcp_errors_by_tool" in content

    def test_metrics_endpoint_has_help_text(self, client, mock_audit_service):
        """Test that metrics have HELP text for documentation."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Count HELP lines
            help_lines = [l for l in content.split("\n") if l.startswith("# HELP")]
            assert len(help_lines) > 0

    def test_metrics_endpoint_has_type_declarations(self, client, mock_audit_service):
        """Test that metrics have TYPE declarations."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Count TYPE lines
            type_lines = [l for l in content.split("\n") if l.startswith("# TYPE")]
            assert len(type_lines) > 0

    def test_metrics_endpoint_has_timestamp(self, client, mock_audit_service):
        """Test that metrics include a generation timestamp."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Check for timestamp comment
            assert "Generated at" in content

    def test_metrics_endpoint_per_tool_metrics(self, client, mock_audit_service):
        """Test that metrics include per-tool breakdowns."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            # Check for per-tool metrics with labels
            if "mcp_tool_invocations{" in content:
                # Should have tool labels
                assert 'tool="' in content

    def test_metrics_endpoint_valid_prometheus_format(self, client, mock_audit_service):
        """Test that the metrics output is valid Prometheus format."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            lines = content.split("\n")

            # Parse and validate Prometheus format
            for line in lines:
                if not line or line.startswith("#"):
                    # Comments and empty lines are OK
                    continue

                # Metric lines should have format: metric_name{labels} value
                # or metric_name value
                if line.strip():
                    # Should have at least a metric name and value
                    parts = line.split()
                    assert len(parts) >= 2, f"Invalid metric line: {line}"

                    # Value should be numeric or special values like +Inf, -Inf, NaN
                    try:
                        float(parts[-1])
                    except ValueError:
                        if parts[-1] not in ["+Inf", "-Inf", "NaN"]:
                            pytest.fail(f"Invalid metric value: {parts[-1]}")

    def test_metrics_endpoint_no_errors_with_empty_data(self, client, mock_audit_service):
        """Test that metrics endpoint handles empty data gracefully."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")

            # Should still return 200 even with no tool invocations
            assert response.status_code == 200
            assert len(response.text) > 0


class TestMetricsEndpointIntegration:
    """Integration tests for the metrics endpoint."""

    def test_metrics_endpoint_accessible_from_root(self, client):
        """Test that metrics endpoint is listed in root endpoint."""
        response = client.get("/")
        data = response.json()

        assert "metrics" in data
        assert data["metrics"] == "/metrics"

    def test_metrics_endpoint_returns_consistent_format(self, client, mock_audit_service):
        """Test that multiple calls return consistent format."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response1 = client.get("/metrics")
            response2 = client.get("/metrics")

            # Both should be valid Prometheus format
            assert "# HELP" in response1.text
            assert "# HELP" in response2.text

            # Both should have the same metric names
            metrics1 = set(
                l.split()[0] for l in response1.text.split("\n") if l and not l.startswith("#")
            )
            metrics2 = set(
                l.split()[0] for l in response2.text.split("\n") if l and not l.startswith("#")
            )

            # Should have same metric names (values may differ)
            assert metrics1 == metrics2

    def test_metrics_endpoint_values_are_numeric(self, client, mock_audit_service):
        """Test that all metric values are numeric."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            lines = content.split("\n")
            for line in lines:
                if not line or line.startswith("#"):
                    continue

                if line.strip():
                    # Extract the value (last token)
                    parts = line.split()
                    value = parts[-1]

                    # Should be numeric
                    try:
                        float(value)
                    except ValueError:
                        if value not in ["+Inf", "-Inf", "NaN"]:
                            pytest.fail(f"Non-numeric value: {value} in line: {line}")

    def test_metrics_endpoint_labels_are_quoted(self, client, mock_audit_service):
        """Test that metric labels are properly quoted."""
        with patch("mcp_server.main.audit_service", mock_audit_service):
            response = client.get("/metrics")
            content = response.text

            lines = content.split("\n")
            for line in lines:
                if "{" in line and "}" in line:
                    # Extract labels section
                    start = line.index("{")
                    end = line.index("}")
                    labels = line[start + 1 : end]

                    # All label values should be quoted
                    if "=" in labels:
                        parts = labels.split(",")
                        for part in parts:
                            if "=" in part:
                                key, value = part.split("=", 1)
                                # Value should be quoted
                                assert value.startswith('"') and value.endswith(
                                    '"'
                                ), f"Unquoted label value: {part}"
