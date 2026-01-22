"""
Property-based tests for untagged resource discovery.

Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
Validates: Requirements 2.1, 2.2, 2.5

Property 4 states:
*For any* untagged resource returned, the result SHALL include: resource ID,
resource type, region, current tags (even if empty), monthly cost estimate,
and age in days. Resources with no tags or missing required tags SHALL be
included in untagged searches.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from mcp_server.clients.aws_client import AWSClient
from mcp_server.models.untagged import UntaggedResourcesResult
from mcp_server.services.policy_service import PolicyService
from mcp_server.tools.find_untagged_resources import (
    _calculate_age_days,
    _get_required_tags_for_resource,
    find_untagged_resources,
)

# =============================================================================
# Strategies for generating test data
# =============================================================================

# Valid resource types supported by the system
VALID_RESOURCE_TYPES = ["ec2:instance", "rds:db", "s3:bucket", "lambda:function", "ecs:service"]
VALID_REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]

# Strategy for generating resource IDs
resource_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=50,
).map(lambda s: f"resource-{s}")

# Strategy for generating tag keys
tag_key_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
)

# Strategy for generating tag values
tag_value_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd", "Zs"), whitelist_characters="-_"
    ),
    min_size=0,
    max_size=50,
)

# Strategy for generating tags dictionary
tags_strategy = st.dictionaries(
    keys=tag_key_strategy,
    values=tag_value_strategy,
    min_size=0,
    max_size=10,
)

# Strategy for generating cost values
cost_strategy = st.floats(min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False)

# Strategy for generating age in days
age_days_strategy = st.integers(min_value=0, max_value=3650)  # Up to 10 years


# =============================================================================
# Helper functions
# =============================================================================


def create_mock_aws_client():
    """Create a mock AWS client."""
    client = MagicMock(spec=AWSClient)
    client.region = "us-east-1"
    # Add the service name mapping method
    client.get_service_name_for_resource_type = MagicMock(
        side_effect=lambda rt: {
            "ec2:instance": "Amazon Elastic Compute Cloud - Compute",
            "rds:db": "Amazon Relational Database Service",
            "s3:bucket": "Amazon Simple Storage Service",
            "lambda:function": "AWS Lambda",
            "ecs:service": "Amazon Elastic Container Service",
        }.get(rt, "")
    )
    return client


def create_mock_policy_service(required_tags: list[dict] = None):
    """Create a mock policy service with configurable required tags."""
    from mcp_server.models.policy import RequiredTag, TagPolicy

    if required_tags is None:
        required_tags = [
            RequiredTag(
                name="CostCenter",
                description="Cost center for billing",
                applies_to=VALID_RESOURCE_TYPES,
            ),
            RequiredTag(
                name="Environment",
                description="Deployment environment",
                applies_to=["ec2:instance", "rds:db", "lambda:function"],
            ),
        ]
    else:
        # Convert dict format to RequiredTag objects
        required_tags = [
            RequiredTag(
                name=tag["name"],
                description=tag.get("description", ""),
                applies_to=tag.get("applies_to", []),
            )
            for tag in required_tags
        ]

    service = MagicMock(spec=PolicyService)
    service.get_policy.return_value = TagPolicy(
        version="1.0",
        required_tags=required_tags,
        optional_tags=[],
    )
    return service


def generate_resource(
    resource_id: str,
    resource_type: str,
    region: str,
    tags: dict,
    cost: float,
    age_days: int,
) -> dict:
    """Generate a resource dictionary for testing."""
    created_at = datetime.now() - timedelta(days=age_days)
    return {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "region": region,
        "tags": tags,
        "created_at": created_at,
        "arn": f"arn:aws:{resource_type.split(':')[0]}:{region}:123456789012:{resource_type.split(':')[1]}/{resource_id}",
    }


# =============================================================================
# Property 4: Resource Metadata Completeness
# =============================================================================


class TestResourceMetadataCompleteness:
    """
    Property 4: Resource Metadata Completeness

    For any untagged resource returned, the result SHALL include: resource ID,
    resource type, region, current tags (even if empty), monthly cost estimate,
    and age in days. Resources with no tags or missing required tags SHALL be
    included in untagged searches.

    Validates: Requirements 2.1, 2.2, 2.5
    """

    @given(
        resource_id=resource_id_strategy,
        resource_type=st.sampled_from(VALID_RESOURCE_TYPES),
        region=st.sampled_from(VALID_REGIONS),
        cost=cost_strategy,
        age_days=age_days_strategy,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_untagged_resource_has_all_required_fields(
        self,
        resource_id: str,
        resource_type: str,
        region: str,
        cost: float,
        age_days: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.1, 2.2, 2.5

        For any untagged resource returned, the result SHALL include:
        resource ID, resource type, region, current tags (even if empty),
        monthly cost estimate, and age in days.
        """
        # Create mocks
        mock_aws_client = create_mock_aws_client()
        mock_policy_service = create_mock_policy_service()

        # Generate a completely untagged resource
        resource = generate_resource(
            resource_id=resource_id,
            resource_type=resource_type,
            region=region,
            tags={},  # No tags
            cost=cost,
            age_days=age_days,
        )

        # Configure mock to return our resource
        fetcher_method = f"get_{resource_type.replace(':', '_').replace('instance', 'instances').replace('db', 'instances').replace('bucket', 'buckets').replace('function', 'functions').replace('service', 'services')}"

        # Set up all fetchers to return empty by default
        mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])
        mock_aws_client.get_rds_instances = AsyncMock(return_value=[])
        mock_aws_client.get_s3_buckets = AsyncMock(return_value=[])
        mock_aws_client.get_lambda_functions = AsyncMock(return_value=[])
        mock_aws_client.get_ecs_services = AsyncMock(return_value=[])

        # Set up the specific fetcher to return our resource
        if resource_type == "ec2:instance":
            mock_aws_client.get_ec2_instances = AsyncMock(return_value=[resource])
        elif resource_type == "rds:db":
            mock_aws_client.get_rds_instances = AsyncMock(return_value=[resource])
        elif resource_type == "s3:bucket":
            mock_aws_client.get_s3_buckets = AsyncMock(return_value=[resource])
        elif resource_type == "lambda:function":
            mock_aws_client.get_lambda_functions = AsyncMock(return_value=[resource])
        elif resource_type == "ecs:service":
            mock_aws_client.get_ecs_services = AsyncMock(return_value=[resource])

        mock_aws_client.get_cost_data_by_resource = AsyncMock(
            return_value=(
                {resource_id: cost},
                {"Amazon Elastic Compute Cloud - Compute": cost},
                {},  # costs_by_name
                "actual",
            )
        )

        # Execute - without include_costs, costs should be None
        result = await find_untagged_resources(
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
            resource_types=[resource_type],
        )

        # Verify result structure
        assert isinstance(result, UntaggedResourcesResult)
        assert result.total_untagged >= 0
        assert isinstance(result.resources, list)
        assert isinstance(result.scan_timestamp, datetime)

        # If resource was found as untagged, verify all required fields
        if result.total_untagged > 0:
            untagged = result.resources[0]

            # Verify all required fields are present
            assert untagged.resource_id is not None, "resource_id must be present"
            assert untagged.resource_type is not None, "resource_type must be present"
            assert untagged.region is not None, "region must be present"
            assert untagged.current_tags is not None, "current_tags must be present (even if empty)"
            # Cost is optional when include_costs=False
            assert (
                untagged.monthly_cost_estimate is None
            ), "monthly_cost_estimate should be None when include_costs=False"
            assert isinstance(untagged.age_days, int), "age_days must be an integer"

            # Verify field values match input
            assert untagged.resource_id == resource_id
            assert untagged.resource_type == resource_type
            assert untagged.region == region

    @given(
        num_resources=st.integers(min_value=1, max_value=20),
        resource_type=st.sampled_from(VALID_RESOURCE_TYPES),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_completely_untagged_resources_are_included(
        self,
        num_resources: int,
        resource_type: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.1

        Resources with no tags SHALL be included in untagged searches.
        """
        # Create mocks
        mock_aws_client = create_mock_aws_client()
        mock_policy_service = create_mock_policy_service()

        # Generate completely untagged resources
        resources = []
        cost_data = {}
        for i in range(num_resources):
            rid = f"resource-{i}"
            resources.append(
                generate_resource(
                    resource_id=rid,
                    resource_type=resource_type,
                    region="us-east-1",
                    tags={},  # No tags at all
                    cost=100.0,
                    age_days=30,
                )
            )
            cost_data[rid] = 100.0

        # Set up all fetchers to return empty by default
        mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])
        mock_aws_client.get_rds_instances = AsyncMock(return_value=[])
        mock_aws_client.get_s3_buckets = AsyncMock(return_value=[])
        mock_aws_client.get_lambda_functions = AsyncMock(return_value=[])
        mock_aws_client.get_ecs_services = AsyncMock(return_value=[])

        # Set up the specific fetcher
        if resource_type == "ec2:instance":
            mock_aws_client.get_ec2_instances = AsyncMock(return_value=resources)
        elif resource_type == "rds:db":
            mock_aws_client.get_rds_instances = AsyncMock(return_value=resources)
        elif resource_type == "s3:bucket":
            mock_aws_client.get_s3_buckets = AsyncMock(return_value=resources)
        elif resource_type == "lambda:function":
            mock_aws_client.get_lambda_functions = AsyncMock(return_value=resources)
        elif resource_type == "ecs:service":
            mock_aws_client.get_ecs_services = AsyncMock(return_value=resources)

        mock_aws_client.get_cost_data_by_resource = AsyncMock(
            return_value=(
                cost_data,
                {"Amazon Elastic Compute Cloud - Compute": sum(cost_data.values())},
                {},  # costs_by_name
                "actual",
            )
        )

        # Execute
        result = await find_untagged_resources(
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
            resource_types=[resource_type],
        )

        # All completely untagged resources should be included
        assert (
            result.total_untagged == num_resources
        ), f"Expected {num_resources} untagged resources, got {result.total_untagged}"

        # Verify each resource has all required metadata
        for untagged in result.resources:
            assert untagged.resource_id is not None
            assert untagged.resource_type == resource_type
            assert untagged.region is not None
            assert untagged.current_tags == {}  # Empty tags
            # Cost is None when include_costs=False
            assert untagged.monthly_cost_estimate is None
            assert isinstance(untagged.age_days, int)

    @given(
        num_resources=st.integers(min_value=1, max_value=20),
        resource_type=st.sampled_from(VALID_RESOURCE_TYPES),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_partially_tagged_resources_are_included(
        self,
        num_resources: int,
        resource_type: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.1

        Resources missing required tags SHALL be included in untagged searches,
        even if they have some tags.
        """
        # Create mocks
        mock_aws_client = create_mock_aws_client()
        mock_policy_service = create_mock_policy_service()

        # Generate partially tagged resources (have some tags but missing required ones)
        resources = []
        cost_data = {}
        for i in range(num_resources):
            rid = f"resource-{i}"
            resources.append(
                generate_resource(
                    resource_id=rid,
                    resource_type=resource_type,
                    region="us-east-1",
                    tags={"SomeOptionalTag": "value"},  # Has tags but missing required ones
                    cost=100.0,
                    age_days=30,
                )
            )
            cost_data[rid] = 100.0

        # Set up all fetchers to return empty by default
        mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])
        mock_aws_client.get_rds_instances = AsyncMock(return_value=[])
        mock_aws_client.get_s3_buckets = AsyncMock(return_value=[])
        mock_aws_client.get_lambda_functions = AsyncMock(return_value=[])
        mock_aws_client.get_ecs_services = AsyncMock(return_value=[])

        # Set up the specific fetcher
        if resource_type == "ec2:instance":
            mock_aws_client.get_ec2_instances = AsyncMock(return_value=resources)
        elif resource_type == "rds:db":
            mock_aws_client.get_rds_instances = AsyncMock(return_value=resources)
        elif resource_type == "s3:bucket":
            mock_aws_client.get_s3_buckets = AsyncMock(return_value=resources)
        elif resource_type == "lambda:function":
            mock_aws_client.get_lambda_functions = AsyncMock(return_value=resources)
        elif resource_type == "ecs:service":
            mock_aws_client.get_ecs_services = AsyncMock(return_value=resources)

        mock_aws_client.get_cost_data_by_resource = AsyncMock(
            return_value=(
                cost_data,
                {"Amazon Elastic Compute Cloud - Compute": sum(cost_data.values())},
                {},  # costs_by_name
                "actual",
            )
        )

        # Execute
        result = await find_untagged_resources(
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
            resource_types=[resource_type],
        )

        # All partially tagged resources should be included
        assert (
            result.total_untagged == num_resources
        ), f"Expected {num_resources} partially tagged resources, got {result.total_untagged}"

        # Verify each resource has current_tags preserved
        for untagged in result.resources:
            assert untagged.current_tags == {"SomeOptionalTag": "value"}
            assert len(untagged.missing_required_tags) > 0

    @given(
        cost=cost_strategy,
        age_days=age_days_strategy,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_cost_estimate_is_included(
        self,
        cost: float,
        age_days: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.2

        For any untagged resource returned, the result SHALL include
        the monthly cost estimate when include_costs=True.
        """
        # Create mocks
        mock_aws_client = create_mock_aws_client()
        mock_policy_service = create_mock_policy_service()

        resource_id = "test-resource"
        resource = generate_resource(
            resource_id=resource_id,
            resource_type="ec2:instance",
            region="us-east-1",
            tags={},
            cost=cost,
            age_days=age_days,
        )

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=[resource])
        mock_aws_client.get_rds_instances = AsyncMock(return_value=[])
        mock_aws_client.get_s3_buckets = AsyncMock(return_value=[])
        mock_aws_client.get_lambda_functions = AsyncMock(return_value=[])
        mock_aws_client.get_ecs_services = AsyncMock(return_value=[])
        mock_aws_client.get_cost_data_by_resource = AsyncMock(
            return_value=(
                {resource_id: cost},
                {"Amazon Elastic Compute Cloud - Compute": cost},
                {},  # costs_by_name
                "actual",
            )
        )

        # Execute with include_costs=True to get cost data
        result = await find_untagged_resources(
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
            resource_types=["ec2:instance"],
            include_costs=True,
        )

        # Verify cost is included
        assert result.total_untagged == 1
        untagged = result.resources[0]
        assert (
            untagged.monthly_cost_estimate == cost
        ), f"Expected cost {cost}, got {untagged.monthly_cost_estimate}"

    @given(
        age_days=age_days_strategy,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_age_in_days_is_included(
        self,
        age_days: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.5

        For any untagged resource returned, the result SHALL include
        the resource age in days.
        """
        # Create mocks
        mock_aws_client = create_mock_aws_client()
        mock_policy_service = create_mock_policy_service()

        resource_id = "test-resource"
        resource = generate_resource(
            resource_id=resource_id,
            resource_type="ec2:instance",
            region="us-east-1",
            tags={},
            cost=100.0,
            age_days=age_days,
        )

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=[resource])
        mock_aws_client.get_rds_instances = AsyncMock(return_value=[])
        mock_aws_client.get_s3_buckets = AsyncMock(return_value=[])
        mock_aws_client.get_lambda_functions = AsyncMock(return_value=[])
        mock_aws_client.get_ecs_services = AsyncMock(return_value=[])
        mock_aws_client.get_cost_data_by_resource = AsyncMock(
            return_value=(
                {resource_id: 100.0},
                {"Amazon Elastic Compute Cloud - Compute": 100.0},
                {},  # costs_by_name
                "actual",
            )
        )

        # Execute
        result = await find_untagged_resources(
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
            resource_types=["ec2:instance"],
        )

        # Verify age is included and approximately correct
        assert result.total_untagged == 1
        untagged = result.resources[0]
        assert isinstance(untagged.age_days, int), "age_days must be an integer"
        # Allow 1 day tolerance for timing issues
        assert (
            abs(untagged.age_days - age_days) <= 1
        ), f"Expected age ~{age_days} days, got {untagged.age_days}"

    @given(
        num_untagged=st.integers(min_value=0, max_value=10),
        num_tagged=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_fully_tagged_resources_are_excluded(
        self,
        num_untagged: int,
        num_tagged: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.1

        Resources that have all required tags SHALL NOT be included
        in untagged searches.
        """
        # Skip if no resources to test
        assume(num_untagged + num_tagged > 0)

        # Create mocks
        mock_aws_client = create_mock_aws_client()
        mock_policy_service = create_mock_policy_service()

        # Generate mix of tagged and untagged resources
        resources = []
        cost_data = {}

        # Untagged resources
        for i in range(num_untagged):
            rid = f"untagged-{i}"
            resources.append(
                generate_resource(
                    resource_id=rid,
                    resource_type="ec2:instance",
                    region="us-east-1",
                    tags={},
                    cost=100.0,
                    age_days=30,
                )
            )
            cost_data[rid] = 100.0

        # Fully tagged resources (have all required tags)
        for i in range(num_tagged):
            rid = f"tagged-{i}"
            resources.append(
                generate_resource(
                    resource_id=rid,
                    resource_type="ec2:instance",
                    region="us-east-1",
                    tags={"CostCenter": "Engineering", "Environment": "production"},
                    cost=100.0,
                    age_days=30,
                )
            )
            cost_data[rid] = 100.0

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=resources)
        mock_aws_client.get_rds_instances = AsyncMock(return_value=[])
        mock_aws_client.get_s3_buckets = AsyncMock(return_value=[])
        mock_aws_client.get_lambda_functions = AsyncMock(return_value=[])
        mock_aws_client.get_ecs_services = AsyncMock(return_value=[])
        mock_aws_client.get_cost_data_by_resource = AsyncMock(
            return_value=(
                cost_data,
                {"Amazon Elastic Compute Cloud - Compute": sum(cost_data.values())},
                {},  # costs_by_name
                "actual",
            )
        )

        # Execute
        result = await find_untagged_resources(
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
            resource_types=["ec2:instance"],
        )

        # Only untagged resources should be included
        assert (
            result.total_untagged == num_untagged
        ), f"Expected {num_untagged} untagged resources, got {result.total_untagged}"

        # Verify no fully tagged resources are in results
        for untagged in result.resources:
            assert untagged.resource_id.startswith(
                "untagged-"
            ), f"Fully tagged resource {untagged.resource_id} should not be in results"

    @given(
        costs=st.lists(cost_strategy, min_size=1, max_size=20),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_total_monthly_cost_is_sum_of_individual_costs(
        self,
        costs: list[float],
    ):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.2

        The total_monthly_cost in the result SHALL equal the sum of
        monthly_cost_estimate for all returned untagged resources when include_costs=True.
        """
        # Create mocks
        mock_aws_client = create_mock_aws_client()
        mock_policy_service = create_mock_policy_service()

        # Generate untagged resources with varying costs
        resources = []
        cost_data = {}
        for i, cost in enumerate(costs):
            rid = f"resource-{i}"
            resources.append(
                generate_resource(
                    resource_id=rid,
                    resource_type="ec2:instance",
                    region="us-east-1",
                    tags={},
                    cost=cost,
                    age_days=30,
                )
            )
            cost_data[rid] = cost

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=resources)
        mock_aws_client.get_rds_instances = AsyncMock(return_value=[])
        mock_aws_client.get_s3_buckets = AsyncMock(return_value=[])
        mock_aws_client.get_lambda_functions = AsyncMock(return_value=[])
        mock_aws_client.get_ecs_services = AsyncMock(return_value=[])
        mock_aws_client.get_cost_data_by_resource = AsyncMock(
            return_value=(
                cost_data,
                {"Amazon Elastic Compute Cloud - Compute": sum(cost_data.values())},
                {},  # costs_by_name
                "actual",
            )
        )

        # Execute with include_costs=True to get cost data
        result = await find_untagged_resources(
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
            resource_types=["ec2:instance"],
            include_costs=True,
        )

        # Verify total cost equals sum of individual costs
        expected_total = sum(costs)
        assert (
            abs(result.total_monthly_cost - expected_total) < 0.01
        ), f"Expected total cost {expected_total}, got {result.total_monthly_cost}"


# =============================================================================
# Helper function tests
# =============================================================================


class TestCalculateAgeDays:
    """Tests for the _calculate_age_days helper function."""

    @given(age_days=st.integers(min_value=0, max_value=3650))
    @settings(max_examples=100)
    def test_age_calculation_is_non_negative(self, age_days: int):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.5

        The calculated age in days SHALL always be non-negative.
        """
        created_at = datetime.now() - timedelta(days=age_days)
        calculated_age = _calculate_age_days(created_at)

        assert calculated_age >= 0, f"Age should be non-negative, got {calculated_age}"

    def test_age_calculation_with_none_returns_zero(self):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.5

        When created_at is None, the age SHALL be 0.
        """
        calculated_age = _calculate_age_days(None)
        assert calculated_age == 0, f"Expected 0 for None created_at, got {calculated_age}"


class TestGetRequiredTagsForResource:
    """Tests for the _get_required_tags_for_resource helper function."""

    @given(resource_type=st.sampled_from(VALID_RESOURCE_TYPES))
    @settings(max_examples=100)
    def test_returns_list_of_tag_names(self, resource_type: str):
        """
        Feature: phase-1-aws-mvp, Property 4: Resource Metadata Completeness
        Validates: Requirements 2.1

        The function SHALL return a list of required tag names for the resource type.
        """
        from mcp_server.models.policy import RequiredTag, TagPolicy

        policy = TagPolicy(
            version="1.0",
            required_tags=[
                RequiredTag(
                    name="CostCenter", description="Cost center", applies_to=VALID_RESOURCE_TYPES
                ),
                RequiredTag(
                    name="Environment",
                    description="Environment",
                    applies_to=["ec2:instance", "rds:db"],
                ),
            ],
            optional_tags=[],
        )

        required_tags = _get_required_tags_for_resource(policy, resource_type)

        assert isinstance(required_tags, list)
        assert all(isinstance(tag, str) for tag in required_tags)
        assert "CostCenter" in required_tags  # Applies to all types
