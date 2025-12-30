"""Service for tracking compliance history over time."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..models import (
    ComplianceHistoryEntry,
    ComplianceHistoryResult,
    ComplianceResult,
    GroupBy,
    TrendDirection,
)


class HistoryService:
    """Service for storing and querying compliance history."""

    def __init__(self, db_path: str = "compliance_history.db"):
        """
        Initialize the history service.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._connection = None
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self.db_path == ":memory:":
            # For in-memory databases, keep a persistent connection
            if self._connection is None:
                self._connection = sqlite3.connect(self.db_path)
            return self._connection
        else:
            # For file-based databases, create a new connection each time
            return sqlite3.connect(self.db_path)

    def _init_database(self) -> None:
        """Initialize the SQLite database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS compliance_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                compliance_score REAL NOT NULL,
                total_resources INTEGER NOT NULL,
                compliant_resources INTEGER NOT NULL,
                violation_count INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create index on timestamp for faster queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON compliance_scans(timestamp)
        """
        )

        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

    async def store_scan_result(self, result: ComplianceResult) -> None:
        """
        Store a compliance scan result in the database.

        Args:
            result: The compliance scan result to store
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO compliance_scans 
            (timestamp, compliance_score, total_resources, compliant_resources, violation_count)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                result.scan_timestamp.isoformat(),
                result.compliance_score,
                result.total_resources,
                result.compliant_resources,
                len(result.violations),
            ),
        )

        conn.commit()
        if self.db_path != ":memory:":
            conn.close()

    async def get_history(
        self, days_back: int = 30, group_by: GroupBy = GroupBy.DAY
    ) -> ComplianceHistoryResult:
        """
        Query historical compliance data.

        Args:
            days_back: Number of days to look back (1-90)
            group_by: How to group the data (day, week, month)

        Returns:
            ComplianceHistoryResult with historical data and trend analysis
        """
        # Validate days_back
        if days_back < 1 or days_back > 90:
            raise ValueError("days_back must be between 1 and 90")

        # Calculate the cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        conn = self._get_connection()
        cursor = conn.cursor()

        # Query data based on grouping
        if group_by == GroupBy.DAY:
            query = """
                SELECT 
                    DATE(timestamp) as period,
                    AVG(compliance_score) as avg_score,
                    SUM(total_resources) as total_res,
                    SUM(compliant_resources) as compliant_res,
                    SUM(violation_count) as violations
                FROM compliance_scans
                WHERE timestamp >= ?
                GROUP BY DATE(timestamp)
                ORDER BY period ASC
            """
        elif group_by == GroupBy.WEEK:
            query = """
                SELECT 
                    DATE(timestamp, 'weekday 0', '-6 days') as period,
                    AVG(compliance_score) as avg_score,
                    SUM(total_resources) as total_res,
                    SUM(compliant_resources) as compliant_res,
                    SUM(violation_count) as violations
                FROM compliance_scans
                WHERE timestamp >= ?
                GROUP BY DATE(timestamp, 'weekday 0', '-6 days')
                ORDER BY period ASC
            """
        else:  # MONTH
            query = """
                SELECT 
                    DATE(timestamp, 'start of month') as period,
                    AVG(compliance_score) as avg_score,
                    SUM(total_resources) as total_res,
                    SUM(compliant_resources) as compliant_res,
                    SUM(violation_count) as violations
                FROM compliance_scans
                WHERE timestamp >= ?
                GROUP BY DATE(timestamp, 'start of month')
                ORDER BY period ASC
            """

        cursor.execute(query, (cutoff_date.isoformat(),))
        rows = cursor.fetchall()
        if self.db_path != ":memory:":
            conn.close()

        # Convert rows to history entries
        history: list[ComplianceHistoryEntry] = []
        for row in rows:
            period_str, avg_score, total_res, compliant_res, violations = row
            history.append(
                ComplianceHistoryEntry(
                    timestamp=datetime.fromisoformat(period_str),
                    compliance_score=avg_score,
                    total_resources=int(total_res),
                    compliant_resources=int(compliant_res),
                    violation_count=int(violations),
                )
            )

        # Calculate trend direction
        if len(history) == 0:
            # No data - return default values
            return ComplianceHistoryResult(
                history=[],
                group_by=group_by,
                trend_direction=TrendDirection.STABLE,
                earliest_score=1.0,
                latest_score=1.0,
                days_back=days_back,
            )

        earliest_score = history[0].compliance_score
        latest_score = history[-1].compliance_score

        # Determine trend direction
        if latest_score > earliest_score:
            trend = TrendDirection.IMPROVING
        elif latest_score < earliest_score:
            trend = TrendDirection.DECLINING
        else:
            trend = TrendDirection.STABLE

        return ComplianceHistoryResult(
            history=history,
            group_by=group_by,
            trend_direction=trend,
            earliest_score=earliest_score,
            latest_score=latest_score,
            days_back=days_back,
        )

    def close(self) -> None:
        """Close any open database connections."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
