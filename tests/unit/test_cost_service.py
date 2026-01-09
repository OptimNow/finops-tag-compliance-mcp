"""Unit tests for CostService."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_server.services.cost_service import CostService, CostAttributionResult
from mcp_server.services.policy_service import PolicyService
from mcp_server.clients.aws_client import AWSClient
from mcp_server.models.violations import Violation
from mcp_server.models.enums import ViolationType, Severity


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    client = MagicMock(spec=AWSClient)
    # Add the service name mapping method
    client.get_service_name_for_resource_type = MagicMock(side_effect=lambda rt: {
        "ec2:instance": "Amazon Elastic Compute Cloud - Compute",
        "rds:db": "Amazon Relational Database Service",
        "s3:bucket": "Amazon Simple Storage Service",
        "lambda:function": "AWS Lambda",
        "ecs:service": "Amazon Elastic Container Service",
    }.get(rt, ""))
    return client


@pytest.fixture
def mock_policy_service():
    """Create a mock policy service."""
    service = MagicMock(spec=PolicyService)
    return service


@pytest.fixture
def cost_service(mock_aws_client, mock_policy_service):
    """Create a CostService instance with mocked dependencies."""
    return CostService(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service
    )


@pytest.mark.asyncio
async def test_calculate_attribution_gap_basic(cost_service, mock_aws_client, mock_policy_service):
    """Test basic cost attribution gap calculation."""
    # Setup: 2 resources, 1 compliant, 1 non-compliant
    mock_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"CostCenter": "Engineering", "Owner": "test@example.com"},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        },
        {
            "resource_id": "i-456",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},  # Missing tags
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
        }
    ]
    
    # Mock resource fetching
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
    
    # Mock cost data - $1000 total spend for EC2, with per-resource costs
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {"i-123": 500.0, "i-456": 500.0},  # Per-resource costs
        {"Amazon Elastic Compute Cloud - Compute": 1000.0},  # Service costs
        "actual"
    ))
    
    # Mock policy validation - first resource compliant, second has violations
    def mock_validate(resource_id, resource_type, region, tags, cost_impact):
        if resource_id == "i-123":
            return []  # No violations
        else:
            return [
                Violation(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=Severity.ERROR
                )
            ]
    
    mock_policy_service.validate_resource_tags = mock_validate
    
    # Execute
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance"]
    )
    
    # Verify
    assert result.total_spend == 1000.0
    assert result.attributable_spend == 500.0  # 1 of 2 resources compliant
    assert result.attribution_gap == 500.0
    assert result.attribution_gap_percentage == 50.0


@pytest.mark.asyncio
async def test_calculate_attribution_gap_all_compliant(cost_service, mock_aws_client, mock_policy_service):
    """Test cost attribution when all resources are compliant."""
    mock_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"CostCenter": "Engineering"},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {"i-123": 1000.0},
        {"Amazon Elastic Compute Cloud - Compute": 1000.0},
        "actual"
    ))
    mock_policy_service.validate_resource_tags = MagicMock(return_value=[])
    
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance"]
    )
    
    assert result.total_spend == 1000.0
    assert result.attributable_spend == 1000.0
    assert result.attribution_gap == 0.0
    assert result.attribution_gap_percentage == 0.0


@pytest.mark.asyncio
async def test_calculate_attribution_gap_all_non_compliant(cost_service, mock_aws_client, mock_policy_service):
    """Test cost attribution when all resources are non-compliant."""
    mock_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {"i-123": 1000.0},
        {"Amazon Elastic Compute Cloud - Compute": 1000.0},
        "actual"
    ))
    mock_policy_service.validate_resource_tags = MagicMock(return_value=[
        Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR
        )
    ])
    
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance"]
    )
    
    assert result.total_spend == 1000.0
    assert result.attributable_spend == 0.0
    assert result.attribution_gap == 1000.0
    assert result.attribution_gap_percentage == 100.0


@pytest.mark.asyncio
async def test_calculate_attribution_gap_with_grouping_by_resource_type(
    cost_service, mock_aws_client, mock_policy_service
):
    """Test cost attribution gap with grouping by resource type."""
    # Setup: 2 EC2 instances, 1 RDS instance
    ec2_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"CostCenter": "Engineering"},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        },
        {
            "resource_id": "i-456",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},  # Missing tags
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
        }
    ]
    
    rds_resources = [
        {
            "resource_id": "db-789",
            "resource_type": "rds:db",
            "region": "us-east-1",
            "tags": {},  # Missing tags
            "arn": "arn:aws:rds:us-east-1:123456789012:db:db-789"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=ec2_resources)
    mock_aws_client.get_rds_instances = AsyncMock(return_value=rds_resources)
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {"i-123": 300.0, "i-456": 300.0, "db-789": 300.0},  # Per-resource costs
        {
            "Amazon Elastic Compute Cloud - Compute": 600.0,
            "Amazon Relational Database Service": 300.0
        },
        "actual"
    ))
    
    # Mock validation: first EC2 compliant, others non-compliant
    def mock_validate(resource_id, resource_type, region, tags, cost_impact):
        if resource_id == "i-123":
            return []
        else:
            return [
                Violation(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=Severity.ERROR
                )
            ]
    
    mock_policy_service.validate_resource_tags = mock_validate
    
    # Execute with grouping
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance", "rds:db"],
        group_by="resource_type"
    )
    
    # Verify overall totals
    assert result.total_spend == 900.0
    assert result.attribution_gap == 600.0  # 2 of 3 resources non-compliant
    
    # Verify breakdown
    assert result.breakdown is not None
    assert "ec2:instance" in result.breakdown
    assert "rds:db" in result.breakdown
    
    # EC2: 2 resources, 1 compliant, 1 non-compliant
    ec2_breakdown = result.breakdown["ec2:instance"]
    assert ec2_breakdown["total"] == 600.0
    assert ec2_breakdown["attributable"] == 300.0  # 1 of 2 EC2 compliant
    assert ec2_breakdown["gap"] == 300.0
    
    # RDS: 1 resource, 0 compliant
    rds_breakdown = result.breakdown["rds:db"]
    assert rds_breakdown["total"] == 300.0
    assert rds_breakdown["attributable"] == 0.0
    assert rds_breakdown["gap"] == 300.0


@pytest.mark.asyncio
async def test_calculate_attribution_gap_with_grouping_by_region(
    cost_service, mock_aws_client, mock_policy_service
):
    """Test cost attribution gap with grouping by region."""
    mock_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"CostCenter": "Engineering"},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        },
        {
            "resource_id": "i-456",
            "resource_type": "ec2:instance",
            "region": "us-west-2",
            "tags": {},
            "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {"i-123": 500.0, "i-456": 500.0},
        {"Amazon Elastic Compute Cloud - Compute": 1000.0},
        "actual"
    ))
    
    def mock_validate(resource_id, resource_type, region, tags, cost_impact):
        if resource_id == "i-123":
            return []
        else:
            return [
                Violation(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=Severity.ERROR
                )
            ]
    
    mock_policy_service.validate_resource_tags = mock_validate
    
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance"],
        group_by="region"
    )
    
    assert result.breakdown is not None
    assert "us-east-1" in result.breakdown
    assert "us-west-2" in result.breakdown
    
    # us-east-1: 1 resource, compliant
    assert result.breakdown["us-east-1"]["attributable"] == 500.0
    assert result.breakdown["us-east-1"]["gap"] == 0.0
    
    # us-west-2: 1 resource, non-compliant
    assert result.breakdown["us-west-2"]["attributable"] == 0.0
    assert result.breakdown["us-west-2"]["gap"] == 500.0


@pytest.mark.asyncio
async def test_calculate_attribution_gap_with_grouping_by_account(
    cost_service, mock_aws_client, mock_policy_service
):
    """Test cost attribution gap with grouping by account."""
    mock_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"CostCenter": "Engineering"},
            "arn": "arn:aws:ec2:us-east-1:111111111111:instance/i-123"
        },
        {
            "resource_id": "i-456",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},
            "arn": "arn:aws:ec2:us-east-1:222222222222:instance/i-456"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {"i-123": 500.0, "i-456": 500.0},
        {"Amazon Elastic Compute Cloud - Compute": 1000.0},
        "actual"
    ))
    
    def mock_validate(resource_id, resource_type, region, tags, cost_impact):
        if resource_id == "i-123":
            return []
        else:
            return [
                Violation(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=Severity.ERROR
                )
            ]
    
    mock_policy_service.validate_resource_tags = mock_validate
    
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance"],
        group_by="account"
    )
    
    assert result.breakdown is not None
    assert "111111111111" in result.breakdown
    assert "222222222222" in result.breakdown
    
    # Account 111111111111: 1 resource, compliant
    assert result.breakdown["111111111111"]["attributable"] == 500.0
    assert result.breakdown["111111111111"]["gap"] == 0.0
    
    # Account 222222222222: 1 resource, non-compliant
    assert result.breakdown["222222222222"]["attributable"] == 0.0
    assert result.breakdown["222222222222"]["gap"] == 500.0


@pytest.mark.asyncio
async def test_calculate_attribution_gap_with_grouping_by_service(
    cost_service, mock_aws_client, mock_policy_service
):
    """Test cost attribution gap with grouping by service."""
    # Setup: 2 EC2 instances, 1 RDS instance
    ec2_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"CostCenter": "Engineering"},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        },
        {
            "resource_id": "i-456",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},  # Missing tags
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
        }
    ]
    
    rds_resources = [
        {
            "resource_id": "db-789",
            "resource_type": "rds:db",
            "region": "us-east-1",
            "tags": {"CostCenter": "Data"},  # Compliant
            "arn": "arn:aws:rds:us-east-1:123456789012:db:db-789"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=ec2_resources)
    mock_aws_client.get_rds_instances = AsyncMock(return_value=rds_resources)
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {"i-123": 300.0, "i-456": 300.0, "db-789": 400.0},
        {
            "Amazon Elastic Compute Cloud - Compute": 600.0,
            "Amazon Relational Database Service": 400.0
        },
        "actual"
    ))
    
    # Mock validation: i-123 and db-789 compliant, i-456 non-compliant
    def mock_validate(resource_id, resource_type, region, tags, cost_impact):
        if resource_id in ["i-123", "db-789"]:
            return []
        else:
            return [
                Violation(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=Severity.ERROR
                )
            ]
    
    mock_policy_service.validate_resource_tags = mock_validate
    
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance", "rds:db"],
        group_by="service"
    )
    
    assert result.breakdown is not None
    assert "ec2" in result.breakdown
    assert "rds" in result.breakdown
    
    # EC2: 2 resources, 1 compliant ($300), 1 non-compliant ($300)
    ec2_breakdown = result.breakdown["ec2"]
    assert ec2_breakdown["total"] == 600.0
    assert ec2_breakdown["attributable"] == 300.0
    assert ec2_breakdown["gap"] == 300.0
    
    # RDS: 1 resource, compliant ($400)
    rds_breakdown = result.breakdown["rds"]
    assert rds_breakdown["total"] == 400.0
    assert rds_breakdown["attributable"] == 400.0
    assert rds_breakdown["gap"] == 0.0


@pytest.mark.asyncio
async def test_calculate_attribution_gap_with_custom_time_period(
    cost_service, mock_aws_client, mock_policy_service
):
    """Test cost attribution gap with custom time period."""
    mock_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"CostCenter": "Engineering"},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {"i-123": 1000.0},
        {"Amazon Elastic Compute Cloud - Compute": 1000.0},
        "actual"
    ))
    mock_policy_service.validate_resource_tags = MagicMock(return_value=[])
    
    custom_period = {
        "Start": "2025-01-01",
        "End": "2025-01-31"
    }
    
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance"],
        time_period=custom_period
    )
    
    # Verify cost data was called with custom time period
    mock_aws_client.get_cost_data_by_resource.assert_called_once()
    call_args = mock_aws_client.get_cost_data_by_resource.call_args
    assert call_args[1]["time_period"] == custom_period


@pytest.mark.asyncio
async def test_calculate_attribution_gap_no_resources(cost_service, mock_aws_client, mock_policy_service):
    """Test cost attribution gap when no resources exist."""
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {},  # No per-resource costs
        {},  # No service costs
        "estimated"
    ))
    
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance"]
    )
    
    assert result.total_spend == 0.0
    assert result.attributable_spend == 0.0
    assert result.attribution_gap == 0.0
    assert result.attribution_gap_percentage == 0.0


@pytest.mark.asyncio
@patch('mcp_server.services.cost_service.logger')
async def test_calculate_attribution_gap_handles_fetch_errors(
    mock_logger, cost_service, mock_aws_client, mock_policy_service
):
    """Test that cost service handles resource fetch errors gracefully."""
    # First resource type succeeds, second fails
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"CostCenter": "Engineering"},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        }
    ])
    mock_aws_client.get_rds_instances = AsyncMock(side_effect=Exception("API Error"))
    mock_aws_client.get_cost_data_by_resource = AsyncMock(return_value=(
        {"i-123": 1000.0},
        {"Amazon Elastic Compute Cloud - Compute": 1000.0},
        "actual"
    ))
    mock_policy_service.validate_resource_tags = MagicMock(return_value=[])
    
    # Should not raise, should continue with available resources
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance", "rds:db"]
    )
    
    # Should have processed EC2 resources despite RDS failure
    assert result.total_spend == 1000.0
    assert result.attributable_spend == 1000.0


def test_extract_account_from_arn(cost_service):
    """Test ARN account extraction."""
    from mcp_server.utils.resource_utils import extract_account_from_arn
    
    # Valid ARN
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
    account = extract_account_from_arn(arn)
    assert account == "123456789012"
    
    # Empty ARN
    account = extract_account_from_arn("")
    assert account == "unknown"
    
    # Invalid ARN format
    account = extract_account_from_arn("invalid")
    assert account == "unknown"
    
    # ARN with empty account field
    arn = "arn:aws:s3:::bucket-name"
    account = extract_account_from_arn(arn)
    assert account == "unknown"


def test_get_group_key(cost_service):
    """Test group key extraction."""
    resource = {
        "resource_id": "i-123",
        "resource_type": "ec2:instance",
        "region": "us-east-1",
        "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
    }
    
    # Group by resource type
    key = cost_service._get_group_key(resource, "resource_type")
    assert key == "ec2:instance"
    
    # Group by region
    key = cost_service._get_group_key(resource, "region")
    assert key == "us-east-1"
    
    # Group by account
    key = cost_service._get_group_key(resource, "account")
    assert key == "123456789012"
    
    # Unknown grouping
    key = cost_service._get_group_key(resource, "unknown")
    assert key == "unknown"
