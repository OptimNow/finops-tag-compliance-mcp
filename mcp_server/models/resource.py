# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""AWS resource data model."""

from datetime import datetime
from pydantic import BaseModel, Field


class Resource(BaseModel):
    """Represents an AWS resource with its tags."""

    resource_id: str = Field(..., description="AWS resource identifier (ARN or ID)")
    resource_type: str = Field(..., description="Type of AWS resource (e.g., ec2:instance)")
    region: str = Field(..., description="AWS region where the resource is located")
    tags: dict[str, str] = Field(
        default_factory=dict, description="Tags associated with the resource"
    )
    created_at: datetime | None = Field(None, description="When the resource was created")
    arn: str | None = Field(None, description="Full ARN of the resource")
    instance_state: str | None = Field(
        None, description="Instance state (running, stopped, terminated, etc.) - EC2 only"
    )
    instance_type: str | None = Field(
        None, description="Instance type (t3.medium, m5.large, etc.) - EC2 only"
    )
