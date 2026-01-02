"""Audit logging service for tracking tool invocations."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..models.audit import AuditLogEntry, AuditStatus
from ..utils.correlation import get_correlation_id


class AuditService:
    """Service for logging and retrieving audit entries."""

    def __init__(self, db_path: str = "audit_logs.db"):
        """
        Initialize the audit service.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the SQLite database with the audit_logs table."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    execution_time_ms REAL,
                    correlation_id TEXT
                )
                """
            )
            # Create index on timestamp for faster queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
                ON audit_logs(timestamp)
                """
            )
            # Create index on correlation_id for faster correlation-based queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_correlation_id 
                ON audit_logs(correlation_id)
                """
            )
            conn.commit()
        finally:
            conn.close()

    def log_invocation(
        self,
        tool_name: str,
        parameters: dict,
        status: AuditStatus,
        error_message: Optional[str] = None,
        execution_time_ms: Optional[float] = None,
        correlation_id: Optional[str] = None,
    ) -> AuditLogEntry:
        """
        Log a tool invocation to the audit database.

        Args:
            tool_name: Name of the tool that was invoked
            parameters: Parameters passed to the tool
            status: Success or failure status
            error_message: Error message if status is failure
            execution_time_ms: Execution time in milliseconds
            correlation_id: Correlation ID for request tracing (auto-captured from context if not provided)

        Returns:
            AuditLogEntry with the logged data including generated ID
        """
        timestamp = datetime.now(timezone.utc)
        
        # Capture correlation ID from context if not explicitly provided
        if correlation_id is None:
            correlation_id = get_correlation_id() or None

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_logs 
                (timestamp, tool_name, parameters, status, error_message, execution_time_ms, correlation_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp.isoformat(),
                    tool_name,
                    json.dumps(parameters),  # Store as JSON string for security
                    status.value,
                    error_message,
                    execution_time_ms,
                    correlation_id,
                ),
            )
            conn.commit()
            entry_id = cursor.lastrowid
        finally:
            conn.close()

        return AuditLogEntry(
            id=entry_id,
            timestamp=timestamp,
            tool_name=tool_name,
            parameters=parameters,
            status=status,
            error_message=error_message,
            execution_time_ms=execution_time_ms,
            correlation_id=correlation_id,
        )

    def get_logs(
        self,
        tool_name: Optional[str] = None,
        status: Optional[AuditStatus] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        """
        Retrieve audit logs with optional filtering.

        Args:
            tool_name: Filter by tool name
            status: Filter by status
            correlation_id: Filter by correlation ID
            limit: Maximum number of logs to return

        Returns:
            List of audit log entries
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM audit_logs WHERE 1=1"
            params = []

            if tool_name:
                query += " AND tool_name = ?"
                params.append(tool_name)

            if status:
                query += " AND status = ?"
                params.append(status.value)

            if correlation_id:
                query += " AND correlation_id = ?"
                params.append(correlation_id)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            logs = []
            for row in rows:
                logs.append(
                    AuditLogEntry(
                        id=row[0],
                        timestamp=datetime.fromisoformat(row[1]),
                        tool_name=row[2],
                        parameters=json.loads(row[3]),  # Convert JSON string back to dict
                        status=AuditStatus(row[4]),
                        error_message=row[5],
                        execution_time_ms=row[6],
                        correlation_id=row[7] if len(row) > 7 else None,
                    )
                )

            return logs
        finally:
            conn.close()
