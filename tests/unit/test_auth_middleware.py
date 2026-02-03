"""Unit tests for API key authentication middleware.

Requirements: 19.1, 19.2, 19.3, 19.5, 19.7
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_server.middleware.auth_middleware import (
    APIKeyAuthMiddleware,
    AuthenticationError,
    PUBLIC_ENDPOINTS,
    hash_api_key,
    parse_api_keys,
)


class TestHashApiKey:
    """Test API key hashing."""

    def test_hash_returns_8_chars(self):
        """Test that hash returns first 8 characters of SHA256."""
        result = hash_api_key("test-api-key")
        assert len(result) == 8
        assert result.isalnum()

    def test_hash_is_deterministic(self):
        """Test that same key produces same hash."""
        key = "my-secret-key"
        assert hash_api_key(key) == hash_api_key(key)

    def test_hash_different_keys_produce_different_hashes(self):
        """Test that different keys produce different hashes."""
        assert hash_api_key("key1") != hash_api_key("key2")


class TestParseApiKeys:
    """Test API key parsing."""

    def test_parse_single_key(self):
        """Test parsing a single API key."""
        result = parse_api_keys("my-api-key")
        assert result == {"my-api-key"}

    def test_parse_multiple_keys(self):
        """Test parsing multiple comma-separated API keys."""
        result = parse_api_keys("key1,key2,key3")
        assert result == {"key1", "key2", "key3"}

    def test_parse_keys_with_whitespace(self):
        """Test parsing keys with surrounding whitespace."""
        result = parse_api_keys("key1 , key2 , key3")
        assert result == {"key1", "key2", "key3"}

    def test_parse_empty_string(self):
        """Test parsing empty string returns empty set."""
        result = parse_api_keys("")
        assert result == set()

    def test_parse_filters_empty_values(self):
        """Test that empty values are filtered out."""
        result = parse_api_keys("key1,,key2, ,key3")
        assert result == {"key1", "key2", "key3"}


class TestPublicEndpoints:
    """Test public endpoints configuration."""

    def test_health_is_public(self):
        """Test that /health is in public endpoints."""
        assert "/health" in PUBLIC_ENDPOINTS

    def test_root_is_public(self):
        """Test that root path is in public endpoints."""
        assert "/" in PUBLIC_ENDPOINTS

    def test_docs_is_public(self):
        """Test that /docs is in public endpoints."""
        assert "/docs" in PUBLIC_ENDPOINTS


class TestAPIKeyAuthMiddleware:
    """Test API key authentication middleware."""

    @pytest.fixture
    def valid_keys(self) -> set[str]:
        """Return a set of valid test API keys."""
        return {"valid-key-1", "valid-key-2", "test-key-abc123"}

    @pytest.fixture
    def app_with_auth(self, valid_keys) -> FastAPI:
        """Create a test FastAPI app with authentication middleware."""
        app = FastAPI()
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_keys=valid_keys,
            enabled=True,
            realm="test-realm",
        )

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/protected")
        async def protected():
            return {"message": "protected data"}

        @app.post("/mcp/tools/call")
        async def mcp_call():
            return {"result": "success"}

        @app.get("/")
        async def root():
            return {"name": "Test API"}

        return app

    @pytest.fixture
    def app_without_auth(self, valid_keys) -> FastAPI:
        """Create a test FastAPI app with authentication disabled."""
        app = FastAPI()
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_keys=valid_keys,
            enabled=False,  # Authentication disabled
        )

        @app.get("/protected")
        async def protected():
            return {"message": "protected data"}

        return app

    # ==================== Requirement 19.1: Bearer token authentication ====================

    def test_valid_bearer_token_accepted(self, app_with_auth, valid_keys):
        """Test that valid Bearer token is accepted.

        Requirement 19.1: Support API key authentication via Bearer token.
        """
        client = TestClient(app_with_auth)
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer valid-key-1"},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "protected data"}

    def test_multiple_valid_keys_work(self, app_with_auth, valid_keys):
        """Test that all configured valid keys work.

        Requirement 19.4: Support multiple API keys.
        """
        client = TestClient(app_with_auth)
        for key in valid_keys:
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {key}"},
            )
            assert response.status_code == 200

    # ==================== Requirement 19.2: Key validation ====================

    def test_invalid_key_rejected(self, app_with_auth):
        """Test that invalid API key is rejected.

        Requirement 19.2: Validate API keys against configured list.
        """
        client = TestClient(app_with_auth)
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert response.status_code == 401

    # ==================== Requirement 19.3: 401 Unauthorized ====================

    def test_missing_auth_header_returns_401(self, app_with_auth):
        """Test that missing Authorization header returns 401.

        Requirement 19.3: Return HTTP 401 for missing API key.
        """
        client = TestClient(app_with_auth)
        response = client.get("/protected")
        assert response.status_code == 401
        assert response.json()["error"] == "Unauthorized"

    def test_empty_bearer_token_returns_401(self, app_with_auth):
        """Test that empty Bearer token returns 401.

        Requirement 19.3: Return HTTP 401 for invalid API key.
        """
        client = TestClient(app_with_auth)
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code == 401

    def test_non_bearer_scheme_returns_401(self, app_with_auth):
        """Test that non-Bearer scheme returns 401.

        Requirement 19.3: Return HTTP 401 for invalid request.
        """
        client = TestClient(app_with_auth)
        response = client.get(
            "/protected",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert response.status_code == 401

    def test_malformed_auth_header_returns_401(self, app_with_auth):
        """Test that malformed Authorization header returns 401.

        Requirement 19.3: Return HTTP 401 for invalid request.
        """
        client = TestClient(app_with_auth)
        response = client.get(
            "/protected",
            headers={"Authorization": "NotBearer token"},
        )
        assert response.status_code == 401

    # ==================== Requirement 19.7: WWW-Authenticate header ====================

    def test_401_includes_www_authenticate_header(self, app_with_auth):
        """Test that 401 response includes WWW-Authenticate header.

        Requirement 19.7: Include WWW-Authenticate header per RFC 6750.
        """
        client = TestClient(app_with_auth)
        response = client.get("/protected")
        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    def test_www_authenticate_includes_bearer_scheme(self, app_with_auth):
        """Test that WWW-Authenticate includes Bearer scheme."""
        client = TestClient(app_with_auth)
        response = client.get("/protected")
        www_auth = response.headers["WWW-Authenticate"]
        assert "Bearer" in www_auth

    def test_www_authenticate_includes_realm(self, app_with_auth):
        """Test that WWW-Authenticate includes realm."""
        client = TestClient(app_with_auth)
        response = client.get("/protected")
        www_auth = response.headers["WWW-Authenticate"]
        assert 'realm="test-realm"' in www_auth

    def test_www_authenticate_includes_error_code(self, app_with_auth):
        """Test that WWW-Authenticate includes error code."""
        client = TestClient(app_with_auth)
        response = client.get("/protected")
        www_auth = response.headers["WWW-Authenticate"]
        assert 'error="missing_token"' in www_auth

    def test_www_authenticate_invalid_token_error(self, app_with_auth):
        """Test that invalid token returns correct error code."""
        client = TestClient(app_with_auth)
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer bad-key"},
        )
        www_auth = response.headers["WWW-Authenticate"]
        assert 'error="invalid_token"' in www_auth

    # ==================== Public endpoint bypass ====================

    def test_health_endpoint_bypasses_auth(self, app_with_auth):
        """Test that /health endpoint bypasses authentication."""
        client = TestClient(app_with_auth)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_root_endpoint_bypasses_auth(self, app_with_auth):
        """Test that root endpoint bypasses authentication."""
        client = TestClient(app_with_auth)
        response = client.get("/")
        assert response.status_code == 200

    # ==================== Authentication disabled ====================

    def test_disabled_auth_allows_all_requests(self, app_without_auth):
        """Test that disabled authentication allows all requests."""
        client = TestClient(app_without_auth)
        response = client.get("/protected")
        assert response.status_code == 200
        assert response.json() == {"message": "protected data"}

    # ==================== MCP endpoint protection ====================

    def test_mcp_endpoint_requires_auth(self, app_with_auth):
        """Test that MCP endpoints require authentication."""
        client = TestClient(app_with_auth)
        response = client.post("/mcp/tools/call")
        assert response.status_code == 401

    def test_mcp_endpoint_with_valid_auth(self, app_with_auth):
        """Test that MCP endpoints work with valid authentication."""
        client = TestClient(app_with_auth)
        response = client.post(
            "/mcp/tools/call",
            headers={"Authorization": "Bearer valid-key-1"},
        )
        assert response.status_code == 200


class TestAuthResponseBody:
    """Test authentication error response body format."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a test FastAPI app with authentication."""
        app = FastAPI()
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_keys={"valid-key"},
            enabled=True,
        )

        @app.get("/protected")
        async def protected():
            return {"data": "secret"}

        return app

    def test_error_response_format(self, app):
        """Test that error response has correct format."""
        client = TestClient(app)
        response = client.get("/protected")
        body = response.json()

        assert "error" in body
        assert "message" in body
        assert "error_code" in body

    def test_missing_token_error_message(self, app):
        """Test error message for missing token."""
        client = TestClient(app)
        response = client.get("/protected")
        body = response.json()

        assert body["error_code"] == "missing_token"
        assert "access token" in body["message"].lower()

    def test_invalid_token_error_message(self, app):
        """Test error message for invalid token."""
        client = TestClient(app)
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer bad-key"},
        )
        body = response.json()

        assert body["error_code"] == "invalid_token"
        assert "invalid" in body["message"].lower()


class TestAuthWithTrailingSlash:
    """Test authentication with trailing slashes in paths."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create a test FastAPI app with authentication."""
        app = FastAPI()
        app.add_middleware(
            APIKeyAuthMiddleware,
            api_keys={"valid-key"},
            enabled=True,
        )

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        @app.get("/health/")
        async def health_with_slash():
            return {"status": "healthy"}

        return app

    def test_health_with_trailing_slash_bypasses_auth(self, app):
        """Test that /health/ also bypasses authentication."""
        client = TestClient(app)
        # Note: FastAPI may redirect, but the middleware should handle both
        response = client.get("/health/", follow_redirects=False)
        # Either 200 (if route exists) or 307 redirect (to /health)
        assert response.status_code in [200, 307]
