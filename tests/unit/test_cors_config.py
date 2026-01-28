"""Unit tests for CORS configuration and middleware.

Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 23.3
"""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from mcp_server.middleware.cors_middleware import (
    CORSLoggingMiddleware,
    get_cors_config,
    parse_cors_origins,
)


class TestParseCorsOrigins:
    """Test CORS origin parsing."""

    def test_parse_single_origin(self):
        """Test parsing a single origin."""
        result = parse_cors_origins("https://example.com")
        assert result == ["https://example.com"]

    def test_parse_multiple_origins(self):
        """Test parsing multiple comma-separated origins."""
        result = parse_cors_origins("https://a.com,https://b.com,https://c.com")
        assert result == ["https://a.com", "https://b.com", "https://c.com"]

    def test_parse_origins_with_whitespace(self):
        """Test parsing origins with surrounding whitespace."""
        result = parse_cors_origins("https://a.com , https://b.com , https://c.com")
        assert result == ["https://a.com", "https://b.com", "https://c.com"]

    def test_parse_wildcard(self):
        """Test parsing wildcard origin."""
        result = parse_cors_origins("*")
        assert result == ["*"]

    def test_parse_wildcard_with_whitespace(self):
        """Test parsing wildcard with whitespace."""
        result = parse_cors_origins("  *  ")
        assert result == ["*"]

    def test_parse_empty_string(self):
        """Test parsing empty string returns empty list."""
        result = parse_cors_origins("")
        assert result == []

    def test_parse_filters_empty_values(self):
        """Test that empty values are filtered out."""
        result = parse_cors_origins("https://a.com,,https://b.com, ,https://c.com")
        assert result == ["https://a.com", "https://b.com", "https://c.com"]


class TestGetCorsConfig:
    """Test CORS configuration builder."""

    def test_config_with_wildcard(self):
        """Test config with wildcard allows all."""
        config = get_cors_config(["*"])

        assert config["allow_origins"] == ["*"]
        assert config["allow_credentials"] is False
        assert "GET" in config["allow_methods"]
        assert "POST" in config["allow_methods"]
        assert "*" in config["allow_headers"]

    def test_config_with_specific_origins(self):
        """Test config with specific origins is restrictive.

        Requirement 20.5: Restrict methods to POST only for MCP tool calls.
        Requirement 20.6: Restrict headers to specific values.
        """
        origins = ["https://claude.ai", "https://example.com"]
        config = get_cors_config(origins)

        assert config["allow_origins"] == origins
        assert config["allow_credentials"] is False
        # Requirement 20.5
        assert "POST" in config["allow_methods"]
        assert "OPTIONS" in config["allow_methods"]
        assert "GET" not in config["allow_methods"]
        # Requirement 20.6
        assert "Content-Type" in config["allow_headers"]
        assert "Authorization" in config["allow_headers"]
        assert "X-Correlation-ID" in config["allow_headers"]
        assert "*" not in config["allow_headers"]

    def test_config_with_empty_list(self):
        """Test config with empty list blocks all.

        Requirement 20.2: NOT use wildcard (*) in production mode.
        """
        config = get_cors_config([])

        assert config["allow_origins"] == []
        assert "POST" in config["allow_methods"]
        assert "GET" not in config["allow_methods"]


