"""Property-based tests for loop detection.

Feature: phase-1-aws-mvp, Property 15: Loop Detection
Validates: Requirements 15.4

Property 15: Loop Detection
*For any* sequence of tool calls within a session, the MCP Server SHALL detect
when the same tool is called with identical parameters more than N times
(configurable, default 3) and block further identical calls. The blocked call
SHALL return a message explaining the loop was detected.
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime, timedelta
import hashlib
import json
from typing import Optional

from mcp_server.utils.loop_detection import (
    LoopDetector,
    LoopDetectedError,
    DEFAULT_MAX_IDENTICAL_CALLS,
    DEFAULT_SLIDING_WINDOW_SECONDS,
)
from mcp_server.models.loop_detection import (
    LoopDetectedResponse,
    LoopDetectionConfiguration,
    LoopDetectionHealthInfo,
)


# Strategies for generating test data
tool_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=50,
).filter(lambda x: x.strip() != "")

session_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-"),
    min_size=8,
    max_size=36,
).filter(lambda x: x.strip() != "")

# Strategy for generating tool parameters
simple_param_value = st.one_of(
    st.text(max_size=100),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.none(),
)

parameters_strategy = st.dictionaries(
    keys=st.text(min_size=1, max_size=20).filter(lambda x: x.strip() != ""),
    values=simple_param_value,
    max_size=10,
)

# Strategy for max identical calls configuration
max_calls_strategy = st.integers(min_value=1, max_value=20)


class TestLoopDetectionProperty:
    """Property tests for loop detection behavior."""

    @pytest.mark.asyncio
    @given(
        session_id=session_id_strategy,
        tool_name=tool_name_strategy,
        parameters=parameters_strategy,
        max_calls=st.integers(min_value=2, max_value=20),  # min 2 to have meaningful test
    )
    @settings(max_examples=100, deadline=None)
    async def test_property_15_loop_detected_after_n_calls(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 15: Loop Detection
        Validates: Requirements 15.4

        For any session, tool, and parameters, calling the same tool with
        identical parameters more than N times SHALL trigger loop detection.
        """
        # Create a loop detector with the specified max calls
        detector = LoopDetector(
            redis_cache=None,  # Use local storage for testing
            max_identical_calls=max_calls,
            sliding_window_seconds=300,
        )

        # Make max_calls calls (should all succeed)
        for i in range(max_calls):
            loop_detected, count = await detector.record_call(
                session_id=session_id,
                tool_name=tool_name,
                parameters=parameters,
            )
            assert not loop_detected, f"Loop should not be detected on call {i + 1}"
            assert count == i + 1, f"Count should be {i + 1}, got {count}"

        # The (N+1)th call should trigger loop detection
        with pytest.raises(LoopDetectedError) as exc_info:
            await detector.record_call(
                session_id=session_id,
                tool_name=tool_name,
                parameters=parameters,
            )

        # Verify the error contains correct information
        error = exc_info.value
        assert error.tool_name == tool_name
        assert error.call_count >= max_calls
        assert error.max_calls == max_calls
        assert error.call_signature is not None

    @pytest.mark.asyncio
    @given(
        session_id=session_id_strategy,
        tool_name=tool_name_strategy,
        params1=parameters_strategy,
        params2=parameters_strategy,
        max_calls=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=100, deadline=None)
    async def test_property_15_different_params_no_loop(
        self,
        session_id: str,
        tool_name: str,
        params1: dict,
        params2: dict,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 15: Loop Detection
        Validates: Requirements 15.4

        For any session and tool, calls with DIFFERENT parameters should NOT
        trigger loop detection, even if the same tool is called many times.
        """
        # Ensure params are actually different
        assume(json.dumps(params1, sort_keys=True) != json.dumps(params2, sort_keys=True))

        detector = LoopDetector(
            redis_cache=None,
            max_identical_calls=max_calls,
            sliding_window_seconds=300,
        )

        # Alternate between two different parameter sets
        # This should never trigger loop detection
        for i in range(max_calls * 2):
            params = params1 if i % 2 == 0 else params2
            loop_detected, count = await detector.record_call(
                session_id=session_id,
                tool_name=tool_name,
                parameters=params,
            )
            # Each parameter set should have its own count
            assert not loop_detected, f"Loop should not be detected with alternating params"

    @pytest.mark.asyncio
    @given(
        session1=session_id_strategy,
        session2=session_id_strategy,
        tool_name=tool_name_strategy,
        parameters=parameters_strategy,
        max_calls=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=100, deadline=None)
    async def test_property_15_different_sessions_independent(
        self,
        session1: str,
        session2: str,
        tool_name: str,
        parameters: dict,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 15: Loop Detection
        Validates: Requirements 15.4

        For any two different sessions, loop detection should be independent.
        Calls in one session should not affect the count in another session.
        """
        # Ensure sessions are different
        assume(session1 != session2)

        detector = LoopDetector(
            redis_cache=None,
            max_identical_calls=max_calls,
            sliding_window_seconds=300,
        )

        # Make max_calls calls in session1 (all should succeed)
        for i in range(max_calls):
            await detector.record_call(
                session_id=session1,
                tool_name=tool_name,
                parameters=parameters,
            )

        # Session2 should start fresh - first call should have count 1
        loop_detected, count = await detector.record_call(
            session_id=session2,
            tool_name=tool_name,
            parameters=parameters,
        )
        assert not loop_detected, "Session2 should not be affected by session1"
        assert count == 1, "Session2 should start with count 1"

    @pytest.mark.asyncio
    @given(
        session_id=session_id_strategy,
        tool_name=tool_name_strategy,
        parameters=parameters_strategy,
        max_calls=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=100, deadline=None)
    async def test_property_15_loop_response_contains_explanation(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict,
        max_calls: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 15: Loop Detection
        Validates: Requirements 15.4

        When a loop is detected, the response SHALL contain a message
        explaining that the loop was detected.
        """
        detector = LoopDetector(
            redis_cache=None,
            max_identical_calls=max_calls,
            sliding_window_seconds=300,
        )

        # Make enough calls to trigger loop detection
        for _ in range(max_calls):
            await detector.record_call(
                session_id=session_id,
                tool_name=tool_name,
                parameters=parameters,
            )

        # Trigger loop detection
        with pytest.raises(LoopDetectedError) as exc_info:
            await detector.record_call(
                session_id=session_id,
                tool_name=tool_name,
                parameters=parameters,
            )

        error = exc_info.value

        # Create the response object
        response = LoopDetectedResponse.create(
            tool_name=error.tool_name,
            call_count=error.call_count,
            max_calls=error.max_calls,
        )

        # Verify response contains explanation
        assert response.error_type == "loop_detected"
        assert tool_name in response.message
        assert "loop" in response.message.lower() or "Loop" in response.message
        assert response.suggestion is not None and len(response.suggestion) > 0

        # Verify MCP content format
        mcp_content = response.to_mcp_content()
        assert len(mcp_content) > 0
        assert mcp_content[0]["type"] == "text"
        assert tool_name in mcp_content[0]["text"]


class TestLoopDetectionCallSignature:
    """Property tests for call signature generation."""

    @pytest.mark.asyncio
    @given(
        tool_name=tool_name_strategy,
        parameters=parameters_strategy,
    )
    @settings(max_examples=100, deadline=None)
    async def test_call_signature_deterministic(
        self,
        tool_name: str,
        parameters: dict,
    ):
        """
        For any tool and parameters, the call signature should be deterministic.
        The same inputs should always produce the same signature.
        """
        detector = LoopDetector(redis_cache=None)

        sig1 = detector._generate_call_signature(tool_name, parameters)
        sig2 = detector._generate_call_signature(tool_name, parameters)

        assert sig1 == sig2, "Same inputs should produce same signature"

    @pytest.mark.asyncio
    @given(
        tool_name=tool_name_strategy,
        params1=parameters_strategy,
        params2=parameters_strategy,
    )
    @settings(max_examples=100, deadline=None)
    async def test_call_signature_different_for_different_params(
        self,
        tool_name: str,
        params1: dict,
        params2: dict,
    ):
        """
        For any tool with different parameters, the call signatures should differ.
        """
        # Ensure params are actually different
        assume(json.dumps(params1, sort_keys=True) != json.dumps(params2, sort_keys=True))

        detector = LoopDetector(redis_cache=None)

        sig1 = detector._generate_call_signature(tool_name, params1)
        sig2 = detector._generate_call_signature(tool_name, params2)

        assert sig1 != sig2, "Different params should produce different signatures"

    @pytest.mark.asyncio
    @given(
        tool1=tool_name_strategy,
        tool2=tool_name_strategy,
        parameters=parameters_strategy,
    )
    @settings(max_examples=100, deadline=None)
    async def test_call_signature_different_for_different_tools(
        self,
        tool1: str,
        tool2: str,
        parameters: dict,
    ):
        """
        For different tools with same parameters, the call signatures should differ.
        """
        assume(tool1 != tool2)

        detector = LoopDetector(redis_cache=None)

        sig1 = detector._generate_call_signature(tool1, parameters)
        sig2 = detector._generate_call_signature(tool2, parameters)

        assert sig1 != sig2, "Different tools should produce different signatures"


class TestLoopDetectionConfiguration:
    """Property tests for loop detection configuration."""

    @given(
        max_calls=st.integers(min_value=1, max_value=100),
        window_seconds=st.integers(min_value=60, max_value=3600),
    )
    @settings(max_examples=50, deadline=None)
    def test_configuration_valid_values(
        self,
        max_calls: int,
        window_seconds: int,
    ):
        """
        For any valid configuration values, the configuration model should accept them.
        """
        config = LoopDetectionConfiguration(
            enabled=True,
            max_identical_calls=max_calls,
            sliding_window_seconds=window_seconds,
        )

        assert config.enabled is True
        assert config.max_identical_calls == max_calls
        assert config.sliding_window_seconds == window_seconds

    @given(
        max_calls=st.integers(min_value=1, max_value=100),
        window_seconds=st.integers(min_value=60, max_value=3600),
    )
    @settings(max_examples=50, deadline=None)
    def test_detector_respects_configuration(
        self,
        max_calls: int,
        window_seconds: int,
    ):
        """
        For any configuration, the detector should respect the configured values.
        """
        detector = LoopDetector(
            redis_cache=None,
            max_identical_calls=max_calls,
            sliding_window_seconds=window_seconds,
        )

        assert detector.max_identical_calls == max_calls
        assert detector.sliding_window_seconds == window_seconds


class TestLoopDetectionStats:
    """Property tests for loop detection statistics."""

    @pytest.mark.asyncio
    @given(
        session_id=session_id_strategy,
        tool_name=tool_name_strategy,
        parameters=parameters_strategy,
        max_calls=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    async def test_stats_track_loop_events(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict,
        max_calls: int,
    ):
        """
        For any loop detection event, the statistics should be updated.
        """
        detector = LoopDetector(
            redis_cache=None,
            max_identical_calls=max_calls,
            sliding_window_seconds=300,
        )

        # Get initial total from internal counter
        initial_total = detector._total_loops_detected

        # Trigger a loop - make max_calls successful calls first
        for _ in range(max_calls):
            await detector.record_call(session_id, tool_name, parameters)

        # This call should trigger loop detection
        try:
            await detector.record_call(session_id, tool_name, parameters)
        except LoopDetectedError:
            pass  # Expected

        # Check internal counter was updated
        assert detector._total_loops_detected > initial_total
        assert tool_name in detector._loop_events_by_tool

        # Also verify stats method returns updated values
        updated_stats = await detector.get_loop_detection_stats()
        assert updated_stats["loops_detected_total"] > initial_total
        assert tool_name in updated_stats.get("loops_by_tool", {})

    @pytest.mark.asyncio
    @given(
        session_id=session_id_strategy,
        tool_name=tool_name_strategy,
        parameters=parameters_strategy,
    )
    @settings(max_examples=50, deadline=None)
    async def test_recent_events_tracked(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict,
    ):
        """
        For any loop detection, the event should be tracked in recent events.
        """
        detector = LoopDetector(
            redis_cache=None,
            max_identical_calls=2,  # Low threshold for quick testing
            sliding_window_seconds=300,
        )

        # Trigger a loop - make 2 successful calls first
        await detector.record_call(session_id, tool_name, parameters)
        await detector.record_call(session_id, tool_name, parameters)

        # This call should trigger loop detection
        try:
            await detector.record_call(session_id, tool_name, parameters)
        except LoopDetectedError:
            pass  # Expected

        # Check recent events
        recent_events = detector.get_recent_loop_events(limit=10)
        assert len(recent_events) > 0

        # Find our event
        found = False
        for event in recent_events:
            if event["tool_name"] == tool_name and event["session_id"] == session_id:
                found = True
                assert event["event_type"] == "loop_detected"
                break

        assert found, f"Event for tool '{tool_name}' should be in recent events"


class TestLoopDetectionReset:
    """Property tests for session reset functionality."""

    @pytest.mark.asyncio
    @given(
        session_id=session_id_strategy,
        tool_name=tool_name_strategy,
        parameters=parameters_strategy,
        max_calls=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    async def test_reset_clears_session_history(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict,
        max_calls: int,
    ):
        """
        For any session, resetting should clear the call history.
        After reset, the same calls should not trigger loop detection.
        """
        detector = LoopDetector(
            redis_cache=None,
            max_identical_calls=max_calls,
            sliding_window_seconds=300,
        )

        # Make some calls (but not enough to trigger loop)
        for _ in range(max_calls):
            await detector.record_call(session_id, tool_name, parameters)

        # Reset the session
        await detector.reset_session(session_id)

        # Now we should be able to make max_calls calls again
        for i in range(max_calls):
            loop_detected, count = await detector.record_call(session_id, tool_name, parameters)
            assert not loop_detected, f"After reset, call {i + 1} should not trigger loop"
            assert count == i + 1, f"After reset, count should restart from 1"
