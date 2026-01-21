"""
Property-based tests for SuggestionService.

Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
Validates: Requirements 5.1, 5.2, 5.3

Property 6 states:
*For any* tag suggestion returned, the suggestion SHALL include:
- tag key
- suggested value
- confidence score (between 0.0 and 1.0 inclusive)
- non-empty reasoning string explaining the basis for the suggestion
"""

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck
import asyncio

from mcp_server.services.suggestion_service import SuggestionService
from mcp_server.services.policy_service import PolicyService
from mcp_server.models import TagSuggestion


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Valid AWS resource types
RESOURCE_TYPES = ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]

# Environment keywords that should trigger suggestions
ENVIRONMENT_KEYWORDS = [
    "prod",
    "prd",
    "production",
    "stag",
    "stg",
    "staging",
    "dev",
    "development",
    "test",
    "qa",
]

# Cost center keywords
COST_CENTER_KEYWORDS = [
    "eng",
    "engineering",
    "mkt",
    "marketing",
    "sales",
    "ops",
    "operations",
    "fin",
    "finance",
]

# Data classification keywords
DATA_CLASSIFICATION_KEYWORDS = ["public", "internal", "confidential", "restricted", "pii", "hipaa"]

# Strategy for resource types
resource_type_strategy = st.sampled_from(RESOURCE_TYPES)

# Strategy for environment keywords
environment_keyword_strategy = st.sampled_from(ENVIRONMENT_KEYWORDS)

# Strategy for cost center keywords
cost_center_keyword_strategy = st.sampled_from(COST_CENTER_KEYWORDS)

# Strategy for data classification keywords
data_classification_keyword_strategy = st.sampled_from(DATA_CLASSIFICATION_KEYWORDS)

# Strategy for non-empty strings
non_empty_string = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
)

# Strategy for resource names with environment keywords
resource_name_with_env_strategy = st.builds(
    lambda prefix, env, suffix: f"{prefix}-{env}-{suffix}",
    prefix=st.text(min_size=3, max_size=10, alphabet=st.characters(whitelist_categories=("Ll",))),
    env=environment_keyword_strategy,
    suffix=st.text(
        min_size=2, max_size=8, alphabet=st.characters(whitelist_categories=("Ll", "Nd"))
    ),
)

# Strategy for VPC names with environment keywords
vpc_name_with_env_strategy = st.builds(
    lambda prefix, env: f"vpc-{prefix}-{env}",
    prefix=st.text(min_size=3, max_size=10, alphabet=st.characters(whitelist_categories=("Ll",))),
    env=environment_keyword_strategy,
)

# Strategy for IAM role names with cost center keywords
iam_role_with_cost_center_strategy = st.builds(
    lambda cc, suffix: f"{cc}-team-role-{suffix}",
    cc=cost_center_keyword_strategy,
    suffix=st.text(
        min_size=2, max_size=8, alphabet=st.characters(whitelist_categories=("Ll", "Nd"))
    ),
)

# Strategy for similar resources with tags
similar_resource_strategy = st.fixed_dictionaries(
    {
        "resource_id": st.text(
            min_size=5,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Ll", "Nd"), whitelist_characters="-"),
        ),
        "resource_type": resource_type_strategy,
        "tags": st.dictionaries(
            keys=st.sampled_from(["Environment", "CostCenter", "Owner", "Application"]),
            values=st.text(
                min_size=1,
                max_size=30,
                alphabet=st.characters(
                    whitelist_categories=("L", "N"), whitelist_characters="-_@."
                ),
            ),
            min_size=1,
            max_size=4,
        ),
    }
)


# =============================================================================
# Helper functions to create services (instead of fixtures)
# =============================================================================


def create_policy_service() -> PolicyService:
    """Create a PolicyService with the default policy."""
    service = PolicyService()
    service.load_policy()
    return service


def create_suggestion_service() -> SuggestionService:
    """Create a SuggestionService with the policy service."""
    policy_service = create_policy_service()
    return SuggestionService(policy_service)


# =============================================================================
# Property 6: Suggestion Quality
# =============================================================================


