# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for generating compliance reports."""

import logging

from ..models.compliance import ComplianceResult
from ..models.report import ComplianceReport, ReportFormat
from ..services.report_service import ReportService

logger = logging.getLogger(__name__)


class GenerateComplianceReportResult:
    """Result from the generate_compliance_report tool."""
    
    def __init__(
        self,
        report: ComplianceReport,
        formatted_output: str,
        format: ReportFormat
    ):
        self.report = report
        self.formatted_output = formatted_output
        self.format = format
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "format": self.format.value,
            "formatted_output": self.formatted_output,
            "summary": {
                "overall_compliance_score": self.report.overall_compliance_score,
                "total_resources": self.report.total_resources,
                "compliant_resources": self.report.compliant_resources,
                "non_compliant_resources": self.report.non_compliant_resources,
                "total_violations": self.report.total_violations,
                "cost_attribution_gap": self.report.cost_attribution_gap,
            },
            "report_timestamp": self.report.report_timestamp.isoformat(),
            "scan_timestamp": self.report.scan_timestamp.isoformat(),
        }


async def generate_compliance_report(
    compliance_result: ComplianceResult,
    format: str = "json",
    include_recommendations: bool = True,
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
        >>> print(f"Compliance score: {result.report.overall_compliance_score:.1%}")
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
    
    # Initialize report service
    report_service = ReportService()
    
    # Generate the report
    report = report_service.generate_report(
        compliance_result=compliance_result,
        include_recommendations=include_recommendations
    )
    
    # Format the report
    formatted_output = report_service.format_report(
        report=report,
        format=report_format
    )
    
    logger.info(
        f"Report generated successfully: {report.total_violations} violations, "
        f"{len(report.recommendations)} recommendations"
    )
    
    return GenerateComplianceReportResult(
        report=report,
        formatted_output=formatted_output,
        format=report_format
    )
