"""Unit tests for ComplianceService caching logic."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.clients.aws_client import AWSClient
from mcp_server.clients.cache import RedisCache
from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.enums import Severity, ViolationType
from mcp_server.models.violations import Violation
from mcp_server.services.compliance_service import ComplianceService
from mcp_server.services.policy_service import PolicyService


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
    client.region = "us-east-1"  # Include region for cache key generation
    return client


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
        cache_ttl=3600,
    )


class TestCacheKeyGeneration:
    """Test cache key generation logic."""

    def test_generate_cache_key_basic(self, compliance_service):
        """Test basic cache key generation."""
        key = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"], filters=None, severity="all"
        )

        assert key.startswith("compliance:")
        assert len(key) > len("compliance:")

    def test_generate_cache_key_with_filters(self, compliance_service):
        """Test cache key generation with filters."""
        key = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"], filters={"region": "us-east-1"}, severity="errors_only"
        )

        assert key.startswith("compliance:")

    def test_generate_cache_key_deterministic(self, compliance_service):
        """Test that same parameters produce same cache key."""
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance", "rds:db"],
            filters={"region": "us-east-1"},
            severity="all",
        )

        key2 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance", "rds:db"],
            filters={"region": "us-east-1"},
            severity="all",
        )

        assert key1 == key2

    def test_generate_cache_key_order_independent(self, compliance_service):
        """Test that resource type order doesn't affect cache key."""
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance", "rds:db"], filters=None, severity="all"
        )

        key2 = compliance_service._generate_cache_key(
            resource_types=["rds:db", "ec2:instance"], filters=None, severity="all"
        )

        assert key1 == key2

    def test_generate_cache_key_different_params(self, compliance_service):
        """Test that different parameters produce different cache keys."""
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"], filters=None, severity="all"
        )

        key2 = compliance_service._generate_cache_key(
            resource_types=["rds:db"], filters=None, severity="all"
        )

        assert key1 != key2

    def test_generate_cache_key_with_scanned_regions(self, compliance_service):
        """Test cache key generation with scanned regions for multi-region support.

        Requirements: 8.1, 8.2 - Cache multi-region results with region-aware keys
        """
        key = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "us-west-2", "eu-west-1"],
        )

        assert key.startswith("compliance:")
        assert len(key) > len("compliance:")

    def test_generate_cache_key_scanned_regions_deterministic(self, compliance_service):
        """Test that same scanned regions produce same cache key.

        Requirements: 8.2 - Ensure cache key determinism
        """
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "us-west-2"],
        )

        key2 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "us-west-2"],
        )

        assert key1 == key2

    def test_generate_cache_key_scanned_regions_order_independent(self, compliance_service):
        """Test that scanned region order doesn't affect cache key.

        Requirements: 8.2 - Ensure cache key determinism (same inputs = same key)
        """
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "us-west-2", "eu-west-1"],
        )

        key2 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["eu-west-1", "us-east-1", "us-west-2"],
        )

        assert key1 == key2

    def test_generate_cache_key_different_scanned_regions(self, compliance_service):
        """Test that different scanned regions produce different cache keys.

        Requirements: 8.1 - Cache key includes list of scanned regions
        """
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "us-west-2"],
        )

        key2 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "eu-west-1"],
        )

        assert key1 != key2

    def test_generate_cache_key_with_vs_without_scanned_regions(self, compliance_service):
        """Test that cache key differs when scanned_regions is provided vs not.

        Requirements: 8.1 - Differentiate full scans from filtered scans
        """
        key_without = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=None,
        )

        key_with = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1"],
        )

        assert key_without != key_with

    def test_generate_cache_key_empty_scanned_regions(self, compliance_service):
        """Test cache key generation with empty scanned regions list."""
        key = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=[],
        )

        assert key.startswith("compliance:")

    def test_generate_cache_key_scanned_regions_with_filters(self, compliance_service):
        """Test cache key generation with both scanned regions and filters."""
        key = compliance_service._generate_cache_key(
            resource_types=["ec2:instance", "rds:db"],
            filters={"account_id": "123456789012"},
            severity="errors_only",
            scanned_regions=["us-east-1", "us-west-2"],
        )

        assert key.startswith("compliance:")
        assert len(key) > len("compliance:")


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
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
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
    @patch("mcp_server.services.compliance_service.logger")
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
            cost_attribution_gap=500.0,
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
            cost_impact_monthly=100.0,
        )

        result = ComplianceResult(
            compliance_score=0.5,
            total_resources=2,
            compliant_resources=1,
            violations=[violation],
            cost_attribution_gap=100.0,
        )

        await compliance_service._cache_result("test_key", result)

        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    @patch("mcp_server.services.compliance_service.logger")
    async def test_cache_result_failure_doesnt_raise(
        self, mock_logger, compliance_service, mock_cache
    ):
        """Test that cache failure doesn't raise exception."""
        mock_cache.set.side_effect = Exception("Cache error")

        result = ComplianceResult(
            compliance_score=1.0, total_resources=0, compliant_resources=0, violations=[]
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
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        mock_cache.get.return_value = cached_data

        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"], filters={"region": "us-east-1"}, severity="all"
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
            resource_types=["ec2:instance"], filters=None, severity="all"
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
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        mock_cache.get.return_value = cached_data

        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"], filters=None, severity="all", force_refresh=True
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
            resource_types=["ec2:instance"], filters={"region": "us-east-1"}
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
                "cost_impact": 100.0,
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing", "Environment": "staging"},
                "cost_impact": 50.0,
            },
        ]

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
        mock_policy_service.validate_resource_tags.return_value = []  # No violations

        result = await compliance_service._scan_and_validate(
            resource_types=["ec2:instance"], filters=None, severity="all"
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
                "cost_impact": 100.0,
            }
        ]

        violation = Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0,
        )

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
        mock_policy_service.validate_resource_tags.return_value = [violation]

        result = await compliance_service._scan_and_validate(
            resource_types=["ec2:instance"], filters=None, severity="all"
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
                "cost_impact": 100.0,
            }
        ]

        rds_resources = [
            {
                "resource_id": "db-456",
                "resource_type": "rds:db",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 200.0,
            }
        ]

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=ec2_resources)
        mock_aws_client.get_rds_instances = AsyncMock(return_value=rds_resources)
        mock_policy_service.validate_resource_tags.return_value = []

        result = await compliance_service._scan_and_validate(
            resource_types=["ec2:instance", "rds:db"], filters=None, severity="all"
        )

        assert result.total_resources == 2
        assert result.compliant_resources == 2
        assert result.compliance_score == 1.0