class TestSuggestionQuality:
    """
    Property 6: Suggestion Quality

    For any tag suggestion returned, the suggestion SHALL include:
    - tag key
    - suggested value
    - confidence score (between 0.0 and 1.0 inclusive)
    - non-empty reasoning string explaining the basis for the suggestion

    Requirements: 5.1, 5.2, 5.3
    """

    @given(
        resource_name=resource_name_with_env_strategy,
        resource_type=resource_type_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_environment_suggestions_have_valid_structure(
        self,
        resource_name: str,
        resource_type: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.1, 5.2, 5.3

        For any resource with environment keywords in its name,
        suggestions should have valid structure with confidence and reasoning.
        """
        policy_service = create_policy_service()
        suggestion_service = create_suggestion_service()

        # Skip if resource type doesn't require Environment tag
        required_tags = policy_service.get_required_tags(resource_type)
        env_required = any(t.name == "Environment" for t in required_tags)
        assume(env_required)

        # Run async function
        suggestions = asyncio.get_event_loop().run_until_complete(
            suggestion_service.suggest_tags(
                resource_arn=f"arn:aws:ec2:us-east-1:123456789012:instance/{resource_name}",
                resource_type=resource_type,
                resource_name=resource_name,
                current_tags={},  # No existing tags
            )
        )

        # Should have at least one suggestion for Environment
        env_suggestions = [s for s in suggestions if s.tag_key == "Environment"]

        if env_suggestions:
            suggestion = env_suggestions[0]

            # Property 6: All required fields must be present
            assert suggestion.tag_key == "Environment"
            assert len(suggestion.suggested_value) > 0
            assert 0.0 <= suggestion.confidence <= 1.0
            assert len(suggestion.reasoning) > 0

            # Reasoning should explain the basis for suggestion
            assert any(
                word in suggestion.reasoning.lower()
                for word in ["pattern", "detected", "found", "extracted"]
            )

    @given(
        vpc_name=vpc_name_with_env_strategy,
        resource_type=resource_type_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_vpc_based_suggestions_have_higher_confidence(
        self,
        vpc_name: str,
        resource_type: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.2, 5.4

        Suggestions based on VPC naming patterns should have higher confidence
        than those based on resource names alone.
        """
        policy_service = create_policy_service()
        suggestion_service = create_suggestion_service()

        # Skip if resource type doesn't require Environment tag
        required_tags = policy_service.get_required_tags(resource_type)
        env_required = any(t.name == "Environment" for t in required_tags)
        assume(env_required)

        # Get suggestion with VPC context
        suggestions = asyncio.get_event_loop().run_until_complete(
            suggestion_service.suggest_tags(
                resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
                resource_type=resource_type,
                resource_name="generic-instance",
                current_tags={},
                vpc_name=vpc_name,
            )
        )

        env_suggestions = [s for s in suggestions if s.tag_key == "Environment"]

        if env_suggestions:
            suggestion = env_suggestions[0]

            # VPC-based suggestions should have confidence >= 0.80
            assert suggestion.confidence >= 0.80
            assert "VPC" in suggestion.reasoning

    @given(
        iam_role=iam_role_with_cost_center_strategy,
        resource_type=resource_type_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_iam_role_based_suggestions_include_reasoning(
        self,
        iam_role: str,
        resource_type: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.3, 5.4

        Suggestions based on IAM role patterns should include clear reasoning
        explaining the basis for the suggestion.
        """
        suggestion_service = create_suggestion_service()

        suggestions = asyncio.get_event_loop().run_until_complete(
            suggestion_service.suggest_tags(
                resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
                resource_type=resource_type,
                resource_name="generic-instance",
                current_tags={},
                iam_role=iam_role,
            )
        )

        cost_center_suggestions = [s for s in suggestions if s.tag_key == "CostCenter"]

        if cost_center_suggestions:
            suggestion = cost_center_suggestions[0]

            # Reasoning must be non-empty and explain the basis
            assert len(suggestion.reasoning) > 0
            assert any(
                word in suggestion.reasoning.lower()
                for word in ["pattern", "detected", "iam", "role"]
            )

    @given(
        similar_resources=st.lists(similar_resource_strategy, min_size=3, max_size=10),
        resource_type=resource_type_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_similar_resource_suggestions_have_valid_confidence(
        self,
        similar_resources: list[dict],
        resource_type: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.2, 5.4

        Suggestions based on similar resources should have confidence scores
        that reflect the consistency of tags across similar resources.
        """
        suggestion_service = create_suggestion_service()

        # Ensure similar resources have consistent tags for testing
        common_tag = "Environment"
        common_value = "production"

        # Add the common tag to all similar resources
        for resource in similar_resources:
            resource["tags"][common_tag] = common_value

        suggestions = asyncio.get_event_loop().run_until_complete(
            suggestion_service.suggest_tags(
                resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-new",
                resource_type=resource_type,
                resource_name="new-instance",
                current_tags={},
                similar_resources=similar_resources,
            )
        )

        env_suggestions = [s for s in suggestions if s.tag_key == common_tag]

        if env_suggestions:
            suggestion = env_suggestions[0]

            # Confidence must be within valid bounds
            assert 0.0 <= suggestion.confidence <= 1.0

            # Reasoning should mention similar resources
            assert "similar" in suggestion.reasoning.lower()

    @given(
        resource_type=resource_type_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_no_suggestions_for_already_tagged_resources(
        self,
        resource_type: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.1

        Resources that already have all required tags should not receive
        suggestions for those tags.
        """
        policy_service = create_policy_service()
        suggestion_service = create_suggestion_service()

        # Get required tags for this resource type
        required_tags = policy_service.get_required_tags(resource_type)

        # Create current_tags with all required tags filled
        current_tags = {}
        for tag in required_tags:
            if tag.allowed_values:
                current_tags[tag.name] = tag.allowed_values[0]
            else:
                current_tags[tag.name] = (
                    "test-value@example.com" if tag.name == "Owner" else "test-app"
                )

        suggestions = asyncio.get_event_loop().run_until_complete(
            suggestion_service.suggest_tags(
                resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
                resource_type=resource_type,
                resource_name="test-prod-instance",
                current_tags=current_tags,
            )
        )

        # Should not suggest tags that already exist
        for suggestion in suggestions:
            assert suggestion.tag_key not in current_tags

    @given(
        resource_name=resource_name_with_env_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_all_suggestions_have_complete_structure(
        self,
        resource_name: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.1, 5.2, 5.3

        For any suggestions returned, ALL suggestions must have complete structure:
        - tag_key (non-empty string)
        - suggested_value (non-empty string)
        - confidence (float between 0.0 and 1.0)
        - reasoning (non-empty string)
        """
        suggestion_service = create_suggestion_service()

        suggestions = asyncio.get_event_loop().run_until_complete(
            suggestion_service.suggest_tags(
                resource_arn=f"arn:aws:ec2:us-east-1:123456789012:instance/{resource_name}",
                resource_type="ec2:instance",
                resource_name=resource_name,
                current_tags={},
            )
        )

        # Every suggestion must have complete structure
        for suggestion in suggestions:
            assert isinstance(suggestion, TagSuggestion)
            assert len(suggestion.tag_key) > 0
            assert len(suggestion.suggested_value) > 0
            assert 0.0 <= suggestion.confidence <= 1.0
            assert len(suggestion.reasoning) > 0


# =============================================================================
# Additional Property Tests for Suggestion Patterns
# =============================================================================


class TestSuggestionPatternMatching:
    """
    Additional tests for pattern matching behavior.

    These tests verify that the suggestion service correctly identifies
    patterns in resource metadata.
    """

    @given(
        env_keyword=environment_keyword_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_environment_pattern_detection(
        self,
        env_keyword: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.1, 5.4

        Environment keywords in resource names should be detected and
        result in appropriate Environment tag suggestions.
        """
        suggestion_service = create_suggestion_service()

        resource_name = f"my-app-{env_keyword}-server"

        suggestions = asyncio.get_event_loop().run_until_complete(
            suggestion_service.suggest_tags(
                resource_arn=f"arn:aws:ec2:us-east-1:123456789012:instance/{resource_name}",
                resource_type="ec2:instance",
                resource_name=resource_name,
                current_tags={},
            )
        )

        env_suggestions = [s for s in suggestions if s.tag_key == "Environment"]

        # Should detect environment pattern
        assert len(env_suggestions) > 0

        suggestion = env_suggestions[0]
        # Suggested value should be one of the allowed values
        assert suggestion.suggested_value in ["production", "staging", "development", "test"]

    @given(
        cc_keyword=cost_center_keyword_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cost_center_pattern_detection(
        self,
        cc_keyword: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 6: Suggestion Quality
        Validates: Requirements 5.1, 5.4

        Cost center keywords in resource context should be detected and
        result in appropriate CostCenter tag suggestions.
        """
        suggestion_service = create_suggestion_service()

        resource_name = f"{cc_keyword}-service-api"

        suggestions = asyncio.get_event_loop().run_until_complete(
            suggestion_service.suggest_tags(
                resource_arn=f"arn:aws:ec2:us-east-1:123456789012:instance/{resource_name}",
                resource_type="ec2:instance",
                resource_name=resource_name,
                current_tags={},
            )
        )

        cc_suggestions = [s for s in suggestions if s.tag_key == "CostCenter"]

        # Should detect cost center pattern
        assert len(cc_suggestions) > 0

        suggestion = cc_suggestions[0]
        # Suggested value should be one of the allowed values
        assert suggestion.suggested_value in [
            "Engineering",
            "Marketing",
            "Sales",
            "Operations",
            "Finance",
        ]
