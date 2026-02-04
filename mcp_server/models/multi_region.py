# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Multi-region scanning data models.

This module contains Pydantic models for multi-region scanning functionality,
including regional scan results, metadata, and aggregated compliance results.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from .violations import Violation


# Resource types that are global (not region-specific)
GLOBAL_RESOURCE_TYPES: frozenset[str] = frozenset([
    "s3:bucket",           # S3 buckets are global
    "iam:role",            # IAM is global
    "iam:user",            # IAM is global
    "iam:policy",          # IAM is global
    "route53:hostedzone",  # Route 53 is global
    "cloudfront:distribution",  # CloudFront is global
])

# Resource types that are regional
REGIONAL_RESOURCE_TYPES: frozenset[str] = frozenset([
    "ec2:instance",
    "ec2:volume",
    "ec2:snapshot",
    "ec2:elastic-ip",
    "ec2:natgateway",
    "rds:db",
    "lambda:function",
    "ecs:service",
    "ecs:cluster",
    "eks:cluster",
    "opensearch:domain",
    "dynamodb:table",
    "elasticache:cluster",
    "sqs:queue",
    "sns:topic",
    "kinesis:stream",
])


class RegionalSummary(BaseModel):
    """Summary of compliance for a single region.
    
    Provides a high-level overview of tag compliance status for resources
    in a specific AWS region.
    """
    
    region: str = Field(..., description="AWS region code")
    total_resources: int = Field(..., ge=0, description="Total resources in this region")
    compliant_resources: int = Field(..., ge=0, description="Compliant resources in this region")
    compliance_score: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Compliance score for this region (0.0 to 1.0)"
    )
    violation_count: int = Field(..., ge=0, description="Number of violations in this region")
    cost_attribution_gap: float = Field(
        default=0.0, 
        ge=0.0, 
        description="Cost attribution gap for this region in USD"
    )


class RegionalScanResult(BaseModel):
    """Result from scanning a single region.
    
    Contains the detailed results of scanning resources in a specific AWS region,
    including success status, resources found, violations, and timing information.
    """
    
    region: str = Field(..., description="AWS region code")
    success: bool = Field(..., description="Whether the scan succeeded")
    resources: list[dict] = Field(
        default_factory=list, 
        description="Resources found in this region"
    )
    violations: list[Violation] = Field(
        default_factory=list, 
        description="Violations found in this region"
    )
    compliant_count: int = Field(
        default=0, 
        ge=0,
        description="Number of compliant resources"
    )
    error_message: str | None = Field(
        default=None, 
        description="Error message if scan failed"
    )
    scan_duration_ms: int = Field(
        default=0, 
        ge=0,
        description="Scan duration in milliseconds"
    )


class RegionScanMetadata(BaseModel):
    """Metadata about which regions were scanned.
    
    Provides information about the regions that were attempted during a
    multi-region scan, including which succeeded, failed, or were skipped.
    """
    
    total_regions: int = Field(..., ge=0, description="Total regions attempted")
    successful_regions: list[str] = Field(
        default_factory=list, 
        description="Regions scanned successfully"
    )
    failed_regions: list[str] = Field(
        default_factory=list, 
        description="Regions that failed to scan"
    )
    skipped_regions: list[str] = Field(
        default_factory=list, 
        description="Regions skipped (disabled/filtered)"
    )


class MultiRegionComplianceResult(BaseModel):
    """Aggregated compliance result from multi-region scanning.
    
    Combines compliance results from scanning resources across multiple AWS regions
    into a single unified result with overall metrics and per-region breakdowns.
    """
    
    compliance_score: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Overall compliance score across all regions"
    )
    total_resources: int = Field(
        ..., 
        ge=0, 
        description="Total resources across all regions"
    )
    compliant_resources: int = Field(
        ..., 
        ge=0, 
        description="Compliant resources across all regions"
    )
    violations: list[Violation] = Field(
        default_factory=list, 
        description="All violations from all regions"
    )
    cost_attribution_gap: float = Field(
        default=0.0, 
        ge=0.0, 
        description="Total cost attribution gap across all regions in USD"
    )
    scan_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the scan was performed"
    )
    
    # Multi-region specific fields
    region_metadata: RegionScanMetadata = Field(
        ..., 
        description="Metadata about which regions were scanned"
    )
    regional_breakdown: dict[str, RegionalSummary] = Field(
        default_factory=dict,
        description="Per-region compliance summary keyed by region code"
    )
