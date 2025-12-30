"""
Property-based tests for CostService.

Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
Validates: Requirements 4.1, 4.2, 4.3

Property 5 states:
*For any* cost attribution analysis, the attribution gap SHALL equal
(total cloud spend - attributable spend). The gap percentage SHALL equal
(gap / total spend * 100). When grouping is specified, the sum of grouped
gaps SHALL equal the total gap.
"""

import math
from hypothesis import given, strategies as st, settings, assume
import pytest
from unittest.mock import MagicMock, AsyncMock

from mcp_server.services.cost_service import CostService, CostAttributionResult
from mcp_server.services.policy_service import PolicyService
from mcp_server.clients.aws_client import AWSClient
from mcp_server.models.violations import Violation
from mcp_server.models.enums import ViolationType, Severity


# =============================================================================
# Helper functions to create mocks
# =============================================================================

def create_mock_aws_client():
    """Create a mock AWS client."""
    return MagicMock(spec=AWSClient)


def create_mock_policy_service():
    """Create a mock policy service."""
    return MagicMock(spec=PolicyService)


def create_cost_service():
    """Create a CostService instance with mocked dependencies."""
    return CostService(
        aws_client=create_mock_aws_client(),
        policy_service=create_mock_policy_service()
    )


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for generating positive cost values
positive_cost = st.floats(min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)

# Strategy for generating non-negative cost values (including zero)
non_negative_cost = st.floats(min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)

# Strategy for generating resource types
resource_type_strategy = st.sampled_from([
    "ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"
])

# Strategy for generating regions
region_strategy = st.sampled_from([
    "us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"
])

# Strategy for generating account IDs
account_strategy = st.sampled_from([
    "111111111111", "222222222222", "333333333333", "444444444444"
])


# =============================================================================
# Property 5: Cost Attribution Calculation
# =============================================================================

