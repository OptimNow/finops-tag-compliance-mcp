"""
Property-based tests for CORS Restriction.

Feature: production-security, Property 21: CORS Restriction
Validates: Requirements 20.1, 20.2, 20.3

Property 21 states:
*For all* origin and allowed_origins:
- If origin in allowed_origins: CORS headers allow request
- If origin not in allowed_origins: CORS headers block request
- Wildcard (*) SHALL NOT be used in production mode

The MCP Server SHALL restrict CORS origins to a configurable allowlist
and reject requests from non-allowed origins with appropriate CORS headers.
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from mcp_server.middleware.cors_middleware import (
    get_cors_config,
    parse_cors_origins,
)


# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def origin_strategy(draw):
    """Generate valid origin URLs."""
    scheme = draw(st.sampled_from(["https", "http"]))
    # Domain with optional subdomain
    subdomain = draw(st.sampled_from(["", "www.", "api.", "app.", "cdn."]))
    domain = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
            min_size=3,
            max_size=20,
        )
    )
    tld = draw(st.sampled_from([".com", ".io", ".ai", ".org", ".net", ".dev"]))
    port = draw(st.sampled_from(["", ":3000", ":8080", ":443"]))

    return f"{scheme}://{subdomain}{domain}{tld}{port}"


@st.composite
def allowed_origins_strategy(draw):
    """Generate a list of allowed origins."""
    origins = draw(st.lists(origin_strategy(), min_size=0, max_size=10, unique=True))
    return origins


@st.composite
def cors_origins_string_strategy(draw):
    """Generate a CORS origins configuration string."""
    # Can be wildcard, empty, or comma-separated origins
    return draw(
        st.one_of(
            st.just("*"),  # Wildcard
            st.just(""),  # Empty
            st.lists(origin_strategy(), min_size=1, max_size=5, unique=True).map(
                lambda origins: ",".join(origins)
            ),
        )
    )


# =============================================================================
# Property 21: CORS Restriction
# =============================================================================


class TestCORSRestriction:
    """
    Property 21: CORS Restriction

    For all origin and allowed_origins:
    - If origin in allowed_origins: CORS headers allow request
    - If origin not in allowed_origins: CORS headers block request

    Validates: Requirements 20.1, 20.2, 20.3
    """

    # -------------------------------------------------------------------------
    # Origin Parsing Property Tests (Requirement 20.4)
    # -------------------------------------------------------------------------

    @given(origins_str=cors_origins_string_strategy())
    @settings(max_examples=100, deadline=None)
    def test_parse_cors_origins_never_crashes(self, origins_str: str):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirement 20.4

        parse_cors_origins SHALL handle any string input without crashing.
        """
        result = parse_cors_origins(origins_str)
        assert isinstance(result, list)

    @given(origins=allowed_origins_strategy())
    @settings(max_examples=100, deadline=None)
    def test_parse_preserves_all_origins(self, origins: list[str]):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirement 20.4

        parse_cors_origins SHALL preserve all valid origins.
        """
        origins_str = ",".join(origins)
        result = parse_cors_origins(origins_str)

        # All original origins should be present
        assert set(result) == set(origins)

    @given(
        origins=st.lists(origin_strategy(), min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=100, deadline=None)
    def test_parse_handles_whitespace(self, origins: list[str]):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirement 20.4

        parse_cors_origins SHALL strip whitespace from origins.
        """
        # Add random whitespace
        origins_with_spaces = [f"  {o}  " for o in origins]
        origins_str = " , ".join(origins_with_spaces)
        result = parse_cors_origins(origins_str)

        # Whitespace should be stripped
        assert set(result) == set(origins)

    # -------------------------------------------------------------------------
    # CORS Configuration Property Tests (Requirements 20.1, 20.2, 20.5, 20.6)
    # -------------------------------------------------------------------------

    @given(origins=allowed_origins_strategy())
    @settings(max_examples=100, deadline=None)
    def test_config_always_returns_valid_structure(self, origins: list[str]):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirements 20.1, 20.5, 20.6

        get_cors_config SHALL always return a valid CORS config structure.
        """
        config = get_cors_config(origins)

        assert "allow_origins" in config
        assert "allow_credentials" in config
        assert "allow_methods" in config
        assert "allow_headers" in config

        assert isinstance(config["allow_origins"], list)
        assert isinstance(config["allow_credentials"], bool)
        assert isinstance(config["allow_methods"], list)
        assert isinstance(config["allow_headers"], list)

    @given(origins=allowed_origins_strategy())
    @settings(max_examples=100, deadline=None)
    def test_config_credentials_always_false(self, origins: list[str]):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: MCP protocol doesn't use cookies

        allow_credentials SHALL always be False for MCP.
        """
        config = get_cors_config(origins)
        assert config["allow_credentials"] is False

    @given(origins=st.lists(origin_strategy(), min_size=1, max_size=10, unique=True))
    @settings(max_examples=100, deadline=None)
    def test_specific_origins_restrict_methods(self, origins: list[str]):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirement 20.5

        Specific origins SHALL restrict methods to POST and OPTIONS.
        """
        config = get_cors_config(origins)

        # POST must be allowed
        assert "POST" in config["allow_methods"]
        # OPTIONS for preflight
        assert "OPTIONS" in config["allow_methods"]
        # GET should NOT be allowed for specific origins
        assert "GET" not in config["allow_methods"]

    @given(origins=st.lists(origin_strategy(), min_size=1, max_size=10, unique=True))
    @settings(max_examples=100, deadline=None)
    def test_specific_origins_restrict_headers(self, origins: list[str]):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirement 20.6

        Specific origins SHALL restrict headers to allowed list.
        """
        config = get_cors_config(origins)

        # Required headers
        assert "Content-Type" in config["allow_headers"]
        assert "Authorization" in config["allow_headers"]
        assert "X-Correlation-ID" in config["allow_headers"]

        # Wildcard should NOT be allowed
        assert "*" not in config["allow_headers"]

    def test_wildcard_allows_all_methods(self):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Development mode behavior

        Wildcard SHALL allow all methods in development.
        """
        config = get_cors_config(["*"])

        assert "GET" in config["allow_methods"]
        assert "POST" in config["allow_methods"]

    def test_wildcard_allows_all_headers(self):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Development mode behavior

        Wildcard SHALL allow all headers in development.
        """
        config = get_cors_config(["*"])

        assert "*" in config["allow_headers"]

    # -------------------------------------------------------------------------
    # Production Mode Property Tests (Requirement 20.2)
    # -------------------------------------------------------------------------

    @given(origins=st.lists(origin_strategy(), min_size=1, max_size=10, unique=True))
    @settings(max_examples=100, deadline=None)
    def test_production_origins_never_wildcard(self, origins: list[str]):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirement 20.2

        Production mode SHALL NOT use wildcard (*) for allowed origins.
        """
        # When specific origins are configured, wildcard should not be present
        config = get_cors_config(origins)

        assert "*" not in config["allow_origins"]

    def test_empty_origins_blocks_all(self):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirement 20.2

        Empty origins list SHALL block all cross-origin requests.
        """
        config = get_cors_config([])

        assert config["allow_origins"] == []

    # -------------------------------------------------------------------------
    # Origin Matching Property Tests (Requirement 20.1, 20.3)
    # -------------------------------------------------------------------------

    @given(
        origin=origin_strategy(),
        allowed_origins=allowed_origins_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_allowed_origin_in_config(self, origin: str, allowed_origins: list[str]):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirement 20.1

        Allowed origins SHALL be present in config.
        """
        # Add the test origin to allowed list
        all_origins = list(set(allowed_origins + [origin]))
        config = get_cors_config(all_origins)

        assert origin in config["allow_origins"]

    @given(
        origin=origin_strategy(),
        allowed_origins=allowed_origins_strategy(),
    )
    @settings(max_examples=100, deadline=None)
    def test_non_allowed_origin_not_in_config(
        self, origin: str, allowed_origins: list[str]
    ):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Requirement 20.3

        Non-allowed origins SHALL NOT be in config (unless wildcard).
        """
        # Ensure origin is not in allowed list
        assume(origin not in allowed_origins)

        config = get_cors_config(allowed_origins)

        # Origin should not be in allow list
        assert origin not in config["allow_origins"]

    # -------------------------------------------------------------------------
    # Configuration Determinism Property Tests
    # -------------------------------------------------------------------------

    @given(origins=allowed_origins_strategy())
    @settings(max_examples=50, deadline=None)
    def test_config_is_deterministic(self, origins: list[str]):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Configuration stability

        get_cors_config SHALL be deterministic.
        """
        config1 = get_cors_config(origins)
        config2 = get_cors_config(origins)

        assert config1 == config2

    @given(origins_str=cors_origins_string_strategy())
    @settings(max_examples=50, deadline=None)
    def test_parse_is_deterministic(self, origins_str: str):
        """
        Feature: production-security, Property 21: CORS Restriction
        Validates: Parsing stability

        parse_cors_origins SHALL be deterministic.
        """
        result1 = parse_cors_origins(origins_str)
        result2 = parse_cors_origins(origins_str)

        assert result1 == result2
