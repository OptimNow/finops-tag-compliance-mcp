# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for retrieving violation history."""

import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, computed_field

from ..models.history import ComplianceHistoryResult, ComplianceHistoryEntry, GroupBy, TrendDirection
from ..services.history_service import HistoryService

logger = logging.getLogger(__name__)


class HistoryEntryInfo(BaseModel):
    """A single compliance history data point."""

    timestamp: datetime = Field(..., description="When the scan was recorded")
    compliance_score: float = Field(..., description="Compliance score (0.0 to 1.0)")
    total_resources: int = Field(..., description="Total resources scanned")
    compliant_resources: int = Field(..., description="Number of compliant resources")
    violation_count: int = Field(..., description="Number of violations")


class TrendAnalysis(BaseModel):
    """Analysis of compliance trend over time."""

    direction: str = Field(..., description="Trend direction (improving, declining, stable)")
    score_change: float = Field(..., description="Absolute change in compliance score")
    score_change_percentage: float = Field(
        ..., description="Score change as percentage points"
    )


class GetViolationHistoryResult(BaseModel):
    """Result from the get_violation_history tool."""

    history: list[HistoryEntryInfo] = Field(
        default_factory=list, description="Historical compliance data points"
    )
    group_by: str = Field(..., description="How data is grouped (day, week, month)")
    trend_direction: str = Field(
        ..., description="Overall trend (improving, declining, stable)"
    )
    earliest_score: float = Field(..., description="Score at start of period")
    latest_score: float = Field(..., description="Score at end of period")
    days_back: int = Field(..., description="Number of days of history")
    trend_analysis: TrendAnalysis = Field(..., description="Detailed trend analysis")

    @classmethod
    def from_history_result(
        cls, history_result: ComplianceHistoryResult
    ) -> "GetViolationHistoryResult":
        """Create result from a ComplianceHistoryResult instance."""
        score_change = history_result.latest_score - history_result.earliest_score

        return cls(
            history=[
                HistoryEntryInfo(
                    timestamp=entry.timestamp,
                    compliance_score=entry.compliance_score,
                    total_resources=entry.total_resources,
                    compliant_resources=entry.compliant_resources,
                    violation_count=entry.violation_count,
                )
                for entry in history_result.history
            ],
            group_by=history_result.group_by.value,
            trend_direction=history_result.trend_direction.value,
            earliest_score=history_result.earliest_score,
            latest_score=history_result.latest_score,
            days_back=history_result.days_back,
            trend_analysis=TrendAnalysis(
                direction=history_result.trend_direction.value,
                score_change=score_change,
                score_change_percentage=score_change * 100,
            ),
        )


async def get_violation_history(
    history_service: Optional[HistoryService] = None,
    days_back: int = 30,
    group_by: str = "day",
    db_path: str = "compliance_history.db",
) -> GetViolationHistoryResult:
    """
    Retrieve historical compliance data with trend analysis.

    This tool queries stored compliance scan results to show how compliance
    has changed over time. It helps track progress, identify trends, and
    measure the effectiveness of remediation efforts.

    Args:
        history_service: Optional injected HistoryService instance
        days_back: Number of days to look back (1-90, default: 30)
        group_by: How to group the data - "day", "week", or "month" (default: "day")
        db_path: Path to the SQLite database (default: "compliance_history.db")
                 Only used if history_service is not provided.

    Returns:
        GetViolationHistoryResult containing:
        - history: List of historical compliance data points
        - group_by: How the data is grouped
        - trend_direction: Overall trend (improving, declining, stable)
        - earliest_score: Compliance score at the start of the period
        - latest_score: Compliance score at the end of the period
        - days_back: Number of days of history returned
        - trend_analysis: Additional analysis including score change

    Requirements: 8.1, 8.2, 8.3, 8.4

    Example:
        >>> result = await get_violation_history(
        ...     days_back=30,
        ...     group_by="week"
        ... )
        >>> print(f"Trend: {result.trend_direction}")
        >>> print(f"Score change: {result.trend_analysis.score_change:.2%}")
    """
    logger.info(
        f"Retrieving violation history: days_back={days_back}, group_by={group_by}"
    )

    # Validate days_back parameter
    if days_back < 1 or days_back > 90:
        raise ValueError("days_back must be between 1 and 90")

    # Validate and convert group_by parameter
    try:
        group_by_enum = GroupBy(group_by.lower())
    except ValueError:
        raise ValueError(
            f"Invalid group_by '{group_by}'. Must be one of: day, week, month"
        )

    # Use injected service or create one
    service = history_service
    should_close = False

    if service is None:
        service = HistoryService(db_path=db_path)
        should_close = True

    try:
        # Query historical data
        history_result = await service.get_history(
            days_back=days_back, group_by=group_by_enum
        )

        logger.info(
            f"History retrieved successfully: {len(history_result.history)} data points, "
            f"trend: {history_result.trend_direction.value}"
        )

        return GetViolationHistoryResult.from_history_result(history_result)

    finally:
        # Only clean up if we created the service
        if should_close:
            service.close()
