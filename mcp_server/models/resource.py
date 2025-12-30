"""AWS resource data model."""

from datetime import datetime
from pydantic import BaseModel, Field


class Resource(BaseModel):
    """Represents an AWS resource with its tags."""
    
    resource_id: str = Field(..., description="AWS resource identifier (ARN or ID)")
    resource_type: str = Field(..., description="Type of AWS resource (e.g., ec2:instance)")
    region: str = Field(..., description="AWS region where the resource is located")
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Tags associated with the resource"
    )
    created_at: datetime | None = Field(
        None,
        description="When the resource was created"
    )
    arn: str | None = Field(
        None,
        description="Full ARN of the resource"
    )
