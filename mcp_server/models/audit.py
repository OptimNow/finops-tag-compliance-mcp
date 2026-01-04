# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Audit log data models."""

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, field_serializer


class AuditStatus(str, Enum):
    """Status of an audit log entry."""

    SUCCESS = "success"
    FAILURE = "failure"


class AuditLogEntry(BaseModel):
    """Represents a single audit log entry for a tool invocation."""

    id: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_name: str
    parameters: dict
    status: AuditStatus
    error_message: str | None = None
    execution_time_ms: float | None = None
    correlation_id: str | None = None

    class Config:
        """Pydantic config."""

    @field_serializer('timestamp')
    def serialize_timestamp(self, timestamp: datetime) -> str:
        return timestamp.isoformat()
