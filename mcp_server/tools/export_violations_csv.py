# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""MCP tool for exporting violation data to CSV format."""

import csv
import io
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from ..services.compliance_service import ComplianceService
from ..services.policy_service import PolicyService

if TYPE_CHECKING:
    from ..services.multi_region_scanner import MultiRegionScanner

logger = logging.getLogger(__name__)

# Available columns for export
AVAILABLE_COLUMNS = [
    "resource_arn",
    "resource_id",
    "resource_type",
    "region",
    "violation_type",
    "tag_name",
    "severity",
    "current_value",
    "allowed_values",
    "cost_impact_monthly",
]

# Default columns if none specified
DEFAULT_COLUMNS = [
    "resource_arn",
    "resource_type",
    "violation_type",
    "tag_name",
    "severity",
    "region",
]


class ExportViolationsCsvResult(BaseModel):
    """Result from the export_violations_csv tool."""

    csv_data: str = Field(..., description="CSV formatted violation data")
    row_count: int = Field(0, description="Number of data rows (excluding header)")
    column_count: int = Field(0, description="Number of columns in the export")
    columns: list[str] = Field(
        default_factory=list, description="Column names in the CSV"
    )
    format: str = Field("csv", description="Output format (always 'csv')")
    filters_applied: dict = Field(
        default_factory=dict, description="Filters that were applied"
    )
    export_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the export was generated",
    )


async def export_violations_csv(
    compliance_service: ComplianceService,
    resource_types: list[str] | None = None,
    severity: str = "all",
    columns: list[str] | None = None,
    multi_region_scanner: "MultiRegionScanner | None" = None,
) -> ExportViolationsCsvResult:
    """
    Export violation data to CSV format for external analysis.

    Runs a compliance scan and formats the violations as CSV data
    suitable for import into spreadsheets or data analysis tools.

    Args:
        compliance_service: ComplianceService for running compliance scans
        resource_types: Resource types to include. Default: ["all"]
        severity: Filter by severity: "all", "errors_only", or "warnings_only".
            Default: "all"
        columns: Which columns to include in the CSV.
            Default: resource_arn, resource_type, violation_type, tag_name, severity, region
            Available: resource_arn, resource_id, resource_type, region,
                      violation_type, tag_name, severity, current_value,
                      allowed_values, cost_impact_monthly
        multi_region_scanner: Optional MultiRegionScanner for multi-region support

    Returns:
        ExportViolationsCsvResult containing:
        - csv_data: The CSV content as a string
        - row_count: Number of violation rows
        - column_count: Number of columns
        - columns: Column headers used
        - filters_applied: Which filters were active
        - export_timestamp: When the export was generated

    Raises:
        ValueError: If invalid columns are specified

    Example:
        >>> result = await export_violations_csv(
        ...     compliance_service=service,
        ...     resource_types=["ec2:instance"],
        ...     severity="errors_only",
        ... )
        >>> print(result.csv_data)
        >>> print(f"Exported {result.row_count} violations")
    """
    if resource_types is None:
        resource_types = ["all"]

    # Validate columns
    if columns:
        invalid_cols = [c for c in columns if c not in AVAILABLE_COLUMNS]
        if invalid_cols:
            raise ValueError(
                f"Invalid columns: {invalid_cols}. "
                f"Available columns: {AVAILABLE_COLUMNS}"
            )
    else:
        columns = DEFAULT_COLUMNS

    # Validate severity
    valid_severities = {"all", "errors_only", "warnings_only"}
    if severity not in valid_severities:
        raise ValueError(
            f"Invalid severity '{severity}'. Must be one of: {valid_severities}"
        )

    logger.info(
        f"Exporting violations to CSV: resource_types={resource_types}, "
        f"severity={severity}, columns={columns}"
    )

    # Run compliance scan to get violations
    if multi_region_scanner and multi_region_scanner.multi_region_enabled:
        result = await multi_region_scanner.scan_all_regions(
            resource_types=resource_types,
            severity=severity,
        )
    else:
        result = await compliance_service.check_compliance(
            resource_types=resource_types,
            severity=severity,
        )

    # Build CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()

    row_count = 0
    for violation in result.violations:
        row = {
            "resource_arn": getattr(violation, "resource_arn", ""),
            "resource_id": violation.resource_id,
            "resource_type": violation.resource_type,
            "region": violation.region,
            "violation_type": violation.violation_type.value,
            "tag_name": violation.tag_name,
            "severity": violation.severity.value,
            "current_value": violation.current_value or "",
            "allowed_values": (
                "; ".join(violation.allowed_values) if violation.allowed_values else ""
            ),
            "cost_impact_monthly": (
                f"{violation.cost_impact_monthly:.2f}"
                if violation.cost_impact_monthly
                else "0.00"
            ),
        }
        writer.writerow(row)
        row_count += 1

    csv_data = output.getvalue()
    output.close()

    filters_applied = {
        "resource_types": resource_types,
        "severity": severity,
    }

    logger.info(f"CSV export complete: {row_count} rows, {len(columns)} columns")

    return ExportViolationsCsvResult(
        csv_data=csv_data,
        row_count=row_count,
        column_count=len(columns),
        columns=columns,
        filters_applied=filters_applied,
    )
