"""Integration tests for check_tag_compliance tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, UTC

from mcp_server.tools.check_tag_compliance import check_tag_compliance
from mcp_server.services.compliance_service import ComplianceService
from mcp_server.clients.cache import RedisCache
from mcp_server.clients.aws_client import AWSClient
from mcp_server.services.policy_service import PolicyService
from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.violations import Violation
from mcp_server.models.enums import ViolationType, Severity


@pytest.fixture
def mock_cache():
    """Create a mock Redis cache."""
    cache = MagicMock(spec=RedisCache)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    cache.clear = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    client = MagicMock(spec=AWSClient)
    
    # Default: return empty lists for all resource types
    client.get_ec2_instances = AsyncMock(return_value=[])
    client.get_rds_instances = AsyncMock(return_value=[])
    client.get_s3_buckets = AsyncMock(return_value=[])
    client.get_lambda_functions = AsyncMock(return_value=[])
    client.get_ecs_services = AsyncMock(return_value=[])
    
    return client


@pytest.fixture
def mock_policy_service():
    """Create a mock policy service."""
    service = MagicMock(spec=PolicyService)
    service.validate_resource_tags = MagicMock(return_value=[])
    return service


@pytest.fixture
def compliance_service(mock_cache, mock_aws_client, mock_policy_service):
    """Create a ComplianceService instance with mocked dependencies."""
    return ComplianceService(
        cache=mock_cache,
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        cache_ttl=3600
    )


@pytest.mark.integration
class TestCheckTagComplianceBasic:
    """Test basic check_tag_compliance functionality."""
    
    @pytest.mark.asyncio
    async def test_check_compliance_single_resource_type(
        self, compliance_service, mock_aws_client
    ):
        """Test checking compliance for a single resource type."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all"
        )
        
        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 1
        assert result.compliance_score >= 0.0
        assert result.compliance_score <= 1.0
    
    @pytest.mark.asyncio
    async def test_check_compliance_multiple_resource_types(
        self, compliance_service, mock_aws_client
    ):
        """Test checking compliance for multiple resource types."""
        # Setup mock resources for EC2
        ec2_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
            }
        ]
        
        # Setup mock resources for RDS
        rds_resources = [
            {
                "resource_id": "db-456",
                "resource_type": "rds:db",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 200.0,
                "arn": "arn:aws:rds:us-east-1:123456789012:db:db-456"
            }
        ]
        
        mock_aws_client.get_ec2_instances.return_value = ec2_resources
        mock_aws_client.get_rds_instances.return_value = rds_resources
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance", "rds:db"],
            filters=None,
            severity="all"
        )
        
        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 2
        assert result.compliance_score >= 0.0
        assert result.compliance_score <= 1.0
    
    @pytest.mark.asyncio
    async def test_check_compliance_empty_resource_types_raises(
        self, compliance_service
    ):
        """Test that empty resource_types raises ValueError."""
        with pytest.raises(ValueError, match="resource_types cannot be empty"):
            await check_tag_compliance(
                compliance_service=compliance_service,
                resource_types=[],
                filters=None,
                severity="all"
            )
    
    @pytest.mark.asyncio
    async def test_check_compliance_invalid_resource_type_raises(
        self, compliance_service
    ):
        """Test that invalid resource type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid resource types"):
            await check_tag_compliance(
                compliance_service=compliance_service,
                resource_types=["invalid:type"],
                filters=None,
                severity="all"
            )
    
    @pytest.mark.asyncio
    async def test_check_compliance_invalid_severity_raises(
        self, compliance_service
    ):
        """Test that invalid severity raises ValueError."""
        with pytest.raises(ValueError, match="Invalid severity"):
            await check_tag_compliance(
                compliance_service=compliance_service,
                resource_types=["ec2:instance"],
                filters=None,
                severity="invalid"
            )


@pytest.mark.integration
class TestCheckTagComplianceFilters:
    """Test check_tag_compliance with various filter combinations."""
    
    @pytest.mark.asyncio
    async def test_check_compliance_filter_by_region(
        self, compliance_service, mock_aws_client
    ):
        """Test filtering by region."""
        # Setup mock resources in different regions
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters={"region": "us-east-1"},
            severity="all"
        )
        
        # Should only include resources from us-east-1
        assert result.total_resources == 1
    
    @pytest.mark.asyncio
    async def test_check_compliance_filter_by_multiple_regions(
        self, compliance_service, mock_aws_client
    ):
        """Test filtering by multiple regions."""
        # Setup mock resources in different regions
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"
            },
            {
                "resource_id": "i-789",
                "resource_type": "ec2:instance",
                "region": "eu-west-1",
                "tags": {"CostCenter": "Sales"},
                "cost_impact": 200.0,
                "arn": "arn:aws:ec2:eu-west-1:123456789012:instance/i-789"
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters={"region": ["us-east-1", "us-west-2"]},
            severity="all"
        )
        
        # Should include resources from us-east-1 and us-west-2
        assert result.total_resources == 2
    
    @pytest.mark.asyncio
    async def test_check_compliance_filter_by_account(
        self, compliance_service, mock_aws_client
    ):
        """Test filtering by account ID."""
        # Setup mock resources in different accounts
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:987654321098:instance/i-456"
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters={"account_id": "123456789012"},
            severity="all"
        )
        
        # Should only include resources from account 123456789012
        assert result.total_resources == 1
    
    @pytest.mark.asyncio
    async def test_check_compliance_filter_combined(
        self, compliance_service, mock_aws_client
    ):
        """Test filtering by both region and account."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"
            },
            {
                "resource_id": "i-789",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Sales"},
                "cost_impact": 200.0,
                "arn": "arn:aws:ec2:us-east-1:987654321098:instance/i-789"
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters={"region": "us-east-1", "account_id": "123456789012"},
            severity="all"
        )
        
        # Should only include i-123 (us-east-1 + account 123456789012)
        assert result.total_resources == 1


