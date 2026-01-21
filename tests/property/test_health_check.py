"""Property-based tests for health check endpoint."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from mcp_server.main import app
from mcp_server.models import HealthStatus


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestHealthCheckProperties:
    """Property-based tests for health check endpoint."""

    @settings(max_examples=100)
    @given(iteration=st.integers(min_value=0, max_value=99))
    def test_property_13_health_response_completeness(self, iteration):
        """
        Feature: phase-1-aws-mvp, Property 13: Health Response Completeness
        Validates: Requirements 13.2

        For any health check request when the server is healthy, the response
        SHALL include: status ("healthy"), version string, and list of supported
        cloud providers (["aws"] for Phase 1).

        This property test verifies that:
        1. The health endpoint always returns HTTP 200
        2. Response always contains required fields: status, version, cloud_providers
        3. Status is always one of "healthy", "degraded", or "unhealthy"
        4. Version is always a non-empty string
        5. Cloud providers list always includes "aws"
        6. Response can always be parsed as a valid HealthStatus model
        """
        client = TestClient(app)
        response = client.get("/health")

        # Property: Health endpoint always returns 200
        assert response.status_code == 200

        data = response.json()

        # Property: Required fields always exist
        assert "status" in data, "Response must include 'status' field"
        assert "version" in data, "Response must include 'version' field"
        assert "cloud_providers" in data, "Response must include 'cloud_providers' field"
        assert "timestamp" in data, "Response must include 'timestamp' field"
        assert "redis_connected" in data, "Response must include 'redis_connected' field"
        assert "sqlite_connected" in data, "Response must include 'sqlite_connected' field"

        # Property: Status is always valid (healthy, degraded, or unhealthy)
        assert data["status"] in [
            "healthy",
            "degraded",
            "unhealthy",
        ], f"Status must be 'healthy', 'degraded', or 'unhealthy', got '{data['status']}'"

        # Property: Version is always a non-empty string
        assert isinstance(data["version"], str), "Version must be a string"
        assert len(data["version"]) > 0, "Version must not be empty"

        # Property: Cloud providers always includes aws
        assert isinstance(data["cloud_providers"], list), "cloud_providers must be a list"
        assert "aws" in data["cloud_providers"], "cloud_providers must include 'aws'"

        # Property: Timestamp is always valid ISO format
        try:
            datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"Timestamp '{data['timestamp']}' is not valid ISO format")

        # Property: Connectivity fields are always booleans
        assert isinstance(data["redis_connected"], bool), "redis_connected must be boolean"
        assert isinstance(data["sqlite_connected"], bool), "sqlite_connected must be boolean"

        # Property: Response can always be parsed as HealthStatus model
        health_status = HealthStatus(**data)
        assert health_status.status in ["healthy", "degraded", "unhealthy"]
        assert health_status.version == data["version"]
        assert "aws" in health_status.cloud_providers

    @settings(max_examples=100)
    @given(iteration=st.integers(min_value=0, max_value=99))
    def test_property_health_response_consistency(self, iteration):
        """
        Feature: phase-1-aws-mvp, Property 13: Health Response Completeness (Consistency)
        Validates: Requirements 13.2

        For any two consecutive health check requests, the version and cloud_providers
        SHALL remain consistent (they are static values).
        """
        client = TestClient(app)

        # Make two consecutive requests
        response1 = client.get("/health")
        response2 = client.get("/health")

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Property: Version is consistent across requests
        assert data1["version"] == data2["version"], "Version should be consistent across requests"

        # Property: Cloud providers are consistent across requests
        assert (
            data1["cloud_providers"] == data2["cloud_providers"]
        ), "Cloud providers should be consistent across requests"

    @settings(max_examples=100)
    @given(iteration=st.integers(min_value=0, max_value=99))
    def test_property_health_status_reflects_connectivity(self, iteration):
        """
        Feature: phase-1-aws-mvp, Property 13: Health Response Completeness (Status Logic)
        Validates: Requirements 13.2

        The health status SHALL reflect the connectivity state:
        - "healthy" when core services are available and Redis is connected
        - "degraded" when core services are available but Redis is not connected
        - "unhealthy" when core services (policy_service, audit_service) are not available
        """
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        redis_connected = data["redis_connected"]
        data["sqlite_connected"]
        status = data["status"]

        # Property: Status is always a valid value
        assert status in [
            "healthy",
            "degraded",
            "unhealthy",
        ], f"Status must be 'healthy', 'degraded', or 'unhealthy', got '{status}'"

        # Property: If status is healthy, Redis should be connected
        if status == "healthy":
            assert redis_connected, "Status should only be 'healthy' when Redis is connected"
