"""Unit tests for generate_compliance_report tool."""

import pytest
import json
from datetime import datetime, UTC

from mcp_server.tools.generate_compliance_report import (
    generate_compliance_report,
    GenerateComplianceReportResult,
)
from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.violations import Violation, ViolationType, Severity
from mcp_server.models.report import ReportFormat


@pytest.fixture
def sample_compliance_result():
    """Create a sample compliance result for testing."""
    # Create enough violations to trigger recommendations
    # Need > 10 violations for count-based recommendations
    # Need > $1000 cost for cost-based recommendations
    violations = []

    # Create 12 CostCenter violations with high cost
    for i in range(12):
        violations.append(
            Violation(
                resource_id=f"i-{i:016x}",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR,
                current_value=None,
                allowed_values=["Engineering", "Marketing", "Sales"],
                cost_impact_monthly=100.0,
            )
        )

    # Create 5 Owner violations with high cost
    for i in range(5):
        violations.append(
            Violation(
                resource_id=f"db-instance-{i}",
                resource_type="rds:db",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="Owner",
                severity=Severity.ERROR,
                current_value=None,
                allowed_values=None,
                cost_impact_monthly=250.0,
            )
        )

    total_cost_gap = sum(v.cost_impact_monthly for v in violations)

    return ComplianceResult(
        compliance_score=0.4,  # Lower score to trigger more recommendations
        total_resources=30,
        compliant_resources=13,
        violations=violations,
        cost_attribution_gap=total_cost_gap,
        scan_timestamp=datetime.now(UTC),
    )


class TestGenerateComplianceReportResult:
    """Test GenerateComplianceReportResult class."""

    def test_result_to_dict_structure(self, sample_compliance_result):
        """Test that result.to_dict() returns complete structure."""
        from mcp_server.services.report_service import ReportService

        report_service = ReportService()
        report = report_service.generate_report(
            sample_compliance_result, include_recommendations=True
        )
        formatted = report_service.format_report(report, ReportFormat.JSON)

        result = GenerateComplianceReportResult(
            report=report, formatted_output=formatted, format=ReportFormat.JSON
        )

        result_dict = result.to_dict()

        assert "format" in result_dict
        assert "formatted_output" in result_dict
        assert "summary" in result_dict
        assert "report_timestamp" in result_dict
        assert "scan_timestamp" in result_dict

    def test_result_to_dict_summary_fields(self, sample_compliance_result):
        """Test that summary contains all required fields."""
        from mcp_server.services.report_service import ReportService

        report_service = ReportService()
        report = report_service.generate_report(
            sample_compliance_result, include_recommendations=True
        )
        formatted = report_service.format_report(report, ReportFormat.JSON)

        result = GenerateComplianceReportResult(
            report=report, formatted_output=formatted, format=ReportFormat.JSON
        )

        result_dict = result.to_dict()
        summary = result_dict["summary"]

        assert "overall_compliance_score" in summary
        assert "total_resources" in summary
        assert "compliant_resources" in summary
        assert "non_compliant_resources" in summary
        assert "total_violations" in summary
        assert "cost_attribution_gap" in summary


