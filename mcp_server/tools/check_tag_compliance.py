# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for checking tag compliance."""

import logging

from ..models.compliance import ComplianceResult
from ..services.compliance_service import ComplianceService
from ..services.history_service import HistoryService
from ..utils.resource_utils import get_supported_resource_types

logger = logging.getLogger(__name__)


async def check_tag_compliance(
    compliance_service: ComplianceService,
    resource_types: list[str],
    filters: dict | None = None,
    severity: str = "all",
    history_service: HistoryService | None = None,
    store_snapshot: bool = False,
    force_refresh: bool = False,
) -> ComplianceResult:
    """
    Check tag compliance for AWS resources.

    This tool scans specified AWS resource types and validates them against
    the organization's tagging policy. It returns a compliance score along
    with detailed violation information.

    By default, results are NOT stored in the history database. Set
    store_snapshot=True to explicitly store the result for trend tracking.
    This prevents ad-hoc queries (e.g., "check EC2 only") from polluting
    the historical data with partial scans.

    Args:
        compliance_service: ComplianceService instance for performing checks
        resource_types: List of resource types to check (e.g., ["ec2:instance", "rds:db"])
                       Supported types: ec2:instance, rds:db, s3:bucket,
                       lambda:function, ecs:service, opensearch:domain
                       Special value: ["all"] - scan ALL taggable resources (50+ types)
                       using AWS Resource Groups Tagging API
        filters: Optional filters for narrowing the scan:
                - region: AWS region(s) to scan (string or list)
                - account_id: AWS account ID(s) to scan (string or list)
        severity: Filter results by severity level:
                 - "all" (default): Return all violations
                 - "errors_only": Return only error-level violations
                 - "warnings_only": Return only warning-level violations
        history_service: Optional HistoryService for storing scan results
        store_snapshot: If True, store the result in history database for
                       trend tracking. Defaults to False to prevent partial
                       scans from affecting historical averages.
        force_refresh: If True, bypass cache and force a fresh scan from AWS.
                      Useful when you need real-time data or suspect cache is stale.

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

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 17.3, 17.7

    Example:
        >>> # Ad-hoc check (not stored in history)
        >>> result = await check_tag_compliance(
        ...     compliance_service=service,
        ...     resource_types=["ec2:instance"],
        ...     filters={"region": "us-east-1"},
        ... )
        >>>
        >>> # Full compliance snapshot (stored in history)
        >>> result = await check_tag_compliance(
        ...     compliance_service=service,
        ...     resource_types=["ec2:instance", "rds:db", "s3:bucket"],
        ...     store_snapshot=True
        ... )
        >>>
        >>> # Scan ALL taggable resources (50+ types)
        >>> result = await check_tag_compliance(
        ...     compliance_service=service,
        ...     resource_types=["all"],
        ...     store_snapshot=True
        ... )
        >>> print(f"Compliance: {result.compliance_score * 100:.1f}%")
    """
    # Validate inputs
    if not resource_types:
        raise ValueError("resource_types cannot be empty")

    # Check for "all" special value
    use_tagging_api = "all" in resource_types

    # Validate resource types (unless using "all")
    if not use_tagging_api:
        valid_types = set(get_supported_resource_types())
        invalid_types = [rt for rt in resource_types if rt not in valid_types]
        if invalid_types:
            raise ValueError(
                f"Invalid resource types: {invalid_types}. "
                f"Valid types are: {sorted(valid_types)} or use ['all'] for comprehensive scan."
            )

    # Validate severity parameter
    valid_severities = {"all", "errors_only", "warnings_only"}
    if severity not in valid_severities:
        raise ValueError(
            f"Invalid severity: {severity}. " f"Valid values are: {sorted(valid_severities)}"
        )

    logger.info(
        f"Checking tag compliance for resource_types={resource_types}, "
        f"filters={filters}, severity={severity}"
    )

    # Call the compliance service
    result = await compliance_service.check_compliance(
        resource_types=resource_types,
        filters=filters,
        severity=severity,
        force_refresh=force_refresh,
    )

    logger.info(
        f"Compliance check complete: score={result.compliance_score:.2%}, "
        f"total={result.total_resources}, violations={len(result.violations)}"
    )

    # Store the result in history database only if explicitly requested
    if store_snapshot and history_service:
        try:
            await history_service.store_scan_result(result)
            logger.info(
                f"Stored compliance snapshot in history database: "
                f"score={result.compliance_score:.2%}, timestamp={result.scan_timestamp}"
            )
        except Exception as e:
            # Log the error but don't fail the compliance check
            logger.warning(
                f"Failed to store compliance result in history database: {e}. "
                f"Compliance check succeeded but history tracking may be incomplete."
            )
    elif not store_snapshot:
        logger.debug(
            "Compliance check complete (not stored in history). "
            "Set store_snapshot=True to record this result for trend tracking."
        )

    return result
