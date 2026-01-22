"""
Property-based tests for data models.

Feature: phase-1-aws-mvp, Property 2: Violation Detail Completeness
Validates: Requirements 1.2, 3.2, 3.3, 3.4

Property 2 states:
*For any* resource that fails policy validation, the violation object SHALL include:
resource ID, resource type, violation type, tag name, and severity.
When the violation is an invalid value, the object SHALL also include the current
value and list of allowed values.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from mcp_server.models import (
    ComplianceResult,
    OptionalTag,
    RequiredTag,
    Severity,
    TagNamingRules,
    TagPolicy,
    TagSuggestion,
    Violation,
    ViolationType,
)

# =============================================================================
# Strategies for generating test data
# =============================================================================

# Valid AWS resource types
RESOURCE_TYPES = ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]

# Valid AWS regions
AWS_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "eu-west-1",
    "eu-west-2",
    "eu-central-1",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
]

# Strategy for non-empty strings (resource IDs, tag names, etc.)
non_empty_string = st.text(min_size=1, max_size=100).filter(lambda x: x.strip())

# Strategy for resource IDs (AWS-like format)
resource_id_strategy = st.from_regex(r"[a-z]{1,10}-[a-z0-9]{8,17}", fullmatch=True)

# Strategy for violation types
violation_type_strategy = st.sampled_from(list(ViolationType))

# Strategy for severity levels
severity_strategy = st.sampled_from(list(Severity))

# Strategy for resource types
resource_type_strategy = st.sampled_from(RESOURCE_TYPES)

# Strategy for AWS regions
region_strategy = st.sampled_from(AWS_REGIONS)

# Strategy for cost values (non-negative floats)
cost_strategy = st.floats(min_value=0.0, max_value=1_000_000.0, allow_nan=False)

# Strategy for confidence scores (0.0 to 1.0)
confidence_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Strategy for compliance scores (0.0 to 1.0)
compliance_score_strategy = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)

# Strategy for allowed values lists
allowed_values_strategy = st.lists(non_empty_string, min_size=1, max_size=10)


# =============================================================================
# Property 2: Violation Detail Completeness
# =============================================================================


class TestViolationDetailCompleteness:
    """
    Property 2: Violation Detail Completeness

    For any resource that fails policy validation, the violation object SHALL include:
    - resource ID
    - resource type
    - violation type
    - tag name
    - severity

    When the violation is an invalid value, it SHALL also include:
    - current value
    - list of allowed values
    """

    @given(
        resource_id=resource_id_strategy,
        resource_type=resource_type_strategy,
        region=region_strategy,
        violation_type=violation_type_strategy,
        tag_name=non_empty_string,
        severity=severity_strategy,
        cost_impact=cost_strategy,
    )
    @settings(max_examples=100)
    def test_violation_has_required_fields(
        self,
        resource_id: str,
        resource_type: str,
        region: str,
        violation_type: ViolationType,
        tag_name: str,
        severity: Severity,
        cost_impact: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 2: Violation Detail Completeness
        Validates: Requirements 1.2, 3.2

        For any violation, all required fields must be present and accessible.
        """
        violation = Violation(
            resource_id=resource_id,
            resource_type=resource_type,
            region=region,
            violation_type=violation_type,
            tag_name=tag_name,
            severity=severity,
            cost_impact_monthly=cost_impact,
        )

        # All required fields must be present
        assert violation.resource_id == resource_id
        assert violation.resource_type == resource_type
        assert violation.region == region
        assert violation.violation_type == violation_type
        assert violation.tag_name == tag_name
        assert violation.severity == severity
        assert violation.cost_impact_monthly >= 0.0

    @given(
        resource_id=resource_id_strategy,
        resource_type=resource_type_strategy,
        region=region_strategy,
        tag_name=non_empty_string,
        severity=severity_strategy,
        current_value=non_empty_string,
        allowed_values=allowed_values_strategy,
    )
    @settings(max_examples=100)
    def test_invalid_value_violation_includes_value_details(
        self,
        resource_id: str,
        resource_type: str,
        region: str,
        tag_name: str,
        severity: Severity,
        current_value: str,
        allowed_values: list[str],
    ):
        """
        Feature: phase-1-aws-mvp, Property 2: Violation Detail Completeness
        Validates: Requirements 3.3

        When the violation is an invalid value, the object SHALL include
        the current value and list of allowed values.
        """
        violation = Violation(
            resource_id=resource_id,
            resource_type=resource_type,
            region=region,
            violation_type=ViolationType.INVALID_VALUE,
            tag_name=tag_name,
            severity=severity,
            current_value=current_value,
            allowed_values=allowed_values,
        )

        # For invalid value violations, current_value and allowed_values should be set
        assert violation.current_value == current_value
        assert violation.allowed_values == allowed_values
        assert len(violation.allowed_values) > 0

    @given(
        resource_id=resource_id_strategy,
        resource_type=resource_type_strategy,
        region=region_strategy,
        tag_name=non_empty_string,
        severity=severity_strategy,
    )
    @settings(max_examples=100)
    def test_missing_tag_violation_has_null_current_value(
        self,
        resource_id: str,
        resource_type: str,
        region: str,
        tag_name: str,
        severity: Severity,
    ):
        """
        Feature: phase-1-aws-mvp, Property 2: Violation Detail Completeness
        Validates: Requirements 3.2

        For missing required tag violations, current_value should be None.
        """
        violation = Violation(
            resource_id=resource_id,
            resource_type=resource_type,
            region=region,
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name=tag_name,
            severity=severity,
        )

        # Missing tag violations should have None for current_value
        assert violation.current_value is None


