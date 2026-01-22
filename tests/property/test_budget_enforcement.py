"""
Property-based tests for Budget Enforcement.

Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
Validates: Requirements 15.3, 15.5

Property 14 states:
*For any* agent session with a configured step budget (max tool calls),
the MCP Server SHALL reject additional tool calls once the budget is exhausted
and return a graceful degradation response explaining the limit was reached.
The response SHALL NOT be an error but a structured message indicating budget exhaustion.
"""


import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from mcp_server.middleware.budget_middleware import (
    BudgetExhaustedError,
    BudgetTracker,
)
from mcp_server.models.budget import (
    BudgetConfiguration,
    BudgetExhaustedResponse,
    BudgetHealthInfo,
)

# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def session_id_strategy(draw):
    """Generate valid session IDs."""
    # Session IDs should be non-empty strings
    prefix = draw(st.sampled_from(["session", "sess", "s", "agent", "user"]))
    suffix = draw(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=1, max_size=30)
    )
    return f"{prefix}_{suffix}"


@st.composite
def budget_config_strategy(draw):
    """Generate valid budget configurations."""
    max_calls = draw(st.integers(min_value=1, max_value=1000))
    session_ttl = draw(st.integers(min_value=60, max_value=86400))  # 1 min to 24 hours
    return {
        "max_calls_per_session": max_calls,
        "session_ttl_seconds": session_ttl,
    }


@st.composite
def call_count_strategy(draw, max_calls: int = 100):
    """Generate valid call counts."""
    return draw(st.integers(min_value=0, max_value=max_calls * 2))


# =============================================================================
# Property 14: Tool Budget Enforcement
# =============================================================================


