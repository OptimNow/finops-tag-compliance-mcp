"""Compliance result data model."""

from datetime import datetime, UTC

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .violations import Violation


class ComplianceResult(BaseModel):
    """Represents the result of a compliance check."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "compliance_score": 0.75,
                "total_resources": 100,
                "compliant_resources": 75,
                "violations": [],
                "cost_attribution_gap": 5000.00,
                "scan_timestamp": "2025-12-29T22:00:00Z",
            }
        }
    )

    compliance_score: float = Field(
        ...,
        description="Compliance score as a ratio (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    total_resources: int = Field(
        ..., description="Total number of resources scanned", ge=0
    )
    compliant_resources: int = Field(
        ..., description="Number of resources that are compliant", ge=0
    )
    violations: list[Violation] = Field(
        default_factory=list, description="List of violations found"
    )
    cost_attribution_gap: float = Field(
        0.0,
        description="Total monthly cost that cannot be attributed due to missing tags",
        ge=0.0,
    )
    scan_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the scan was performed",
    )

    @field_validator("compliant_resources")
    @classmethod
    def validate_compliant_count(cls, v: int, info) -> int:
        """Ensure compliant resources doesn't exceed total resources."""
        if "total_resources" in info.data and v > info.data["total_resources"]:
            raise ValueError("compliant_resources cannot exceed total_resources")
        return v