class TestCORSLoggingMiddleware:
    """Test CORS logging middleware."""

    @pytest.fixture
    def app_with_logging(self) -> FastAPI:
        """Create a test FastAPI app with CORS logging."""
        app = FastAPI()

        # Add CORS logging middleware
        app.add_middleware(
            CORSLoggingMiddleware,
            allowed_origins=["https://allowed.com"],
            enabled=True,
        )

        # Add actual CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://allowed.com"],
            allow_methods=["POST", "OPTIONS"],
            allow_headers=["*"],
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        @app.post("/mcp/tools/call")
        async def mcp_call():
            return {"result": "success"}

        return app

    @pytest.fixture
    def app_with_wildcard(self) -> FastAPI:
        """Create a test FastAPI app with wildcard CORS."""
        app = FastAPI()

        app.add_middleware(
            CORSLoggingMiddleware,
            allowed_origins=["*"],
            enabled=True,
        )

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        return app

    def test_allowed_origin_passes(self, app_with_logging):
        """Test that allowed origin passes through."""
        client = TestClient(app_with_logging)
        response = client.get(
            "/test",
            headers={"Origin": "https://allowed.com"},
        )
        assert response.status_code == 200

    def test_non_allowed_origin_still_processes(self, app_with_logging):
        """Test that non-allowed origin request is still processed.

        The logging middleware doesn't block - CORS middleware handles that.
        """
        client = TestClient(app_with_logging)
        response = client.get(
            "/test",
            headers={"Origin": "https://not-allowed.com"},
        )
        # Request still goes through, but CORS headers won't be set
        assert response.status_code == 200

    def test_no_origin_header_passes(self, app_with_logging):
        """Test that requests without Origin header pass through."""
        client = TestClient(app_with_logging)
        response = client.get("/test")
        assert response.status_code == 200

    def test_wildcard_allows_all_origins(self, app_with_wildcard):
        """Test that wildcard allows all origins."""
        client = TestClient(app_with_wildcard)
        response = client.get(
            "/test",
            headers={"Origin": "https://any-site.com"},
        )
        assert response.status_code == 200


class TestCORSIntegration:
    """Test CORS integration with FastAPI app."""

    @pytest.fixture
    def app_with_cors(self) -> FastAPI:
        """Create a test FastAPI app with proper CORS setup."""
        app = FastAPI()

        allowed_origins = ["https://claude.ai"]
        config = get_cors_config(allowed_origins)

        app.add_middleware(
            CORSMiddleware,
            **config,
        )

        @app.post("/mcp/tools/call")
        async def mcp_call():
            return {"result": "success"}

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        return app

    def test_cors_headers_for_allowed_origin(self, app_with_cors):
        """Test CORS headers are set for allowed origin."""
        client = TestClient(app_with_cors)
        response = client.options(
            "/mcp/tools/call",
            headers={
                "Origin": "https://claude.ai",
                "Access-Control-Request-Method": "POST",
            },
        )
        # Preflight should succeed
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_headers_missing_for_non_allowed_origin(self, app_with_cors):
        """Test CORS headers are not set for non-allowed origin.

        Requirement 20.3: Reject requests from non-allowed origins.
        """
        client = TestClient(app_with_cors)
        response = client.options(
            "/mcp/tools/call",
            headers={
                "Origin": "https://malicious-site.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        # CORS middleware should not set allow-origin header
        # (Starlette returns 400 for disallowed origins in preflight)
        assert "access-control-allow-origin" not in response.headers or \
               response.headers.get("access-control-allow-origin") != "https://malicious-site.com"

    def test_post_method_allowed(self, app_with_cors):
        """Test POST method is allowed.

        Requirement 20.5: Restrict allowed methods to POST.
        """
        client = TestClient(app_with_cors)
        response = client.options(
            "/mcp/tools/call",
            headers={
                "Origin": "https://claude.ai",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200

    def test_health_endpoint_accessible(self, app_with_cors):
        """Test health endpoint is accessible without CORS concerns."""
        client = TestClient(app_with_cors)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestCORSMiddlewareDisabled:
    """Test CORS logging middleware when disabled."""

    @pytest.fixture
    def app_with_disabled_logging(self) -> FastAPI:
        """Create app with disabled CORS logging."""
        app = FastAPI()

        app.add_middleware(
            CORSLoggingMiddleware,
            allowed_origins=["https://allowed.com"],
            enabled=False,  # Disabled
        )

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        return app

    def test_disabled_logging_passes_all_requests(self, app_with_disabled_logging):
        """Test that disabled logging doesn't interfere."""
        client = TestClient(app_with_disabled_logging)

        # Request with non-allowed origin
        response = client.get(
            "/test",
            headers={"Origin": "https://not-allowed.com"},
        )
        assert response.status_code == 200

        # Request without origin
        response = client.get("/test")
        assert response.status_code == 200
