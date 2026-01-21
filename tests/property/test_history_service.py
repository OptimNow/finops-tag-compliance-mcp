"""
Property-based tests for HistoryService.

Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
Validates: Requirements 8.1, 8.2, 8.3

Property 9 states:
*For any* violation history request, the response SHALL include historical
compliance scores grouped by the specified interval (day, week, month).
The trend direction SHALL be calculated correctly: "improving" if latest
score > earliest score, "declining" if latest < earliest, "stable" otherwise.
"""

from datetime import datetime, timedelta

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.history import ComplianceHistoryResult, GroupBy, TrendDirection
from mcp_server.services.history_service import HistoryService

# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def compliance_score_strategy(draw):
    """Generate a valid compliance score between 0.0 and 1.0."""
    return draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))


@st.composite
def compliance_result_strategy(draw, timestamp: datetime = None):
    """Generate a valid ComplianceResult for testing."""
    total = draw(st.integers(min_value=1, max_value=1000))
    compliant = draw(st.integers(min_value=0, max_value=total))
    score = compliant / total if total > 0 else 1.0

    ts = timestamp or datetime.utcnow()

    return ComplianceResult(
        compliance_score=score,
        total_resources=total,
        compliant_resources=compliant,
        violations=[],
        cost_attribution_gap=0.0,
        scan_timestamp=ts,
    )


# =============================================================================
# Property 9: History Tracking Correctness
# =============================================================================


