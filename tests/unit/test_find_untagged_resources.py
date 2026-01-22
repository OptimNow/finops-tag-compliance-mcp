"""Unit tests for find_untagged_resources tool."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.clients.aws_client import AWSClient
from mcp_server.models.policy import RequiredTag, TagPolicy
from mcp_server.services.policy_service import PolicyService
from mcp_server.tools.find_untagged_resources import find_untagged_resources


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    client = MagicMock(spec=AWSClient)
    client.region = "us-east-1"
    # Add the new method for cost data
    client.get_service_name_for_resource_type = MagicMock(
        side_effect=lambda rt: {
            "ec2:instance": "Amazon Elastic Compute Cloud - Compute",
            "rds:db": "Amazon Relational Database Service",
            "s3:bucket": "Amazon Simple Storage Service",
            "lambda:function": "AWS Lambda",
        }.get(rt, "")
    )
    return client


@pytest.fixture
def mock_policy_service():
    """Create a mock policy service."""
    service = MagicMock(spec=PolicyService)
    # Return a proper TagPolicy object instead of a dict
    service.get_policy.return_value = TagPolicy(
        version="1.0",
        required_tags=[
            RequiredTag(
                name="CostCenter", description="Cost center", applies_to=["ec2:instance", "rds:db"]
            ),
            RequiredTag(name="Environment", description="Environment", applies_to=["ec2:instance"]),
        ],
    )
    return service


@pytest.mark.asyncio
async def test_find_untagged_resources_empty_list():
    """Test finding untagged resources with empty resource types."""
    mock_client = MagicMock()
    mock_policy = MagicMock()

    with pytest.raises(ValueError, match="resource_types cannot be empty"):
        await find_untagged_resources(
            aws_client=mock_client, policy_service=mock_policy, resource_types=[]
        )


@pytest.mark.asyncio
async def test_find_untagged_resources_invalid_type():
    """Test finding untagged resources with invalid resource type."""
    mock_client = MagicMock()
    mock_policy = MagicMock()

    with pytest.raises(ValueError, match="Invalid resource types"):
        await find_untagged_resources(
            aws_client=mock_client, policy_service=mock_policy, resource_types=["invalid:type"]
        )


@pytest.mark.asyncio
async def test_find_untagged_resources_no_resources(mock_aws_client, mock_policy_service):
    """Test finding untagged resources when no resources exist."""
    # Mock AWS client to return no resources
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])

    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
    )

    assert result.total_untagged == 0
    assert len(result.resources) == 0
    assert result.total_monthly_cost == 0.0
    assert result.cost_data_note is None  # No costs requested


@pytest.mark.asyncio
async def test_find_untagged_resources_completely_untagged(mock_aws_client, mock_policy_service):
    """Test finding resources with no tags at all (without costs)."""
    # Mock AWS client to return untagged resource
    created_at = datetime.now() - timedelta(days=30)
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},  # No tags
                "created_at": created_at,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
            }
        ]
    )

    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
    )

    assert result.total_untagged == 1
    assert len(result.resources) == 1

    resource = result.resources[0]
    assert resource.resource_id == "i-12345"
    assert resource.resource_type == "ec2:instance"
    assert len(resource.missing_required_tags) == 2  # CostCenter and Environment
    assert "CostCenter" in resource.missing_required_tags
    assert "Environment" in resource.missing_required_tags
    assert resource.monthly_cost_estimate is None  # No costs requested
    assert resource.cost_source is None
    assert resource.age_days == 30


@pytest.mark.asyncio
async def test_find_untagged_resources_with_costs(mock_aws_client, mock_policy_service):
    """Test finding resources with include_costs=True."""
    created_at = datetime.now() - timedelta(days=30)
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "created_at": created_at,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
            }
        ]
    )
    # Return per-resource cost data (4-tuple: resource_costs, service_costs, costs_by_name, cost_source)
    mock_aws_client.get_cost_data_by_resource = AsyncMock(
        return_value=(
            {"i-12345": 100.0},  # resource_costs
            {"Amazon Elastic Compute Cloud - Compute": 100.0},  # service_costs
            {},  # costs_by_name
            "actual",  # cost_source
        )
    )

    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
        include_costs=True,
    )

    assert result.total_untagged == 1
    resource = result.resources[0]
    assert resource.monthly_cost_estimate == 100.0
    assert resource.cost_source == "actual"
    assert result.total_monthly_cost == 100.0
    assert result.cost_data_note is not None


@pytest.mark.asyncio
async def test_find_untagged_resources_partially_tagged(mock_aws_client, mock_policy_service):
    """Test finding resources with some tags but missing required ones."""
    created_at = datetime.now() - timedelta(days=15)
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-67890",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"Environment": "production"},  # Has Environment but missing CostCenter
                "created_at": created_at,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-67890",
            }
        ]
    )

    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
    )

    assert result.total_untagged == 1
    assert len(result.resources) == 1

    resource = result.resources[0]
    assert resource.resource_id == "i-67890"
    assert len(resource.missing_required_tags) == 1
    assert "CostCenter" in resource.missing_required_tags
    assert "Environment" not in resource.missing_required_tags
    assert resource.current_tags == {"Environment": "production"}
    assert resource.monthly_cost_estimate is None  # No costs requested
    assert resource.age_days == 15


@pytest.mark.asyncio
async def test_find_untagged_resources_fully_tagged(mock_aws_client, mock_policy_service):
    """Test that fully tagged resources are not returned."""
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-11111",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "created_at": datetime.now(),
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-11111",
            }
        ]
    )

    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
    )

    # Fully tagged resource should not be in results
    assert result.total_untagged == 0
    assert len(result.resources) == 0


@pytest.mark.asyncio
async def test_find_untagged_resources_cost_threshold(mock_aws_client, mock_policy_service):
    """Test filtering by minimum cost threshold (implies include_costs=True)."""
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-low-cost",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "created_at": datetime.now(),
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-low-cost",
            },
            {
                "resource_id": "i-high-cost",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "created_at": datetime.now(),
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-high-cost",
            },
        ]
    )
    # Return per-resource cost data (4-tuple: resource_costs, service_costs, costs_by_name, cost_source)
    mock_aws_client.get_cost_data_by_resource = AsyncMock(
        return_value=(
            {"i-low-cost": 25.0, "i-high-cost": 200.0},  # resource_costs
            {"Amazon Elastic Compute Cloud - Compute": 225.0},  # service_costs
            {},  # costs_by_name
            "actual",  # cost_source
        )
    )

    # Filter for resources costing at least $100/month (implies include_costs=True)
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
        min_cost_threshold=100.0,
    )

    # Only high-cost resource should be returned
    assert result.total_untagged == 1
    assert len(result.resources) == 1
    assert result.resources[0].resource_id == "i-high-cost"
    assert result.resources[0].cost_source == "actual"
    assert result.resources[0].monthly_cost_estimate == 200.0
    assert result.total_monthly_cost == 200.0


@pytest.mark.asyncio
async def test_find_untagged_resources_multiple_types(mock_aws_client, mock_policy_service):
    """Test finding untagged resources across multiple resource types (without costs)."""
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "created_at": datetime.now(),
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
            }
        ]
    )
    mock_aws_client.get_rds_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "db-67890",
                "resource_type": "rds:db",
                "region": "us-east-1",
                "tags": {},
                "created_at": datetime.now(),
                "arn": "arn:aws:rds:us-east-1::db:db-67890",
            }
        ]
    )

    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance", "rds:db"],
    )

    assert result.total_untagged == 2
    assert len(result.resources) == 2
    assert result.total_monthly_cost == 0.0  # No costs requested
    # Verify no cost data was fetched
    for resource in result.resources:
        assert resource.monthly_cost_estimate is None


@pytest.mark.asyncio
@patch("mcp_server.tools.find_untagged_resources.logger")
async def test_find_untagged_resources_cost_data_unavailable(
    mock_logger, mock_aws_client, mock_policy_service
):
    """Test handling when cost data is unavailable (with include_costs=True)."""
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "created_at": datetime.now(),
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
            }
        ]
    )
    # Simulate cost data fetch failure
    mock_aws_client.get_cost_data_by_resource = AsyncMock(
        side_effect=Exception("Cost Explorer unavailable")
    )

    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
        include_costs=True,
    )

    # Should still return results with None cost and estimated source
    assert result.total_untagged == 1
    assert len(result.resources) == 1
    assert result.resources[0].monthly_cost_estimate == 0.0
    assert result.resources[0].cost_source == "estimated"


@pytest.mark.asyncio
async def test_find_untagged_resources_all_resource_types(mock_aws_client, mock_policy_service):
    """Test finding untagged resources using 'all' to scan via Resource Groups Tagging API."""
    # Mock the Resource Groups Tagging API method
    mock_aws_client.get_all_tagged_resources = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},  # No tags
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
            },
            {
                "resource_id": "table/MyTable",
                "resource_type": "dynamodb:table",
                "region": "us-east-1",
                "tags": {"Environment": "prod"},  # Has some tags but missing CostCenter
                "arn": "arn:aws:dynamodb:us-east-1:123456789012:table/MyTable",
            },
            {
                "resource_id": "my-queue",
                "resource_type": "sqs:queue",
                "region": "us-east-1",
                "tags": {},  # No tags
                "arn": "arn:aws:sqs:us-east-1:123456789012:my-queue",
            },
        ]
    )

    # Update policy to apply to all resource types (empty applies_to)
    mock_policy_service.get_policy.return_value = TagPolicy(
        version="1.0",
        required_tags=[
            RequiredTag(
                name="CostCenter",
                description="Cost center",
                applies_to=[],  # Applies to all resource types
            )
        ],
    )

    result = await find_untagged_resources(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_types=["all"]
    )

    # All 3 resources should be returned (all missing CostCenter)
    assert result.total_untagged == 3
    assert len(result.resources) == 3

    # Verify resource types include non-standard types from Tagging API
    resource_types = {r.resource_type for r in result.resources}
    assert "ec2:instance" in resource_types
    assert "dynamodb:table" in resource_types
    assert "sqs:queue" in resource_types


@pytest.mark.asyncio
async def test_find_untagged_resources_all_with_filters(mock_aws_client, mock_policy_service):
    """Test 'all' resource type with tag filters passed to Tagging API."""
    mock_aws_client.get_all_tagged_resources = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"Environment": "prod"},
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
            }
        ]
    )

    mock_policy_service.get_policy.return_value = TagPolicy(
        version="1.0",
        required_tags=[RequiredTag(name="CostCenter", description="Cost center", applies_to=[])],
    )

    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["all"],
        regions=["us-east-1"],
    )

    assert result.total_untagged == 1
    # Verify the Tagging API was called
    mock_aws_client.get_all_tagged_resources.assert_called_once()


@pytest.mark.asyncio
async def test_find_untagged_resources_all_no_validation_error():
    """Test that 'all' bypasses the normal resource type validation."""
    mock_client = MagicMock()
    mock_policy = MagicMock()

    # Mock the Tagging API to return empty list
    mock_client.get_all_tagged_resources = AsyncMock(return_value=[])
    mock_policy.get_policy.return_value = TagPolicy(version="1.0", required_tags=[])

    # Should NOT raise ValueError for "all"
    result = await find_untagged_resources(
        aws_client=mock_client, policy_service=mock_policy, resource_types=["all"]
    )

    assert result.total_untagged == 0


@pytest.mark.asyncio
async def test_find_untagged_resources_age_days_none_when_no_created_at(mock_aws_client, mock_policy_service):
    """Test that age_days is None when created_at is not available (e.g., from Tagging API)."""
    # Mock resource without created_at (like from Resource Groups Tagging API)
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[
        {
            "resource_id": "i-12345",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},  # No tags
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
            "created_at": None  # Tagging API doesn't provide creation date
        }
    ])
    
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["all"]
    )
    
    assert result.total_untagged == 1
    resource = result.resources[0]
    # age_days should be None when created_at is not available
    assert resource.age_days is None
    assert resource.created_at is None


@pytest.mark.asyncio
async def test_find_untagged_resources_age_days_calculated_when_created_at_available(mock_aws_client, mock_policy_service):
    """Test that age_days is calculated when created_at is available."""
    created_at = datetime.now() - timedelta(days=45)
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[
        {
            "resource_id": "i-12345",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},  # No tags
            "created_at": created_at,
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345"
        }
    ])
    
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    assert result.total_untagged == 1
    resource = result.resources[0]
    # age_days should be calculated when created_at is available
    assert resource.age_days == 45
    assert resource.created_at == created_at
