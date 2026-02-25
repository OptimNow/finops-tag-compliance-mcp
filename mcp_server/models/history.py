# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Data models for compliance history tracking."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class GroupBy(str, Enum):
    """Time grouping options for history queries."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class TrendDirection(str, Enum):
    """Trend direction for compliance scores."""

    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"


class ComplianceHistoryEntry(BaseModel):
    """A single historical compliance data point."""

    timestamp: datetime = Field(description="When this scan was recorded")
    compliance_score: float = Field(
        ge=0.0, le=1.0, description="Compliance score at this point in time"
    )
    total_resources: int = Field(ge=0, description="Total resources scanned")
    compliant_resources: int = Field(ge=0, description="Number of compliant resources")
    violation_count: int = Field(ge=0, description="Total number of violations")


class ComplianceHistoryResult(BaseModel):
    """Result of a compliance history query."""

    history: list[ComplianceHistoryEntry] = Field(description="Historical compliance data points")
    group_by: GroupBy = Field(description="How the data is grouped")
    trend_direction: TrendDirection = Field(
        description="Overall trend direction (improving, declining, stable)"
    )
    earliest_score: float = Field(
        ge=0.0, le=1.0, description="Earliest compliance score in the range"
    )
    latest_score: float = Field(ge=0.0, le=1.0, description="Latest compliance score in the range")
    days_back: int = Field(ge=1, le=90, description="Number of days of history returned")
