# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Observability data models for agent monitoring and metrics.

This module defines data models for tracking session metrics, tool usage statistics,
error rates, budget utilization, and loop detection statistics for observability
and monitoring purposes.

Requirements: 15.2
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ToolUsageStats(BaseModel):
    """Statistics for a single tool's usage."""

    tool_name: str = Field(..., description="Name of the tool")
    invocation_count: int = Field(
        default=0, ge=0, description="Total number of times this tool was invoked"
    )
    success_count: int = Field(default=0, ge=0, description="Number of successful invocations")
    failure_count: int = Field(default=0, ge=0, description="Number of failed invocations")
    total_execution_time_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Total execution time across all invocations in milliseconds",
    )
    average_execution_time_ms: float = Field(
        default=0.0, ge=0.0, description="Average execution time per invocation in milliseconds"
    )
    min_execution_time_ms: float | None = Field(
        default=None, ge=0.0, description="Minimum execution time in milliseconds"
    )
    max_execution_time_ms: float | None = Field(
        default=None, ge=0.0, description="Maximum execution time in milliseconds"
    )
    error_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Error rate as a fraction (0.0 to 1.0)"
    )
    last_invoked_at: datetime | None = Field(
        default=None, description="Timestamp of the last invocation"
    )
    last_error: str | None = Field(
        default=None, description="Error message from the last failed invocation"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class ErrorRateMetrics(BaseModel):
    """Error rate metrics for the system."""

    total_invocations: int = Field(default=0, ge=0, description="Total number of tool invocations")
    total_errors: int = Field(default=0, ge=0, description="Total number of errors")
    overall_error_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall error rate as a fraction (0.0 to 1.0)"
    )
    errors_by_type: dict[str, int] = Field(
        default_factory=dict, description="Count of errors by error type"
    )
    errors_by_tool: dict[str, int] = Field(
        default_factory=dict, description="Count of errors by tool name"
    )
    recent_errors: list[dict] = Field(
        default_factory=list, description="List of recent error events with timestamps and details"
    )
    error_trend: str = Field(
        default="stable", description="Trend direction: 'improving', 'declining', or 'stable'"
    )


class BudgetUtilizationMetrics(BaseModel):
    """Budget utilization metrics for a session or globally."""

    session_id: str | None = Field(
        default=None, description="Session identifier (None for global metrics)"
    )
    current_usage: int = Field(default=0, ge=0, description="Current number of tool calls made")
    max_budget: int = Field(..., ge=1, description="Maximum tool calls allowed")
    remaining_budget: int = Field(default=0, ge=0, description="Remaining tool calls available")
    utilization_percent: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Percentage of budget used"
    )
    is_exhausted: bool = Field(default=False, description="Whether the budget is exhausted")
    exhaustion_timestamp: datetime | None = Field(
        default=None, description="Timestamp when budget was exhausted (if applicable)"
    )
    reset_timestamp: datetime | None = Field(
        default=None, description="Timestamp when budget will reset (if applicable)"
    )
    active_sessions_count: int = Field(
        default=0, ge=0, description="Number of active sessions (for global metrics)"
    )
    sessions_exhausted_count: int = Field(
        default=0, ge=0, description="Number of sessions that have exhausted their budget"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class LoopDetectionMetrics(BaseModel):
    """Loop detection metrics for monitoring repeated tool calls."""

    total_loops_detected: int = Field(
        default=0, ge=0, description="Total number of loops detected since server start"
    )
    active_sessions_with_loops: int = Field(
        default=0, ge=0, description="Number of active sessions currently tracking loops"
    )
    loops_by_tool: dict[str, int] = Field(
        default_factory=dict, description="Count of loops detected by tool name"
    )
    loops_by_session: dict[str, int] = Field(
        default_factory=dict, description="Count of loops detected by session ID"
    )
    last_loop_detected_at: datetime | None = Field(
        default=None, description="Timestamp of the last loop detection event"
    )
    last_loop_tool_name: str | None = Field(
        default=None, description="Tool name that triggered the last loop detection"
    )
    last_loop_session_id: str | None = Field(
        default=None, description="Session ID that triggered the last loop detection"
    )
    loop_prevention_enabled: bool = Field(
        default=True, description="Whether loop detection and prevention is enabled"
    )
    max_identical_calls_threshold: int = Field(
        default=3, ge=1, description="Maximum identical calls allowed before blocking"
    )
    recent_loops: list[dict] = Field(
        default_factory=list, description="List of recent loop detection events with details"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class SessionMetrics(BaseModel):
    """Metrics for a single session."""

    session_id: str = Field(..., description="Unique session identifier")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the session was created",
    )
    last_activity_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the last activity in this session",
    )
    tool_invocation_count: int = Field(
        default=0, ge=0, description="Total number of tool invocations in this session"
    )
    tool_success_count: int = Field(
        default=0, ge=0, description="Number of successful tool invocations"
    )
    tool_failure_count: int = Field(
        default=0, ge=0, description="Number of failed tool invocations"
    )
    total_execution_time_ms: float = Field(
        default=0.0, ge=0.0, description="Total execution time for all tools in this session"
    )
    average_execution_time_ms: float = Field(
        default=0.0, ge=0.0, description="Average execution time per tool invocation"
    )
    budget_status: BudgetUtilizationMetrics | None = Field(
        default=None, description="Current budget status for this session"
    )
    loop_detection_status: LoopDetectionMetrics | None = Field(
        default=None, description="Loop detection status for this session"
    )
    tools_used: list[str] = Field(
        default_factory=list, description="List of unique tools invoked in this session"
    )
    error_count: int = Field(default=0, ge=0, description="Total number of errors in this session")
    is_active: bool = Field(default=True, description="Whether this session is currently active")

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class GlobalMetrics(BaseModel):
    """Global metrics aggregated across all sessions."""

    server_start_time: datetime = Field(..., description="Timestamp when the server started")
    current_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Current timestamp"
    )
    uptime_seconds: float = Field(default=0.0, ge=0.0, description="Server uptime in seconds")
    total_sessions: int = Field(default=0, ge=0, description="Total number of sessions created")
    active_sessions: int = Field(default=0, ge=0, description="Number of currently active sessions")
    total_tool_invocations: int = Field(
        default=0, ge=0, description="Total number of tool invocations across all sessions"
    )
    total_tool_successes: int = Field(
        default=0, ge=0, description="Total number of successful tool invocations"
    )
    total_tool_failures: int = Field(
        default=0, ge=0, description="Total number of failed tool invocations"
    )
    overall_error_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall error rate as a fraction (0.0 to 1.0)"
    )
    total_execution_time_ms: float = Field(
        default=0.0, ge=0.0, description="Total execution time across all tool invocations"
    )
    average_execution_time_ms: float = Field(
        default=0.0, ge=0.0, description="Average execution time per tool invocation"
    )
    tool_stats: list[ToolUsageStats] = Field(
        default_factory=list, description="Usage statistics for each tool"
    )
    error_metrics: ErrorRateMetrics | None = Field(
        default=None, description="Error rate metrics"
    )
    budget_metrics: BudgetUtilizationMetrics | None = Field(
        default=None, description="Global budget utilization metrics"
    )
    loop_detection_metrics: LoopDetectionMetrics | None = Field(
        default=None, description="Global loop detection metrics"
    )
    most_used_tool: str | None = Field(
        default=None, description="Name of the most frequently used tool"
    )
    least_used_tool: str | None = Field(
        default=None, description="Name of the least frequently used tool"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}
