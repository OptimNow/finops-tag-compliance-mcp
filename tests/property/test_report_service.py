"""
Property-based tests for ReportService.

Feature: phase-1-aws-mvp, Property 8: Report Content Completeness
Validates: Requirements 7.1, 7.3, 7.4, 7.5

Property 8 states:
*For any* compliance report generated, the report SHALL include: overall
compliance score, total resource count, compliant count, non-compliant count,
and top violations ranked by count and cost impact. When recommendations are
requested, actionable suggestions SHALL be included.
"""

from datetime import datetime, UTC

from hypothesis import given, strategies as st, settings
import pytest

from mcp_server.services.report_service import ReportService
from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.report import (
    ComplianceReport,
    ReportFormat,
    ViolationRanking,
)
from mcp_server.models.violations import Violation
from mcp_server.models.enums import ViolationType, Severity


# =============================================================================
# Hypothesis Strategies for generating test data
# =============================================================================

def violation_strategy():
    """Strategy for generating random Violation objects."""
    return st.builds(
        Violation,
        resource_id=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-"),
        resource_type=st.sampled_from(["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]),
        region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]),
        violation_type=st.sampled_from(list(ViolationType)),
        tag_name=st.sampled_from(["CostCenter", "Owner", "Environment", "Application", "Project"]),
        severity=st.sampled_from(list(Severity)),
        current_value=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
        allowed_values=st.one_of(st.none(), st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5)),
        cost_impact_monthly=st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    )


def compliance_result_strategy():
    """Strategy for generating random ComplianceResult objects."""
    return st.builds(
        lambda total, compliant, violations, cost_gap: ComplianceResult(
            compliance_score=compliant / total if total > 0 else 1.0,
            total_resources=total,
            compliant_resources=compliant,
            violations=violations,
            cost_attribution_gap=cost_gap,
            scan_timestamp=datetime.now(UTC),
        ),
        total=st.integers(min_value=0, max_value=1000),
        compliant=st.integers(min_value=0, max_value=1000),
        violations=st.lists(violation_strategy(), min_size=0, max_size=50),
        cost_gap=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    ).filter(lambda x: x.compliant_resources <= x.total_resources)


# =============================================================================
# Property 8: Report Content Completeness
# =============================================================================

