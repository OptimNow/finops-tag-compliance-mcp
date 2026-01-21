# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Metrics collection service for agent observability.

This service aggregates tool usage, execution times, error rates, and other
metrics from various sources (audit logs, budget tracker, loop detector) to
provide comprehensive observability data for monitoring agent behavior.

Requirements: 15.2
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime

from ..middleware.budget_middleware import BudgetTracker, get_budget_tracker
from ..models.audit import AuditStatus
from ..models.observability import (
    BudgetUtilizationMetrics,
    ErrorRateMetrics,
    GlobalMetrics,
    LoopDetectionMetrics,
    SessionMetrics,
    ToolUsageStats,
)
from ..services.audit_service import AuditService
from ..utils.loop_detection import LoopDetector, get_loop_detector

logger = logging.getLogger(__name__)


class MetricsService:
    """
    Service for collecting and aggregating metrics across the MCP server.

    Aggregates data from:
    - Audit logs (tool invocations, execution times, errors)
    - Budget tracker (session budgets, utilization)
    - Loop detector (loop detection events)

    Requirements: 15.2
    """

    def __init__(
        self,
        audit_service: AuditService,
        budget_tracker: BudgetTracker | None = None,
        loop_detector: LoopDetector | None = None,
        server_start_time: datetime | None = None,
    ):
        """
        Initialize the metrics service.

        Args:
            audit_service: Audit service for retrieving tool invocation logs
            budget_tracker: Budget tracker for session budget metrics
            loop_detector: Loop detector for loop detection metrics
            server_start_time: Server start timestamp (defaults to now)
        """
        self._audit_service = audit_service
        self._budget_tracker = budget_tracker or get_budget_tracker()
        self._loop_detector = loop_detector or get_loop_detector()
        self._server_start_time = server_start_time or datetime.now(UTC)

        logger.info("MetricsService initialized")

    async def get_tool_usage_stats(
        self, tool_name: str | None = None, limit: int = 1000
    ) -> list[ToolUsageStats]:
        """
        Get usage statistics for tools.

        Args:
            tool_name: Optional filter for specific tool
            limit: Maximum number of audit logs to analyze

        Returns:
            List of tool usage statistics
        """
        # Retrieve audit logs
        logs = self._audit_service.get_logs(tool_name=tool_name, limit=limit)

        # Aggregate by tool name
        tool_data: dict[str, dict] = defaultdict(
            lambda: {
                "invocation_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "execution_times": [],
                "last_invoked_at": None,
                "last_error": None,
            }
        )

        for log in logs:
            data = tool_data[log.tool_name]
            data["invocation_count"] += 1

            if log.status == AuditStatus.SUCCESS:
                data["success_count"] += 1
            else:
                data["failure_count"] += 1
                data["last_error"] = log.error_message

            if log.execution_time_ms is not None:
                data["execution_times"].append(log.execution_time_ms)

            # Track most recent invocation
            if data["last_invoked_at"] is None or log.timestamp > data["last_invoked_at"]:
                data["last_invoked_at"] = log.timestamp

        # Convert to ToolUsageStats objects
        stats = []
        for tool_name, data in tool_data.items():
            execution_times = data["execution_times"]
            total_execution_time = sum(execution_times) if execution_times else 0.0
            avg_execution_time = (
                total_execution_time / len(execution_times) if execution_times else 0.0
            )
            min_execution_time = min(execution_times) if execution_times else None
            max_execution_time = max(execution_times) if execution_times else None

            invocation_count = data["invocation_count"]
            failure_count = data["failure_count"]
            error_rate = failure_count / invocation_count if invocation_count > 0 else 0.0

            stats.append(
                ToolUsageStats(
                    tool_name=tool_name,
                    invocation_count=invocation_count,
                    success_count=data["success_count"],
                    failure_count=failure_count,
                    total_execution_time_ms=total_execution_time,
                    average_execution_time_ms=avg_execution_time,
                    min_execution_time_ms=min_execution_time,
                    max_execution_time_ms=max_execution_time,
                    error_rate=error_rate,
                    last_invoked_at=data["last_invoked_at"],
                    last_error=data["last_error"],
                )
            )

        # Sort by invocation count descending
        stats.sort(key=lambda s: s.invocation_count, reverse=True)

        return stats

    async def get_error_rate_metrics(self, limit: int = 1000) -> ErrorRateMetrics:
        """
        Get error rate metrics across all tools.

        Args:
            limit: Maximum number of audit logs to analyze

        Returns:
            Error rate metrics
        """
        # Retrieve all audit logs
        logs = self._audit_service.get_logs(limit=limit)

        total_invocations = len(logs)
        total_errors = sum(1 for log in logs if log.status == AuditStatus.FAILURE)
        overall_error_rate = total_errors / total_invocations if total_invocations > 0 else 0.0

        # Count errors by type (using error message prefix as type)
        errors_by_type: dict[str, int] = defaultdict(int)
        errors_by_tool: dict[str, int] = defaultdict(int)
        recent_errors = []

        for log in logs:
            if log.status == AuditStatus.FAILURE:
                # Extract error type from error message
                error_type = "unknown"
                if log.error_message:
                    # Use first word of error message as type
                    error_type = log.error_message.split(":")[0].split()[0]

                errors_by_type[error_type] += 1
                errors_by_tool[log.tool_name] += 1

                # Keep recent errors (last 10)
                if len(recent_errors) < 10:
                    recent_errors.append(
                        {
                            "timestamp": log.timestamp.isoformat(),
                            "tool_name": log.tool_name,
                            "error_message": log.error_message,
                            "correlation_id": log.correlation_id,
                        }
                    )

        # Calculate error trend (simple: compare first half vs second half)
        if total_invocations >= 10:
            mid_point = total_invocations // 2
            first_half_errors = sum(
                1 for log in logs[:mid_point] if log.status == AuditStatus.FAILURE
            )
            second_half_errors = sum(
                1 for log in logs[mid_point:] if log.status == AuditStatus.FAILURE
            )
            first_half_rate = first_half_errors / mid_point if mid_point > 0 else 0.0
            second_half_rate = (
                second_half_errors / (total_invocations - mid_point)
                if (total_invocations - mid_point) > 0
                else 0.0
            )

            if second_half_rate < first_half_rate * 0.9:
                error_trend = "improving"
            elif second_half_rate > first_half_rate * 1.1:
                error_trend = "declining"
            else:
                error_trend = "stable"
        else:
            error_trend = "stable"

        return ErrorRateMetrics(
            total_invocations=total_invocations,
            total_errors=total_errors,
            overall_error_rate=overall_error_rate,
            errors_by_type=dict(errors_by_type),
            errors_by_tool=dict(errors_by_tool),
            recent_errors=recent_errors,
            error_trend=error_trend,
        )

    async def get_budget_utilization_metrics(
        self, session_id: str | None = None
    ) -> BudgetUtilizationMetrics | None:
        """
        Get budget utilization metrics.

        Args:
            session_id: Optional session ID for session-specific metrics

        Returns:
            Budget utilization metrics or None if budget tracking not enabled
        """
        if not self._budget_tracker:
            return None

        if session_id:
            # Session-specific metrics
            current_usage = await self._budget_tracker.get_current_count(session_id)
            max_budget = self._budget_tracker.max_calls_per_session
            remaining_budget = max(0, max_budget - current_usage)
            utilization_percent = (current_usage / max_budget * 100) if max_budget > 0 else 0.0
            is_exhausted = current_usage >= max_budget

            return BudgetUtilizationMetrics(
                session_id=session_id,
                current_usage=current_usage,
                max_budget=max_budget,
                remaining_budget=remaining_budget,
                utilization_percent=utilization_percent,
                is_exhausted=is_exhausted,
                active_sessions_count=0,
                sessions_exhausted_count=0,
            )
        else:
            # Global metrics
            active_sessions = await self._budget_tracker.get_active_session_count()
            max_budget = self._budget_tracker.max_calls_per_session

            return BudgetUtilizationMetrics(
                session_id=None,
                current_usage=0,
                max_budget=max_budget,
                remaining_budget=max_budget,
                utilization_percent=0.0,
                is_exhausted=False,
                active_sessions_count=active_sessions,
                sessions_exhausted_count=0,  # Would need additional tracking
            )

    async def get_loop_detection_metrics(
        self, session_id: str | None = None
    ) -> LoopDetectionMetrics | None:
        """
        Get loop detection metrics.

        Args:
            session_id: Optional session ID for session-specific metrics

        Returns:
            Loop detection metrics or None if loop detection not enabled
        """
        if not self._loop_detector:
            return None

        # Get stats from loop detector
        stats = await self._loop_detector.get_loop_detection_stats(session_id)
        recent_loops = self._loop_detector.get_recent_loop_events(limit=10)

        return LoopDetectionMetrics(
            total_loops_detected=stats.get("loops_detected_total", 0),
            active_sessions_with_loops=stats.get("active_sessions", 0),
            loops_by_tool=stats.get("loops_by_tool", {}),
            loops_by_session={},  # Would need additional tracking
            last_loop_detected_at=(
                datetime.fromisoformat(stats["last_loop_detected_at"])
                if stats.get("last_loop_detected_at")
                else None
            ),
            last_loop_tool_name=stats.get("last_loop_tool_name"),
            last_loop_session_id=stats.get("last_loop_session_id"),
            loop_prevention_enabled=stats.get("enabled", True),
            max_identical_calls_threshold=stats.get("max_identical_calls", 3),
            recent_loops=recent_loops,
        )

    async def get_session_metrics(self, session_id: str) -> SessionMetrics:
        """
        Get metrics for a specific session.

        Args:
            session_id: Session identifier

        Returns:
            Session metrics
        """
        # Get audit logs for this session (using correlation_id as session_id)
        logs = self._audit_service.get_logs(correlation_id=session_id, limit=1000)

        if not logs:
            # No logs for this session, return empty metrics
            return SessionMetrics(
                session_id=session_id,
                created_at=datetime.now(UTC),
                last_activity_at=datetime.now(UTC),
            )

        # Calculate metrics from logs
        tool_invocation_count = len(logs)
        tool_success_count = sum(1 for log in logs if log.status == AuditStatus.SUCCESS)
        tool_failure_count = sum(1 for log in logs if log.status == AuditStatus.FAILURE)

        execution_times = [
            log.execution_time_ms for log in logs if log.execution_time_ms is not None
        ]
        total_execution_time_ms = sum(execution_times) if execution_times else 0.0
        average_execution_time_ms = (
            total_execution_time_ms / len(execution_times) if execution_times else 0.0
        )

        tools_used = list({log.tool_name for log in logs})

        # Get timestamps
        created_at = min(log.timestamp for log in logs)
        last_activity_at = max(log.timestamp for log in logs)

        # Get budget status
        budget_status = await self.get_budget_utilization_metrics(session_id)

        # Get loop detection status
        loop_detection_status = await self.get_loop_detection_metrics(session_id)

        return SessionMetrics(
            session_id=session_id,
            created_at=created_at,
            last_activity_at=last_activity_at,
            tool_invocation_count=tool_invocation_count,
            tool_success_count=tool_success_count,
            tool_failure_count=tool_failure_count,
            total_execution_time_ms=total_execution_time_ms,
            average_execution_time_ms=average_execution_time_ms,
            budget_status=budget_status,
            loop_detection_status=loop_detection_status,
            tools_used=tools_used,
            error_count=tool_failure_count,
            is_active=True,  # Would need additional logic to determine if session is still active
        )

    async def get_global_metrics(self, limit: int = 1000) -> GlobalMetrics:
        """
        Get global metrics aggregated across all sessions.

        Args:
            limit: Maximum number of audit logs to analyze

        Returns:
            Global metrics
        """
        current_time = datetime.now(UTC)
        uptime_seconds = (current_time - self._server_start_time).total_seconds()

        # Get all audit logs
        logs = self._audit_service.get_logs(limit=limit)

        # Calculate global statistics
        total_tool_invocations = len(logs)
        total_tool_successes = sum(1 for log in logs if log.status == AuditStatus.SUCCESS)
        total_tool_failures = sum(1 for log in logs if log.status == AuditStatus.FAILURE)
        overall_error_rate = (
            total_tool_failures / total_tool_invocations if total_tool_invocations > 0 else 0.0
        )

        execution_times = [
            log.execution_time_ms for log in logs if log.execution_time_ms is not None
        ]
        total_execution_time_ms = sum(execution_times) if execution_times else 0.0
        average_execution_time_ms = (
            total_execution_time_ms / len(execution_times) if execution_times else 0.0
        )

        # Count unique sessions (using correlation_id as session_id)
        unique_sessions = {log.correlation_id for log in logs if log.correlation_id}
        total_sessions = len(unique_sessions)

        # Get active sessions from budget tracker
        active_sessions = 0
        if self._budget_tracker:
            active_sessions = await self._budget_tracker.get_active_session_count()

        # Get tool usage stats
        tool_stats = await self.get_tool_usage_stats(limit=limit)

        # Find most and least used tools
        most_used_tool = None
        least_used_tool = None
        if tool_stats:
            most_used_tool = tool_stats[0].tool_name
            least_used_tool = tool_stats[-1].tool_name

        # Get error metrics
        error_metrics = await self.get_error_rate_metrics(limit=limit)

        # Get budget metrics
        budget_metrics = await self.get_budget_utilization_metrics()

        # Get loop detection metrics
        loop_detection_metrics = await self.get_loop_detection_metrics()

        return GlobalMetrics(
            server_start_time=self._server_start_time,
            current_time=current_time,
            uptime_seconds=uptime_seconds,
            total_sessions=total_sessions,
            active_sessions=active_sessions,
            total_tool_invocations=total_tool_invocations,
            total_tool_successes=total_tool_successes,
            total_tool_failures=total_tool_failures,
            overall_error_rate=overall_error_rate,
            total_execution_time_ms=total_execution_time_ms,
            average_execution_time_ms=average_execution_time_ms,
            tool_stats=tool_stats,
            error_metrics=error_metrics,
            budget_metrics=budget_metrics,
            loop_detection_metrics=loop_detection_metrics,
            most_used_tool=most_used_tool,
            least_used_tool=least_used_tool,
        )
