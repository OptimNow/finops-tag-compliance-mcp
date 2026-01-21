"""Unit tests for get_violation_history tool."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.models.history import (
    ComplianceHistoryEntry,
    ComplianceHistoryResult,
    GroupBy,
    TrendDirection,
)
from mcp_server.services.history_service import HistoryService
from mcp_server.tools.get_violation_history import (
    GetViolationHistoryResult,
    get_violation_history,
)


@pytest.fixture
def sample_history_entries():
    """Create sample history entries for testing."""
    base_date = datetime(2025, 12, 1)
    return [
        ComplianceHistoryEntry(
            timestamp=base_date,
            compliance_score=0.70,
            total_resources=100,
            compliant_resources=70,
            violation_count=30,
        ),
        ComplianceHistoryEntry(
            timestamp=base_date + timedelta(days=1),
            compliance_score=0.75,
            total_resources=100,
            compliant_resources=75,
            violation_count=25,
        ),
        ComplianceHistoryEntry(
            timestamp=base_date + timedelta(days=2),
            compliance_score=0.80,
            total_resources=100,
            compliant_resources=80,
            violation_count=20,
        ),
    ]


@pytest.fixture
def mock_history_service(sample_history_entries):
    """Create a mock history service."""
    service = MagicMock(spec=HistoryService)

    # Default return value for get_history
    service.get_history = AsyncMock(
        return_value=ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )
    )

    return service


class TestGetViolationHistoryResult:
    """Test GetViolationHistoryResult class."""

    def test_result_to_dict_complete_structure(self, sample_history_entries):
        """Test that result.to_dict() returns complete structure."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        # Verify all required fields are present
        assert "history" in result_dict
        assert "group_by" in result_dict
        assert "trend_direction" in result_dict
        assert "earliest_score" in result_dict
        assert "latest_score" in result_dict
        assert "days_back" in result_dict
        assert "trend_analysis" in result_dict

    def test_result_to_dict_history_entries(self, sample_history_entries):
        """Test that history entries are correctly serialized."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        assert len(result_dict["history"]) == 3

        # Check first entry
        first_entry = result_dict["history"][0]
        assert "timestamp" in first_entry
        assert "compliance_score" in first_entry
        assert "total_resources" in first_entry
        assert "compliant_resources" in first_entry
        assert "violation_count" in first_entry
        assert first_entry["compliance_score"] == 0.70
        assert first_entry["total_resources"] == 100
        assert first_entry["compliant_resources"] == 70
        assert first_entry["violation_count"] == 30

    def test_result_to_dict_timestamp_format(self, sample_history_entries):
        """Test that timestamps are in ISO format."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        for entry in result_dict["history"]:
            timestamp_str = entry["timestamp"]
            # Should be ISO format
            assert "T" in timestamp_str
            # Should be parseable
            datetime.fromisoformat(timestamp_str)

    def test_result_to_dict_group_by_value(self, sample_history_entries):
        """Test that group_by is correctly serialized."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.WEEK,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        assert result_dict["group_by"] == "week"

    def test_result_to_dict_trend_direction_value(self, sample_history_entries):
        """Test that trend_direction is correctly serialized."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.DECLINING,
            earliest_score=0.80,
            latest_score=0.70,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        assert result_dict["trend_direction"] == "declining"

    def test_result_to_dict_trend_analysis_improving(self, sample_history_entries):
        """Test trend analysis for improving trend."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        trend = result_dict["trend_analysis"]
        assert trend["direction"] == "improving"
        assert abs(trend["score_change"] - 0.10) < 0.0001
        assert abs(trend["score_change_percentage"] - 10.0) < 0.0001

    def test_result_to_dict_trend_analysis_declining(self, sample_history_entries):
        """Test trend analysis for declining trend."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.DECLINING,
            earliest_score=0.80,
            latest_score=0.70,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        trend = result_dict["trend_analysis"]
        assert trend["direction"] == "declining"
        assert abs(trend["score_change"] - (-0.10)) < 0.0001
        assert abs(trend["score_change_percentage"] - (-10.0)) < 0.0001

    def test_result_to_dict_trend_analysis_stable(self, sample_history_entries):
        """Test trend analysis for stable trend."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.STABLE,
            earliest_score=0.75,
            latest_score=0.75,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        trend = result_dict["trend_analysis"]
        assert trend["direction"] == "stable"
        assert trend["score_change"] == 0.0
        assert trend["score_change_percentage"] == 0.0

    def test_result_to_dict_scores(self, sample_history_entries):
        """Test that earliest and latest scores are correctly serialized."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        assert result_dict["earliest_score"] == 0.70
        assert result_dict["latest_score"] == 0.80

    def test_result_to_dict_days_back(self, sample_history_entries):
        """Test that days_back is correctly serialized."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=60,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        assert result_dict["days_back"] == 60

    def test_result_to_dict_empty_history(self):
        """Test that empty history is handled correctly."""
        history_result = ComplianceHistoryResult(
            history=[],
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.STABLE,
            earliest_score=1.0,
            latest_score=1.0,
            days_back=30,
        )
        result = GetViolationHistoryResult(history_result=history_result)

        result_dict = result.to_dict()

        assert result_dict["history"] == []
        assert result_dict["earliest_score"] == 1.0
        assert result_dict["latest_score"] == 1.0


class TestGetViolationHistoryTool:
    """Test get_violation_history tool."""

    @pytest.mark.asyncio
    async def test_get_violation_history_default_parameters(self, mock_history_service):
        """Test get_violation_history with default parameters."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history()

            assert isinstance(result, GetViolationHistoryResult)
            assert result.history_result is not None

            # Verify service was called with defaults
            mock_history_service.get_history.assert_called_once()
            call_args = mock_history_service.get_history.call_args
            assert call_args[1]["days_back"] == 30
            assert call_args[1]["group_by"] == GroupBy.DAY

    @pytest.mark.asyncio
    async def test_get_violation_history_custom_days_back(self, mock_history_service):
        """Test get_violation_history with custom days_back."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history(days_back=60)

            assert isinstance(result, GetViolationHistoryResult)

            # Verify service was called with custom days_back
            mock_history_service.get_history.assert_called_once()
            call_args = mock_history_service.get_history.call_args
            assert call_args[1]["days_back"] == 60

    @pytest.mark.asyncio
    async def test_get_violation_history_invalid_days_back_too_low(self):
        """Test that days_back < 1 raises ValueError."""
        with pytest.raises(ValueError, match="days_back must be between 1 and 90"):
            await get_violation_history(days_back=0)

    @pytest.mark.asyncio
    async def test_get_violation_history_invalid_days_back_too_high(self):
        """Test that days_back > 90 raises ValueError."""
        with pytest.raises(ValueError, match="days_back must be between 1 and 90"):
            await get_violation_history(days_back=91)

    @pytest.mark.asyncio
    async def test_get_violation_history_group_by_day(self, mock_history_service):
        """Test get_violation_history with group_by='day'."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history(group_by="day")

            assert isinstance(result, GetViolationHistoryResult)

            # Verify service was called with day grouping
            mock_history_service.get_history.assert_called_once()
            call_args = mock_history_service.get_history.call_args
            assert call_args[1]["group_by"] == GroupBy.DAY

    @pytest.mark.asyncio
    async def test_get_violation_history_group_by_week(self, mock_history_service):
        """Test get_violation_history with group_by='week'."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history(group_by="week")

            assert isinstance(result, GetViolationHistoryResult)

            # Verify service was called with week grouping
            mock_history_service.get_history.assert_called_once()
            call_args = mock_history_service.get_history.call_args
            assert call_args[1]["group_by"] == GroupBy.WEEK

    @pytest.mark.asyncio
    async def test_get_violation_history_group_by_month(self, mock_history_service):
        """Test get_violation_history with group_by='month'."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history(group_by="month")

            assert isinstance(result, GetViolationHistoryResult)

            # Verify service was called with month grouping
            mock_history_service.get_history.assert_called_once()
            call_args = mock_history_service.get_history.call_args
            assert call_args[1]["group_by"] == GroupBy.MONTH

    @pytest.mark.asyncio
    async def test_get_violation_history_invalid_group_by(self):
        """Test that invalid group_by raises ValueError."""
        with pytest.raises(ValueError, match="Invalid group_by"):
            await get_violation_history(group_by="invalid")

    @pytest.mark.asyncio
    async def test_get_violation_history_group_by_case_insensitive(self, mock_history_service):
        """Test that group_by is case-insensitive."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history(group_by="WEEK")

            assert isinstance(result, GetViolationHistoryResult)

            # Verify service was called with week grouping
            call_args = mock_history_service.get_history.call_args
            assert call_args[1]["group_by"] == GroupBy.WEEK

    @pytest.mark.asyncio
    async def test_get_violation_history_custom_db_path(self, mock_history_service):
        """Test get_violation_history with custom db_path."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ) as mock_service_class:
            result = await get_violation_history(db_path="/custom/path.db")

            assert isinstance(result, GetViolationHistoryResult)

            # Verify HistoryService was initialized with custom path
            mock_service_class.assert_called_once_with(db_path="/custom/path.db")

    @pytest.mark.asyncio
    async def test_get_violation_history_returns_result_object(self, mock_history_service):
        """Test that get_violation_history returns GetViolationHistoryResult."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history()

            assert isinstance(result, GetViolationHistoryResult)
            assert hasattr(result, "history_result")
            assert hasattr(result, "to_dict")

    @pytest.mark.asyncio
    async def test_get_violation_history_result_to_dict(self, mock_history_service):
        """Test that result.to_dict() works correctly."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history()

            result_dict = result.to_dict()

            assert isinstance(result_dict, dict)
            assert "history" in result_dict
            assert "group_by" in result_dict
            assert "trend_direction" in result_dict

    @pytest.mark.asyncio
    async def test_get_violation_history_closes_service(self, mock_history_service):
        """Test that history service is closed after use."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            await get_violation_history()

            # Verify close was called
            mock_history_service.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_violation_history_closes_service_on_error(self, mock_history_service):
        """Test that history service is closed even if an error occurs."""
        mock_history_service.get_history = AsyncMock(side_effect=Exception("Database error"))

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            with pytest.raises(Exception, match="Database error"):
                await get_violation_history()

            # Verify close was still called
            mock_history_service.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_violation_history_improving_trend(self, sample_history_entries):
        """Test get_violation_history with improving trend."""
        history_result = ComplianceHistoryResult(
            history=sample_history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )

        mock_service = MagicMock(spec=HistoryService)
        mock_service.get_history = AsyncMock(return_value=history_result)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service,
        ):
            result = await get_violation_history()

            result_dict = result.to_dict()
            assert result_dict["trend_direction"] == "improving"
            assert abs(result_dict["trend_analysis"]["score_change"] - 0.10) < 0.0001

    @pytest.mark.asyncio
    async def test_get_violation_history_declining_trend(self):
        """Test get_violation_history with declining trend."""
        base_date = datetime(2025, 12, 1)
        history_entries = [
            ComplianceHistoryEntry(
                timestamp=base_date,
                compliance_score=0.80,
                total_resources=100,
                compliant_resources=80,
                violation_count=20,
            ),
            ComplianceHistoryEntry(
                timestamp=base_date + timedelta(days=1),
                compliance_score=0.75,
                total_resources=100,
                compliant_resources=75,
                violation_count=25,
            ),
            ComplianceHistoryEntry(
                timestamp=base_date + timedelta(days=2),
                compliance_score=0.70,
                total_resources=100,
                compliant_resources=70,
                violation_count=30,
            ),
        ]

        history_result = ComplianceHistoryResult(
            history=history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.DECLINING,
            earliest_score=0.80,
            latest_score=0.70,
            days_back=30,
        )

        mock_service = MagicMock(spec=HistoryService)
        mock_service.get_history = AsyncMock(return_value=history_result)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service,
        ):
            result = await get_violation_history()

            result_dict = result.to_dict()
            assert result_dict["trend_direction"] == "declining"
            assert abs(result_dict["trend_analysis"]["score_change"] - (-0.10)) < 0.0001

    @pytest.mark.asyncio
    async def test_get_violation_history_stable_trend(self):
        """Test get_violation_history with stable trend."""
        base_date = datetime(2025, 12, 1)
        history_entries = [
            ComplianceHistoryEntry(
                timestamp=base_date,
                compliance_score=0.75,
                total_resources=100,
                compliant_resources=75,
                violation_count=25,
            ),
            ComplianceHistoryEntry(
                timestamp=base_date + timedelta(days=1),
                compliance_score=0.75,
                total_resources=100,
                compliant_resources=75,
                violation_count=25,
            ),
            ComplianceHistoryEntry(
                timestamp=base_date + timedelta(days=2),
                compliance_score=0.75,
                total_resources=100,
                compliant_resources=75,
                violation_count=25,
            ),
        ]

        history_result = ComplianceHistoryResult(
            history=history_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.STABLE,
            earliest_score=0.75,
            latest_score=0.75,
            days_back=30,
        )

        mock_service = MagicMock(spec=HistoryService)
        mock_service.get_history = AsyncMock(return_value=history_result)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service,
        ):
            result = await get_violation_history()

            result_dict = result.to_dict()
            assert result_dict["trend_direction"] == "stable"
            assert result_dict["trend_analysis"]["score_change"] == 0.0

    @pytest.mark.asyncio
    async def test_get_violation_history_empty_history(self):
        """Test get_violation_history with empty history."""
        history_result = ComplianceHistoryResult(
            history=[],
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.STABLE,
            earliest_score=1.0,
            latest_score=1.0,
            days_back=30,
        )

        mock_service = MagicMock(spec=HistoryService)
        mock_service.get_history = AsyncMock(return_value=history_result)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service,
        ):
            result = await get_violation_history()

            result_dict = result.to_dict()
            assert result_dict["history"] == []
            assert result_dict["earliest_score"] == 1.0
            assert result_dict["latest_score"] == 1.0

    @pytest.mark.asyncio
    async def test_get_violation_history_multiple_grouping_options(self):
        """Test get_violation_history with different grouping options."""
        base_date = datetime(2025, 12, 1)
        sample_entries = [
            ComplianceHistoryEntry(
                timestamp=base_date,
                compliance_score=0.70,
                total_resources=100,
                compliant_resources=70,
                violation_count=30,
            ),
        ]

        # Test day grouping
        history_result_day = ComplianceHistoryResult(
            history=sample_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )

        mock_service_day = MagicMock(spec=HistoryService)
        mock_service_day.get_history = AsyncMock(return_value=history_result_day)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service_day,
        ):
            result_day = await get_violation_history(group_by="day")
            assert result_day.history_result.group_by == GroupBy.DAY

        # Test week grouping
        history_result_week = ComplianceHistoryResult(
            history=sample_entries,
            group_by=GroupBy.WEEK,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )

        mock_service_week = MagicMock(spec=HistoryService)
        mock_service_week.get_history = AsyncMock(return_value=history_result_week)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service_week,
        ):
            result_week = await get_violation_history(group_by="week")
            assert result_week.history_result.group_by == GroupBy.WEEK

        # Test month grouping
        history_result_month = ComplianceHistoryResult(
            history=sample_entries,
            group_by=GroupBy.MONTH,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=30,
        )

        mock_service_month = MagicMock(spec=HistoryService)
        mock_service_month.get_history = AsyncMock(return_value=history_result_month)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service_month,
        ):
            result_month = await get_violation_history(group_by="month")
            assert result_month.history_result.group_by == GroupBy.MONTH

    @pytest.mark.asyncio
    async def test_get_violation_history_requirements_8_2(self):
        """Test Requirement 8.2: Support grouping history by day, week, or month."""
        base_date = datetime(2025, 12, 1)
        sample_entries = [
            ComplianceHistoryEntry(
                timestamp=base_date,
                compliance_score=0.70,
                total_resources=100,
                compliant_resources=70,
                violation_count=30,
            ),
        ]

        for group_by_value in ["day", "week", "month"]:
            group_by_enum = GroupBy(group_by_value)
            history_result = ComplianceHistoryResult(
                history=sample_entries,
                group_by=group_by_enum,
                trend_direction=TrendDirection.IMPROVING,
                earliest_score=0.70,
                latest_score=0.80,
                days_back=30,
            )

            mock_service = MagicMock(spec=HistoryService)
            mock_service.get_history = AsyncMock(return_value=history_result)

            with patch(
                "mcp_server.tools.get_violation_history.HistoryService",
                return_value=mock_service,
            ):
                result = await get_violation_history(group_by=group_by_value)
                assert result.history_result.group_by.value == group_by_value

    @pytest.mark.asyncio
    async def test_get_violation_history_requirements_8_3(self, mock_history_service):
        """Test Requirement 8.3: Calculate and return trend direction."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history()

            result_dict = result.to_dict()

            # Verify trend direction is present and valid
            assert "trend_direction" in result_dict
            assert result_dict["trend_direction"] in ["improving", "declining", "stable"]

            # Verify trend analysis is present
            assert "trend_analysis" in result_dict
            assert "direction" in result_dict["trend_analysis"]
            assert "score_change" in result_dict["trend_analysis"]
            assert "score_change_percentage" in result_dict["trend_analysis"]

    @pytest.mark.asyncio
    async def test_get_violation_history_requirements_8_1(self, mock_history_service):
        """Test Requirement 8.1: Return historical compliance scores."""
        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_history_service,
        ):
            result = await get_violation_history()

            result_dict = result.to_dict()

            # Verify history is present with compliance scores
            assert "history" in result_dict
            assert isinstance(result_dict["history"], list)

            for entry in result_dict["history"]:
                assert "timestamp" in entry
                assert "compliance_score" in entry
                assert 0.0 <= entry["compliance_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_get_violation_history_requirements_8_4(self):
        """Test Requirement 8.4: Support looking back up to 90 days."""
        base_date = datetime(2025, 12, 1)
        sample_entries = [
            ComplianceHistoryEntry(
                timestamp=base_date,
                compliance_score=0.70,
                total_resources=100,
                compliant_resources=70,
                violation_count=30,
            ),
        ]

        # Test minimum days_back
        history_result_1 = ComplianceHistoryResult(
            history=sample_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=1,
        )

        mock_service_1 = MagicMock(spec=HistoryService)
        mock_service_1.get_history = AsyncMock(return_value=history_result_1)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service_1,
        ):
            result_1 = await get_violation_history(days_back=1)
            assert result_1.history_result.days_back == 1

        # Test maximum days_back
        history_result_90 = ComplianceHistoryResult(
            history=sample_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=90,
        )

        mock_service_90 = MagicMock(spec=HistoryService)
        mock_service_90.get_history = AsyncMock(return_value=history_result_90)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service_90,
        ):
            result_90 = await get_violation_history(days_back=90)
            assert result_90.history_result.days_back == 90

        # Test mid-range days_back
        history_result_45 = ComplianceHistoryResult(
            history=sample_entries,
            group_by=GroupBy.DAY,
            trend_direction=TrendDirection.IMPROVING,
            earliest_score=0.70,
            latest_score=0.80,
            days_back=45,
        )

        mock_service_45 = MagicMock(spec=HistoryService)
        mock_service_45.get_history = AsyncMock(return_value=history_result_45)

        with patch(
            "mcp_server.tools.get_violation_history.HistoryService",
            return_value=mock_service_45,
        ):
            result_45 = await get_violation_history(days_back=45)
            assert result_45.history_result.days_back == 45