class TestReportContentCompleteness:
    """
    Property 8: Report Content Completeness
    
    For any compliance report generated, the report SHALL include: overall
    compliance score, total resource count, compliant count, non-compliant count,
    and top violations ranked by count and cost impact. When recommendations are
    requested, actionable suggestions SHALL be included.
    
    Validates: Requirements 7.1, 7.3, 7.4, 7.5
    """

    @given(
        total_resources=st.integers(min_value=0, max_value=1000),
        compliant_resources=st.integers(min_value=0, max_value=1000),
        num_violations=st.integers(min_value=0, max_value=50),
        cost_gap=st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_report_includes_compliance_score(
        self,
        total_resources: int,
        compliant_resources: int,
        num_violations: int,
        cost_gap: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 8: Report Content Completeness
        Validates: Requirements 7.1
        
        For any compliance report generated, the report SHALL include the
        overall compliance score.
        """
        # Ensure compliant doesn't exceed total
        compliant = min(compliant_resources, total_resources)
        score = compliant / total_resources if total_resources > 0 else 1.0
        
        # Generate violations
        violations = []
        for i in range(num_violations):
            violations.append(Violation(
                resource_id=f"resource-{i}",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR,
                cost_impact_monthly=100.0,
            ))
        
        compliance_result = ComplianceResult(
            compliance_score=score,
            total_resources=total_resources,
            compliant_resources=compliant,
            violations=violations,
            cost_attribution_gap=cost_gap,
            scan_timestamp=datetime.now(UTC),
        )
        
        service = ReportService()
        report = service.generate_report(compliance_result, include_recommendations=False)
        
        # Report must include compliance score
        assert hasattr(report, 'overall_compliance_score'), "Report missing overall_compliance_score"
        assert report.overall_compliance_score == score, (
            f"Report score {report.overall_compliance_score} != expected {score}"
        )
        assert 0.0 <= report.overall_compliance_score <= 1.0, (
            f"Compliance score {report.overall_compliance_score} out of bounds"
        )

    @given(
        total_resources=st.integers(min_value=0, max_value=1000),
        compliant_resources=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=100)
    def test_report_includes_resource_counts(
        self,
        total_resources: int,
        compliant_resources: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 8: Report Content Completeness
        Validates: Requirements 7.5
        
        For any compliance report generated, the report SHALL include total
        resource count, compliant count, and non-compliant count.
        """
        # Ensure compliant doesn't exceed total
        compliant = min(compliant_resources, total_resources)
        score = compliant / total_resources if total_resources > 0 else 1.0
        
        compliance_result = ComplianceResult(
            compliance_score=score,
            total_resources=total_resources,
            compliant_resources=compliant,
            violations=[],
            cost_attribution_gap=0.0,
            scan_timestamp=datetime.now(UTC),
        )
        
        service = ReportService()
        report = service.generate_report(compliance_result, include_recommendations=False)
        
        # Report must include all resource counts
        assert hasattr(report, 'total_resources'), "Report missing total_resources"
        assert hasattr(report, 'compliant_resources'), "Report missing compliant_resources"
        assert hasattr(report, 'non_compliant_resources'), "Report missing non_compliant_resources"
        
        # Counts must be correct
        assert report.total_resources == total_resources
        assert report.compliant_resources == compliant
        assert report.non_compliant_resources == total_resources - compliant
        
        # Non-compliant + compliant must equal total
        assert report.compliant_resources + report.non_compliant_resources == report.total_resources

    @given(
        num_violations=st.integers(min_value=1, max_value=50),
        num_tag_types=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_report_includes_violations_ranked_by_count(
        self,
        num_violations: int,
        num_tag_types: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 8: Report Content Completeness
        Validates: Requirements 7.4
        
        For any compliance report generated, the report SHALL include top
        violations ranked by count.
        """
        tag_names = ["CostCenter", "Owner", "Environment", "Application", "Project"][:num_tag_types]
        
        # Generate violations with varying tag names
        violations = []
        for i in range(num_violations):
            tag_name = tag_names[i % len(tag_names)]
            violations.append(Violation(
                resource_id=f"resource-{i}",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name=tag_name,
                severity=Severity.ERROR,
                cost_impact_monthly=100.0,
            ))
        
        compliance_result = ComplianceResult(
            compliance_score=0.5,
            total_resources=num_violations * 2,
            compliant_resources=num_violations,
            violations=violations,
            cost_attribution_gap=1000.0,
            scan_timestamp=datetime.now(UTC),
        )
        
        service = ReportService()
        report = service.generate_report(compliance_result, include_recommendations=False)
        
        # Report must include top violations by count
        assert hasattr(report, 'top_violations_by_count'), "Report missing top_violations_by_count"
        assert isinstance(report.top_violations_by_count, list)
        
        # Violations must be sorted by count (descending)
        for i in range(len(report.top_violations_by_count) - 1):
            assert report.top_violations_by_count[i].violation_count >= report.top_violations_by_count[i + 1].violation_count, (
                f"Violations not sorted by count: {report.top_violations_by_count[i].violation_count} < "
                f"{report.top_violations_by_count[i + 1].violation_count}"
            )

    @given(
        num_violations=st.integers(min_value=1, max_value=50),
        num_tag_types=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_report_includes_violations_ranked_by_cost(
        self,
        num_violations: int,
        num_tag_types: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 8: Report Content Completeness
        Validates: Requirements 7.4
        
        For any compliance report generated, the report SHALL include top
        violations ranked by cost impact.
        """
        tag_names = ["CostCenter", "Owner", "Environment", "Application", "Project"][:num_tag_types]
        
        # Generate violations with varying costs
        violations = []
        for i in range(num_violations):
            tag_name = tag_names[i % len(tag_names)]
            cost = (i + 1) * 50.0  # Varying costs
            violations.append(Violation(
                resource_id=f"resource-{i}",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name=tag_name,
                severity=Severity.ERROR,
                cost_impact_monthly=cost,
            ))
        
        compliance_result = ComplianceResult(
            compliance_score=0.5,
            total_resources=num_violations * 2,
            compliant_resources=num_violations,
            violations=violations,
            cost_attribution_gap=5000.0,
            scan_timestamp=datetime.now(UTC),
        )
        
        service = ReportService()
        report = service.generate_report(compliance_result, include_recommendations=False)
        
        # Report must include top violations by cost
        assert hasattr(report, 'top_violations_by_cost'), "Report missing top_violations_by_cost"
        assert isinstance(report.top_violations_by_cost, list)
        
        # Violations must be sorted by cost (descending)
        for i in range(len(report.top_violations_by_cost) - 1):
            assert report.top_violations_by_cost[i].total_cost_impact >= report.top_violations_by_cost[i + 1].total_cost_impact, (
                f"Violations not sorted by cost: {report.top_violations_by_cost[i].total_cost_impact} < "
                f"{report.top_violations_by_cost[i + 1].total_cost_impact}"
            )

    @given(
        total_resources=st.integers(min_value=10, max_value=100),
        num_violations=st.integers(min_value=15, max_value=50),
        cost_gap=st.floats(min_value=2000.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_report_includes_recommendations_when_requested(
        self,
        total_resources: int,
        num_violations: int,
        cost_gap: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 8: Report Content Completeness
        Validates: Requirements 7.3
        
        When recommendations are requested, the report SHALL include actionable
        suggestions.
        """
        # Generate violations to trigger recommendations
        violations = []
        for i in range(num_violations):
            violations.append(Violation(
                resource_id=f"resource-{i}",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR,
                cost_impact_monthly=200.0,  # High cost to trigger recommendations
            ))
        
        # Low compliance score to trigger recommendations
        compliant = total_resources // 4
        score = compliant / total_resources
        
        compliance_result = ComplianceResult(
            compliance_score=score,
            total_resources=total_resources,
            compliant_resources=compliant,
            violations=violations,
            cost_attribution_gap=cost_gap,
            scan_timestamp=datetime.now(UTC),
        )
        
        service = ReportService()
        report = service.generate_report(compliance_result, include_recommendations=True)
        
        # Report must include recommendations
        assert hasattr(report, 'recommendations'), "Report missing recommendations"
        assert isinstance(report.recommendations, list)
        
        # With high violations and cost gap, recommendations should be generated
        assert len(report.recommendations) > 0, (
            f"Expected recommendations for {num_violations} violations and ${cost_gap} gap"
        )
        
        # Each recommendation must have required fields
        for rec in report.recommendations:
            assert rec.priority in ["high", "medium", "low"], f"Invalid priority: {rec.priority}"
            assert len(rec.title) > 0, "Recommendation missing title"
            assert len(rec.description) > 0, "Recommendation missing description"
            assert len(rec.estimated_impact) > 0, "Recommendation missing estimated_impact"

    @given(
        total_resources=st.integers(min_value=0, max_value=100),
        compliant_resources=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100)
    def test_report_excludes_recommendations_when_not_requested(
        self,
        total_resources: int,
        compliant_resources: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 8: Report Content Completeness
        Validates: Requirements 7.3
        
        When recommendations are not requested, the report SHALL NOT include
        recommendations.
        """
        compliant = min(compliant_resources, total_resources)
        score = compliant / total_resources if total_resources > 0 else 1.0
        
        compliance_result = ComplianceResult(
            compliance_score=score,
            total_resources=total_resources,
            compliant_resources=compliant,
            violations=[],
            cost_attribution_gap=0.0,
            scan_timestamp=datetime.now(UTC),
        )
        
        service = ReportService()
        report = service.generate_report(compliance_result, include_recommendations=False)
        
        # Report should have empty recommendations list
        assert report.recommendations == [], (
            f"Expected no recommendations but got {len(report.recommendations)}"
        )

    @given(
        num_violations=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_report_total_violations_matches_input(
        self,
        num_violations: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 8: Report Content Completeness
        Validates: Requirements 7.5
        
        For any compliance report generated, the total_violations count SHALL
        match the number of violations in the input ComplianceResult.
        """
        violations = []
        for i in range(num_violations):
            violations.append(Violation(
                resource_id=f"resource-{i}",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR,
                cost_impact_monthly=100.0,
            ))
        
        compliance_result = ComplianceResult(
            compliance_score=0.5,
            total_resources=100,
            compliant_resources=50,
            violations=violations,
            cost_attribution_gap=1000.0,
            scan_timestamp=datetime.now(UTC),
        )
        
        service = ReportService()
        report = service.generate_report(compliance_result, include_recommendations=False)
        
        assert report.total_violations == num_violations, (
            f"Report total_violations {report.total_violations} != input {num_violations}"
        )

    @given(
        num_violations=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_violation_rankings_contain_required_fields(
        self,
        num_violations: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 8: Report Content Completeness
        Validates: Requirements 7.4
        
        For any violation ranking in the report, it SHALL include tag_name,
        violation_count, total_cost_impact, and affected_resource_types.
        """
        violations = []
        resource_types = ["ec2:instance", "rds:db", "s3:bucket"]
        for i in range(num_violations):
            violations.append(Violation(
                resource_id=f"resource-{i}",
                resource_type=resource_types[i % len(resource_types)],
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR,
                cost_impact_monthly=100.0 * (i + 1),
            ))
        
        compliance_result = ComplianceResult(
            compliance_score=0.5,
            total_resources=100,
            compliant_resources=50,
            violations=violations,
            cost_attribution_gap=1000.0,
            scan_timestamp=datetime.now(UTC),
        )
        
        service = ReportService()
        report = service.generate_report(compliance_result, include_recommendations=False)
        
        # Check all rankings have required fields
        for ranking in report.top_violations_by_count + report.top_violations_by_cost:
            assert hasattr(ranking, 'tag_name') and ranking.tag_name, "Ranking missing tag_name"
            assert hasattr(ranking, 'violation_count') and ranking.violation_count >= 0, "Ranking missing violation_count"
            assert hasattr(ranking, 'total_cost_impact') and ranking.total_cost_impact >= 0, "Ranking missing total_cost_impact"
            assert hasattr(ranking, 'affected_resource_types'), "Ranking missing affected_resource_types"
            assert isinstance(ranking.affected_resource_types, list), "affected_resource_types must be a list"