class TestHistoryTrackingCorrectness:
    """
    Property 9: History Tracking Correctness

    For any violation history request, the response SHALL include historical
    compliance scores grouped by the specified interval (day, week, month).
    The trend direction SHALL be calculated correctly: "improving" if latest
    score > earliest score, "declining" if latest < earliest, "stable" otherwise.

    Validates: Requirements 8.1, 8.2, 8.3
    """

    # -------------------------------------------------------------------------
    # Trend Direction Tests
    # -------------------------------------------------------------------------

    @given(
        earliest_score=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
        latest_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_trend_direction_improving_when_latest_greater(
        self,
        earliest_score: float,
        latest_score: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.3

        The trend direction SHALL be "improving" if latest score > earliest score.
        """
        assume(latest_score > earliest_score)

        service = HistoryService(db_path=":memory:")

        try:
            # Store two scan results with different scores
            now = datetime.utcnow()

            # Earlier scan with lower score
            earlier_result = ComplianceResult(
                compliance_score=earliest_score,
                total_resources=100,
                compliant_resources=int(earliest_score * 100),
                violations=[],
                scan_timestamp=now - timedelta(days=5),
            )
            await service.store_scan_result(earlier_result)

            # Later scan with higher score
            later_result = ComplianceResult(
                compliance_score=latest_score,
                total_resources=100,
                compliant_resources=int(latest_score * 100),
                violations=[],
                scan_timestamp=now,
            )
            await service.store_scan_result(later_result)

            # Get history
            history = await service.get_history(days_back=30, group_by=GroupBy.DAY)

            # Trend should be improving
            assert history.trend_direction == TrendDirection.IMPROVING, (
                f"Expected IMPROVING trend for earliest={earliest_score}, "
                f"latest={latest_score}, got {history.trend_direction}"
            )
        finally:
            service.close()

    @given(
        earliest_score=st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
        latest_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_trend_direction_declining_when_latest_less(
        self,
        earliest_score: float,
        latest_score: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.3

        The trend direction SHALL be "declining" if latest score < earliest score.
        """
        assume(latest_score < earliest_score)

        service = HistoryService(db_path=":memory:")

        try:
            now = datetime.utcnow()

            # Earlier scan with higher score
            earlier_result = ComplianceResult(
                compliance_score=earliest_score,
                total_resources=100,
                compliant_resources=int(earliest_score * 100),
                violations=[],
                scan_timestamp=now - timedelta(days=5),
            )
            await service.store_scan_result(earlier_result)

            # Later scan with lower score
            later_result = ComplianceResult(
                compliance_score=latest_score,
                total_resources=100,
                compliant_resources=int(latest_score * 100),
                violations=[],
                scan_timestamp=now,
            )
            await service.store_scan_result(later_result)

            # Get history
            history = await service.get_history(days_back=30, group_by=GroupBy.DAY)

            # Trend should be declining
            assert history.trend_direction == TrendDirection.DECLINING, (
                f"Expected DECLINING trend for earliest={earliest_score}, "
                f"latest={latest_score}, got {history.trend_direction}"
            )
        finally:
            service.close()

    @given(
        score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_trend_direction_stable_when_scores_equal(
        self,
        score: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.3

        The trend direction SHALL be "stable" if latest score == earliest score.
        """
        service = HistoryService(db_path=":memory:")

        try:
            now = datetime.utcnow()

            # Two scans with same score
            earlier_result = ComplianceResult(
                compliance_score=score,
                total_resources=100,
                compliant_resources=int(score * 100),
                violations=[],
                scan_timestamp=now - timedelta(days=5),
            )
            await service.store_scan_result(earlier_result)

            later_result = ComplianceResult(
                compliance_score=score,
                total_resources=100,
                compliant_resources=int(score * 100),
                violations=[],
                scan_timestamp=now,
            )
            await service.store_scan_result(later_result)

            # Get history
            history = await service.get_history(days_back=30, group_by=GroupBy.DAY)

            # Trend should be stable
            assert history.trend_direction == TrendDirection.STABLE, (
                f"Expected STABLE trend for equal scores {score}, " f"got {history.trend_direction}"
            )
        finally:
            service.close()

    # -------------------------------------------------------------------------
    # Grouping Tests
    # -------------------------------------------------------------------------

    @given(
        group_by=st.sampled_from([GroupBy.DAY, GroupBy.WEEK, GroupBy.MONTH]),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_history_grouped_by_specified_interval(
        self,
        group_by: GroupBy,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.2

        The response SHALL include historical compliance scores grouped by
        the specified interval (day, week, month).
        """
        service = HistoryService(db_path=":memory:")

        try:
            now = datetime.utcnow()

            # Store multiple scan results
            for i in range(10):
                result = ComplianceResult(
                    compliance_score=0.5 + (i * 0.05),
                    total_resources=100,
                    compliant_resources=50 + (i * 5),
                    violations=[],
                    scan_timestamp=now - timedelta(days=i * 3),
                )
                await service.store_scan_result(result)

            # Get history with specified grouping
            history = await service.get_history(days_back=90, group_by=group_by)

            # Verify grouping is as specified
            assert (
                history.group_by == group_by
            ), f"Expected group_by={group_by}, got {history.group_by}"
        finally:
            service.close()

    # -------------------------------------------------------------------------
    # Score Bounds Tests
    # -------------------------------------------------------------------------

    @given(
        num_scans=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_history_scores_within_bounds(
        self,
        num_scans: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.1

        All historical compliance scores SHALL be between 0.0 and 1.0 inclusive.
        """
        service = HistoryService(db_path=":memory:")

        try:
            now = datetime.utcnow()

            # Store multiple scan results with various scores
            for i in range(num_scans):
                score = (i % 11) / 10.0  # Scores from 0.0 to 1.0
                result = ComplianceResult(
                    compliance_score=score,
                    total_resources=100,
                    compliant_resources=int(score * 100),
                    violations=[],
                    scan_timestamp=now - timedelta(days=i),
                )
                await service.store_scan_result(result)

            # Get history
            history = await service.get_history(days_back=90, group_by=GroupBy.DAY)

            # All scores should be within bounds
            for entry in history.history:
                assert (
                    0.0 <= entry.compliance_score <= 1.0
                ), f"Score {entry.compliance_score} out of bounds"

            # earliest_score and latest_score should also be within bounds
            assert 0.0 <= history.earliest_score <= 1.0
            assert 0.0 <= history.latest_score <= 1.0
        finally:
            service.close()

    # -------------------------------------------------------------------------
    # Days Back Validation Tests
    # -------------------------------------------------------------------------

    @given(
        days_back=st.integers(min_value=1, max_value=90),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_days_back_within_valid_range(
        self,
        days_back: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.4

        The service SHALL support looking back up to 90 days of history.
        """
        service = HistoryService(db_path=":memory:")

        try:
            # Get history with valid days_back
            history = await service.get_history(days_back=days_back, group_by=GroupBy.DAY)

            # Should return a valid result
            assert isinstance(history, ComplianceHistoryResult)
            assert history.days_back == days_back
        finally:
            service.close()

    @given(
        days_back=st.integers(min_value=91, max_value=1000),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_days_back_exceeding_90_raises_error(
        self,
        days_back: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.4

        The service SHALL reject days_back values exceeding 90.
        """
        service = HistoryService(db_path=":memory:")

        try:
            with pytest.raises(ValueError, match="days_back must be between 1 and 90"):
                await service.get_history(days_back=days_back, group_by=GroupBy.DAY)
        finally:
            service.close()

    @given(
        days_back=st.integers(min_value=-100, max_value=0),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_days_back_zero_or_negative_raises_error(
        self,
        days_back: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.4

        The service SHALL reject days_back values of zero or negative.
        """
        service = HistoryService(db_path=":memory:")

        try:
            with pytest.raises(ValueError, match="days_back must be between 1 and 90"):
                await service.get_history(days_back=days_back, group_by=GroupBy.DAY)
        finally:
            service.close()

    # -------------------------------------------------------------------------
    # Empty History Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_empty_history_returns_stable_trend(self):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.1, 8.3

        When no history exists, the trend SHALL be "stable" with default scores.
        """
        service = HistoryService(db_path=":memory:")

        try:
            history = await service.get_history(days_back=30, group_by=GroupBy.DAY)

            assert history.trend_direction == TrendDirection.STABLE
            assert history.earliest_score == 1.0
            assert history.latest_score == 1.0
            assert len(history.history) == 0
        finally:
            service.close()

    # -------------------------------------------------------------------------
    # Data Integrity Tests
    # -------------------------------------------------------------------------

    @given(
        total_resources=st.integers(min_value=1, max_value=10000),
        compliant_resources=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_stored_data_matches_input(
        self,
        total_resources: int,
        compliant_resources: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.1

        Stored compliance data SHALL accurately reflect the input scan results.
        """
        # Ensure compliant doesn't exceed total
        compliant = min(compliant_resources, total_resources)
        score = compliant / total_resources

        service = HistoryService(db_path=":memory:")

        try:
            now = datetime.utcnow()

            result = ComplianceResult(
                compliance_score=score,
                total_resources=total_resources,
                compliant_resources=compliant,
                violations=[],
                scan_timestamp=now,
            )
            await service.store_scan_result(result)

            # Get history
            history = await service.get_history(days_back=1, group_by=GroupBy.DAY)

            # Should have one entry
            assert len(history.history) == 1

            entry = history.history[0]
            assert entry.total_resources == total_resources
            assert entry.compliant_resources == compliant
            # Score should be close (may have floating point differences)
            assert abs(entry.compliance_score - score) < 1e-6
        finally:
            service.close()

    # -------------------------------------------------------------------------
    # Earliest/Latest Score Consistency Tests
    # -------------------------------------------------------------------------

    @given(
        num_scans=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_earliest_latest_scores_match_history(
        self,
        num_scans: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 9: History Tracking Correctness
        Validates: Requirements 8.1, 8.3

        The earliest_score and latest_score SHALL match the first and last
        entries in the history list respectively.
        """
        service = HistoryService(db_path=":memory:")

        try:
            now = datetime.utcnow()

            # Store multiple scan results on different days
            for i in range(num_scans):
                score = 0.5 + (i * 0.05)
                result = ComplianceResult(
                    compliance_score=score,
                    total_resources=100,
                    compliant_resources=int(score * 100),
                    violations=[],
                    scan_timestamp=now - timedelta(days=num_scans - 1 - i),
                )
                await service.store_scan_result(result)

            # Get history
            history = await service.get_history(days_back=90, group_by=GroupBy.DAY)

            if len(history.history) > 0:
                # earliest_score should match first entry
                assert abs(history.earliest_score - history.history[0].compliance_score) < 1e-6, (
                    f"earliest_score {history.earliest_score} != "
                    f"first entry {history.history[0].compliance_score}"
                )

                # latest_score should match last entry
                assert abs(history.latest_score - history.history[-1].compliance_score) < 1e-6, (
                    f"latest_score {history.latest_score} != "
                    f"last entry {history.history[-1].compliance_score}"
                )
        finally:
            service.close()
