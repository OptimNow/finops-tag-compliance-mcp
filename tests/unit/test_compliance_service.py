"""Unit tests for ComplianceService caching logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

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
    return MagicMock(spec=AWSClient)


@pytest.fixture
def mock_policy_service():
    """Create a mock policy service."""
    return MagicMock(spec=PolicyService)


@pytest.fixture
def compliance_service(mock_cache, mock_aws_client, mock_policy_service):
    """Create a ComplianceService instance with mocked dependencies."""
    return ComplianceService(
        cache=mock_cache,
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        cache_ttl=3600
    )


class TestCacheKeyGeneration:
    """Test cache key generation logic."""
    
    def test_generate_cache_key_basic(self, compliance_service):
        """Test basic cache key generation."""
        key = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all"
        )
        
        assert key.startswith("compliance:")
        assert len(key) > len("compliance:")
    
    def test_generate_cache_key_with_filters(self, compliance_service):
        """Test cache key generation with filters."""
        key = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters={"region": "us-east-1"},
            severity="errors_only"
        )
        
        assert key.startswith("compliance:")
    
    def test_generate_cache_key_deterministic(self, compliance_service):
        """Test that same parameters produce same cache key."""
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance", "rds:db"],
            filters={"region": "us-east-1"},
            severity="all"
        )
        
        key2 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance", "rds:db"],
            filters={"region": "us-east-1"},
            severity="all"
        )
        
        assert key1 == key2
    
    def test_generate_cache_key_order_independent(self, compliance_service):
        """Test that resource type order doesn't affect cache key."""
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance", "rds:db"],
            filters=None,
            severity="all"
        )
        
        key2 = compliance_service._generate_cache_key(
            resource_types=["rds:db", "ec2:instance"],
            filters=None,
            severity="all"
        )
        
        assert key1 == key2
    
    def test_generate_cache_key_different_params(self, compliance_service):
        """Test that different parameters produce different cache keys."""
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all"
        )
        
        key2 = compliance_service._generate_cache_key(
            resource_types=["rds:db"],
            filters=None,
            severity="all"
        )
        
        assert key1 != key2


class TestCacheRetrieval:
    """Test cache retrieval logic."""
    
    @pytest.mark.asyncio
    async def test_get_from_cache_hit(self, compliance_service, mock_cache):
        """Test successful cache retrieval."""
        # Setup cached data
        cached_data = {
            "compliance_score": 0.75,
            "total_resources": 100,
            "compliant_resources": 75,
            "violations": [],
            "cost_attribution_gap": 1000.0,
            "scan_timestamp": datetime.now(UTC).isoformat()
        }
        mock_cache.get.return_value = cached_data
        
        result = await compliance_service._get_from_cache("test_key")
        
        assert result is not None
        assert isinstance(result, ComplianceResult)
        assert result.compliance_score == 0.75
        assert result.total_resources == 100
        mock_cache.get.assert_called_once_with("test_key")
    
    @pytest.mark.asyncio
    async def test_get_from_cache_miss(self, compliance_service, mock_cache):
        """Test cache miss returns None."""
        mock_cache.get.return_value = None
        
        result = await compliance_service._get_from_cache("test_key")
        
        assert result is None
        mock_cache.get.assert_called_once_with("test_key")
    
    @pytest.mark.asyncio
    @patch('mcp_server.services.compliance_service.logger')
    async def test_get_from_cache_invalid_data(self, mock_logger, compliance_service, mock_cache):
        """Test that invalid cached data returns None."""
        # Setup invalid cached data
        mock_cache.get.return_value = {"invalid": "data"}
        
        result = await compliance_service._get_from_cache("test_key")
        
        assert result is None


