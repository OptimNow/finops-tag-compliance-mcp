# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Report generation service."""

import csv
import io
import json
import logging
from collections import defaultdict

from ..models.compliance import ComplianceResult
from ..models.report import (
    ComplianceRecommendation,
    ComplianceReport,
    ReportFormat,
    ViolationRanking,
)

logger = logging.getLogger(__name__)


class ReportService:
    """
    Service for generating compliance reports in various formats.

    Transforms ComplianceResult data into formatted reports with:
    - Compliance summary statistics
    - Top violations ranked by count and cost
    - Actionable recommendations (optional)
    - Multiple output formats (JSON, CSV, Markdown)
    """

    def __init__(self):
        """Initialize report service."""
        pass

    def generate_report(
        self, compliance_result: ComplianceResult, include_recommendations: bool = True
    ) -> ComplianceReport:
        """
        Generate a comprehensive compliance report from compliance results.

        Args:
            compliance_result: ComplianceResult from a compliance scan
            include_recommendations: Whether to include actionable recommendations

        Returns:
            ComplianceReport with summary, rankings, and recommendations

        Requirements: 7.1, 7.3, 7.4, 7.5
        """
        logger.info(
            f"Generating compliance report for {compliance_result.total_resources} resources"
        )

        # Calculate summary statistics
        non_compliant_resources = (
            compliance_result.total_resources - compliance_result.compliant_resources
        )
        total_violations = len(compliance_result.violations)

        # Rank violations by count and cost
        top_by_count = self._rank_violations_by_count(compliance_result.violations)
        top_by_cost = self._rank_violations_by_cost(compliance_result.violations)

        # Generate recommendations if requested
        recommendations = []
        if include_recommendations:
            recommendations = self._generate_recommendations(
                compliance_result, top_by_count, top_by_cost
            )

        report = ComplianceReport(
            overall_compliance_score=compliance_result.compliance_score,
            total_resources=compliance_result.total_resources,
            compliant_resources=compliance_result.compliant_resources,
            non_compliant_resources=non_compliant_resources,
            total_violations=total_violations,
            cost_attribution_gap=compliance_result.cost_attribution_gap,
            top_violations_by_count=top_by_count,
            top_violations_by_cost=top_by_cost,
            recommendations=recommendations,
            scan_timestamp=compliance_result.scan_timestamp,
        )

        logger.info(f"Report generated with {len(recommendations)} recommendations")
        return report

    def _rank_violations_by_count(
        self, violations: list, top_n: int = 10
    ) -> list[ViolationRanking]:
        """
        Rank violations by occurrence count.

        Groups violations by tag name and counts occurrences.

        Args:
            violations: List of Violation objects
            top_n: Number of top violations to return

        Returns:
            List of ViolationRanking objects sorted by count (descending)

        Requirements: 7.4 - Rank violations by count
        """
        # Group violations by tag name
        violation_groups = defaultdict(lambda: {"count": 0, "cost": 0.0, "resource_types": set()})

        for violation in violations:
            tag_name = violation.tag_name
            violation_groups[tag_name]["count"] += 1
            violation_groups[tag_name]["cost"] += violation.cost_impact_monthly
            violation_groups[tag_name]["resource_types"].add(violation.resource_type)

        # Convert to ViolationRanking objects
        rankings = []
        for tag_name, data in violation_groups.items():
            rankings.append(
                ViolationRanking(
                    tag_name=tag_name,
                    violation_count=data["count"],
                    total_cost_impact=data["cost"],
                    affected_resource_types=sorted(data["resource_types"]),
                )
            )

        # Sort by count (descending) and return top N
        rankings.sort(key=lambda x: x.violation_count, reverse=True)
        return rankings[:top_n]

    def _rank_violations_by_cost(self, violations: list, top_n: int = 10) -> list[ViolationRanking]:
        """
        Rank violations by cost impact.

        Groups violations by tag name and sums cost impacts.

        Args:
            violations: List of Violation objects
            top_n: Number of top violations to return

        Returns:
            List of ViolationRanking objects sorted by cost (descending)

        Requirements: 7.4 - Rank violations by cost impact
        """
        # Group violations by tag name
        violation_groups = defaultdict(lambda: {"count": 0, "cost": 0.0, "resource_types": set()})

        for violation in violations:
            tag_name = violation.tag_name
            violation_groups[tag_name]["count"] += 1
            violation_groups[tag_name]["cost"] += violation.cost_impact_monthly
            violation_groups[tag_name]["resource_types"].add(violation.resource_type)

        # Convert to ViolationRanking objects
        rankings = []
        for tag_name, data in violation_groups.items():
            rankings.append(
                ViolationRanking(
                    tag_name=tag_name,
                    violation_count=data["count"],
                    total_cost_impact=data["cost"],
                    affected_resource_types=sorted(data["resource_types"]),
                )
            )

        # Sort by cost (descending) and return top N
        rankings.sort(key=lambda x: x.total_cost_impact, reverse=True)
        return rankings[:top_n]

    def _generate_recommendations(
        self,
        compliance_result: ComplianceResult,
        top_by_count: list[ViolationRanking],
        top_by_cost: list[ViolationRanking],
    ) -> list[ComplianceRecommendation]:
        """
        Generate actionable recommendations based on compliance results.

        Analyzes violation patterns and generates prioritized recommendations
        for improving compliance.

        Args:
            compliance_result: ComplianceResult from scan
            top_by_count: Top violations by count
            top_by_cost: Top violations by cost

        Returns:
            List of ComplianceRecommendation objects

        Requirements: 7.3 - Include actionable remediation suggestions
        """
        recommendations = []

        # Recommendation 1: Address highest-cost violations first
        if top_by_cost and top_by_cost[0].total_cost_impact > 1000:
            top_cost_violation = top_by_cost[0]
            recommendations.append(
                ComplianceRecommendation(
                    priority="high",
                    title=f"Address missing '{top_cost_violation.tag_name}' tags",
                    description=(
                        f"The '{top_cost_violation.tag_name}' tag has the highest cost impact "
                        f"(${top_cost_violation.total_cost_impact:.2f}/month). "
                        f"Tagging these {top_cost_violation.violation_count} resources will "
                        f"significantly improve cost attribution."
                    ),
                    estimated_impact=f"${top_cost_violation.total_cost_impact:.2f}/month in attributable spend",
                    affected_resources=top_cost_violation.violation_count,
                )
            )

        # Recommendation 2: Address most common violations
        if top_by_count and top_by_count[0].violation_count > 10:
            top_count_violation = top_by_count[0]
            recommendations.append(
                ComplianceRecommendation(
                    priority="high",
                    title=f"Fix widespread '{top_count_violation.tag_name}' violations",
                    description=(
                        f"The '{top_count_violation.tag_name}' tag is missing on "
                        f"{top_count_violation.violation_count} resources. "
                        f"This is the most common violation and should be addressed systematically."
                    ),
                    estimated_impact=f"{top_count_violation.violation_count} resources become compliant",
                    affected_resources=top_count_violation.violation_count,
                )
            )

        # Recommendation 3: Low compliance score warning
        if compliance_result.compliance_score < 0.5:
            recommendations.append(
                ComplianceRecommendation(
                    priority="high",
                    title="Implement automated tagging policies",
                    description=(
                        f"Your compliance score is {compliance_result.compliance_score:.1%}, "
                        f"indicating systemic tagging issues. Consider implementing automated "
                        f"tagging via AWS Config rules, Lambda functions, or infrastructure-as-code "
                        f"to enforce tagging at resource creation time."
                    ),
                    estimated_impact="Prevent future violations and improve compliance to >80%",
                    affected_resources=compliance_result.total_resources,
                )
            )

        # Recommendation 4: Focus on specific resource types
        if top_by_count:
            # Find resource type with most violations
            resource_type_violations = defaultdict(int)
            for violation in compliance_result.violations:
                resource_type_violations[violation.resource_type] += 1

            if resource_type_violations:
                worst_resource_type = max(resource_type_violations.items(), key=lambda x: x[1])
                resource_type, count = worst_resource_type

                if count > 5:
                    recommendations.append(
                        ComplianceRecommendation(
                            priority="medium",
                            title=f"Focus tagging efforts on {resource_type} resources",
                            description=(
                                f"{resource_type} resources have {count} violations, "
                                f"the highest of any resource type. Consider creating a "
                                f"tagging campaign specifically for this resource type."
                            ),
                            estimated_impact=f"{count} violations resolved",
                            affected_resources=count,
                        )
                    )

        # Recommendation 5: Cost attribution gap
        if compliance_result.cost_attribution_gap > 5000:
            recommendations.append(
                ComplianceRecommendation(
                    priority="high",
                    title="Reduce cost attribution gap",
                    description=(
                        f"${compliance_result.cost_attribution_gap:.2f}/month in cloud spend "
                        f"cannot be attributed to teams or projects due to missing tags. "
                        f"This makes accurate chargebacks and cost optimization difficult."
                    ),
                    estimated_impact=f"${compliance_result.cost_attribution_gap:.2f}/month becomes attributable",
                    affected_resources=compliance_result.total_resources
                    - compliance_result.compliant_resources,
                )
            )
        elif compliance_result.cost_attribution_gap > 1000:
            recommendations.append(
                ComplianceRecommendation(
                    priority="medium",
                    title="Improve cost attribution",
                    description=(
                        f"${compliance_result.cost_attribution_gap:.2f}/month in cloud spend "
                        f"lacks proper tagging. Focus on high-cost resources first to maximize impact."
                    ),
                    estimated_impact=f"${compliance_result.cost_attribution_gap:.2f}/month becomes attributable",
                    affected_resources=compliance_result.total_resources
                    - compliance_result.compliant_resources,
                )
            )

        # Recommendation 6: Good compliance - maintain it
        if compliance_result.compliance_score >= 0.9:
            recommendations.append(
                ComplianceRecommendation(
                    priority="low",
                    title="Maintain excellent compliance",
                    description=(
                        f"Your compliance score of {compliance_result.compliance_score:.1%} is excellent. "
                        f"Continue monitoring and address the remaining "
                        f"{compliance_result.total_resources - compliance_result.compliant_resources} "
                        f"non-compliant resources to achieve 100% compliance."
                    ),
                    estimated_impact="Achieve perfect compliance",
                    affected_resources=compliance_result.total_resources
                    - compliance_result.compliant_resources,
                )
            )

        return recommendations

    def format_report(self, report: ComplianceReport, format: ReportFormat) -> str:
        """
        Format a compliance report in the specified output format.

        Args:
            report: ComplianceReport to format
            format: Output format (JSON, CSV, or Markdown)

        Returns:
            Formatted report as a string

        Requirements: 7.2 - Support JSON, CSV, and Markdown output formats
        """
        if format == ReportFormat.JSON:
            return self._format_as_json(report)
        elif format == ReportFormat.CSV:
            return self._format_as_csv(report)
        elif format == ReportFormat.MARKDOWN:
            return self._format_as_markdown(report)
        else:
            raise ValueError(f"Unsupported report format: {format}")

    def _format_as_json(self, report: ComplianceReport) -> str:
        """
        Format report as JSON.

        Args:
            report: ComplianceReport to format

        Returns:
            JSON string
        """
        # Use Pydantic's model_dump with mode='json' for proper serialization
        report_dict = report.model_dump(mode="json")
        return json.dumps(report_dict, indent=2)

    def _format_as_csv(self, report: ComplianceReport) -> str:
        """
        Format report as CSV.

        Creates multiple CSV sections:
        1. Summary statistics
        2. Top violations by count
        3. Top violations by cost
        4. Recommendations (if present)

        Args:
            report: ComplianceReport to format

        Returns:
            CSV string
        """
        output = io.StringIO()
        writer = csv.writer(output)

        # Summary section
        writer.writerow(["Compliance Summary"])
        writer.writerow(["Metric", "Value"])
        writer.writerow(["Overall Compliance Score", f"{report.overall_compliance_score:.2%}"])
        writer.writerow(["Total Resources", report.total_resources])
        writer.writerow(["Compliant Resources", report.compliant_resources])
        writer.writerow(["Non-Compliant Resources", report.non_compliant_resources])
        writer.writerow(["Total Violations", report.total_violations])
        writer.writerow(["Cost Attribution Gap", f"${report.cost_attribution_gap:.2f}"])
        writer.writerow([])

        # Top violations by count
        writer.writerow(["Top Violations by Count"])
        writer.writerow(["Tag Name", "Violation Count", "Cost Impact", "Affected Resource Types"])
        for ranking in report.top_violations_by_count:
            writer.writerow(
                [
                    ranking.tag_name,
                    ranking.violation_count,
                    f"${ranking.total_cost_impact:.2f}",
                    ", ".join(ranking.affected_resource_types),
                ]
            )
        writer.writerow([])

        # Top violations by cost
        writer.writerow(["Top Violations by Cost"])
        writer.writerow(["Tag Name", "Cost Impact", "Violation Count", "Affected Resource Types"])
        for ranking in report.top_violations_by_cost:
            writer.writerow(
                [
                    ranking.tag_name,
                    f"${ranking.total_cost_impact:.2f}",
                    ranking.violation_count,
                    ", ".join(ranking.affected_resource_types),
                ]
            )
        writer.writerow([])

        # Recommendations
        if report.recommendations:
            writer.writerow(["Recommendations"])
            writer.writerow(
                ["Priority", "Title", "Description", "Estimated Impact", "Affected Resources"]
            )
            for rec in report.recommendations:
                writer.writerow(
                    [
                        rec.priority,
                        rec.title,
                        rec.description,
                        rec.estimated_impact,
                        rec.affected_resources,
                    ]
                )

        return output.getvalue()

    def _format_as_markdown(self, report: ComplianceReport) -> str:
        """
        Format report as Markdown.

        Creates a well-structured Markdown document with:
        - Summary section with key metrics
        - Top violations tables
        - Recommendations section

        Args:
            report: ComplianceReport to format

        Returns:
            Markdown string
        """
        lines = []

        # Title
        lines.append("# Tag Compliance Report")
        lines.append("")
        lines.append(f"**Generated:** {report.report_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"**Scan Date:** {report.scan_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append("")

        # Summary section
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Overall Compliance Score:** {report.overall_compliance_score:.1%}")
        lines.append(f"- **Total Resources:** {report.total_resources}")
        lines.append(f"- **Compliant Resources:** {report.compliant_resources}")
        lines.append(f"- **Non-Compliant Resources:** {report.non_compliant_resources}")
        lines.append(f"- **Total Violations:** {report.total_violations}")
        lines.append(f"- **Cost Attribution Gap:** ${report.cost_attribution_gap:,.2f}/month")
        lines.append("")

        # Top violations by count
        if report.top_violations_by_count:
            lines.append("## Top Violations by Count")
            lines.append("")
            lines.append("| Tag Name | Violation Count | Cost Impact | Affected Resource Types |")
            lines.append("|----------|----------------|-------------|------------------------|")
            for ranking in report.top_violations_by_count:
                resource_types = ", ".join(ranking.affected_resource_types)
                lines.append(
                    f"| {ranking.tag_name} | {ranking.violation_count} | "
                    f"${ranking.total_cost_impact:,.2f} | {resource_types} |"
                )
            lines.append("")

        # Top violations by cost
        if report.top_violations_by_cost:
            lines.append("## Top Violations by Cost Impact")
            lines.append("")
            lines.append("| Tag Name | Cost Impact | Violation Count | Affected Resource Types |")
            lines.append("|----------|-------------|----------------|------------------------|")
            for ranking in report.top_violations_by_cost:
                resource_types = ", ".join(ranking.affected_resource_types)
                lines.append(
                    f"| {ranking.tag_name} | ${ranking.total_cost_impact:,.2f} | "
                    f"{ranking.violation_count} | {resource_types} |"
                )
            lines.append("")

        # Recommendations
        if report.recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for i, rec in enumerate(report.recommendations, 1):
                lines.append(f"### {i}. {rec.title}")
                lines.append("")
                lines.append(f"**Priority:** {rec.priority.upper()}")
                lines.append("")
                lines.append(rec.description)
                lines.append("")
                lines.append(f"**Estimated Impact:** {rec.estimated_impact}")
                lines.append("")
                lines.append(f"**Affected Resources:** {rec.affected_resources}")
                lines.append("")

        return "\n".join(lines)
