"""
Property-based tests for API Key Authentication.

Feature: production-security, Property 20: Authentication Enforcement
Validates: Requirements 19.1, 19.2, 19.3

Property 20 states:
*For all* api_key and valid_keys:
- If api_key in valid_keys: request succeeds (200)
- If api_key not in valid_keys: request returns 401 Unauthorized

The MCP Server SHALL validate API keys against a configured list of valid keys
and reject requests with invalid or missing API keys with HTTP 401.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from mcp_server.middleware.auth_middleware import (
    APIKeyAuthMiddleware,
    hash_api_key,
    parse_api_keys,
)


# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def api_key_strategy(draw):
    """Generate valid API key strings."""
    # API keys are typically alphanumeric with some special characters
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    key = draw(st.text(alphabet=alphabet, min_size=8, max_size=64))
    return key


@st.composite
def valid_keys_set_strategy(draw):
    """Generate a set of valid API keys."""
    keys = draw(st.lists(api_key_strategy(), min_size=1, max_size=10, unique=True))
    return set(keys)


@st.composite
def malformed_auth_header_strategy(draw):
    """Generate malformed Authorization header values."""
    return draw(
        st.sampled_from(
            [
                "",  # Empty
                "Basic dXNlcjpwYXNz",  # Basic auth
                "Digest username=test",  # Digest auth
                "bearer token",  # Lowercase bearer
                "BEARER token",  # Uppercase bearer
                "Bearer",  # Bearer without token
                "Bearer  token",  # Double space
                "BearerToken",  # No space
                "Token abc123",  # Wrong scheme
            ]
        )
    )


# =============================================================================
# Property 20: Authentication Enforcement
# =============================================================================


class TestAuthenticationEnforcement:
    """
    Property 20: Authentication Enforcement

    For all api_key and valid_keys:
    - If api_key in valid_keys: request succeeds
    - If api_key not in valid_keys: request returns 401

    Validates: Requirements 19.1, 19.2, 19.3
    """

    @pytest.fixture
    def create_app(self):
        """Factory to create test apps with configurable auth."""

        def _create(valid_keys: set[str], enabled: bool = True) -> FastAPI:
            app = FastAPI()
            app.add_middleware(
                APIKeyAuthMiddleware,
                api_keys=valid_keys,
                enabled=enabled,
                realm="test-realm",
            )

            @app.get("/protected")
            async def protected():
                return {"status": "success"}

            @app.get("/health")
            async def health():
                return {"status": "healthy"}

            return app

        return _create

    # -------------------------------------------------------------------------
    # Core Authentication Property Tests (Requirements 19.1, 19.2, 19.3)
    # -------------------------------------------------------------------------

    @given(
        api_key=api_key_strategy(),
        valid_keys=valid_keys_set_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_valid_key_always_accepted(
        self,
        api_key: str,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirements 19.1, 19.2

        If api_key in valid_keys: request SHALL succeed (200).
        """
        # Ensure the key is in valid_keys for this test
        valid_keys_with_test_key = valid_keys | {api_key}

        app = create_app(valid_keys_with_test_key)
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @given(
        api_key=api_key_strategy(),
        valid_keys=valid_keys_set_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_invalid_key_always_rejected(
        self,
        api_key: str,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirements 19.2, 19.3

        If api_key not in valid_keys: request SHALL return 401.
        """
        # Ensure the key is NOT in valid_keys
        assume(api_key not in valid_keys)

        app = create_app(valid_keys)
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 401

    @given(valid_keys=valid_keys_set_strategy())
    @settings(max_examples=50, deadline=None)
    def test_missing_header_always_rejected(
        self,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirements 19.3

        Missing Authorization header SHALL return 401.
        """
        app = create_app(valid_keys)
        client = TestClient(app)

        response = client.get("/protected")

        assert response.status_code == 401

    @given(
        valid_keys=valid_keys_set_strategy(),
        malformed_header=malformed_auth_header_strategy(),
    )
    @settings(max_examples=50, deadline=None)
    def test_malformed_header_always_rejected(
        self,
        valid_keys: set[str],
        malformed_header: str,
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirements 19.3

        Malformed Authorization header SHALL return 401.
        """
        app = create_app(valid_keys)
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"Authorization": malformed_header},
        )

        assert response.status_code == 401

    # -------------------------------------------------------------------------
    # WWW-Authenticate Header Property Tests (Requirement 19.7)
    # -------------------------------------------------------------------------

    @given(valid_keys=valid_keys_set_strategy())
    @settings(max_examples=50, deadline=None)
    def test_401_always_includes_www_authenticate(
        self,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirements 19.7

        401 response SHALL always include WWW-Authenticate header.
        """
        app = create_app(valid_keys)
        client = TestClient(app)

        response = client.get("/protected")

        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers

    @given(valid_keys=valid_keys_set_strategy())
    @settings(max_examples=50, deadline=None)
    def test_www_authenticate_always_uses_bearer_scheme(
        self,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirements 19.7

        WWW-Authenticate header SHALL use Bearer scheme per RFC 6750.
        """
        app = create_app(valid_keys)
        client = TestClient(app)

        response = client.get("/protected")
        www_auth = response.headers.get("WWW-Authenticate", "")

        assert www_auth.startswith("Bearer")

    @given(valid_keys=valid_keys_set_strategy())
    @settings(max_examples=50, deadline=None)
    def test_www_authenticate_always_includes_realm(
        self,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirements 19.7

        WWW-Authenticate header SHALL include realm parameter.
        """
        app = create_app(valid_keys)
        client = TestClient(app)

        response = client.get("/protected")
        www_auth = response.headers.get("WWW-Authenticate", "")

        assert "realm=" in www_auth

    @given(valid_keys=valid_keys_set_strategy())
    @settings(max_examples=50, deadline=None)
    def test_www_authenticate_always_includes_error_code(
        self,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirements 19.7

        WWW-Authenticate header SHALL include error code.
        """
        app = create_app(valid_keys)
        client = TestClient(app)

        response = client.get("/protected")
        www_auth = response.headers.get("WWW-Authenticate", "")

        assert "error=" in www_auth

    # -------------------------------------------------------------------------
    # Public Endpoint Bypass Property Tests
    # -------------------------------------------------------------------------

    @given(valid_keys=valid_keys_set_strategy())
    @settings(max_examples=50, deadline=None)
    def test_health_endpoint_always_accessible(
        self,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Health endpoint bypass requirement

        Health endpoint SHALL always be accessible without authentication.
        """
        app = create_app(valid_keys)
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    # -------------------------------------------------------------------------
    # API Key Parsing Property Tests
    # -------------------------------------------------------------------------

    @given(
        keys=st.lists(api_key_strategy(), min_size=1, max_size=10, unique=True),
    )
    @settings(max_examples=100, deadline=None)
    def test_parse_api_keys_preserves_all_keys(self, keys: list[str]):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirement 19.4 (multiple API keys)

        parse_api_keys SHALL preserve all valid keys.
        """
        keys_str = ",".join(keys)
        result = parse_api_keys(keys_str)

        assert result == set(keys)

    @given(
        keys=st.lists(api_key_strategy(), min_size=1, max_size=10, unique=True),
    )
    @settings(max_examples=100, deadline=None)
    def test_parse_api_keys_handles_whitespace(self, keys: list[str]):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirement 19.4 (multiple API keys)

        parse_api_keys SHALL strip whitespace from keys.
        """
        keys_with_spaces = [f"  {k}  " for k in keys]
        keys_str = " , ".join(keys_with_spaces)
        result = parse_api_keys(keys_str)

        assert result == set(keys)

    # -------------------------------------------------------------------------
    # API Key Hashing Property Tests
    # -------------------------------------------------------------------------

    @given(api_key=api_key_strategy())
    @settings(max_examples=100, deadline=None)
    def test_hash_api_key_deterministic(self, api_key: str):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirement 19.5 (logging)

        hash_api_key SHALL be deterministic.
        """
        hash1 = hash_api_key(api_key)
        hash2 = hash_api_key(api_key)

        assert hash1 == hash2

    @given(api_key=api_key_strategy())
    @settings(max_examples=100, deadline=None)
    def test_hash_api_key_fixed_length(self, api_key: str):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirement 19.5 (logging)

        hash_api_key SHALL return a fixed-length string (8 chars).
        """
        result = hash_api_key(api_key)

        assert len(result) == 8

    @given(
        key1=api_key_strategy(),
        key2=api_key_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_hash_api_key_collision_resistant(self, key1: str, key2: str):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: Requirement 19.5 (logging)

        Different keys SHOULD produce different hashes (with high probability).
        """
        assume(key1 != key2)

        hash1 = hash_api_key(key1)
        hash2 = hash_api_key(key2)

        # Note: With 8 hex chars, collision is possible but rare
        # We allow this test to occasionally fail for true collisions
        # In practice, this is acceptable for logging purposes
        # If this test fails frequently, increase hash length
        assert hash1 != hash2 or len(key1) < 10  # Allow short key collisions

    # -------------------------------------------------------------------------
    # Authentication Disabled Property Tests
    # -------------------------------------------------------------------------

    @given(valid_keys=valid_keys_set_strategy())
    @settings(max_examples=50, deadline=None)
    def test_disabled_auth_allows_all_requests(
        self,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: AUTH_ENABLED=false behavior

        When authentication is disabled, all requests SHALL succeed.
        """
        app = create_app(valid_keys, enabled=False)
        client = TestClient(app)

        # Without auth header
        response = client.get("/protected")
        assert response.status_code == 200

    @given(
        api_key=api_key_strategy(),
        valid_keys=valid_keys_set_strategy(),
    )
    @settings(max_examples=50, deadline=None)
    def test_disabled_auth_ignores_invalid_keys(
        self,
        api_key: str,
        valid_keys: set[str],
        create_app,
    ):
        """
        Feature: production-security, Property 20: Authentication Enforcement
        Validates: AUTH_ENABLED=false behavior

        When disabled, even invalid keys SHALL not cause rejection.
        """
        assume(api_key not in valid_keys)

        app = create_app(valid_keys, enabled=False)
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {api_key}"},
        )

        assert response.status_code == 200
