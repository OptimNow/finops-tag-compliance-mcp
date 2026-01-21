# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Violation data model."""

from pydantic import BaseModel, ConfigDict, Field

from .enums import ViolationType, Severity


class Violation(BaseModel):
    """Represents a tagging policy violation for a resource."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resource_id": "i-1234567890abcdef0",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "violation_type": "missing_required_tag",
                "tag_name": "CostCenter",
                "severity": "error",
                "current_value": None,
                "allowed_values": ["Engineering", "Marketing", "Sales"],
                "cost_impact_monthly": 150.50,
            }
        }
    )

    resource_id: str = Field(..., description="AWS resource identifier (ARN or ID)")
    resource_type: str = Field(..., description="Type of AWS resource (e.g., ec2:instance)")
    region: str = Field(..., description="AWS region where the resource is located")
    violation_type: ViolationType = Field(..., description="Type of violation")
    tag_name: str = Field(..., description="Name of the tag that violated the policy")
    severity: Severity = Field(..., description="Severity level of the violation")
    current_value: str | None = Field(None, description="Current value of the tag (if present)")
    allowed_values: list[str] | None = Field(
        None, description="List of allowed values for this tag (if applicable)"
    )
    cost_impact_monthly: float = Field(
        0.0, description="Estimated monthly cost impact of this violation in USD", ge=0.0
    )