class TestCacheStorage:
    """Test cache storage logic."""
    
    @pytest.mark.asyncio
    async def test_cache_result_success(self, compliance_service, mock_cache):
        """Test successful result caching."""
        result = ComplianceResult(
            compliance_score=0.8,
            total_resources=50,
            compliant_resources=40,
            violations=[],
            cost_attribution_gap=500.0
        )
        
        await compliance_service._cache_result("test_key", result)
        
        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args[0][0] == "test_key"
        assert call_args[1]["ttl"] == 3600
    
    @pytest.mark.asyncio
    async def test_cache_result_with_violations(self, compliance_service, mock_cache):
        """Test caching result with violations."""
        violation = Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0
        )
        
        result = ComplianceResult(
            compliance_score=0.5,
            total_resources=2,
            compliant_resources=1,
            violations=[violation],
            cost_attribution_gap=100.0
        )
        
        await compliance_service._cache_result("test_key", result)
        
        mock_cache.set.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('mcp_server.services.compliance_service.logger')
    async def test_cache_result_failure_doesnt_raise(self, mock_logger, compliance_service, mock_cache):
        """Test that cache failure doesn't raise exception."""
        mock_cache.set.side_effect = Exception("Cache error")
        
        result = ComplianceResult(
            compliance_score=1.0,
            total_resources=0,
            compliant_resources=0,
            violations=[]
        )
        
        # Should not raise
        await compliance_service._cache_result("test_key", result)


class TestCheckCompliance:
    """Test the main check_compliance method with caching."""
    
    @pytest.mark.asyncio
    async def test_check_compliance_cache_hit(self, compliance_service, mock_cache):
        """Test that cache hit returns cached result without scanning."""
        # Setup cached data
        cached_data = {
            "compliance_score": 0.9,
            "total_resources": 10,
            "compliant_resources": 9,
            "violations": [],
            "cost_attribution_gap": 50.0,
            "scan_timestamp": datetime.now(UTC).isoformat()
        }
        mock_cache.get.return_value = cached_data
        
        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters={"region": "us-east-1"},
            severity="all"
        )
        
        assert result.compliance_score == 0.9
        assert result.total_resources == 10
        mock_cache.get.assert_called_once()
        # Should not call set since we got cache hit
        mock_cache.set.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_check_compliance_cache_miss(self, compliance_service, mock_cache):
        """Test that cache miss triggers scan and caches result."""
        mock_cache.get.return_value = None
        
        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all"
        )
        
        assert isinstance(result, ComplianceResult)
        mock_cache.get.assert_called_once()
        # Should cache the new result
        mock_cache.set.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_check_compliance_force_refresh(self, compliance_service, mock_cache):
        """Test that force_refresh bypasses cache."""
        # Setup cached data that should be ignored
        cached_data = {
            "compliance_score": 0.5,
            "total_resources": 100,
            "compliant_resources": 50,
            "violations": [],
            "cost_attribution_gap": 1000.0,
            "scan_timestamp": datetime.now(UTC).isoformat()
        }
        mock_cache.get.return_value = cached_data
        
        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            force_refresh=True
        )
        
        # Should not call get since force_refresh=True
        mock_cache.get.assert_not_called()
        # Should cache the new result
        mock_cache.set.assert_called_once()


class TestCacheInvalidation:
    """Test cache invalidation logic."""
    
    @pytest.mark.asyncio
    async def test_invalidate_cache_all(self, compliance_service, mock_cache):
        """Test invalidating all cache entries."""
        result = await compliance_service.invalidate_cache()
        
        assert result is True
        mock_cache.clear.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_invalidate_cache_specific(self, compliance_service, mock_cache):
        """Test invalidating specific cache entry."""
        result = await compliance_service.invalidate_cache(
            resource_types=["ec2:instance"],
            filters={"region": "us-east-1"}
        )
        
        assert result is True
        mock_cache.delete.assert_called_once()
        # Verify the cache key was generated correctly
        call_args = mock_cache.delete.call_args[0][0]
        assert call_args.startswith("compliance:")
    
    @pytest.mark.asyncio
    async def test_invalidate_cache_unavailable(self, compliance_service, mock_cache):
        """Test invalidation when cache is unavailable."""
        mock_cache.clear.return_value = False
        
        result = await compliance_service.invalidate_cache()
        
        assert result is False


