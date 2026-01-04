# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Budget tracking data models.

This module defines data models for tool-call budget tracking
and graceful degradation responses.

Requirements: 15.3, 15.5
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class BudgetStatus(BaseModel):
    """Current budget status for a session."""
    
    session_id: str = Field(
        ...,
        description="The session identifier"
    )
    current_count: int = Field(
        ...,
        ge=0,
        description="Current number of tool calls made in this session"
    )
    max_calls: int = Field(
        ...,
        ge=0,
        description="Maximum tool calls allowed per session"
    )
    remaining: int = Field(
        ...,
        ge=0,
        description="Remaining tool calls available"
    )
    utilization_percent: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of budget used"
    )
    is_exhausted: bool = Field(
        ...,
        description="Whether the budget is exhausted"
    )


class BudgetExhaustedResponse(BaseModel):
    """
    Structured response for budget exhaustion.
    
    This is returned when a session's tool-call budget is exhausted,
    providing a graceful degradation response with helpful information.
    
    Requirements: 15.5
    """
    
    error_type: str = Field(
        default="budget_exhausted",
        description="Type of error for programmatic handling"
    )
    message: str = Field(
        ...,
        description="Human-readable message explaining the budget exhaustion"
    )
    session_id: str = Field(
        ...,
        description="The session identifier that exhausted its budget"
    )
    current_usage: int = Field(
        ...,
        ge=0,
        description="Current number of tool calls made"
    )
    limit: int = Field(
        ...,
        ge=0,
        description="Maximum tool calls allowed per session"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when budget exhaustion occurred"
    )
    suggestion: str = Field(
        default="Please start a new session or wait for the current session to expire.",
        description="Suggestion for the user on how to proceed"
    )
    retry_after_seconds: Optional[int] = Field(
        default=None,
        description="Seconds until the session budget resets (if applicable)"
    )
    
    @classmethod
    def create(
        cls,
        session_id: str,
        current_usage: int,
        limit: int,
        retry_after_seconds: Optional[int] = None,
    ) -> "BudgetExhaustedResponse":
        """
        Create a budget exhausted response with a helpful message.
        
        Args:
            session_id: The session identifier
            current_usage: Current number of tool calls made
            limit: Maximum tool calls allowed
            retry_after_seconds: Optional seconds until reset
        
        Returns:
            BudgetExhaustedResponse with formatted message
        """
        message = (
            f"Tool-call budget exhausted. You have used {current_usage} out of "
            f"{limit} allowed tool calls for this session."
        )
        
        suggestion = "Please start a new session to continue using tools."
        if retry_after_seconds:
            minutes = retry_after_seconds // 60
            if minutes > 0:
                suggestion = (
                    f"Your session budget will reset in approximately {minutes} minutes, "
                    f"or you can start a new session."
                )
        
        return cls(
            message=message,
            session_id=session_id,
            current_usage=current_usage,
            limit=limit,
            suggestion=suggestion,
            retry_after_seconds=retry_after_seconds,
        )
    
    def to_mcp_content(self) -> list[dict]:
        """
        Convert to MCP tool response content format.
        
        Returns:
            List of content items for MCP response
        """
        return [
            {
                "type": "text",
                "text": (
                    f"⚠️ {self.message}\n\n"
                    f"Session: {self.session_id}\n"
                    f"Usage: {self.current_usage}/{self.limit} calls\n\n"
                    f"💡 {self.suggestion}"
                ),
            }
        ]


class BudgetConfiguration(BaseModel):
    """Budget tracking configuration."""
    
    enabled: bool = Field(
        default=True,
        description="Whether budget tracking is enabled"
    )
    max_calls_per_session: int = Field(
        default=100,
        ge=1,
        description="Maximum tool calls allowed per session"
    )
    session_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="TTL for session budget tracking in seconds"
    )


class BudgetHealthInfo(BaseModel):
    """Budget tracking information for health endpoint."""
    
    enabled: bool = Field(
        ...,
        description="Whether budget tracking is enabled"
    )
    max_calls_per_session: int = Field(
        ...,
        description="Maximum tool calls allowed per session"
    )
    session_ttl_seconds: int = Field(
        ...,
        description="TTL for session budget tracking in seconds"
    )
    active_sessions: int = Field(
        default=0,
        ge=0,
        description="Number of active sessions being tracked"
    )
