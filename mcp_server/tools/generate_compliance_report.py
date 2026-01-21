# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for generating compliance reports."""

import logging
from datetime import datetime

from pydantic import BaseModel, Field, computed_field

from typing import Optional

from ..models.compliance import ComplianceResult
from ..models.report import ComplianceReport, ReportFormat
from ..services.report_service import ReportService

logger = logging.getLogger(__name__)


class ReportSummary(BaseModel):
    """Summary statistics from a compliance report."""

    overall_compliance_score: float = Field(
        ..., description="Overall compliance score (0.0 to 1.0)"
    )
    total_resources: int = Field(..., description="Total resources scanned")
    compliant_resources: int = Field(..., description="Number of compliant resources")
    non_compliant_resources: int = Field(
        ..., description="Number of non-compliant resources"
    )
    total_violations: int = Field(..., description="Total number of violations")
    cost_attribution_gap: float = Field(
        ..., description="Dollar amount of unattributable spend"
    )


class GenerateComplianceReportResult(BaseModel):
    """Result from the generate_compliance_report tool."""

    format: str = Field(..., description="Output format used (json, csv, markdown)")
    formatted_output: str = Field(..., description="Complete formatted report string")
    summary: ReportSummary = Field(..., description="Quick summary with key metrics")
    report_timestamp: datetime = Field(..., description="When the report was generated")
    scan_timestamp: datetime = Field(..., description="When the scan was performed")

    @classmethod
    def from_report(
        cls,
        report: ComplianceReport,
        formatted_output: str,
        report_format: ReportFormat,
    ) -> "GenerateComplianceReportResult":
        """Create result from a ComplianceReport instance."""
        return cls(
            format=report_format.value,
            formatted_output=formatted_output,
            summary=ReportSummary(
                overall_compliance_score=report.overall_compliance_score,
                total_resources=report.total_resources,
                compliant_resources=report.compliant_resources,
                non_compliant_resources=report.non_compliant_resources,
                total_violations=report.total_violations,
                cost_attribution_gap=report.cost_attribution_gap,
            ),
            report_timestamp=report.report_timestamp,
            scan_timestamp=report.scan_timestamp,
        )


async def generate_compliance_report(
    compliance_result: ComplianceResult,
    format: str = "json",
    include_recommendations: bool = True,
    report_service: Optional[ReportService] = None,
) -> GenerateComplianceReportResult:
    """
    Generate a comprehensive compliance report in the specified format.

    This tool transforms compliance scan results into formatted reports with:
    - Overall compliance summary with key metrics
    - Top violations ranked by count and cost impact
    - Actionable recommendations for improving compliance (optional)
    - Multiple output formats: JSON, CSV, or Markdown

    Args:
        compliance_result: ComplianceResult from a compliance scan
        format: Output format - "json", "csv", or "markdown" (default: "json")
        include_recommendations: Whether to include actionable recommendations (default: True)
        report_service: Optional injected ReportService instance. If not provided, one
                       will be created internally.

    Returns:
        GenerateComplianceReportResult containing:
        - format: The output format used
        - formatted_output: The complete formatted report as a string
        - summary: Quick summary with key metrics
        - report_timestamp: When the report was generated
        - scan_timestamp: When the underlying scan was performed

    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5

    Example:
        >>> result = await generate_compliance_report(
        ...     compliance_result=scan_result,
        ...     format="markdown",
        ...     include_recommendations=True
        ... )
        >>> print(result.formatted_output)
        >>> print(f"Compliance score: {result.summary.overall_compliance_score:.1%}")
    """
    logger.info(
        f"Generating compliance report in {format} format "
        f"(recommendations: {include_recommendations})"
    )

    # Validate format parameter
    try:
        report_format = ReportFormat(format.lower())
    except ValueError:
        raise ValueError(
            f"Invalid format '{format}'. Must be one of: json, csv, markdown"
        )

    # Use injected service or create one
    service = report_service
    if service is None:
        service = ReportService()

    # Generate the report
    report = service.generate_report(
        compliance_result=compliance_result,
        include_recommendations=include_recommendations,
    )

    # Format the report
    formatted_output = service.format_report(report=report, format=report_format)

    logger.info(
        f"Report generated successfully: {report.total_violations} violations, "
        f"{len(report.recommendations)} recommendations"
    )

    return GenerateComplianceReportResult.from_report(
        report=report,
        formatted_output=formatted_output,
        report_format=report_format,
    )
