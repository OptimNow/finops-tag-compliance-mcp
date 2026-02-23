# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Resource validation result data model."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from .violations import Violation


class ResourceValidationResult(BaseModel):
    """Represents the validation result for a single resource."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resource_arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                "resource_id": "i-1234567890abcdef0",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "is_compliant": False,
                "violations": [],
                "current_tags": {"Environment": "production"},
            }
        }
    )

    resource_arn: str = Field(..., description="Full ARN of the resource")
    resource_id: str = Field(..., description="AWS resource identifier")
    resource_type: str = Field(..., description="Type of AWS resource (e.g., ec2:instance)")
    region: str = Field(..., description="AWS region where the resource is located")
    is_compliant: bool = Field(..., description="Whether the resource is compliant with the policy")
    violations: list[Violation] = Field(
        default_factory=list, description="List of violations found for this resource"
    )
    current_tags: dict[str, str] = Field(
        default_factory=dict, description="Current tags on the resource"
    )


class ValidateResourceTagsResult(BaseModel):
    """Represents the result of validating multiple resources."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_resources": 5,
                "compliant_resources": 3,
                "non_compliant_resources": 2,
                "results": [],
                "validation_timestamp": "2025-12-30T10:00:00Z",
            }
        }
    )

    total_resources: int = Field(..., description="Total number of resources validated", ge=0)
    compliant_resources: int = Field(
        ..., description="Number of resources that are compliant", ge=0
    )
    non_compliant_resources: int = Field(
        ..., description="Number of resources that are non-compliant", ge=0
    )
    results: list[ResourceValidationResult] = Field(
        default_factory=list, description="Validation results for each resource"
    )
    validation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the validation was performed",
    )