class TestComplianceScoreCalculation:
    """Test compliance score calculation logic."""

    def test_calculate_compliance_score_all_compliant(self, compliance_service):
        """Test score calculation when all resources are compliant."""
        score = compliance_service._calculate_compliance_score(
            compliant_resources=10, total_resources=10
        )
        assert score == 1.0

    def test_calculate_compliance_score_none_compliant(self, compliance_service):
        """Test score calculation when no resources are compliant."""
        score = compliance_service._calculate_compliance_score(
            compliant_resources=0, total_resources=10
        )
        assert score == 0.0

    def test_calculate_compliance_score_partial(self, compliance_service):
        """Test score calculation with partial compliance."""
        score = compliance_service._calculate_compliance_score(
            compliant_resources=7, total_resources=10
        )
        assert score == 0.7

    def test_calculate_compliance_score_zero_resources(self, compliance_service):
        """Test score calculation with zero resources returns 1.0."""
        score = compliance_service._calculate_compliance_score(
            compliant_resources=0, total_resources=0
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
                severity=Severity.ERROR,
            ),
            Violation(
                resource_id="i-456",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.INVALID_VALUE,
                tag_name="Environment",
                severity=Severity.WARNING,
            ),
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
                severity=Severity.ERROR,
            ),
            Violation(
                resource_id="i-456",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.INVALID_VALUE,
                tag_name="Environment",
                severity=Severity.WARNING,
            ),
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
                severity=Severity.ERROR,
            ),
            Violation(
                resource_id="i-456",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.INVALID_VALUE,
                tag_name="Environment",
                severity=Severity.WARNING,
            ),
        ]

        filtered = compliance_service._filter_by_severity(violations, "warnings_only")
        assert len(filtered) == 1
        assert filtered[0].severity == Severity.WARNING


