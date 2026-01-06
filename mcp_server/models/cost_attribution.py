# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Data models for cost attribution analysis."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CostBreakdown(BaseModel):
    """Breakdown of costs by a grouping dimension."""
    
    total: float = Field(
        description="Total spend for this group"
    )
    attributable: float = Field(
        description="Spend from properly tagged resources in this group"
    )
    gap: float = Field(
        description="Spend that cannot be attributed in this group"
    )
    resources_scanned: int = Field(
        default=0,
        description="Number of resources scanned in this group"
    )
    resources_compliant: int = Field(
        default=0,
        description="Number of resources with proper tags in this group"
    )
    resources_non_compliant: int = Field(
        default=0,
        description="Number of resources missing required tags in this group"
    )
    note: Optional[str] = Field(
        default=None,
        description="Clarification note when spend is $0 (e.g., no resources found vs resources with $0 cost)"
    )


class CostAttributionGapResult(BaseModel):
    """
    Result of cost attribution gap analysis.
    
    Shows the financial impact of tagging gaps - how much cloud spend
    cannot be allocated to teams/projects due to missing or invalid tags.
    
    Requirements: 4.1, 4.2, 4.3, 4.5
    """
    
    total_spend: float = Field(
        description="Total cloud spend for the time period in USD"
    )
    attributable_spend: float = Field(
        description="Spend from resources with proper tags in USD"
    )
    attribution_gap: float = Field(
        description="Dollar amount that cannot be attributed (total - attributable)"
    )
    attribution_gap_percentage: float = Field(
        description="Gap as percentage of total spend (0-100)"
    )
    time_period: dict[str, str] = Field(
        description="Time period analyzed (Start and End dates)"
    )
    breakdown: Optional[dict[str, CostBreakdown]] = Field(
        default=None,
        description="Optional breakdown by grouping dimension (resource_type, region, or account)"
    )
    total_resources_scanned: int = Field(
        default=0,
        description="Total number of resources scanned across all types"
    )
    total_resources_compliant: int = Field(
        default=0,
        description="Total number of resources with proper tags"
    )
    total_resources_non_compliant: int = Field(
        default=0,
        description="Total number of resources missing required tags"
    )
    scan_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When this analysis was performed"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_spend": 50000.00,
                "attributable_spend": 35000.00,
                "attribution_gap": 15000.00,
                "attribution_gap_percentage": 30.0,
                "time_period": {
                    "Start": "2025-01-01",
                    "End": "2025-01-31"
                },
                "breakdown": {
                    "ec2:instance": {
                        "total": 30000.00,
                        "attributable": 20000.00,
                        "gap": 10000.00,
                        "resources_scanned": 10,
                        "resources_compliant": 6,
                        "resources_non_compliant": 4,
                        "note": None
                    },
                    "rds:db": {
                        "total": 20000.00,
                        "attributable": 15000.00,
                        "gap": 5000.00,
                        "resources_scanned": 3,
                        "resources_compliant": 2,
                        "resources_non_compliant": 1,
                        "note": None
                    }
                },
                "total_resources_scanned": 13,
                "total_resources_compliant": 8,
                "total_resources_non_compliant": 5,
                "scan_timestamp": "2025-01-31T12:00:00"
            }
        }
