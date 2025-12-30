"""MCP tool for retrieving violation history."""

import logging

from ..models.history import ComplianceHistoryResult, GroupBy
from ..services.history_service import HistoryService

logger = logging.getLogger(__name__)


class GetViolationHistoryResult:
    """Result from the get_violation_history tool."""
    
    def __init__(self, history_result: ComplianceHistoryResult):
        self.history_result = history_result
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "history": [
                {
                    "timestamp": entry.timestamp.isoformat(),
                    "compliance_score": entry.compliance_score,
                    "total_resources": entry.total_resources,
                    "compliant_resources": entry.compliant_resources,
                    "violation_count": entry.violation_count,
                }
                for entry in self.history_result.history
            ],
            "group_by": self.history_result.group_by.value,
            "trend_direction": self.history_result.trend_direction.value,
            "earliest_score": self.history_result.earliest_score,
            "latest_score": self.history_result.latest_score,
            "days_back": self.history_result.days_back,
            "trend_analysis": {
                "direction": self.history_result.trend_direction.value,
                "score_change": self.history_result.latest_score - self.history_result.earliest_score,
                "score_change_percentage": (
                    (self.history_result.latest_score - self.history_result.earliest_score) * 100
                ),
            },
        }


async def get_violation_history(
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
        days_back: Number of days to look back (1-90, default: 30)
        group_by: How to group the data - "day", "week", or "month" (default: "day")
        db_path: Path to the SQLite database (default: "compliance_history.db")
    
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
        >>> print(f"Trend: {result.history_result.trend_direction.value}")
        >>> print(f"Score change: {result.history_result.latest_score - result.history_result.earliest_score:.2%}")
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
    
    # Initialize history service
    history_service = HistoryService(db_path=db_path)
    
    try:
        # Query historical data
        history_result = await history_service.get_history(
            days_back=days_back,
            group_by=group_by_enum
        )
        
        logger.info(
            f"History retrieved successfully: {len(history_result.history)} data points, "
            f"trend: {history_result.trend_direction.value}"
        )
        
        return GetViolationHistoryResult(history_result=history_result)
    
    finally:
        # Clean up database connection
        history_service.close()