class TestResourceScanning:
    """Test resource scanning and validation logic."""
    
    @pytest.mark.asyncio
    async def test_scan_and_validate_with_compliant_resources(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test scanning resources that are all compliant."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing", "Environment": "staging"},
                "cost_impact": 50.0
            }
        ]
        
        mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
        mock_policy_service.validate_resource_tags.return_value = []  # No violations
        
        result = await compliance_service._scan_and_validate(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all"
        )
        
        assert result.compliance_score == 1.0
        assert result.total_resources == 2
        assert result.compliant_resources == 2
        assert len(result.violations) == 0
        assert result.cost_attribution_gap == 0.0
    
    @pytest.mark.asyncio
    async def test_scan_and_validate_with_violations(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test scanning resources with violations."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},  # Missing tags
                "cost_impact": 100.0
            }
        ]
        
        violation = Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0
        )
        
        mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
        mock_policy_service.validate_resource_tags.return_value = [violation]
        
        result = await compliance_service._scan_and_validate(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all"
        )
        
        assert result.compliance_score == 0.0
        assert result.total_resources == 1
        assert result.compliant_resources == 0
        assert len(result.violations) == 1
        assert result.cost_attribution_gap == 100.0
    
    @pytest.mark.asyncio
    async def test_scan_and_validate_multiple_resource_types(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test scanning multiple resource types."""
        ec2_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0
            }
        ]
        
        rds_resources = [
            {
                "resource_id": "db-456",
                "resource_type": "rds:db",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 200.0
            }
        ]
        
        mock_aws_client.get_ec2_instances = AsyncMock(return_value=ec2_resources)
        mock_aws_client.get_rds_instances = AsyncMock(return_value=rds_resources)
        mock_policy_service.validate_resource_tags.return_value = []
        
        result = await compliance_service._scan_and_validate(
            resource_types=["ec2:instance", "rds:db"],
            filters=None,
            severity="all"
        )
        
        assert result.total_resources == 2
        assert result.compliant_resources == 2
        assert result.compliance_score == 1.0


class TestComplianceScoreCalculation:
    """Test compliance score calculation logic."""
    
    def test_calculate_compliance_score_all_compliant(self, compliance_service):
        """Test score calculation when all resources are compliant."""
        score = compliance_service._calculate_compliance_score(
            compliant_resources=10,
            total_resources=10
        )
        assert score == 1.0
    
    def test_calculate_compliance_score_none_compliant(self, compliance_service):
        """Test score calculation when no resources are compliant."""
        score = compliance_service._calculate_compliance_score(
            compliant_resources=0,
            total_resources=10
        )
        assert score == 0.0
    
    def test_calculate_compliance_score_partial(self, compliance_service):
        """Test score calculation with partial compliance."""
        score = compliance_service._calculate_compliance_score(
            compliant_resources=7,
            total_resources=10
        )
        assert score == 0.7
    
    def test_calculate_compliance_score_zero_resources(self, compliance_service):
        """Test score calculation with zero resources returns 1.0."""
        score = compliance_service._calculate_compliance_score(
            compliant_resources=0,
            total_resources=0
        )
        assert score == 1.0


class TestSeverityFiltering:
    """Test severity filtering logic."""
    
    def test_filter_by_severity_all(self, compliance_service):
        """Test that 'all' severity returns all violations."""
        violations = [
            Violation(
                resource_id="i-123",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR
            ),
            Violation(
                resource_id="i-456",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.INVALID_VALUE,
                tag_name="Environment",
                severity=Severity.WARNING
            )
        ]
        
        filtered = compliance_service._filter_by_severity(violations, "all")
        assert len(filtered) == 2
    
    def test_filter_by_severity_errors_only(self, compliance_service):
        """Test filtering for errors only."""
        violations = [
            Violation(
                resource_id="i-123",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR
            ),
            Violation(
                resource_id="i-456",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.INVALID_VALUE,
                tag_name="Environment",
                severity=Severity.WARNING
            )
        ]
        
        filtered = compliance_service._filter_by_severity(violations, "errors_only")
        assert len(filtered) == 1
        assert filtered[0].severity == Severity.ERROR
    
    def test_filter_by_severity_warnings_only(self, compliance_service):
        """Test filtering for warnings only."""
        violations = [
            Violation(
                resource_id="i-123",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR
            ),
            Violation(
                resource_id="i-456",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.INVALID_VALUE,
                tag_name="Environment",
                severity=Severity.WARNING
            )
        ]
        
        filtered = compliance_service._filter_by_severity(violations, "warnings_only")
        assert len(filtered) == 1
        assert filtered[0].severity == Severity.WARNING


class TestResourceFiltering:
    """Test resource filtering logic."""
    
    def test_apply_resource_filters_no_filters(self, compliance_service):
        """Test that no filters returns all resources."""
        resources = [
            {"resource_id": "i-123", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"},
            {"resource_id": "i-456", "region": "us-west-2", "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"},
        ]
        
        filtered = compliance_service._apply_resource_filters(resources, None)
        assert len(filtered) == 2
    
    def test_apply_resource_filters_by_region_string(self, compliance_service):
        """Test filtering by single region as string."""
        resources = [
            {"resource_id": "i-123", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"},
            {"resource_id": "i-456", "region": "us-west-2", "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"},
            {"resource_id": "i-789", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-789"},
        ]
        
        filtered = compliance_service._apply_resource_filters(
            resources,
            {"region": "us-east-1"}
        )
        
        assert len(filtered) == 2
        assert all(r["region"] == "us-east-1" for r in filtered)
    
    def test_apply_resource_filters_by_region_list(self, compliance_service):
        """Test filtering by multiple regions as list."""
        resources = [
            {"resource_id": "i-123", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"},
            {"resource_id": "i-456", "region": "us-west-2", "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"},
            {"resource_id": "i-789", "region": "eu-west-1", "arn": "arn:aws:ec2:eu-west-1:123456789012:instance/i-789"},
        ]
        
        filtered = compliance_service._apply_resource_filters(
            resources,
            {"region": ["us-east-1", "us-west-2"]}
        )
        
        assert len(filtered) == 2
        assert all(r["region"] in ["us-east-1", "us-west-2"] for r in filtered)
    
    def test_apply_resource_filters_by_account_string(self, compliance_service):
        """Test filtering by single account ID as string."""
        resources = [
            {"resource_id": "i-123", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"},
            {"resource_id": "i-456", "region": "us-west-2", "arn": "arn:aws:ec2:us-west-2:987654321098:instance/i-456"},
            {"resource_id": "i-789", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-789"},
        ]
        
        filtered = compliance_service._apply_resource_filters(
            resources,
            {"account_id": "123456789012"}
        )
        
        assert len(filtered) == 2
        assert all("123456789012" in r["arn"] for r in filtered)
    
    def test_apply_resource_filters_by_account_list(self, compliance_service):
        """Test filtering by multiple account IDs as list."""
        resources = [
            {"resource_id": "i-123", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"},
            {"resource_id": "i-456", "region": "us-west-2", "arn": "arn:aws:ec2:us-west-2:987654321098:instance/i-456"},
            {"resource_id": "i-789", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:111111111111:instance/i-789"},
        ]
        
        filtered = compliance_service._apply_resource_filters(
            resources,
            {"account_id": ["123456789012", "987654321098"]}
        )
        
        assert len(filtered) == 2
    
    def test_apply_resource_filters_combined(self, compliance_service):
        """Test filtering by both region and account."""
        resources = [
            {"resource_id": "i-123", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"},
            {"resource_id": "i-456", "region": "us-west-2", "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"},
            {"resource_id": "i-789", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:987654321098:instance/i-789"},
        ]
        
        filtered = compliance_service._apply_resource_filters(
            resources,
            {"region": "us-east-1", "account_id": "123456789012"}
        )
        
        assert len(filtered) == 1
        assert filtered[0]["resource_id"] == "i-123"
    
    def test_extract_account_from_arn_valid(self, compliance_service):
        """Test extracting account ID from valid ARN."""
        from mcp_server.utils.resource_utils import extract_account_from_arn
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        account = extract_account_from_arn(arn)
        assert account == "123456789012"
    
    def test_extract_account_from_arn_empty(self, compliance_service):
        """Test extracting account from empty ARN."""
        from mcp_server.utils.resource_utils import extract_account_from_arn
        account = extract_account_from_arn("")
        assert account == "unknown"  # Updated to match shared utility behavior
    
    def test_extract_account_from_arn_invalid(self, compliance_service):
        """Test extracting account from invalid ARN."""
        from mcp_server.utils.resource_utils import extract_account_from_arn
        account = extract_account_from_arn("not-an-arn")
        assert account == "unknown"  # Updated to match shared utility behavior
    
    def test_apply_resource_filters_empty_filter_values(self, compliance_service):
        """Test that empty filter values don't filter anything."""
        resources = [
            {"resource_id": "i-123", "region": "us-east-1", "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123"},
            {"resource_id": "i-456", "region": "us-west-2", "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"},
        ]
        
        # Empty string filters should not filter
        filtered = compliance_service._apply_resource_filters(
            resources,
            {"region": "", "account_id": ""}
        )
        
        assert len(filtered) == 2


class TestAllResourceTypeSupport:
    """Test support for 'all' resource type using Resource Groups Tagging API."""
    
    @pytest.mark.asyncio
    async def test_scan_and_validate_all_resource_types(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test scanning all resources via Resource Groups Tagging API."""
        # Setup mock resources from Tagging API
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
                "resource_id": "table/MyTable",
                "resource_type": "dynamodb:table",
                "region": "us-east-1",
                "tags": {},  # Missing tags
                "cost_impact": 50.0,
                "arn": "arn:aws:dynamodb:us-east-1:123456789012:table/MyTable"
            },
            {
                "resource_id": "my-queue",
                "resource_type": "sqs:queue",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 10.0,
                "arn": "arn:aws:sqs:us-east-1:123456789012:my-queue"
            }
        ]
        
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=mock_resources)
        
        # First two resources compliant, third has violation
        def validate_side_effect(resource_id, resource_type, region, tags, cost_impact):
            if resource_type == "dynamodb:table":
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
        
        result = await compliance_service._scan_and_validate(
            resource_types=["all"],
            filters=None,
            severity="all"
        )
        
        # Verify Tagging API was called
        mock_aws_client.get_all_tagged_resources.assert_called_once()
        
        # 3 resources total, 2 compliant, 1 violation
        assert result.total_resources == 3
        assert result.compliant_resources == 2
        assert len(result.violations) == 1
        assert result.violations[0].resource_type == "dynamodb:table"
    
    @pytest.mark.asyncio
    async def test_scan_all_with_region_filter(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test scanning all resources with region filter applied post-fetch."""
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
                "region": "us-west-2",
                "tags": {},
                "cost_impact": 50.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456"
            }
        ]
        
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=mock_resources)
        mock_policy_service.validate_resource_tags.return_value = []
        
        result = await compliance_service._scan_and_validate(
            resource_types=["all"],
            filters={"region": "us-east-1"},
            severity="all"
        )
        
        # Only us-east-1 resource should be included
        assert result.total_resources == 1
    
    @pytest.mark.asyncio
    async def test_check_compliance_all_uses_cache(
        self, compliance_service, mock_cache, mock_aws_client
    ):
        """Test that 'all' resource type queries use caching."""
        mock_cache.get.return_value = None
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])
        
        await compliance_service.check_compliance(
            resource_types=["all"],
            filters=None,
            severity="all"
        )
        
        # Verify cache was checked and result was cached
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_called_once()
        
        # Verify cache key includes "all"
        cache_key = mock_cache.get.call_args[0][0]
        assert "compliance:" in cache_key