# =============================================================================
# Property 6: Suggestion Quality (partial - model validation)
# =============================================================================


class TestSuggestionQuality:
    """
    Property 6: Suggestion Quality (model-level validation)

    For any tag suggestion returned, the suggestion SHALL include:
    - tag key
    - suggested value
    - confidence score (between 0.0 and 1.0 inclusive)
    - non-empty reasoning string
    """

    @given(
        tag_key=non_empty_string,
        suggested_value=non_empty_string,
        confidence=confidence_strategy,
        reasoning=st.text(min_size=1, max_size=500).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100)
    def test_suggestion_has_required_fields(
        self,
        tag_key: str,
        suggested_value: str,
        confidence: float,
        reasoning: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.1, 5.2, 5.3

        All suggestion fields must be present and valid.
        """
        suggestion = TagSuggestion(
            tag_key=tag_key,
            suggested_value=suggested_value,
            confidence=confidence,
            reasoning=reasoning,
        )

        assert suggestion.tag_key == tag_key
        assert suggestion.suggested_value == suggested_value
        assert 0.0 <= suggestion.confidence <= 1.0
        assert len(suggestion.reasoning) > 0

    @given(confidence=st.floats(min_value=1.01, max_value=100.0, allow_nan=False))
    @settings(max_examples=50)
    def test_suggestion_rejects_invalid_confidence(self, confidence: float):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.2

        Confidence scores outside 0.0-1.0 range should be rejected.
        """
        with pytest.raises(ValidationError):
            TagSuggestion(
                tag_key="Environment",
                suggested_value="production",
                confidence=confidence,
                reasoning="Test reasoning",
            )

    def test_suggestion_rejects_empty_reasoning(self):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.3

        Empty reasoning strings should be rejected.
        """
        with pytest.raises(ValidationError):
            TagSuggestion(
                tag_key="Environment",
                suggested_value="production",
                confidence=0.8,
                reasoning="",
            )


# =============================================================================
# Property 1: Compliance Score Bounds (model-level validation)
# =============================================================================


class TestComplianceScoreBounds:
    """
    Property 1: Compliance Score Bounds (model-level validation)

    For any set of resources scanned, the compliance score returned SHALL be
    between 0.0 and 1.0 inclusive.
    """

    @given(
        total_resources=st.integers(min_value=0, max_value=10000),
        compliance_score=compliance_score_strategy,
    )
    @settings(max_examples=100)
    def test_compliance_score_within_bounds(
        self,
        total_resources: int,
        compliance_score: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        Compliance score must always be between 0.0 and 1.0.
        """
        compliant = int(total_resources * compliance_score)

        result = ComplianceResult(
            compliance_score=compliance_score,
            total_resources=total_resources,
            compliant_resources=compliant,
        )

        assert 0.0 <= result.compliance_score <= 1.0

    @given(score=st.floats(min_value=1.01, max_value=100.0, allow_nan=False))
    @settings(max_examples=50)
    def test_compliance_score_rejects_above_one(self, score: float):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        Scores above 1.0 should be rejected.
        """
        with pytest.raises(ValidationError):
            ComplianceResult(
                compliance_score=score,
                total_resources=100,
                compliant_resources=100,
            )

    @given(score=st.floats(max_value=-0.01, allow_nan=False))
    @settings(max_examples=50)
    def test_compliance_score_rejects_negative(self, score: float):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        Negative scores should be rejected.
        """
        with pytest.raises(ValidationError):
            ComplianceResult(
                compliance_score=score,
                total_resources=100,
                compliant_resources=100,
            )


# =============================================================================
# Property 7: Policy Structure Completeness (model-level validation)
# =============================================================================


class TestPolicyStructureCompleteness:
    """
    Property 7: Policy Structure Completeness (model-level validation)

    For any tagging policy returned, the policy SHALL include:
    - version
    - last updated timestamp
    - required tags list
    - optional tags list
    """

    @given(
        version=st.from_regex(r"\d+\.\d+(\.\d+)?", fullmatch=True),
        tag_name=non_empty_string,
        description=non_empty_string,
    )
    @settings(max_examples=100)
    def test_policy_has_required_structure(
        self,
        version: str,
        tag_name: str,
        description: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.1, 6.2, 6.3, 6.4

        Policy must have all required structural elements.
        """
        required_tag = RequiredTag(
            name=tag_name,
            description=description,
            applies_to=["ec2:instance"],
        )

        optional_tag = OptionalTag(
            name=f"optional_{tag_name}",
            description=f"Optional {description}",
        )

        policy = TagPolicy(
            version=version,
            required_tags=[required_tag],
            optional_tags=[optional_tag],
        )

        # All structural elements must be present
        assert policy.version == version
        assert policy.last_updated is not None
        assert isinstance(policy.required_tags, list)
        assert isinstance(policy.optional_tags, list)
        assert isinstance(policy.tag_naming_rules, TagNamingRules)

    @given(
        tag_name=non_empty_string,
        description=non_empty_string,
        allowed_values=allowed_values_strategy,
    )
    @settings(max_examples=100)
    def test_required_tag_has_applies_to(
        self,
        tag_name: str,
        description: str,
        allowed_values: list[str],
    ):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.4

        Each required tag SHALL include applies_to list.
        """
        required_tag = RequiredTag(
            name=tag_name,
            description=description,
            allowed_values=allowed_values,
            applies_to=["ec2:instance", "rds:db"],
        )

        assert required_tag.name == tag_name
        assert required_tag.description == description
        assert required_tag.applies_to is not None
        assert len(required_tag.applies_to) > 0

    def test_required_tag_must_have_applies_to(self):
        """
        Feature: phase-1-aws-mvp, Property 7: Policy Structure Completeness
        Validates: Requirements 6.4

        Required tags without applies_to should be rejected.
        """
        with pytest.raises(ValidationError):
            RequiredTag(
                name="CostCenter",
                description="Cost allocation tag",
                # Missing applies_to - should fail
            )