class TestResourceFiltering:
    """Test resource filtering logic."""

    def test_apply_resource_filters_no_filters(self, compliance_service):
        """Test that no filters returns all resources."""
        resources = [
            {
                "resource_id": "i-123",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "region": "us-west-2",
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456",
            },
        ]

        filtered = compliance_service._apply_resource_filters(resources, None)
        assert len(filtered) == 2

    def test_apply_resource_filters_by_region_string(self, compliance_service):
        """Test filtering by single region as string."""
        resources = [
            {
                "resource_id": "i-123",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "region": "us-west-2",
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456",
            },
            {
                "resource_id": "i-789",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-789",
            },
        ]

        filtered = compliance_service._apply_resource_filters(resources, {"region": "us-east-1"})

        assert len(filtered) == 2
        assert all(r["region"] == "us-east-1" for r in filtered)

    def test_apply_resource_filters_by_region_list(self, compliance_service):
        """Test filtering by multiple regions as list."""
        resources = [
            {
                "resource_id": "i-123",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "region": "us-west-2",
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456",
            },
            {
                "resource_id": "i-789",
                "region": "eu-west-1",
                "arn": "arn:aws:ec2:eu-west-1:123456789012:instance/i-789",
            },
        ]

        filtered = compliance_service._apply_resource_filters(
            resources, {"region": ["us-east-1", "us-west-2"]}
        )

        assert len(filtered) == 2
        assert all(r["region"] in ["us-east-1", "us-west-2"] for r in filtered)

    def test_apply_resource_filters_by_account_string(self, compliance_service):
        """Test filtering by single account ID as string."""
        resources = [
            {
                "resource_id": "i-123",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "region": "us-west-2",
                "arn": "arn:aws:ec2:us-west-2:987654321098:instance/i-456",
            },
            {
                "resource_id": "i-789",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-789",
            },
        ]

        filtered = compliance_service._apply_resource_filters(
            resources, {"account_id": "123456789012"}
        )

        assert len(filtered) == 2
        assert all("123456789012" in r["arn"] for r in filtered)

    def test_apply_resource_filters_by_account_list(self, compliance_service):
        """Test filtering by multiple account IDs as list."""
        resources = [
            {
                "resource_id": "i-123",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "region": "us-west-2",
                "arn": "arn:aws:ec2:us-west-2:987654321098:instance/i-456",
            },
            {
                "resource_id": "i-789",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:111111111111:instance/i-789",
            },
        ]

        filtered = compliance_service._apply_resource_filters(
            resources, {"account_id": ["123456789012", "987654321098"]}
        )

        assert len(filtered) == 2

    def test_apply_resource_filters_combined(self, compliance_service):
        """Test filtering by both region and account."""
        resources = [
            {
                "resource_id": "i-123",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "region": "us-west-2",
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456",
            },
            {
                "resource_id": "i-789",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:987654321098:instance/i-789",
            },
        ]

        filtered = compliance_service._apply_resource_filters(
            resources, {"region": "us-east-1", "account_id": "123456789012"}
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
            {
                "resource_id": "i-123",
                "region": "us-east-1",
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "region": "us-west-2",
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456",
            },
        ]

        # Empty string filters should not filter
        filtered = compliance_service._apply_resource_filters(
            resources, {"region": "", "account_id": ""}
        )

        assert len(filtered) == 2