class TestGenerateComplianceReportTool:
    """Test generate_compliance_report tool."""

    @pytest.mark.asyncio
    async def test_generate_report_json_format(self, sample_compliance_result):
        """Test generating report in JSON format."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json", include_recommendations=True
        )

        assert isinstance(result, GenerateComplianceReportResult)
        assert result.format == ReportFormat.JSON
        assert isinstance(result.formatted_output, str)

        # Verify it's valid JSON
        parsed = json.loads(result.formatted_output)
        assert "overall_compliance_score" in parsed

    @pytest.mark.asyncio
    async def test_generate_report_csv_format(self, sample_compliance_result):
        """Test generating report in CSV format."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="csv", include_recommendations=True
        )

        assert isinstance(result, GenerateComplianceReportResult)
        assert result.format == ReportFormat.CSV
        assert isinstance(result.formatted_output, str)
        assert "Compliance Summary" in result.formatted_output

    @pytest.mark.asyncio
    async def test_generate_report_markdown_format(self, sample_compliance_result):
        """Test generating report in Markdown format."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result,
            format="markdown",
            include_recommendations=True,
        )

        assert isinstance(result, GenerateComplianceReportResult)
        assert result.format == ReportFormat.MARKDOWN
        assert isinstance(result.formatted_output, str)
        assert "# Tag Compliance Report" in result.formatted_output

    @pytest.mark.asyncio
    async def test_generate_report_invalid_format(self, sample_compliance_result):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid format"):
            await generate_compliance_report(
                compliance_result=sample_compliance_result,
                format="xml",
                include_recommendations=True,
            )

    @pytest.mark.asyncio
    async def test_generate_report_with_recommendations(self, sample_compliance_result):
        """Test generating report with recommendations."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json", include_recommendations=True
        )

        assert len(result.report.recommendations) > 0

    @pytest.mark.asyncio
    async def test_generate_report_without_recommendations(self, sample_compliance_result):
        """Test generating report without recommendations."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json", include_recommendations=False
        )

        assert len(result.report.recommendations) == 0

    @pytest.mark.asyncio
    async def test_generate_report_default_format(self, sample_compliance_result):
        """Test that default format is JSON."""
        result = await generate_compliance_report(compliance_result=sample_compliance_result)

        assert result.format == ReportFormat.JSON

    @pytest.mark.asyncio
    async def test_generate_report_default_recommendations(self, sample_compliance_result):
        """Test that recommendations are included by default."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json"
        )

        assert len(result.report.recommendations) > 0

    @pytest.mark.asyncio
    async def test_generate_report_summary_accuracy(self, sample_compliance_result):
        """Test that summary matches the compliance result."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json"
        )

        assert result.report.overall_compliance_score == sample_compliance_result.compliance_score
        assert result.report.total_resources == sample_compliance_result.total_resources
        assert result.report.compliant_resources == sample_compliance_result.compliant_resources
        assert result.report.total_violations == len(sample_compliance_result.violations)
        # Cost attribution gap should match (allowing for floating point precision)
        assert (
            abs(result.report.cost_attribution_gap - sample_compliance_result.cost_attribution_gap)
            < 0.01
        )

    @pytest.mark.asyncio
    async def test_generate_report_requirements_7_1(self, sample_compliance_result):
        """Test Requirement 7.1: Generate summary with overall compliance score."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json"
        )

        assert result.report.overall_compliance_score is not None
        assert 0.0 <= result.report.overall_compliance_score <= 1.0

    @pytest.mark.asyncio
    async def test_generate_report_requirements_7_2(self, sample_compliance_result):
        """Test Requirement 7.2: Support JSON, CSV, and Markdown output formats."""
        # Test JSON
        json_result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json"
        )
        assert json_result.format == ReportFormat.JSON

        # Test CSV
        csv_result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="csv"
        )
        assert csv_result.format == ReportFormat.CSV

        # Test Markdown
        md_result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="markdown"
        )
        assert md_result.format == ReportFormat.MARKDOWN

    @pytest.mark.asyncio
    async def test_generate_report_requirements_7_3(self, sample_compliance_result):
        """Test Requirement 7.3: Include actionable remediation suggestions when requested."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json", include_recommendations=True
        )

        assert len(result.report.recommendations) > 0
        for rec in result.report.recommendations:
            assert rec.title is not None
            assert rec.description is not None
            assert rec.priority is not None

    @pytest.mark.asyncio
    async def test_generate_report_requirements_7_4(self, sample_compliance_result):
        """Test Requirement 7.4: Include top violations ranked by count and cost impact."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json"
        )

        assert len(result.report.top_violations_by_count) > 0
        assert len(result.report.top_violations_by_cost) > 0

    @pytest.mark.asyncio
    async def test_generate_report_requirements_7_5(self, sample_compliance_result):
        """Test Requirement 7.5: Include total resource counts (compliant vs. non-compliant)."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json"
        )

        assert result.report.total_resources is not None
        assert result.report.compliant_resources is not None
        assert result.report.non_compliant_resources is not None
        assert (
            result.report.compliant_resources + result.report.non_compliant_resources
            == result.report.total_resources
        )

    @pytest.mark.asyncio
    async def test_generate_report_case_insensitive_format(self, sample_compliance_result):
        """Test that format parameter is case-insensitive."""
        result_upper = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="JSON"
        )
        assert result_upper.format == ReportFormat.JSON

        result_mixed = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="Markdown"
        )
        assert result_mixed.format == ReportFormat.MARKDOWN

    @pytest.mark.asyncio
    async def test_generate_report_to_dict_json_serializable(self, sample_compliance_result):
        """Test that result.to_dict() is JSON serializable."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="json"
        )

        result_dict = result.to_dict()
        json_str = json.dumps(result_dict)
        assert isinstance(json_str, str)


