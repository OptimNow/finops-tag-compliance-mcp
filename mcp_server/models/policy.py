# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Tagging policy data models."""

from datetime import datetime, UTC

from pydantic import BaseModel, ConfigDict, Field


class TagNamingRules(BaseModel):
    """Rules for tag naming conventions."""

    case_sensitivity: bool = Field(
        False, description="Whether tag names are case-sensitive"
    )
    allow_special_characters: bool = Field(
        False, description="Whether special characters are allowed in tag names"
    )
    max_key_length: int = Field(
        128, description="Maximum length for tag keys", ge=1, le=256
    )
    max_value_length: int = Field(
        256, description="Maximum length for tag values", ge=1, le=512
    )


class RequiredTag(BaseModel):
    """Definition of a required tag in the policy."""

    name: str = Field(..., description="Name of the required tag")
    description: str = Field(..., description="Description of what this tag is for")
    allowed_values: list[str] | None = Field(
        None, description="List of allowed values (if restricted)"
    )
    validation_regex: str | None = Field(
        None, description="Regex pattern for validating tag values (if applicable)"
    )
    applies_to: list[str] = Field(
        ..., description="List of resource types this tag applies to (e.g., ['ec2:instance', 'rds:db'])"
    )


class OptionalTag(BaseModel):
    """Definition of an optional tag in the policy."""

    name: str = Field(..., description="Name of the optional tag")
    description: str = Field(..., description="Description of what this tag is for")
    allowed_values: list[str] | None = Field(
        None, description="List of allowed values (if restricted)"
    )


class TagPolicy(BaseModel):
    """Complete tagging policy configuration."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": "1.0",
                "last_updated": "2025-12-29T22:00:00Z",
                "required_tags": [
                    {
                        "name": "CostCenter",
                        "description": "Department for cost allocation",
                        "allowed_values": ["Engineering", "Marketing", "Sales"],
                        "validation_regex": None,
                        "applies_to": ["ec2:instance", "rds:db", "s3:bucket"],
                    }
                ],
                "optional_tags": [
                    {
                        "name": "Project",
                        "description": "Project name",
                        "allowed_values": None,
                    }
                ],
                "tag_naming_rules": {
                    "case_sensitivity": False,
                    "allow_special_characters": False,
                    "max_key_length": 128,
                    "max_value_length": 256,
                },
            }
        }
    )

    version: str = Field(..., description="Version of the policy")
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when policy was last updated",
    )
    required_tags: list[RequiredTag] = Field(
        default_factory=list, description="List of required tags"
    )
    optional_tags: list[OptionalTag] = Field(
        default_factory=list, description="List of optional tags"
    )
    tag_naming_rules: TagNamingRules = Field(
        default_factory=TagNamingRules, description="Rules for tag naming conventions"
    )