class TestAllResourceTypeSupport:
    """Test support for 'all' resource type using Resource Groups Tagging API."""

    @pytest.mark.asyncio
    async def test_scan_and_validate_all_resource_types(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test scanning all resources via two-strategy approach.

        The implementation uses:
        1. Direct fetchers for 6 types (EC2, RDS, S3, Lambda, ECS, OpenSearch)
           — these catch untagged resources
        2. One batch Tagging API call for all remaining types (~30)
           — efficient but only returns resources with ≥1 tag
        """
        # Resources returned by direct fetchers (EC2, Lambda)
        ec2_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
        ]
        lambda_resources = [
            {
                "resource_id": "my-function",
                "resource_type": "lambda:function",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 10.0,
                "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            },
        ]

        # Resource returned by batch Tagging API (DynamoDB)
        tagging_api_resources = [
            {
                "resource_id": "table/MyTable",
                "resource_type": "dynamodb:table",
                "region": "us-east-1",
                "tags": {},  # Missing tags
                "cost_impact": 50.0,
                "arn": "arn:aws:dynamodb:us-east-1:123456789012:table/MyTable",
            },
        ]

        # Mock direct fetchers — return resources for EC2 and Lambda, empty for others
        async def mock_fetch_by_type(resource_type, filters):
            if resource_type == "ec2:instance":
                return ec2_resources
            elif resource_type == "lambda:function":
                return lambda_resources
            return []

        compliance_service._fetch_resources_by_type = AsyncMock(side_effect=mock_fetch_by_type)

        # Mock batch Tagging API call
        mock_aws_client.get_all_tagged_resources = AsyncMock(
            return_value=tagging_api_resources
        )

        # DynamoDB table has violation, others are compliant
        def validate_side_effect(resource_id, resource_type, region, tags, cost_impact):
            if resource_type == "dynamodb:table":
                return [
                    Violation(
                        resource_id=resource_id,
                        resource_type=resource_type,
                        region=region,
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        tag_name="CostCenter",
                        severity=Severity.ERROR,
                        cost_impact_monthly=cost_impact,
                    )
                ]
            return []

        mock_policy_service.validate_resource_tags.side_effect = validate_side_effect

        result = await compliance_service._scan_and_validate(
            resource_types=["all"], filters=None, severity="all"
        )

        # Verify direct fetchers were called (6 types)
        assert compliance_service._fetch_resources_by_type.call_count == 6

        # Verify batch Tagging API was called once for the remaining types
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
        # Direct fetchers return EC2 instances in two regions
        ec2_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {},
                "cost_impact": 50.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456",
            },
        ]

        async def mock_fetch_by_type(resource_type, filters):
            if resource_type == "ec2:instance":
                return ec2_resources
            return []

        compliance_service._fetch_resources_by_type = AsyncMock(side_effect=mock_fetch_by_type)
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])
        mock_policy_service.validate_resource_tags.return_value = []

        result = await compliance_service._scan_and_validate(
            resource_types=["all"], filters={"region": "us-east-1"}, severity="all"
        )

        # Only us-east-1 resource should be included
        assert result.total_resources == 1

    @pytest.mark.asyncio
    async def test_check_compliance_all_uses_cache(
        self, compliance_service, mock_cache, mock_aws_client
    ):
        """Test that 'all' resource type queries use caching."""
        mock_cache.get.return_value = None

        # Mock both fetching strategies so _scan_and_validate succeeds
        compliance_service._fetch_resources_by_type = AsyncMock(return_value=[])
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

        await compliance_service.check_compliance(
            resource_types=["all"], filters=None, severity="all"
        )

        # Verify cache was checked and result was cached
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_called_once()

        # Verify cache key includes "all"
        cache_key = mock_cache.get.call_args[0][0]
        assert "compliance:" in cache_key

    @pytest.mark.asyncio
    async def test_free_resources_filtered_from_compliance_scan(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test that free resources (VPC, Subnet, Security Group, etc.) are filtered out."""
        # EC2 instance returned by direct fetcher
        ec2_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
        ]
        # S3 bucket returned by direct fetcher
        s3_resources = [
            {
                "resource_id": "my-bucket",
                "resource_type": "s3:bucket",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 10.0,
                "arn": "arn:aws:s3:::my-bucket",
            },
        ]

        async def mock_fetch_by_type(resource_type, filters):
            if resource_type == "ec2:instance":
                return ec2_resources
            elif resource_type == "s3:bucket":
                return s3_resources
            return []

        compliance_service._fetch_resources_by_type = AsyncMock(side_effect=mock_fetch_by_type)

        # Free resources returned by batch Tagging API (these should be filtered)
        tagging_api_resources = [
            {
                "resource_id": "vpc-123",
                "resource_type": "ec2:vpc",  # FREE - should be filtered
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 0.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:vpc/vpc-123",
            },
            {
                "resource_id": "subnet-123",
                "resource_type": "ec2:subnet",  # FREE - should be filtered
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 0.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:subnet/subnet-123",
            },
            {
                "resource_id": "sg-123",
                "resource_type": "ec2:security-group",  # FREE - should be filtered
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 0.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:security-group/sg-123",
            },
        ]

        mock_aws_client.get_all_tagged_resources = AsyncMock(
            return_value=tagging_api_resources
        )
        mock_policy_service.validate_resource_tags.return_value = []

        result = await compliance_service._scan_and_validate(
            resource_types=["all"], filters=None, severity="all"
        )

        # Only 2 cost-generating resources should be included (ec2:instance, s3:bucket)
        # VPC, Subnet, Security Group should be filtered out
        assert result.total_resources == 2
        assert result.compliant_resources == 2