@pytest.fixture
def zero_cost_compliance_result():
    """Create a compliance result with zero cost impact (typical for Tagging API resources)."""
    violations = []

    # Create violations with zero cost (like resources from Tagging API)
    for i in range(15):
        violations.append(
            Violation(
                resource_id=f"i-{i:016x}",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="Owner",
                severity=Severity.ERROR,
                current_value=None,
                allowed_values=None,
                cost_impact_monthly=0.0,  # Zero cost
            )
        )

    for i in range(10):
        violations.append(
            Violation(
                resource_id=f"bucket-{i}",
                resource_type="s3:bucket",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="Environment",
                severity=Severity.ERROR,
                current_value=None,
                allowed_values=["prod", "dev", "staging"],
                cost_impact_monthly=0.0,  # Zero cost
            )
        )

    return ComplianceResult(
        compliance_score=0.55,
        total_resources=69,
        compliant_resources=39,
        violations=violations,
        cost_attribution_gap=15.40,  # Cost attribution gap is still calculated separately
        scan_timestamp=datetime.now(UTC),
    )


class TestZeroCostReportFormatting:
    """Test report formatting when all violation costs are zero."""

    @pytest.mark.asyncio
    async def test_markdown_hides_cost_column_when_all_zero(self, zero_cost_compliance_result):
        """Test that Markdown format hides Cost Impact column when all costs are zero."""
        result = await generate_compliance_report(
            compliance_result=zero_cost_compliance_result,
            format="markdown",
            include_recommendations=True,
        )

        # Should NOT contain "Cost Impact" in the violations table header
        # But should still contain "Cost Attribution Gap" in summary
        assert "Cost Attribution Gap" in result.formatted_output

        # The "Top Violations by Count" table should not have Cost Impact column
        lines = result.formatted_output.split("\n")
        for i, line in enumerate(lines):
            if "## Top Violations by Count" in line:
                # Check the header row (should be 2 lines after the section title)
                header_line = lines[i + 2] if i + 2 < len(lines) else ""
                assert "Cost Impact" not in header_line
                break

    @pytest.mark.asyncio
    async def test_markdown_hides_cost_section_when_all_zero(self, zero_cost_compliance_result):
        """Test that Markdown format hides 'Top Violations by Cost Impact' section when all costs are zero."""
        result = await generate_compliance_report(
            compliance_result=zero_cost_compliance_result,
            format="markdown",
            include_recommendations=True,
        )

        # Should NOT contain the "Top Violations by Cost Impact" section
        assert "## Top Violations by Cost Impact" not in result.formatted_output

    @pytest.mark.asyncio
    async def test_csv_hides_cost_column_when_all_zero(self, zero_cost_compliance_result):
        """Test that CSV format hides Cost Impact column when all costs are zero."""
        result = await generate_compliance_report(
            compliance_result=zero_cost_compliance_result,
            format="csv",
            include_recommendations=True,
        )

        # Should NOT contain "Top Violations by Cost" section
        assert "Top Violations by Cost" not in result.formatted_output

        # The "Top Violations by Count" header should not have Cost Impact
        lines = result.formatted_output.split("\n")
        for i, line in enumerate(lines):
            if "Top Violations by Count" in line:
                # Check the header row (next line)
                header_line = lines[i + 1] if i + 1 < len(lines) else ""
                assert "Cost Impact" not in header_line
                break

    @pytest.mark.asyncio
    async def test_markdown_shows_cost_when_available(self, sample_compliance_result):
        """Test that Markdown format shows Cost Impact when costs are non-zero."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result,
            format="markdown",
            include_recommendations=True,
        )

        # Should contain "Top Violations by Cost Impact" section
        assert "## Top Violations by Cost Impact" in result.formatted_output

        # The "Top Violations by Count" table should have Cost Impact column
        lines = result.formatted_output.split("\n")
        for i, line in enumerate(lines):
            if "## Top Violations by Count" in line:
                # Check the header row (should be 2 lines after the section title)
                header_line = lines[i + 2] if i + 2 < len(lines) else ""
                assert "Cost Impact" in header_line
                break

    @pytest.mark.asyncio
    async def test_csv_shows_cost_when_available(self, sample_compliance_result):
        """Test that CSV format shows Cost Impact when costs are non-zero."""
        result = await generate_compliance_report(
            compliance_result=sample_compliance_result, format="csv", include_recommendations=True
        )

        # Should contain "Top Violations by Cost" section
        assert "Top Violations by Cost" in result.formatted_output

    @pytest.mark.asyncio
    async def test_cost_attribution_gap_always_shown(self, zero_cost_compliance_result):
        """Test that Cost Attribution Gap is always shown even when violation costs are zero."""
        result = await generate_compliance_report(
            compliance_result=zero_cost_compliance_result,
            format="markdown",
            include_recommendations=True,
        )

        # Cost Attribution Gap should always be shown (it's calculated separately via Cost Explorer)
        assert "$15.40/month" in result.formatted_output
