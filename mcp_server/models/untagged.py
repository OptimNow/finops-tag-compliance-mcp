# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Untagged resource data models."""

from datetime import datetime
from pydantic import BaseModel, Field


class UntaggedResource(BaseModel):
    """Represents a resource that is untagged or missing required tags."""
    
    resource_id: str = Field(..., description="AWS resource identifier")
    resource_type: str = Field(..., description="Type of AWS resource")
    region: str = Field(..., description="AWS region")
    arn: str = Field(..., description="Full ARN of the resource")
    current_tags: dict[str, str] = Field(
        default_factory=dict,
        description="Current tags on the resource (may be empty)"
    )
    missing_required_tags: list[str] = Field(
        default_factory=list,
        description="List of required tag names that are missing"
    )
    monthly_cost_estimate: float | None = Field(
        None,
        description=(
            "Estimated monthly cost in USD. Only populated when include_costs=True. "
            "For EC2/RDS this is actual per-resource cost from Cost Explorer. "
            "For S3/Lambda/ECS this is a rough estimate (service total / resource count)."
        )
    )
    cost_source: str | None = Field(
        None,
        description=(
            "Source of cost data (only populated when include_costs=True): "
            "'actual' = from Cost Explorer per-resource data (EC2/RDS), "
            "'service_average' = service total divided by resource count (rough estimate), "
            "'estimated' = placeholder (Cost Explorer unavailable)"
        )
    )
    age_days: int = Field(
        0,
        description="Age of the resource in days"
    )
    created_at: datetime | None = Field(
        None,
        description="When the resource was created"
    )


class UntaggedResourcesResult(BaseModel):
    """Result of finding untagged resources."""
    
    total_untagged: int = Field(
        ...,
        description="Total number of untagged or partially tagged resources found"
    )
    resources: list[UntaggedResource] = Field(
        default_factory=list,
        description="List of untagged resources"
    )
    total_monthly_cost: float = Field(
        0.0,
        description=(
            "Total estimated monthly cost of all untagged resources. "
            "Only populated when include_costs=True was requested."
        )
    )
    cost_data_note: str | None = Field(
        None,
        description=(
            "Note about cost data accuracy (only when include_costs=True). "
            "EC2/RDS costs are actual per-resource data from Cost Explorer. "
            "S3/Lambda/ECS costs are rough estimates (service total / resource count)."
        )
    )
    scan_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the scan was performed"
    )