class TestMultiRegionCacheBehavior:
    """Test cache behavior with multi-region scanning support.

    These tests verify that the caching mechanism works correctly when
    scanning resources across multiple AWS regions, ensuring:
    - Cache hits return cached results without re-scanning
    - Cache misses trigger new scans
    - force_refresh bypasses cache even with cached multi-region results
    - Cache invalidation clears multi-region cached results
    - scanned_regions parameter affects cache key generation

    Requirements: 8.1, 8.3, 8.4
    """

    @pytest.mark.asyncio
    async def test_cache_hit_with_multi_region_results(self, compliance_service, mock_cache):
        """Test that cache hit returns cached multi-region result without scanning.

        When a cached result exists for a multi-region scan, the service should
        return the cached result without making any AWS API calls.

        Requirements: 8.1 - Cache multi-region results
        """
        # Setup cached multi-region data
        cached_data = {
            "compliance_score": 0.85,
            "total_resources": 50,
            "compliant_resources": 42,
            "violations": [
                {
                    "resource_id": "i-123",
                    "resource_type": "ec2:instance",
                    "region": "us-west-2",
                    "violation_type": "missing_required_tag",
                    "tag_name": "CostCenter",
                    "severity": "error",
                    "cost_impact_monthly": 100.0,
                }
            ],
            "cost_attribution_gap": 800.0,
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        mock_cache.get.return_value = cached_data

        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance", "rds:db"],
            filters=None,
            severity="all",
        )

        # Verify cached result was returned
        assert result.compliance_score == 0.85
        assert result.total_resources == 50
        assert result.compliant_resources == 42
        assert len(result.violations) == 1
        assert result.cost_attribution_gap == 800.0

        # Verify cache was checked
        mock_cache.get.assert_called_once()
        # Verify no new cache entry was created (cache hit)
        mock_cache.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_scan_for_multi_region(
        self, compliance_service, mock_cache, mock_aws_client, mock_policy_service
    ):
        """Test that cache miss triggers actual scan and caches result.

        When no cached result exists, the service should perform a full scan
        and cache the results for future requests.

        Requirements: 8.1 - Cache multi-region results after scan
        """
        # Setup cache miss
        mock_cache.get.return_value = None

        # Setup mock resources from multiple regions
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 150.0,
            },
        ]

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
        mock_policy_service.validate_resource_tags.return_value = []

        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Verify scan was performed
        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 2
        assert result.compliance_score == 1.0

        # Verify cache was checked and result was cached
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_called_once()

        # Verify cached data structure
        cached_call = mock_cache.set.call_args
        assert cached_call[0][0].startswith("compliance:")
        assert cached_call[1]["ttl"] == 3600

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_multi_region_cache(
        self, compliance_service, mock_cache, mock_aws_client, mock_policy_service
    ):
        """Test that force_refresh=True bypasses cache even with cached multi-region results.

        When force_refresh is True, the service should ignore any cached results
        and perform a fresh scan, then update the cache with new results.

        Requirements: 8.3 - force_refresh bypasses cache
        """
        # Setup cached data that should be ignored
        cached_data = {
            "compliance_score": 0.5,
            "total_resources": 100,
            "compliant_resources": 50,
            "violations": [],
            "cost_attribution_gap": 5000.0,
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        mock_cache.get.return_value = cached_data

        # Setup fresh scan results (different from cached)
        mock_resources = [
            {
                "resource_id": "i-new-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 200.0,
            },
        ]

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
        mock_policy_service.validate_resource_tags.return_value = []

        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            force_refresh=True,
        )

        # Verify fresh scan result (not cached data)
        assert result.total_resources == 1  # Fresh scan has 1 resource, not 100
        assert result.compliance_score == 1.0  # Fresh scan is fully compliant

        # Verify cache.get was NOT called (force_refresh bypasses cache check)
        mock_cache.get.assert_not_called()

        # Verify new result was cached
        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_invalidation_clears_multi_region_results(
        self, compliance_service, mock_cache
    ):
        """Test that cache invalidation clears all cached multi-region results.

        When invalidate_cache is called without parameters, all compliance
        cache entries should be cleared, including multi-region results.

        Requirements: 8.4 - Cache invalidation clears cached results
        """
        result = await compliance_service.invalidate_cache()

        assert result is True
        mock_cache.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_invalidation_specific_multi_region_entry(
        self, compliance_service, mock_cache
    ):
        """Test invalidating a specific multi-region cache entry.

        When invalidate_cache is called with specific resource types and filters,
        only the matching cache entry should be invalidated.

        Requirements: 8.4 - Cache invalidation for specific entries
        """
        result = await compliance_service.invalidate_cache(
            resource_types=["ec2:instance", "rds:db"],
            filters={"region": ["us-east-1", "us-west-2"]},
        )

        assert result is True
        mock_cache.delete.assert_called_once()

        # Verify the cache key was generated correctly
        deleted_key = mock_cache.delete.call_args[0][0]
        assert deleted_key.startswith("compliance:")

    @pytest.mark.asyncio
    async def test_scanned_regions_affects_cache_key(self, compliance_service, mock_cache):
        """Test that scanned_regions parameter creates different cache keys.

        Different sets of scanned regions should produce different cache keys
        to prevent cache pollution between different region combinations.

        Requirements: 8.1, 8.2 - Cache key includes scanned regions
        """
        # Generate cache keys with different scanned regions
        key_regions_1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "us-west-2"],
        )

        key_regions_2 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "eu-west-1"],
        )

        key_no_regions = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=None,
        )

        # All keys should be different
        assert key_regions_1 != key_regions_2
        assert key_regions_1 != key_no_regions
        assert key_regions_2 != key_no_regions

    @pytest.mark.asyncio
    async def test_cache_key_deterministic_with_scanned_regions(self, compliance_service):
        """Test that same scanned regions always produce same cache key.

        Cache key generation must be deterministic - same inputs should
        always produce the same key regardless of call order.

        Requirements: 8.2 - Deterministic cache key generation
        """
        scanned_regions = ["us-east-1", "us-west-2", "eu-west-1"]

        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=scanned_regions,
        )

        key2 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=scanned_regions,
        )

        assert key1 == key2

    @pytest.mark.asyncio
    async def test_cache_key_order_independent_for_scanned_regions(self, compliance_service):
        """Test that scanned region order doesn't affect cache key.

        The cache key should be the same regardless of the order in which
        scanned regions are provided.

        Requirements: 8.2 - Deterministic cache key (order independent)
        """
        key1 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "us-west-2", "eu-west-1"],
        )

        key2 = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["eu-west-1", "us-east-1", "us-west-2"],
        )

        assert key1 == key2

    @pytest.mark.asyncio
    async def test_cache_stores_multi_region_violations(
        self, compliance_service, mock_cache, mock_aws_client, mock_policy_service
    ):
        """Test that cached results preserve violations from multiple regions.

        When caching multi-region results, violations from all regions should
        be preserved and retrievable from cache.

        Requirements: 8.1 - Cache multi-region results with all violations
        """
        mock_cache.get.return_value = None

        # Setup resources from multiple regions with violations
        mock_resources = [
            {
                "resource_id": "i-east-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},  # Missing tags - will have violation
                "cost_impact": 100.0,
            },
            {
                "resource_id": "i-west-456",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {},  # Missing tags - will have violation
                "cost_impact": 150.0,
            },
        ]

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)

        # Create violations for each resource
        def create_violation(resource_id, resource_type, region, tags, cost_impact):
            return [
                Violation(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=Severity.ERROR,
                    cost_impact_monthly=cost_impact,
                )
            ]

        mock_policy_service.validate_resource_tags.side_effect = create_violation

        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Verify violations from both regions
        assert len(result.violations) == 2
        violation_regions = {v.region for v in result.violations}
        assert "us-east-1" in violation_regions
        assert "us-west-2" in violation_regions

        # Verify result was cached
        mock_cache.set.assert_called_once()

        # Verify cached data includes all violations
        cached_data = mock_cache.set.call_args[0][1]
        assert len(cached_data["violations"]) == 2

    @pytest.mark.asyncio
    async def test_cache_ttl_applied_to_multi_region_results(
        self, compliance_service, mock_cache, mock_aws_client, mock_policy_service
    ):
        """Test that cache TTL is correctly applied to multi-region results.

        The configured cache TTL should be applied when caching multi-region
        scan results.

        Requirements: 8.1 - Cache with configurable TTL
        """
        mock_cache.get.return_value = None
        mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])
        mock_policy_service.validate_resource_tags.return_value = []

        await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Verify TTL was applied
        mock_cache.set.assert_called_once()
        call_kwargs = mock_cache.set.call_args[1]
        assert call_kwargs["ttl"] == 3600  # Default TTL from fixture

    @pytest.mark.asyncio
    async def test_cache_hit_preserves_cost_attribution_gap(self, compliance_service, mock_cache):
        """Test that cached results preserve cost attribution gap from all regions.

        The cost_attribution_gap should be correctly preserved and returned
        from cached multi-region results.

        Requirements: 8.1 - Cache preserves aggregated cost data
        """
        # Setup cached data with cost attribution gap from multiple regions
        cached_data = {
            "compliance_score": 0.75,
            "total_resources": 40,
            "compliant_resources": 30,
            "violations": [
                {
                    "resource_id": "i-east-123",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "violation_type": "missing_required_tag",
                    "tag_name": "CostCenter",
                    "severity": "error",
                    "cost_impact_monthly": 500.0,
                },
                {
                    "resource_id": "i-west-456",
                    "resource_type": "ec2:instance",
                    "region": "us-west-2",
                    "violation_type": "missing_required_tag",
                    "tag_name": "Environment",
                    "severity": "error",
                    "cost_impact_monthly": 300.0,
                },
            ],
            "cost_attribution_gap": 800.0,  # Sum of all regional cost gaps
            "scan_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        mock_cache.get.return_value = cached_data

        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Verify cost attribution gap is preserved
        assert result.cost_attribution_gap == 800.0

    @pytest.mark.asyncio
    async def test_different_severity_filters_produce_different_cache_keys(
        self, compliance_service
    ):
        """Test that different severity filters produce different cache keys.

        Cache keys should differentiate between scans with different severity
        filters to prevent returning incorrect cached results.

        Requirements: 8.2 - Cache key includes all query parameters
        """
        key_all = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1"],
        )

        key_errors = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="errors_only",
            scanned_regions=["us-east-1"],
        )

        key_warnings = compliance_service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="warnings_only",
            scanned_regions=["us-east-1"],
        )

        # All keys should be different
        assert key_all != key_errors
        assert key_all != key_warnings
        assert key_errors != key_warnings

    @pytest.mark.asyncio
    async def test_cache_failure_does_not_break_multi_region_scan(
        self, compliance_service, mock_cache, mock_aws_client, mock_policy_service
    ):
        """Test that cache failures don't break multi-region scanning.

        If caching fails (e.g., Redis unavailable), the scan should still
        complete successfully and return results.

        Requirements: 8.1 - Graceful degradation on cache failure
        """
        # Setup cache to fail
        mock_cache.get.return_value = None
        mock_cache.set.side_effect = Exception("Redis connection failed")

        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
            },
        ]

        mock_aws_client.get_ec2_instances = AsyncMock(return_value=mock_resources)
        mock_policy_service.validate_resource_tags.return_value = []

        # Should not raise exception despite cache failure
        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Verify scan completed successfully
        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 1
        assert result.compliance_score == 1.0