class TestBudgetEnforcement:
    """
    Property 14: Tool Budget Enforcement

    For any agent session with a configured step budget (max tool calls),
    the MCP Server SHALL reject additional tool calls once the budget is exhausted
    and return a graceful degradation response explaining the limit was reached.
    The response SHALL NOT be an error but a structured message indicating budget exhaustion.

    Validates: Requirements 15.3, 15.5
    """

    # -------------------------------------------------------------------------
    # Budget Tracking Initialization Tests (Requirement 15.3)
    # -------------------------------------------------------------------------

    @given(config=budget_config_strategy())
    @settings(max_examples=100, deadline=None)
    def test_budget_tracker_respects_configuration(self, config: dict):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        Budget tracker SHALL respect the configured max calls and TTL.
        """
        tracker = BudgetTracker(
            redis_cache=None,
            max_calls_per_session=config["max_calls_per_session"],
            session_ttl_seconds=config["session_ttl_seconds"],
        )

        assert tracker.max_calls_per_session == config["max_calls_per_session"]
        assert tracker.session_ttl_seconds == config["session_ttl_seconds"]

    # -------------------------------------------------------------------------
    # Budget Consumption Tests (Requirement 15.3)
    # -------------------------------------------------------------------------

    @given(
        session_id=session_id_strategy(),
        max_calls=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_budget_allows_calls_within_limit(
        self,
        session_id: str,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        Budget tracker SHALL allow tool calls while within the budget limit.
        """
        tracker = BudgetTracker(
            redis_cache=None,
            max_calls_per_session=max_calls,
        )

        # Make calls up to the limit
        for i in range(max_calls):
            success, count, limit = await tracker.consume_budget(session_id)
            assert success is True, f"Call {i+1} should succeed"
            assert count == i + 1, f"Count should be {i+1}"
            assert limit == max_calls, f"Limit should be {max_calls}"

    @given(
        session_id=session_id_strategy(),
        max_calls=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_budget_rejects_calls_when_exhausted(
        self,
        session_id: str,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        Budget tracker SHALL reject tool calls once budget is exhausted.
        """
        tracker = BudgetTracker(
            redis_cache=None,
            max_calls_per_session=max_calls,
        )

        # Exhaust the budget
        for _ in range(max_calls):
            await tracker.consume_budget(session_id)

        # Next call should raise BudgetExhaustedError
        with pytest.raises(BudgetExhaustedError) as exc_info:
            await tracker.consume_budget(session_id)

        error = exc_info.value
        assert error.session_id == session_id
        assert error.current_count == max_calls
        assert error.max_calls == max_calls

    # -------------------------------------------------------------------------
    # Graceful Degradation Response Tests (Requirement 15.5)
    # -------------------------------------------------------------------------

    @given(
        session_id=session_id_strategy(),
        current_usage=st.integers(min_value=1, max_value=1000),
        limit=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=100, deadline=None)
    def test_budget_exhausted_response_is_structured(
        self,
        session_id: str,
        current_usage: int,
        limit: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.5

        Budget exhaustion response SHALL be a structured message, not an error.
        """
        response = BudgetExhaustedResponse.create(
            session_id=session_id,
            current_usage=current_usage,
            limit=limit,
        )

        # Response should be a structured object, not an exception
        assert isinstance(response, BudgetExhaustedResponse)
        assert response.error_type == "budget_exhausted"
        assert response.session_id == session_id
        assert response.current_usage == current_usage
        assert response.limit == limit

    @given(
        session_id=session_id_strategy(),
        current_usage=st.integers(min_value=1, max_value=1000),
        limit=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=100, deadline=None)
    def test_budget_exhausted_response_contains_explanation(
        self,
        session_id: str,
        current_usage: int,
        limit: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.5

        Budget exhaustion response SHALL explain the limit was reached.
        """
        response = BudgetExhaustedResponse.create(
            session_id=session_id,
            current_usage=current_usage,
            limit=limit,
        )

        # Message should explain the situation
        assert "budget" in response.message.lower() or "exhausted" in response.message.lower()
        assert str(current_usage) in response.message
        assert str(limit) in response.message

        # Should have a suggestion for the user
        assert response.suggestion is not None
        assert len(response.suggestion) > 0

    @given(
        session_id=session_id_strategy(),
        current_usage=st.integers(min_value=1, max_value=1000),
        limit=st.integers(min_value=1, max_value=1000),
        retry_after=st.integers(min_value=60, max_value=3600),
    )
    @settings(max_examples=100, deadline=None)
    def test_budget_exhausted_response_includes_retry_info(
        self,
        session_id: str,
        current_usage: int,
        limit: int,
        retry_after: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.5

        Budget exhaustion response SHALL include retry information when available.
        """
        response = BudgetExhaustedResponse.create(
            session_id=session_id,
            current_usage=current_usage,
            limit=limit,
            retry_after_seconds=retry_after,
        )

        assert response.retry_after_seconds == retry_after
        # Suggestion should mention the retry time
        assert "minute" in response.suggestion.lower() or "session" in response.suggestion.lower()

    @given(
        session_id=session_id_strategy(),
        current_usage=st.integers(min_value=1, max_value=1000),
        limit=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=100, deadline=None)
    def test_budget_exhausted_response_converts_to_mcp_content(
        self,
        session_id: str,
        current_usage: int,
        limit: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.5

        Budget exhaustion response SHALL convert to MCP content format.
        """
        response = BudgetExhaustedResponse.create(
            session_id=session_id,
            current_usage=current_usage,
            limit=limit,
        )

        mcp_content = response.to_mcp_content()

        # Should be a list of content items
        assert isinstance(mcp_content, list)
        assert len(mcp_content) >= 1

        # First item should be text content
        assert mcp_content[0]["type"] == "text"
        assert "text" in mcp_content[0]

        # Text should contain relevant information
        text = mcp_content[0]["text"]
        assert session_id in text
        assert str(current_usage) in text
        assert str(limit) in text

    # -------------------------------------------------------------------------
    # Budget Status Tracking Tests (Requirement 15.3)
    # -------------------------------------------------------------------------

    @given(
        session_id=session_id_strategy(),
        max_calls=st.integers(min_value=5, max_value=50),
        calls_made=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_budget_status_reflects_current_state(
        self,
        session_id: str,
        max_calls: int,
        calls_made: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        Budget status SHALL accurately reflect the current usage state.
        """
        # Ensure calls_made doesn't exceed max_calls for this test
        calls_made = min(calls_made, max_calls)

        tracker = BudgetTracker(
            redis_cache=None,
            max_calls_per_session=max_calls,
        )

        # Make the specified number of calls
        for _ in range(calls_made):
            await tracker.consume_budget(session_id)

        # Get status
        status = await tracker.get_budget_status(session_id)

        assert status["session_id"] == session_id
        assert status["current_count"] == calls_made
        assert status["max_calls"] == max_calls
        assert status["remaining"] == max_calls - calls_made
        assert status["is_exhausted"] == (calls_made >= max_calls)

    @given(
        session_id=session_id_strategy(),
        max_calls=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_budget_utilization_percentage_correct(
        self,
        session_id: str,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        Budget utilization percentage SHALL be calculated correctly.
        """
        tracker = BudgetTracker(
            redis_cache=None,
            max_calls_per_session=max_calls,
        )

        # Make half the calls
        half_calls = max_calls // 2
        for _ in range(half_calls):
            await tracker.consume_budget(session_id)

        status = await tracker.get_budget_status(session_id)

        expected_utilization = (half_calls / max_calls) * 100
        assert abs(status["utilization_percent"] - expected_utilization) < 0.01

    # -------------------------------------------------------------------------
    # Budget Reset Tests (Requirement 15.3)
    # -------------------------------------------------------------------------

    @given(
        session_id=session_id_strategy(),
        max_calls=st.integers(min_value=5, max_value=20),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_budget_reset_clears_count(
        self,
        session_id: str,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        Budget reset SHALL clear the call count for a session.
        """
        tracker = BudgetTracker(
            redis_cache=None,
            max_calls_per_session=max_calls,
        )

        # Make some calls
        for _ in range(max_calls // 2):
            await tracker.consume_budget(session_id)

        # Reset budget
        result = await tracker.reset_budget(session_id)
        assert result is True

        # Count should be zero
        count = await tracker.get_current_count(session_id)
        assert count == 0

    # -------------------------------------------------------------------------
    # Budget Check Without Consumption Tests (Requirement 15.3)
    # -------------------------------------------------------------------------

    @given(
        session_id=session_id_strategy(),
        max_calls=st.integers(min_value=5, max_value=50),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_check_budget_does_not_consume(
        self,
        session_id: str,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        Checking budget SHALL NOT consume budget units.
        """
        tracker = BudgetTracker(
            redis_cache=None,
            max_calls_per_session=max_calls,
        )

        # Check budget multiple times
        for _ in range(10):
            has_budget, count, limit = await tracker.check_budget(session_id)
            assert has_budget is True
            assert count == 0  # Should not increment
            assert limit == max_calls

    # -------------------------------------------------------------------------
    # Session Isolation Tests (Requirement 15.3)
    # -------------------------------------------------------------------------

    @given(
        session_id_1=session_id_strategy(),
        session_id_2=session_id_strategy(),
        max_calls=st.integers(min_value=5, max_value=20),
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_budget_isolated_per_session(
        self,
        session_id_1: str,
        session_id_2: str,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        Budget tracking SHALL be isolated per session.
        """
        # Ensure different session IDs
        assume(session_id_1 != session_id_2)

        tracker = BudgetTracker(
            redis_cache=None,
            max_calls_per_session=max_calls,
        )

        # Exhaust budget for session 1
        for _ in range(max_calls):
            await tracker.consume_budget(session_id_1)

        # Session 2 should still have full budget
        has_budget, count, limit = await tracker.check_budget(session_id_2)
        assert has_budget is True
        assert count == 0

    # -------------------------------------------------------------------------
    # BudgetExhaustedError Tests (Requirement 15.3)
    # -------------------------------------------------------------------------

    @given(
        session_id=session_id_strategy(),
        current_count=st.integers(min_value=1, max_value=1000),
        max_calls=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=100, deadline=None)
    def test_budget_exhausted_error_contains_details(
        self,
        session_id: str,
        current_count: int,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        BudgetExhaustedError SHALL contain session and count details.
        """
        error = BudgetExhaustedError(
            session_id=session_id,
            current_count=current_count,
            max_calls=max_calls,
        )

        assert error.session_id == session_id
        assert error.current_count == current_count
        assert error.max_calls == max_calls
        assert session_id in str(error)

    # -------------------------------------------------------------------------
    # Model Validation Tests (Requirement 15.5)
    # -------------------------------------------------------------------------

    @given(
        enabled=st.booleans(),
        max_calls=st.integers(min_value=1, max_value=10000),
        session_ttl=st.integers(min_value=60, max_value=86400),
    )
    @settings(max_examples=100, deadline=None)
    def test_budget_configuration_model_valid(
        self,
        enabled: bool,
        max_calls: int,
        session_ttl: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        BudgetConfiguration model SHALL accept valid configurations.
        """
        config = BudgetConfiguration(
            enabled=enabled,
            max_calls_per_session=max_calls,
            session_ttl_seconds=session_ttl,
        )

        assert config.enabled == enabled
        assert config.max_calls_per_session == max_calls
        assert config.session_ttl_seconds == session_ttl

    @given(
        enabled=st.booleans(),
        max_calls=st.integers(min_value=0, max_value=10000),
        session_ttl=st.integers(min_value=0, max_value=86400),
        active_sessions=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=100, deadline=None)
    def test_budget_health_info_model_valid(
        self,
        enabled: bool,
        max_calls: int,
        session_ttl: int,
        active_sessions: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 14: Tool Budget Enforcement
        Validates: Requirements 15.3

        BudgetHealthInfo model SHALL accept valid health information.
        """
        health_info = BudgetHealthInfo(
            enabled=enabled,
            max_calls_per_session=max_calls,
            session_ttl_seconds=session_ttl,
            active_sessions=active_sessions,
        )

        assert health_info.enabled == enabled
        assert health_info.max_calls_per_session == max_calls
        assert health_info.session_ttl_seconds == session_ttl
        assert health_info.active_sessions == active_sessions
