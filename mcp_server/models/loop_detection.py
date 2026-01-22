# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Loop detection data models.

This module defines data models for loop detection responses
when repeated tool calls are detected.

Requirements: 15.4
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class LoopDetectedResponse(BaseModel):
    """
    Structured response for loop detection.

    This is returned when the same tool is called repeatedly with
    identical parameters, indicating a potential agent loop.

    Requirements: 15.4
    """

    error_type: str = Field(
        default="loop_detected", description="Type of error for programmatic handling"
    )
    message: str = Field(..., description="Human-readable message explaining the loop detection")
    tool_name: str = Field(..., description="The tool that was called repeatedly")
    call_count: int = Field(
        ..., ge=0, description="Number of times the tool was called with identical parameters"
    )
    max_calls: int = Field(..., ge=0, description="Maximum identical calls allowed")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when loop was detected",
    )
    suggestion: str = Field(
        default="Please review your request and try a different approach.",
        description="Suggestion for the user on how to proceed",
    )

    @classmethod
    def create(
        cls,
        tool_name: str,
        call_count: int,
        max_calls: int,
    ) -> "LoopDetectedResponse":
        """
        Create a loop detected response with a helpful message.

        Args:
            tool_name: The tool that was called repeatedly
            call_count: Number of times the tool was called
            max_calls: Maximum identical calls allowed

        Returns:
            LoopDetectedResponse with formatted message
        """
        message = (
            f"Loop detected: The tool '{tool_name}' has been called {call_count} times "
            f"with identical parameters (maximum allowed: {max_calls}). "
            f"This may indicate a repeated pattern that isn't making progress."
        )

        suggestion = (
            "Please review your request and try a different approach. "
            "If you're stuck, consider:\n"
            "- Modifying your query or parameters\n"
            "- Breaking down the task into smaller steps\n"
            "- Asking for help or clarification"
        )

        return cls(
            message=message,
            tool_name=tool_name,
            call_count=call_count,
            max_calls=max_calls,
            suggestion=suggestion,
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
                    f"🔄 {self.message}\n\n"
                    f"Tool: {self.tool_name}\n"
                    f"Calls: {self.call_count}/{self.max_calls}\n\n"
                    f"💡 {self.suggestion}"
                ),
            }
        ]


class LoopDetectionConfiguration(BaseModel):
    """Loop detection configuration."""

    enabled: bool = Field(default=True, description="Whether loop detection is enabled")
    max_identical_calls: int = Field(
        default=3, ge=1, description="Maximum identical calls allowed before blocking"
    )
    sliding_window_seconds: int = Field(
        default=300, ge=60, description="Time window for tracking calls in seconds"
    )


class LoopDetectionHealthInfo(BaseModel):
    """Loop detection information for health endpoint."""

    enabled: bool = Field(..., description="Whether loop detection is enabled")
    max_identical_calls: int = Field(
        ..., description="Maximum identical calls allowed before blocking"
    )
    sliding_window_seconds: int = Field(
        ..., description="Time window for tracking calls in seconds"
    )
