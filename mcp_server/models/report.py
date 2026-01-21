# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Report data models."""

from datetime import datetime, UTC
from enum import Enum

from pydantic import BaseModel, Field


class ReportFormat(str, Enum):
    """Supported report output formats."""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ViolationRanking(BaseModel):
    """Represents a violation ranked by count and cost."""

    tag_name: str = Field(..., description="Name of the tag with violations")
    violation_count: int = Field(..., description="Number of violations for this tag", ge=0)
    total_cost_impact: float = Field(..., description="Total monthly cost impact in USD", ge=0.0)
    affected_resource_types: list[str] = Field(
        default_factory=list, description="List of resource types affected by this violation"
    )


class ComplianceRecommendation(BaseModel):
    """Represents an actionable recommendation for improving compliance."""

    priority: str = Field(..., description="Priority level (high, medium, low)")
    title: str = Field(..., description="Short title of the recommendation")
    description: str = Field(..., description="Detailed description of the recommendation")
    estimated_impact: str = Field(..., description="Estimated impact if implemented")
    affected_resources: int = Field(0, description="Number of resources affected", ge=0)


class ComplianceReport(BaseModel):
    """Represents a comprehensive compliance report."""

    # Summary section
    overall_compliance_score: float = Field(
        ..., description="Overall compliance score (0.0 to 1.0)", ge=0.0, le=1.0
    )
    total_resources: int = Field(..., description="Total number of resources scanned", ge=0)
    compliant_resources: int = Field(..., description="Number of compliant resources", ge=0)
    non_compliant_resources: int = Field(..., description="Number of non-compliant resources", ge=0)
    total_violations: int = Field(..., description="Total number of violations found", ge=0)
    cost_attribution_gap: float = Field(
        0.0, description="Total monthly cost that cannot be attributed", ge=0.0
    )

    # Top violations ranked by count and cost
    top_violations_by_count: list[ViolationRanking] = Field(
        default_factory=list, description="Top violations ranked by occurrence count"
    )
    top_violations_by_cost: list[ViolationRanking] = Field(
        default_factory=list, description="Top violations ranked by cost impact"
    )

    # Recommendations (optional)
    recommendations: list[ComplianceRecommendation] = Field(
        default_factory=list, description="Actionable recommendations for improving compliance"
    )

    # Metadata
    report_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the report was generated",
    )
    scan_timestamp: datetime = Field(
        ..., description="Timestamp when the underlying compliance scan was performed"
    )
