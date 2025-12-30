"""Unit tests for health check endpoint."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from mcp_server.main import app
from mcp_server.models import HealthStatus


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestHealthCheckEndpoint:
    """Tests for the /health endpoint."""

    def test_health_check_returns_200(self, client):
        """Test that health check endpoint returns 200 status code."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_check_response_structure(self, client):
        """Test that health check response has required fields."""
        response = client.get("/health")
        data = response.json()
        
        # Check required fields
        assert "status" in data
        assert "version" in data
        assert "timestamp" in data
        assert "cloud_providers" in data
        assert "redis_connected" in data
        assert "sqlite_connected" in data

    def test_health_check_status_is_valid(self, client):
        """Test that health status is a valid status value."""
        response = client.get("/health")
        data = response.json()
        
        # Valid statuses include healthy, degraded, and unhealthy
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_check_version_matches(self, client):
        """Test that version in response matches package version."""
        from mcp_server import __version__
        
        response = client.get("/health")
        data = response.json()
        
        assert data["version"] == __version__

    def test_health_check_cloud_providers_includes_aws(self, client):
        """Test that cloud_providers list includes 'aws'."""
        response = client.get("/health")
        data = response.json()
        
        assert "aws" in data["cloud_providers"]

    def test_health_check_timestamp_is_iso_format(self, client):
        """Test that timestamp is in ISO format."""
        from datetime import datetime
        
        response = client.get("/health")
        data = response.json()
        
        # Should be able to parse as ISO format
        timestamp = data["timestamp"]
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            pytest.fail(f"Timestamp {timestamp} is not in ISO format")

    def test_health_check_redis_connectivity_boolean(self, client):
        """Test that redis_connected is a boolean."""
        response = client.get("/health")
        data = response.json()
        
        assert isinstance(data["redis_connected"], bool)

    def test_health_check_sqlite_connectivity_boolean(self, client):
        """Test that sqlite_connected is a boolean."""
        response = client.get("/health")
        data = response.json()
        
        assert isinstance(data["sqlite_connected"], bool)

    def test_health_check_response_model_validation(self, client):
        """Test that response can be parsed as HealthStatus model."""
        response = client.get("/health")
        data = response.json()
        
        # Should not raise validation error
        health_status = HealthStatus(**data)
        # Valid statuses include healthy, degraded, and unhealthy
        assert health_status.status in ["healthy", "degraded", "unhealthy"]


class TestRootEndpoint:
    """Tests for the root endpoint."""

    def test_root_endpoint_returns_200(self, client):
        """Test that root endpoint returns 200 status code."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_endpoint_has_required_fields(self, client):
        """Test that root endpoint response has required fields."""
        response = client.get("/")
        data = response.json()
        
        assert "name" in data
        assert "version" in data
        assert "description" in data
        assert "health_check" in data

    def test_root_endpoint_health_check_link(self, client):
        """Test that root endpoint points to health check."""
        response = client.get("/")
        data = response.json()
        
        assert data["health_check"] == "/health"
