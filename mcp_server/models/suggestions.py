# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Tag suggestion data model."""

from pydantic import BaseModel, ConfigDict, Field


class TagSuggestion(BaseModel):
    """Represents a suggested tag value for a resource."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tag_key": "Environment",
                "suggested_value": "production",
                "confidence": 0.85,
                "reasoning": "Resource is in the production VPC (vpc-prod-12345) and follows production naming convention",
            }
        }
    )

    tag_key: str = Field(..., description="Name of the tag to suggest")
    suggested_value: str = Field(..., description="Suggested value for the tag")
    confidence: float = Field(
        ...,
        description="Confidence score for this suggestion (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    reasoning: str = Field(
        ..., description="Explanation of why this value is suggested", min_length=1
    )
