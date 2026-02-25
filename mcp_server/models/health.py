# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Health check data models."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class BudgetHealthInfo(BaseModel):
    """Budget tracking information for health endpoint."""

    enabled: bool = Field(..., description="Whether budget tracking is enabled")
    max_calls_per_session: int = Field(..., description="Maximum tool calls allowed per session")
    session_ttl_seconds: int = Field(..., description="TTL for session budget tracking in seconds")
    active_sessions: int = Field(
        default=0, ge=0, description="Number of active sessions being tracked"
    )


class LoopDetectionHealthInfo(BaseModel):
    """Loop detection information for health endpoint."""

    enabled: bool = Field(..., description="Whether loop detection is enabled")
    max_identical_calls: int = Field(
        ..., description="Maximum identical calls allowed before blocking"
    )
    sliding_window_seconds: int = Field(
        ..., description="Time window for tracking identical calls in seconds"
    )
    active_sessions: int = Field(
        default=0, ge=0, description="Number of active sessions with loop tracking"
    )
    loops_detected_total: int = Field(
        default=0, ge=0, description="Total number of loops detected since server start"
    )
    loops_by_tool: dict = Field(
        default_factory=dict, description="Loop detection counts by tool name"
    )
    last_loop_detected_at: str | None = Field(
        default=None, description="Timestamp of the last loop detection event"
    )
    last_loop_tool_name: str | None = Field(
        default=None, description="Tool name that triggered the last loop detection"
    )


class SecurityHealthInfo(BaseModel):
    """Security monitoring information for health endpoint."""

    enabled: bool = Field(..., description="Whether security monitoring is enabled")
    max_unknown_tool_attempts: int = Field(
        ..., description="Maximum unknown tool attempts allowed before rate limiting"
    )
    window_seconds: int = Field(
        ..., description="Time window for tracking security events in seconds"
    )
    total_events: int = Field(default=0, ge=0, description="Total number of security events logged")
    events_by_type: dict = Field(default_factory=dict, description="Security event counts by type")
    events_by_severity: dict = Field(
        default_factory=dict, description="Security event counts by severity"
    )
    recent_events_count: int = Field(
        default=0, ge=0, description="Number of recent security events in memory"
    )
    redis_enabled: bool = Field(
        default=False, description="Whether Redis is being used for distributed security tracking"
    )


class HealthStatus(BaseModel):
    """Health status response for the MCP server."""

    status: str = Field(
        ..., description="Overall health status: 'healthy' or 'degraded'", examples=["healthy"]
    )
    version: str = Field(..., description="Version of the MCP server", examples=["0.1.0"])
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when health check was performed",
    )
    cloud_providers: list[str] = Field(
        default=["aws"], description="List of supported cloud providers"
    )
    redis_connected: bool = Field(..., description="Whether Redis cache is connected")
    sqlite_connected: bool = Field(..., description="Whether SQLite database is accessible")
    budget_tracking: BudgetHealthInfo | None = Field(
        default=None, description="Budget tracking configuration and status"
    )
    loop_detection: LoopDetectionHealthInfo | None = Field(
        default=None, description="Loop detection configuration and status"
    )
    security_monitoring: SecurityHealthInfo | None = Field(
        default=None, description="Security monitoring configuration and status"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}
