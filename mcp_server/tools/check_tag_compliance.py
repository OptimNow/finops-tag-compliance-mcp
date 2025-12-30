"""MCP tool for checking tag compliance."""

import logging
from typing import Optional

from ..models.compliance import ComplianceResult
from ..services.compliance_service import ComplianceService

logger = logging.getLogger(__name__)


async def check_tag_compliance(
    compliance_service: ComplianceService,
    resource_types: list[str],
    filters: Optional[dict] = None,
    severity: str = "all"
) -> ComplianceResult:
    """
    Check tag compliance for AWS resources.
    
    This tool scans specified AWS resource types and validates them against
    the organization's tagging policy. It returns a compliance score along
    with detailed violation information.
    
    Args:
        compliance_service: ComplianceService instance for performing checks
        resource_types: List of resource types to check (e.g., ["ec2:instance", "rds:db"])
                       Supported types: ec2:instance, rds:db, s3:bucket, 
                       lambda:function, ecs:service
        filters: Optional filters for narrowing the scan:
                - region: AWS region(s) to scan (string or list)
                - account_id: AWS account ID(s) to scan (string or list)
        severity: Filter results by severity level:
                 - "all" (default): Return all violations
                 - "errors_only": Return only error-level violations
                 - "warnings_only": Return only warning-level violations
    
    Returns:
        ComplianceResult containing:
        - compliance_score: Percentage of compliant resources (0.0 to 1.0)
        - total_resources: Total number of resources scanned
        - compliant_resources: Number of resources meeting all requirements
        - violations: List of detailed violation information
        - cost_attribution_gap: Dollar amount of unattributable spend
        - scan_timestamp: When the scan was performed
    
    Raises:
        ValueError: If resource_types is empty or contains invalid types
        
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
    
    Example:
        >>> result = await check_tag_compliance(
        ...     compliance_service=service,
        ...     resource_types=["ec2:instance", "rds:db"],
        ...     filters={"region": "us-east-1"},
        ...     severity="errors_only"
        ... )
        >>> print(f"Compliance: {result.compliance_score * 100:.1f}%")
    """
    # Validate inputs
    if not resource_types:
        raise ValueError("resource_types cannot be empty")
    
    # Validate resource types
    valid_types = {
        "ec2:instance",
        "rds:db",
        "s3:bucket",
        "lambda:function",
        "ecs:service"
    }
    
    invalid_types = [rt for rt in resource_types if rt not in valid_types]
    if invalid_types:
        raise ValueError(
            f"Invalid resource types: {invalid_types}. "
            f"Valid types are: {sorted(valid_types)}"
        )
    
    # Validate severity parameter
    valid_severities = {"all", "errors_only", "warnings_only"}
    if severity not in valid_severities:
        raise ValueError(
            f"Invalid severity: {severity}. "
            f"Valid values are: {sorted(valid_severities)}"
        )
    
    logger.info(
        f"Checking tag compliance for resource_types={resource_types}, "
        f"filters={filters}, severity={severity}"
    )
    
    # Call the compliance service
    result = await compliance_service.check_compliance(
        resource_types=resource_types,
        filters=filters,
        severity=severity
    )
    
    logger.info(
        f"Compliance check complete: score={result.compliance_score:.2%}, "
        f"total={result.total_resources}, violations={len(result.violations)}"
    )
    
    return result