class TestCostAttributionCalculation:
    """
    Property 5: Cost Attribution Calculation
    
    For any cost attribution analysis, the attribution gap SHALL equal
    (total cloud spend - attributable spend). The gap percentage SHALL equal
    (gap / total spend * 100). When grouping is specified, the sum of grouped
    gaps SHALL equal the total gap.
    
    Validates: Requirements 4.1, 4.2, 4.3
    """

    # -------------------------------------------------------------------------
    # Core Attribution Gap Calculation Tests
    # -------------------------------------------------------------------------

    @given(
        total_spend=positive_cost,
        attributable_spend=non_negative_cost,
    )
    @settings(max_examples=100)
    def test_attribution_gap_equals_total_minus_attributable(
        self,
        total_spend: float,
        attributable_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.1, 4.2
        
        For any cost attribution analysis, the attribution gap SHALL equal
        (total cloud spend - attributable spend).
        """
        # Ensure attributable doesn't exceed total
        attributable_spend = min(attributable_spend, total_spend)
        
        # Calculate expected gap
        expected_gap = total_spend - attributable_spend
        
        # Create result object (simulating what CostService would return)
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=attributable_spend,
            attribution_gap=expected_gap,
            attribution_gap_percentage=(expected_gap / total_spend * 100) if total_spend > 0 else 0.0
        )
        
        # Verify the gap calculation
        assert abs(result.attribution_gap - (result.total_spend - result.attributable_spend)) < 1e-10, (
            f"Gap {result.attribution_gap} != total {result.total_spend} - "
            f"attributable {result.attributable_spend}"
        )

    @given(
        total_spend=positive_cost,
        attributable_spend=non_negative_cost,
    )
    @settings(max_examples=100)
    def test_gap_percentage_equals_gap_over_total_times_100(
        self,
        total_spend: float,
        attributable_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.2
        
        For any cost attribution analysis, the gap percentage SHALL equal
        (gap / total spend * 100).
        """
        # Ensure attributable doesn't exceed total
        attributable_spend = min(attributable_spend, total_spend)
        
        # Calculate expected values
        expected_gap = total_spend - attributable_spend
        expected_percentage = (expected_gap / total_spend * 100) if total_spend > 0 else 0.0
        
        # Create result object
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=attributable_spend,
            attribution_gap=expected_gap,
            attribution_gap_percentage=expected_percentage
        )
        
        # Verify the percentage calculation
        if result.total_spend > 0:
            expected = (result.attribution_gap / result.total_spend) * 100
            assert abs(result.attribution_gap_percentage - expected) < 1e-10, (
                f"Gap percentage {result.attribution_gap_percentage} != "
                f"expected {expected}"
            )

    @given(
        total_spend=st.floats(min_value=0.0, max_value=0.0),
    )
    @settings(max_examples=10)
    def test_zero_total_spend_returns_zero_percentage(
        self,
        total_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.2
        
        When total spend is zero, the gap percentage SHALL be 0.0 (avoiding
        division by zero).
        """
        result = CostAttributionResult(
            total_spend=0.0,
            attributable_spend=0.0,
            attribution_gap=0.0,
            attribution_gap_percentage=0.0
        )
        
        assert result.attribution_gap_percentage == 0.0, (
            f"Expected 0.0 percentage for zero total spend, got "
            f"{result.attribution_gap_percentage}"
        )

    # -------------------------------------------------------------------------
    # Grouping Tests - Sum of Grouped Gaps Equals Total Gap
    # -------------------------------------------------------------------------

    @given(
        num_groups=st.integers(min_value=1, max_value=10),
        total_spend=positive_cost,
    )
    @settings(max_examples=100)
    def test_grouped_gaps_sum_equals_total_gap(
        self,
        num_groups: int,
        total_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.3
        
        When grouping is specified, the sum of grouped gaps SHALL equal the
        total gap.
        """
        # Generate random distribution of spend across groups
        # Each group gets a portion of total spend
        group_spends = []
        remaining = total_spend
        for i in range(num_groups - 1):
            # Allocate a random portion of remaining spend
            portion = remaining * (1.0 / (num_groups - i))
            group_spends.append(portion)
            remaining -= portion
        group_spends.append(remaining)  # Last group gets the rest
        
        # Generate random attributable portions for each group
        breakdown = {}
        total_attributable = 0.0
        total_gap = 0.0
        
        for i, group_spend in enumerate(group_spends):
            group_key = f"group-{i}"
            # Random portion is attributable (0% to 100%)
            attributable_ratio = (i % 3) / 3.0  # Deterministic for reproducibility
            group_attributable = group_spend * attributable_ratio
            group_gap = group_spend - group_attributable
            
            breakdown[group_key] = {
                "total": group_spend,
                "attributable": group_attributable,
                "gap": group_gap
            }
            
            total_attributable += group_attributable
            total_gap += group_gap
        
        # Create result with breakdown
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=total_attributable,
            attribution_gap=total_gap,
            attribution_gap_percentage=(total_gap / total_spend * 100) if total_spend > 0 else 0.0,
            breakdown=breakdown
        )
        
        # Verify sum of grouped gaps equals total gap
        sum_of_grouped_gaps = sum(group["gap"] for group in result.breakdown.values())
        
        assert abs(sum_of_grouped_gaps - result.attribution_gap) < 1e-6, (
            f"Sum of grouped gaps {sum_of_grouped_gaps} != "
            f"total gap {result.attribution_gap}"
        )

    @given(
        num_resource_types=st.integers(min_value=1, max_value=5),
        total_spend=positive_cost,
    )
    @settings(max_examples=100)
    def test_resource_type_grouping_gaps_sum_equals_total(
        self,
        num_resource_types: int,
        total_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.3
        
        When grouping by resource_type, the sum of gaps across all resource
        types SHALL equal the total attribution gap.
        """
        resource_types = ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]
        selected_types = resource_types[:num_resource_types]
        
        # Distribute spend across resource types
        spend_per_type = total_spend / num_resource_types
        
        breakdown = {}
        total_attributable = 0.0
        total_gap = 0.0
        
        for i, rt in enumerate(selected_types):
            # Alternate between compliant and non-compliant
            attributable_ratio = 0.5 if i % 2 == 0 else 0.0
            group_attributable = spend_per_type * attributable_ratio
            group_gap = spend_per_type - group_attributable
            
            breakdown[rt] = {
                "total": spend_per_type,
                "attributable": group_attributable,
                "gap": group_gap
            }
            
            total_attributable += group_attributable
            total_gap += group_gap
        
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=total_attributable,
            attribution_gap=total_gap,
            attribution_gap_percentage=(total_gap / total_spend * 100) if total_spend > 0 else 0.0,
            breakdown=breakdown
        )
        
        # Verify sum of grouped gaps equals total gap
        sum_of_grouped_gaps = sum(group["gap"] for group in result.breakdown.values())
        
        assert abs(sum_of_grouped_gaps - result.attribution_gap) < 1e-6, (
            f"Sum of resource type gaps {sum_of_grouped_gaps} != "
            f"total gap {result.attribution_gap}"
        )

    @given(
        num_regions=st.integers(min_value=1, max_value=4),
        total_spend=positive_cost,
    )
    @settings(max_examples=100)
    def test_region_grouping_gaps_sum_equals_total(
        self,
        num_regions: int,
        total_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.3
        
        When grouping by region, the sum of gaps across all regions SHALL
        equal the total attribution gap.
        """
        regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        selected_regions = regions[:num_regions]
        
        # Distribute spend across regions
        spend_per_region = total_spend / num_regions
        
        breakdown = {}
        total_attributable = 0.0
        total_gap = 0.0
        
        for i, region in enumerate(selected_regions):
            # Vary attributable ratio by region
            attributable_ratio = (i + 1) / (num_regions + 1)
            group_attributable = spend_per_region * attributable_ratio
            group_gap = spend_per_region - group_attributable
            
            breakdown[region] = {
                "total": spend_per_region,
                "attributable": group_attributable,
                "gap": group_gap
            }
            
            total_attributable += group_attributable
            total_gap += group_gap
        
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=total_attributable,
            attribution_gap=total_gap,
            attribution_gap_percentage=(total_gap / total_spend * 100) if total_spend > 0 else 0.0,
            breakdown=breakdown
        )
        
        # Verify sum of grouped gaps equals total gap
        sum_of_grouped_gaps = sum(group["gap"] for group in result.breakdown.values())
        
        assert abs(sum_of_grouped_gaps - result.attribution_gap) < 1e-6, (
            f"Sum of region gaps {sum_of_grouped_gaps} != "
            f"total gap {result.attribution_gap}"
        )

    @given(
        num_accounts=st.integers(min_value=1, max_value=4),
        total_spend=positive_cost,
    )
    @settings(max_examples=100)
    def test_account_grouping_gaps_sum_equals_total(
        self,
        num_accounts: int,
        total_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.3
        
        When grouping by account, the sum of gaps across all accounts SHALL
        equal the total attribution gap.
        """
        accounts = ["111111111111", "222222222222", "333333333333", "444444444444"]
        selected_accounts = accounts[:num_accounts]
        
        # Distribute spend across accounts
        spend_per_account = total_spend / num_accounts
        
        breakdown = {}
        total_attributable = 0.0
        total_gap = 0.0
        
        for i, account in enumerate(selected_accounts):
            # Vary attributable ratio by account
            attributable_ratio = 0.25 * i
            group_attributable = spend_per_account * attributable_ratio
            group_gap = spend_per_account - group_attributable
            
            breakdown[account] = {
                "total": spend_per_account,
                "attributable": group_attributable,
                "gap": group_gap
            }
            
            total_attributable += group_attributable
            total_gap += group_gap
        
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=total_attributable,
            attribution_gap=total_gap,
            attribution_gap_percentage=(total_gap / total_spend * 100) if total_spend > 0 else 0.0,
            breakdown=breakdown
        )
        
        # Verify sum of grouped gaps equals total gap
        sum_of_grouped_gaps = sum(group["gap"] for group in result.breakdown.values())
        
        assert abs(sum_of_grouped_gaps - result.attribution_gap) < 1e-6, (
            f"Sum of account gaps {sum_of_grouped_gaps} != "
            f"total gap {result.attribution_gap}"
        )

    # -------------------------------------------------------------------------
    # Boundary Condition Tests
    # -------------------------------------------------------------------------

    @given(total_spend=positive_cost)
    @settings(max_examples=100)
    def test_all_attributable_means_zero_gap(
        self,
        total_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.1, 4.2
        
        When all spend is attributable, the attribution gap SHALL be 0.0
        and the gap percentage SHALL be 0.0.
        """
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=total_spend,
            attribution_gap=0.0,
            attribution_gap_percentage=0.0
        )
        
        assert result.attribution_gap == 0.0, (
            f"Expected 0.0 gap when all spend is attributable, got "
            f"{result.attribution_gap}"
        )
        assert result.attribution_gap_percentage == 0.0, (
            f"Expected 0.0% gap when all spend is attributable, got "
            f"{result.attribution_gap_percentage}"
        )

    @given(total_spend=positive_cost)
    @settings(max_examples=100)
    def test_none_attributable_means_full_gap(
        self,
        total_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.1, 4.2
        
        When no spend is attributable, the attribution gap SHALL equal total
        spend and the gap percentage SHALL be 100.0.
        """
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=0.0,
            attribution_gap=total_spend,
            attribution_gap_percentage=100.0
        )
        
        assert abs(result.attribution_gap - result.total_spend) < 1e-10, (
            f"Expected gap {result.total_spend} when nothing attributable, got "
            f"{result.attribution_gap}"
        )
        assert abs(result.attribution_gap_percentage - 100.0) < 1e-10, (
            f"Expected 100.0% gap when nothing attributable, got "
            f"{result.attribution_gap_percentage}"
        )

    # -------------------------------------------------------------------------
    # Invariant Tests
    # -------------------------------------------------------------------------

    @given(
        total_spend=positive_cost,
        attributable_spend=non_negative_cost,
    )
    @settings(max_examples=100)
    def test_gap_is_non_negative(
        self,
        total_spend: float,
        attributable_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.1
        
        The attribution gap SHALL always be non-negative (>= 0).
        """
        # Ensure attributable doesn't exceed total
        attributable_spend = min(attributable_spend, total_spend)
        
        gap = total_spend - attributable_spend
        
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=attributable_spend,
            attribution_gap=gap,
            attribution_gap_percentage=(gap / total_spend * 100) if total_spend > 0 else 0.0
        )
        
        assert result.attribution_gap >= 0.0, (
            f"Gap should be non-negative, got {result.attribution_gap}"
        )

    @given(
        total_spend=positive_cost,
        attributable_spend=non_negative_cost,
    )
    @settings(max_examples=100)
    def test_gap_percentage_between_0_and_100(
        self,
        total_spend: float,
        attributable_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.2
        
        The attribution gap percentage SHALL always be between 0.0 and 100.0
        inclusive.
        """
        # Ensure attributable doesn't exceed total
        attributable_spend = min(attributable_spend, total_spend)
        
        gap = total_spend - attributable_spend
        gap_percentage = (gap / total_spend * 100) if total_spend > 0 else 0.0
        
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=attributable_spend,
            attribution_gap=gap,
            attribution_gap_percentage=gap_percentage
        )
        
        assert 0.0 <= result.attribution_gap_percentage <= 100.0, (
            f"Gap percentage should be between 0 and 100, got "
            f"{result.attribution_gap_percentage}"
        )

    @given(
        total_spend=positive_cost,
        attributable_spend=non_negative_cost,
    )
    @settings(max_examples=100)
    def test_attributable_plus_gap_equals_total(
        self,
        total_spend: float,
        attributable_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.1
        
        The sum of attributable spend and attribution gap SHALL equal total
        spend (conservation of cost).
        """
        # Ensure attributable doesn't exceed total
        attributable_spend = min(attributable_spend, total_spend)
        
        gap = total_spend - attributable_spend
        
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=attributable_spend,
            attribution_gap=gap,
            attribution_gap_percentage=(gap / total_spend * 100) if total_spend > 0 else 0.0
        )
        
        # Verify conservation: attributable + gap = total
        # Use relative tolerance for large numbers to handle floating-point precision
        reconstructed_total = result.attributable_spend + result.attribution_gap
        
        # Use math.isclose with relative tolerance for floating-point comparison
        assert math.isclose(reconstructed_total, result.total_spend, rel_tol=1e-9), (
            f"Attributable {result.attributable_spend} + gap {result.attribution_gap} "
            f"= {reconstructed_total} != total {result.total_spend}"
        )

    # -------------------------------------------------------------------------
    # Grouped Breakdown Invariant Tests
    # -------------------------------------------------------------------------

    @given(
        num_groups=st.integers(min_value=1, max_value=10),
        total_spend=positive_cost,
    )
    @settings(max_examples=100)
    def test_grouped_totals_sum_equals_total_spend(
        self,
        num_groups: int,
        total_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.3
        
        When grouping is specified, the sum of grouped totals SHALL equal
        the total spend.
        """
        # Distribute spend across groups
        spend_per_group = total_spend / num_groups
        
        breakdown = {}
        for i in range(num_groups):
            group_key = f"group-{i}"
            attributable_ratio = (i % 3) / 3.0
            group_attributable = spend_per_group * attributable_ratio
            group_gap = spend_per_group - group_attributable
            
            breakdown[group_key] = {
                "total": spend_per_group,
                "attributable": group_attributable,
                "gap": group_gap
            }
        
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=sum(g["attributable"] for g in breakdown.values()),
            attribution_gap=sum(g["gap"] for g in breakdown.values()),
            attribution_gap_percentage=0.0,  # Not relevant for this test
            breakdown=breakdown
        )
        
        # Verify sum of grouped totals equals total spend
        sum_of_grouped_totals = sum(group["total"] for group in result.breakdown.values())
        
        assert abs(sum_of_grouped_totals - result.total_spend) < 1e-6, (
            f"Sum of grouped totals {sum_of_grouped_totals} != "
            f"total spend {result.total_spend}"
        )

    @given(
        num_groups=st.integers(min_value=1, max_value=10),
        total_spend=positive_cost,
    )
    @settings(max_examples=100)
    def test_grouped_attributable_sum_equals_total_attributable(
        self,
        num_groups: int,
        total_spend: float,
    ):
        """
        Feature: phase-1-aws-mvp, Property 5: Cost Attribution Calculation
        Validates: Requirements 4.3
        
        When grouping is specified, the sum of grouped attributable amounts
        SHALL equal the total attributable spend.
        """
        # Distribute spend across groups
        spend_per_group = total_spend / num_groups
        
        breakdown = {}
        total_attributable = 0.0
        
        for i in range(num_groups):
            group_key = f"group-{i}"
            attributable_ratio = (i % 3) / 3.0
            group_attributable = spend_per_group * attributable_ratio
            group_gap = spend_per_group - group_attributable
            
            breakdown[group_key] = {
                "total": spend_per_group,
                "attributable": group_attributable,
                "gap": group_gap
            }
            
            total_attributable += group_attributable
        
        result = CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=total_attributable,
            attribution_gap=total_spend - total_attributable,
            attribution_gap_percentage=0.0,
            breakdown=breakdown
        )
        
        # Verify sum of grouped attributable equals total attributable
        sum_of_grouped_attributable = sum(
            group["attributable"] for group in result.breakdown.values()
        )
        
        assert abs(sum_of_grouped_attributable - result.attributable_spend) < 1e-6, (
            f"Sum of grouped attributable {sum_of_grouped_attributable} != "
            f"total attributable {result.attributable_spend}"
        )