@pytest.mark.integration
class TestCheckTagComplianceSeverity:
    """Test check_tag_compliance with severity filtering."""
    
    @pytest.mark.asyncio
    async def test_check_compliance_severity_all(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test severity filter 'all' returns all violations."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "InvalidValue"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        
        # Setup violations with different severities
        error_violation = Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0
        )
        
        warning_violation = Violation(
            resource_id="i-456",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.INVALID_VALUE,
            tag_name="CostCenter",
            severity=Severity.WARNING,
            cost_impact_monthly=150.0
        )
        
        mock_policy_service.validate_resource_tags.side_effect = [
            [error_violation],
            [warning_violation]
        ]
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all"
        )
        
        # Should include both error and warning violations
        assert len(result.violations) == 2
    
    @pytest.mark.asyncio
    async def test_check_compliance_severity_errors_only(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test severity filter 'errors_only' returns only errors."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "InvalidValue"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        
        # Setup violations with different severities
        error_violation = Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0
        )
        
        warning_violation = Violation(
            resource_id="i-456",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.INVALID_VALUE,
            tag_name="CostCenter",
            severity=Severity.WARNING,
            cost_impact_monthly=150.0
        )
        
        mock_policy_service.validate_resource_tags.side_effect = [
            [error_violation],
            [warning_violation]
        ]
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="errors_only"
        )
        
        # Should only include error violations
        assert len(result.violations) == 1
        assert result.violations[0].severity == Severity.ERROR
    
    @pytest.mark.asyncio
    async def test_check_compliance_severity_warnings_only(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test severity filter 'warnings_only' returns only warnings."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "InvalidValue"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456"
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        
        # Setup violations with different severities
        error_violation = Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0
        )
        
        warning_violation = Violation(
            resource_id="i-456",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.INVALID_VALUE,
            tag_name="CostCenter",
            severity=Severity.WARNING,
            cost_impact_monthly=150.0
        )
        
        mock_policy_service.validate_resource_tags.side_effect = [
            [error_violation],
            [warning_violation]
        ]
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="warnings_only"
        )
        
        # Should only include warning violations
        assert len(result.violations) == 1
        assert result.violations[0].severity == Severity.WARNING


@pytest.mark.integration
@pytest.mark.slow
class TestCheckTagCompliancePerformance:
    """Test check_tag_compliance performance with large datasets."""
    
    @pytest.mark.asyncio
    async def test_check_compliance_1000_resources(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test performance with 1000 resources (Requirement 1.5)."""
        import time
        
        # Generate 1000 mock resources
        mock_resources = []
        for i in range(1000):
            mock_resources.append({
                "resource_id": f"i-{i:016x}",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0,
                "arn": f"arn:aws:ec2:us-east-1:123456789012:instance/i-{i:016x}"
            })
        
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        mock_policy_service.validate_resource_tags.return_value = []  # All compliant
        
        # Measure execution time
        start_time = time.time()
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all"
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify results
        assert result.total_resources == 1000
        assert result.compliance_score == 1.0
        
        # Performance requirement: complete within 5 seconds
        assert execution_time < 5.0, f"Execution took {execution_time:.2f}s, expected < 5s"
    
    @pytest.mark.asyncio
    async def test_check_compliance_1000_resources_with_violations(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test performance with 1000 resources including violations."""
        import time
        
        # Generate 1000 mock resources (50% with violations)
        mock_resources = []
        for i in range(1000):
            tags = {"CostCenter": "Engineering"} if i % 2 == 0 else {}
            mock_resources.append({
                "resource_id": f"i-{i:016x}",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": tags,
                "cost_impact": 100.0,
                "arn": f"arn:aws:ec2:us-east-1:123456789012:instance/i-{i:016x}"
            })
        
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        
        # Setup violations for resources without tags
        def validate_side_effect(resource_id, resource_type, region, tags, cost_impact):
            if not tags:
                return [Violation(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=Severity.ERROR,
                    cost_impact_monthly=cost_impact
                )]
            return []
        
        mock_policy_service.validate_resource_tags.side_effect = validate_side_effect
        
        # Measure execution time
        start_time = time.time()
        
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all"
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Verify results
        assert result.total_resources == 1000
        assert result.compliance_score == 0.5  # 50% compliant
        assert len(result.violations) == 500
        
        # Performance requirement: complete within 5 seconds
        assert execution_time < 5.0, f"Execution took {execution_time:.2f}s, expected < 5s"
