"""Unit tests for find_untagged_resources tool."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_server.tools.find_untagged_resources import find_untagged_resources
from mcp_server.clients.aws_client import AWSClient
from mcp_server.services.policy_service import PolicyService
from mcp_server.models.policy import TagPolicy, RequiredTag


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    client = MagicMock(spec=AWSClient)
    client.region = "us-east-1"
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
                name="CostCenter",
                description="Cost center",
                applies_to=["ec2:instance", "rds:db"]
            ),
            RequiredTag(
                name="Environment",
                description="Environment",
                applies_to=["ec2:instance"]
            )
        ]
    )
    return service


@pytest.mark.asyncio
async def test_find_untagged_resources_empty_list():
    """Test finding untagged resources with empty resource types."""
    mock_client = MagicMock()
    mock_policy = MagicMock()
    
    with pytest.raises(ValueError, match="resource_types cannot be empty"):
        await find_untagged_resources(
            aws_client=mock_client,
            policy_service=mock_policy,
            resource_types=[]
        )


@pytest.mark.asyncio
async def test_find_untagged_resources_invalid_type():
    """Test finding untagged resources with invalid resource type."""
    mock_client = MagicMock()
    mock_policy = MagicMock()
    
    with pytest.raises(ValueError, match="Invalid resource types"):
        await find_untagged_resources(
            aws_client=mock_client,
            policy_service=mock_policy,
            resource_types=["invalid:type"]
        )


@pytest.mark.asyncio
async def test_find_untagged_resources_no_resources(mock_aws_client, mock_policy_service):
    """Test finding untagged resources when no resources exist."""
    # Mock AWS client to return no resources
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])
    mock_aws_client.get_cost_data = AsyncMock(return_value={})
    
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    assert result.total_untagged == 0
    assert len(result.resources) == 0
    assert result.total_monthly_cost == 0.0


@pytest.mark.asyncio
async def test_find_untagged_resources_completely_untagged(mock_aws_client, mock_policy_service):
    """Test finding resources with no tags at all."""
    # Mock AWS client to return untagged resource
    created_at = datetime.now() - timedelta(days=30)
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
    mock_aws_client.get_cost_data = AsyncMock(return_value={"i-12345": 100.0})
    
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    assert result.total_untagged == 1
    assert len(result.resources) == 1
    
    resource = result.resources[0]
    assert resource.resource_id == "i-12345"
    assert resource.resource_type == "ec2:instance"
    assert len(resource.missing_required_tags) == 2  # CostCenter and Environment
    assert "CostCenter" in resource.missing_required_tags
    assert "Environment" in resource.missing_required_tags
    assert resource.monthly_cost_estimate == 100.0
    assert resource.age_days == 30


@pytest.mark.asyncio
async def test_find_untagged_resources_partially_tagged(mock_aws_client, mock_policy_service):
    """Test finding resources with some tags but missing required ones."""
    created_at = datetime.now() - timedelta(days=15)
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[
        {
            "resource_id": "i-67890",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"Environment": "production"},  # Has Environment but missing CostCenter
            "created_at": created_at,
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-67890"
        }
    ])
    mock_aws_client.get_cost_data = AsyncMock(return_value={"i-67890": 50.0})
    
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    assert result.total_untagged == 1
    assert len(result.resources) == 1
    
    resource = result.resources[0]
    assert resource.resource_id == "i-67890"
    assert len(resource.missing_required_tags) == 1
    assert "CostCenter" in resource.missing_required_tags
    assert "Environment" not in resource.missing_required_tags
    assert resource.current_tags == {"Environment": "production"}
    assert resource.monthly_cost_estimate == 50.0
    assert resource.age_days == 15


@pytest.mark.asyncio
async def test_find_untagged_resources_fully_tagged(mock_aws_client, mock_policy_service):
    """Test that fully tagged resources are not returned."""
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[
        {
            "resource_id": "i-11111",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {
                "CostCenter": "Engineering",
                "Environment": "production"
            },
            "created_at": datetime.now(),
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-11111"
        }
    ])
    mock_aws_client.get_cost_data = AsyncMock(return_value={"i-11111": 75.0})
    
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    # Fully tagged resource should not be in results
    assert result.total_untagged == 0
    assert len(result.resources) == 0


@pytest.mark.asyncio
async def test_find_untagged_resources_cost_threshold(mock_aws_client, mock_policy_service):
    """Test filtering by minimum cost threshold."""
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[
        {
            "resource_id": "i-low-cost",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},
            "created_at": datetime.now(),
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-low-cost"
        },
        {
            "resource_id": "i-high-cost",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},
            "created_at": datetime.now(),
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-high-cost"
        }
    ])
    mock_aws_client.get_cost_data = AsyncMock(return_value={
        "i-low-cost": 25.0,
        "i-high-cost": 200.0
    })
    
    # Filter for resources costing at least $100/month
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
        min_cost_threshold=100.0
    )
    
    # Only high-cost resource should be returned
    assert result.total_untagged == 1
    assert len(result.resources) == 1
    assert result.resources[0].resource_id == "i-high-cost"
    assert result.total_monthly_cost == 200.0


@pytest.mark.asyncio
async def test_find_untagged_resources_multiple_types(mock_aws_client, mock_policy_service):
    """Test finding untagged resources across multiple resource types."""
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[
        {
            "resource_id": "i-12345",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},
            "created_at": datetime.now(),
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345"
        }
    ])
    mock_aws_client.get_rds_instances = AsyncMock(return_value=[
        {
            "resource_id": "db-67890",
            "resource_type": "rds:db",
            "region": "us-east-1",
            "tags": {},
            "created_at": datetime.now(),
            "arn": "arn:aws:rds:us-east-1::db:db-67890"
        }
    ])
    mock_aws_client.get_cost_data = AsyncMock(return_value={
        "i-12345": 100.0,
        "db-67890": 150.0
    })
    
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance", "rds:db"]
    )
    
    assert result.total_untagged == 2
    assert len(result.resources) == 2
    assert result.total_monthly_cost == 250.0


@pytest.mark.asyncio
@patch('mcp_server.tools.find_untagged_resources.logger')
async def test_find_untagged_resources_cost_data_unavailable(mock_logger, mock_aws_client, mock_policy_service):
    """Test handling when cost data is unavailable."""
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[
        {
            "resource_id": "i-12345",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},
            "created_at": datetime.now(),
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345"
        }
    ])
    # Simulate cost data fetch failure
    mock_aws_client.get_cost_data = AsyncMock(side_effect=Exception("Cost Explorer unavailable"))
    
    result = await find_untagged_resources(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    # Should still return results with zero cost
    assert result.total_untagged == 1
    assert len(result.resources) == 1
    assert result.resources[0].monthly_cost_estimate == 0.0
