"""Unit tests for get_cost_attribution_gap tool."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_server.tools.get_cost_attribution_gap import get_cost_attribution_gap
from mcp_server.clients.aws_client import AWSClient
from mcp_server.services.policy_service import PolicyService
from mcp_server.models.violations import Violation
from mcp_server.models.enums import ViolationType, Severity


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
    service.get_policy.return_value = {
        "version": "1.0",
        "required_tags": [
            {
                "name": "CostCenter",
                "description": "Cost center",
                "applies_to": ["ec2:instance", "rds:db"]
            }
        ]
    }
    return service


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_empty_resource_types():
    """Test that empty resource_types raises ValueError."""
    mock_client = MagicMock()
    mock_policy = MagicMock()
    
    with pytest.raises(ValueError, match="resource_types cannot be empty"):
        await get_cost_attribution_gap(
            aws_client=mock_client,
            policy_service=mock_policy,
            resource_types=[]
        )


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_invalid_resource_type():
    """Test that invalid resource types raise ValueError."""
    mock_client = MagicMock()
    mock_policy = MagicMock()
    
    with pytest.raises(ValueError, match="Invalid resource types"):
        await get_cost_attribution_gap(
            aws_client=mock_client,
            policy_service=mock_policy,
            resource_types=["invalid:type"]
        )


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_invalid_group_by():
    """Test that invalid group_by parameter raises ValueError."""
    mock_client = MagicMock()
    mock_policy = MagicMock()
    
    with pytest.raises(ValueError, match="Invalid group_by"):
        await get_cost_attribution_gap(
            aws_client=mock_client,
            policy_service=mock_policy,
            resource_types=["ec2:instance"],
            group_by="invalid_grouping"
        )


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_invalid_time_period_format():
    """Test that invalid time period format raises ValueError."""
    mock_client = MagicMock()
    mock_policy = MagicMock()
    
    # Missing End date
    with pytest.raises(ValueError, match="time_period must contain"):
        await get_cost_attribution_gap(
            aws_client=mock_client,
            policy_service=mock_policy,
            resource_types=["ec2:instance"],
            time_period={"Start": "2025-01-01"}
        )
    
    # Invalid date format
    with pytest.raises(ValueError, match="Invalid date format"):
        await get_cost_attribution_gap(
            aws_client=mock_client,
            policy_service=mock_policy,
            resource_types=["ec2:instance"],
            time_period={"Start": "01-01-2025", "End": "01-31-2025"}
        )


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_basic(mock_aws_client, mock_policy_service):
    """Test basic cost attribution gap calculation."""
    # Setup: 2 resources, 1 compliant, 1 non-compliant
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
            "region": "us-east-1",
            "tags": {},  # Missing required tag
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 1000.0})
    
    # Mock validation: first resource compliant, second has violations
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
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    # Verify result structure
    assert result.total_spend == 1000.0
    assert result.attributable_spend == 500.0  # 1 of 2 resources compliant
    assert result.attribution_gap == 500.0
    assert result.attribution_gap_percentage == 50.0
    assert result.time_period is not None
    assert "Start" in result.time_period
    assert "End" in result.time_period
    assert result.scan_timestamp is not None


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_all_compliant(mock_aws_client, mock_policy_service):
    """Test cost attribution when all resources are compliant."""
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
            "region": "us-east-1",
            "tags": {"CostCenter": "Marketing"},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 1000.0})
    mock_policy_service.validate_resource_tags = MagicMock(return_value=[])
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    assert result.total_spend == 1000.0
    assert result.attributable_spend == 1000.0
    assert result.attribution_gap == 0.0
    assert result.attribution_gap_percentage == 0.0


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_all_non_compliant(mock_aws_client, mock_policy_service):
    """Test cost attribution when all resources are non-compliant."""
    mock_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        },
        {
            "resource_id": "i-456",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 1000.0})
    
    def mock_validate(resource_id, resource_type, region, tags, cost_impact):
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
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    assert result.total_spend == 1000.0
    assert result.attributable_spend == 0.0
    assert result.attribution_gap == 1000.0
    assert result.attribution_gap_percentage == 100.0


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_no_resources(mock_aws_client, mock_policy_service):
    """Test cost attribution gap when no resources exist."""
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])
    mock_aws_client.get_cost_data = AsyncMock(return_value={})
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    assert result.total_spend == 0.0
    assert result.attributable_spend == 0.0
    assert result.attribution_gap == 0.0
    assert result.attribution_gap_percentage == 0.0


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_with_custom_time_period(mock_aws_client, mock_policy_service):
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
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 1000.0})
    mock_policy_service.validate_resource_tags = MagicMock(return_value=[])
    
    custom_period = {
        "Start": "2025-01-01",
        "End": "2025-01-31"
    }
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
        time_period=custom_period
    )
    
    # Verify time period is returned correctly
    assert result.time_period == custom_period
    
    # Verify cost data was called with custom time period
    mock_aws_client.get_cost_data.assert_called_once()
    call_args = mock_aws_client.get_cost_data.call_args
    assert call_args[1]["time_period"] == custom_period


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_group_by_resource_type(mock_aws_client, mock_policy_service):
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
            "tags": {},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
        }
    ]
    
    rds_resources = [
        {
            "resource_id": "db-789",
            "resource_type": "rds:db",
            "region": "us-east-1",
            "tags": {},
            "arn": "arn:aws:rds:us-east-1:123456789012:db:db-789"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=ec2_resources)
    mock_aws_client.get_rds_instances = AsyncMock(return_value=rds_resources)
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 600.0, "Amazon RDS": 300.0})
    
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
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance", "rds:db"],
        group_by="resource_type"
    )
    
    # Verify overall totals
    assert result.total_spend == 900.0
    assert result.attribution_gap == 600.0
    
    # Verify breakdown exists
    assert result.breakdown is not None
    assert "ec2:instance" in result.breakdown
    assert "rds:db" in result.breakdown
    
    # EC2: 2 resources, 1 compliant
    ec2_breakdown = result.breakdown["ec2:instance"]
    assert ec2_breakdown.total == 600.0
    assert ec2_breakdown.attributable == 300.0
    assert ec2_breakdown.gap == 300.0
    
    # RDS: 1 resource, 0 compliant
    rds_breakdown = result.breakdown["rds:db"]
    assert rds_breakdown.total == 300.0
    assert rds_breakdown.attributable == 0.0
    assert rds_breakdown.gap == 300.0


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_group_by_region(mock_aws_client, mock_policy_service):
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
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 1000.0})
    
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
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
        group_by="region"
    )
    
    assert result.breakdown is not None
    assert "us-east-1" in result.breakdown
    assert "us-west-2" in result.breakdown
    
    # us-east-1: 1 resource, compliant
    assert result.breakdown["us-east-1"].attributable == 500.0
    assert result.breakdown["us-east-1"].gap == 0.0
    
    # us-west-2: 1 resource, non-compliant
    assert result.breakdown["us-west-2"].attributable == 0.0
    assert result.breakdown["us-west-2"].gap == 500.0


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_group_by_account(mock_aws_client, mock_policy_service):
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
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 1000.0})
    
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
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"],
        group_by="account"
    )
    
    assert result.breakdown is not None
    assert "111111111111" in result.breakdown
    assert "222222222222" in result.breakdown
    
    # Account 111111111111: 1 resource, compliant
    assert result.breakdown["111111111111"].attributable == 500.0
    assert result.breakdown["111111111111"].gap == 0.0
    
    # Account 222222222222: 1 resource, non-compliant
    assert result.breakdown["222222222222"].attributable == 0.0
    assert result.breakdown["222222222222"].gap == 500.0


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_multiple_resource_types(mock_aws_client, mock_policy_service):
    """Test cost attribution gap with multiple resource types."""
    ec2_resources = [
        {
            "resource_id": "i-123",
            "resource_type": "ec2:instance",
            "region": "us-east-1",
            "tags": {"CostCenter": "Engineering"},
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        }
    ]
    
    rds_resources = [
        {
            "resource_id": "db-456",
            "resource_type": "rds:db",
            "region": "us-east-1",
            "tags": {"CostCenter": "Marketing"},
            "arn": "arn:aws:rds:us-east-1:123456789012:db:db-456"
        }
    ]
    
    s3_resources = [
        {
            "resource_id": "bucket-789",
            "resource_type": "s3:bucket",
            "region": "us-east-1",
            "tags": {},
            "arn": "arn:aws:s3:::bucket-789"
        }
    ]
    
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=ec2_resources)
    mock_aws_client.get_rds_instances = AsyncMock(return_value=rds_resources)
    mock_aws_client.get_s3_buckets = AsyncMock(return_value=s3_resources)
    mock_aws_client.get_cost_data = AsyncMock(return_value={
        "Amazon EC2": 400.0,
        "Amazon RDS": 300.0,
        "Amazon S3": 300.0
    })
    
    def mock_validate(resource_id, resource_type, region, tags, cost_impact):
        if resource_id == "bucket-789":
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
        return []
    
    mock_policy_service.validate_resource_tags = mock_validate
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance", "rds:db", "s3:bucket"]
    )
    
    assert result.total_spend == 1000.0
    # 2 of 3 resources compliant: 2/3 * 1000 = 666.67
    assert abs(result.attributable_spend - 666.67) < 0.01
    # 1 of 3 resources non-compliant: 1/3 * 1000 = 333.33
    assert abs(result.attribution_gap - 333.33) < 0.01
    assert abs(result.attribution_gap_percentage - 33.33) < 0.01


@pytest.mark.asyncio
@patch('mcp_server.services.cost_service.logger')
async def test_get_cost_attribution_gap_handles_fetch_errors(mock_logger, mock_aws_client, mock_policy_service):
    """Test that tool handles resource fetch errors gracefully."""
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
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 1000.0})
    mock_policy_service.validate_resource_tags = MagicMock(return_value=[])
    
    # Should not raise, should continue with available resources
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance", "rds:db"]
    )
    
    # Should have processed EC2 resources despite RDS failure
    assert result.total_spend == 1000.0
    assert result.attributable_spend == 1000.0


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_default_time_period(mock_aws_client, mock_policy_service):
    """Test that default time period is used when not specified."""
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
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 1000.0})
    mock_policy_service.validate_resource_tags = MagicMock(return_value=[])
    
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    
    # Verify time period was set to default (last 30 days)
    assert result.time_period is not None
    assert "Start" in result.time_period
    assert "End" in result.time_period
    
    # Verify dates are in correct format
    start = datetime.strptime(result.time_period["Start"], "%Y-%m-%d")
    end = datetime.strptime(result.time_period["End"], "%Y-%m-%d")
    
    # End should be today or close to it
    today = datetime.now()
    assert (today - end).days <= 1
    
    # Start should be approximately 30 days before end
    delta = (end - start).days
    assert 29 <= delta <= 31


@pytest.mark.asyncio
async def test_get_cost_attribution_gap_result_has_timestamp(mock_aws_client, mock_policy_service):
    """Test that result includes scan timestamp."""
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
    mock_aws_client.get_cost_data = AsyncMock(return_value={"Amazon EC2": 1000.0})
    mock_policy_service.validate_resource_tags = MagicMock(return_value=[])
    
    before = datetime.now()
    result = await get_cost_attribution_gap(
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        resource_types=["ec2:instance"]
    )
    after = datetime.now()
    
    assert result.scan_timestamp is not None
    assert before <= result.scan_timestamp <= after
