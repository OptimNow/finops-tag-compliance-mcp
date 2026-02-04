"""Unit tests for RegionDiscoveryService.

Tests caching behavior, fallback on API failure, and region filtering by opt-in status.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from mcp_server.clients.cache import RedisCache
from mcp_server.services.region_discovery_service import (
    ENABLED_REGIONS_CACHE_KEY,
    VALID_OPT_IN_STATUSES,
    RegionDiscoveryError,
    RegionDiscoveryService,
    filter_regions_by_opt_in_status,
)


@pytest.fixture
def mock_cache():
    """Create a mock Redis cache."""
    cache = MagicMock(spec=RedisCache)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def mock_ec2_client():
    """Create a mock EC2 client."""
    client = MagicMock()
    return client


@pytest.fixture
def region_discovery_service(mock_ec2_client, mock_cache):
    """Create a RegionDiscoveryService instance with mocked dependencies."""
    return RegionDiscoveryService(
        ec2_client=mock_ec2_client,
        cache=mock_cache,
        cache_ttl=3600,
        default_region="us-east-1",
    )


class TestRegionDiscoveryServiceInit:
    """Test RegionDiscoveryService initialization."""

    def test_init_with_defaults(self, mock_ec2_client, mock_cache):
        """Test initialization with default values."""
        service = RegionDiscoveryService(
            ec2_client=mock_ec2_client,
            cache=mock_cache,
        )

        assert service.ec2_client == mock_ec2_client
        assert service.cache == mock_cache
        assert service.cache_ttl == 3600  # Default
        assert service.default_region == "us-east-1"  # Default

    def test_init_with_custom_values(self, mock_ec2_client, mock_cache):
        """Test initialization with custom values."""
        service = RegionDiscoveryService(
            ec2_client=mock_ec2_client,
            cache=mock_cache,
            cache_ttl=7200,
            default_region="eu-west-1",
        )

        assert service.cache_ttl == 7200
        assert service.default_region == "eu-west-1"


class TestGetEnabledRegions:
    """Test get_enabled_regions method."""

    @pytest.mark.asyncio
    async def test_get_enabled_regions_cache_hit(
        self, region_discovery_service, mock_cache
    ):
        """Test that cache hit returns cached regions without API call.
        
        Requirements: 1.4 - Cache the list of enabled regions
        """
        cached_regions = ["us-east-1", "us-west-2", "eu-west-1"]
        mock_cache.get.return_value = cached_regions

        result = await region_discovery_service.get_enabled_regions()

        assert result == cached_regions
        mock_cache.get.assert_called_once_with(ENABLED_REGIONS_CACHE_KEY)
        # EC2 client should not be called on cache hit
        region_discovery_service.ec2_client.describe_regions.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_enabled_regions_cache_miss(
        self, region_discovery_service, mock_cache, mock_ec2_client
    ):
        """Test that cache miss triggers API call and caches result.
        
        Requirements: 1.1 - Call EC2 DescribeRegions API
        Requirements: 1.4 - Cache the list of enabled regions
        """
        mock_cache.get.return_value = None
        mock_ec2_client.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
                {"RegionName": "us-west-2", "OptInStatus": "opt-in-not-required"},
                {"RegionName": "eu-west-1", "OptInStatus": "opted-in"},
            ]
        }

        result = await region_discovery_service.get_enabled_regions()

        assert "us-east-1" in result
        assert "us-west-2" in result
        assert "eu-west-1" in result
        mock_cache.get.assert_called_once()
        mock_cache.set.assert_called_once()
        # Verify TTL is passed
        call_args = mock_cache.set.call_args
        assert call_args[1]["ttl"] == 3600

    @pytest.mark.asyncio
    async def test_get_enabled_regions_filters_disabled_regions(
        self, region_discovery_service, mock_cache, mock_ec2_client
    ):
        """Test that disabled regions are excluded from results.
        
        Requirements: 1.2 - Exclude regions with "not-opted-in" status
        """
        mock_cache.get.return_value = None
        mock_ec2_client.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
                {"RegionName": "af-south-1", "OptInStatus": "not-opted-in"},
                {"RegionName": "ap-east-1", "OptInStatus": "opted-in"},
                {"RegionName": "me-south-1", "OptInStatus": "not-opted-in"},
            ]
        }

        result = await region_discovery_service.get_enabled_regions()

        assert "us-east-1" in result
        assert "ap-east-1" in result
        assert "af-south-1" not in result
        assert "me-south-1" not in result
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_enabled_regions_fallback_on_api_failure(
        self, region_discovery_service, mock_cache, mock_ec2_client
    ):
        """Test fallback to default region on API failure.
        
        Requirements: 1.3 - Fall back to default region on failure
        """
        mock_cache.get.return_value = None
        mock_ec2_client.describe_regions.side_effect = ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "Access denied"}},
            "DescribeRegions",
        )

        result = await region_discovery_service.get_enabled_regions()

        assert result == ["us-east-1"]  # Default region

    @pytest.mark.asyncio
    async def test_get_enabled_regions_fallback_on_timeout(
        self, region_discovery_service, mock_cache, mock_ec2_client
    ):
        """Test fallback to default region on timeout.
        
        Requirements: 1.3 - Fall back to default region on failure
        """
        mock_cache.get.return_value = None
        mock_ec2_client.describe_regions.side_effect = Exception("Connection timeout")

        result = await region_discovery_service.get_enabled_regions()

        assert result == ["us-east-1"]

    @pytest.mark.asyncio
    async def test_get_enabled_regions_returns_sorted_list(
        self, region_discovery_service, mock_cache, mock_ec2_client
    ):
        """Test that regions are returned in sorted order."""
        mock_cache.get.return_value = None
        mock_ec2_client.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-west-2", "OptInStatus": "opt-in-not-required"},
                {"RegionName": "ap-southeast-1", "OptInStatus": "opt-in-not-required"},
                {"RegionName": "eu-west-1", "OptInStatus": "opt-in-not-required"},
                {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
            ]
        }

        result = await region_discovery_service.get_enabled_regions()

        assert result == sorted(result)

    @pytest.mark.asyncio
    async def test_get_enabled_regions_custom_default_region(
        self, mock_ec2_client, mock_cache
    ):
        """Test fallback uses custom default region."""
        service = RegionDiscoveryService(
            ec2_client=mock_ec2_client,
            cache=mock_cache,
            default_region="eu-central-1",
        )
        mock_cache.get.return_value = None
        mock_ec2_client.describe_regions.side_effect = Exception("API error")

        result = await service.get_enabled_regions()

        assert result == ["eu-central-1"]


class TestCacheBehavior:
    """Test caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_stores_regions_with_ttl(
        self, region_discovery_service, mock_cache, mock_ec2_client
    ):
        """Test that regions are cached with correct TTL."""
        mock_cache.get.return_value = None
        mock_ec2_client.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
            ]
        }

        await region_discovery_service.get_enabled_regions()

        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args[0][0] == ENABLED_REGIONS_CACHE_KEY
        assert call_args[0][1] == ["us-east-1"]
        assert call_args[1]["ttl"] == 3600

    @pytest.mark.asyncio
    async def test_cache_failure_doesnt_break_discovery(
        self, region_discovery_service, mock_cache, mock_ec2_client
    ):
        """Test that cache failure doesn't prevent region discovery."""
        mock_cache.get.return_value = None
        mock_cache.set.side_effect = Exception("Redis connection error")
        mock_ec2_client.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
            ]
        }

        # Should not raise
        result = await region_discovery_service.get_enabled_regions()

        assert result == ["us-east-1"]

    @pytest.mark.asyncio
    async def test_invalid_cached_data_triggers_api_call(
        self, region_discovery_service, mock_cache, mock_ec2_client
    ):
        """Test that invalid cached data triggers fresh API call."""
        # Return invalid data (not a list of strings)
        mock_cache.get.return_value = {"invalid": "data"}
        mock_ec2_client.describe_regions.return_value = {
            "Regions": [
                {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
            ]
        }

        result = await region_discovery_service.get_enabled_regions()

        assert result == ["us-east-1"]
        mock_ec2_client.describe_regions.assert_called_once()


class TestInvalidateCache:
    """Test cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_cache_success(
        self, region_discovery_service, mock_cache
    ):
        """Test successful cache invalidation."""
        mock_cache.delete.return_value = True

        result = await region_discovery_service.invalidate_cache()

        assert result is True
        mock_cache.delete.assert_called_once_with(ENABLED_REGIONS_CACHE_KEY)

    @pytest.mark.asyncio
    async def test_invalidate_cache_not_found(
        self, region_discovery_service, mock_cache
    ):
        """Test cache invalidation when key doesn't exist."""
        mock_cache.delete.return_value = False

        result = await region_discovery_service.invalidate_cache()

        assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_cache_failure(
        self, region_discovery_service, mock_cache
    ):
        """Test cache invalidation failure."""
        mock_cache.delete.side_effect = Exception("Redis error")

        result = await region_discovery_service.invalidate_cache()

        assert result is False


class TestFilterRegionsByOptInStatus:
    """Test the pure filter_regions_by_opt_in_status function."""

    def test_filter_includes_opt_in_not_required(self):
        """Test that opt-in-not-required regions are included."""
        regions = [
            {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "us-west-2", "OptInStatus": "opt-in-not-required"},
        ]

        result = filter_regions_by_opt_in_status(regions)

        assert "us-east-1" in result
        assert "us-west-2" in result

    def test_filter_includes_opted_in(self):
        """Test that opted-in regions are included."""
        regions = [
            {"RegionName": "af-south-1", "OptInStatus": "opted-in"},
            {"RegionName": "ap-east-1", "OptInStatus": "opted-in"},
        ]

        result = filter_regions_by_opt_in_status(regions)

        assert "af-south-1" in result
        assert "ap-east-1" in result

    def test_filter_excludes_not_opted_in(self):
        """Test that not-opted-in regions are excluded.
        
        Requirements: 1.2 - Exclude regions with "not-opted-in" status
        """
        regions = [
            {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "af-south-1", "OptInStatus": "not-opted-in"},
            {"RegionName": "me-south-1", "OptInStatus": "not-opted-in"},
        ]

        result = filter_regions_by_opt_in_status(regions)

        assert "us-east-1" in result
        assert "af-south-1" not in result
        assert "me-south-1" not in result
        assert len(result) == 1

    def test_filter_handles_empty_list(self):
        """Test filtering empty region list."""
        result = filter_regions_by_opt_in_status([])

        assert result == []

    def test_filter_handles_missing_fields(self):
        """Test filtering regions with missing fields."""
        regions = [
            {"RegionName": "us-east-1"},  # Missing OptInStatus
            {"OptInStatus": "opt-in-not-required"},  # Missing RegionName
            {"RegionName": "us-west-2", "OptInStatus": "opt-in-not-required"},
        ]

        result = filter_regions_by_opt_in_status(regions)

        # Only us-west-2 should be included (has both fields with valid status)
        assert result == ["us-west-2"]
        assert len(result) == 1

    def test_filter_returns_sorted_list(self):
        """Test that filtered regions are sorted."""
        regions = [
            {"RegionName": "us-west-2", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "ap-southeast-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "eu-west-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
        ]

        result = filter_regions_by_opt_in_status(regions)

        assert result == sorted(result)

    def test_filter_handles_unknown_status(self):
        """Test filtering regions with unknown opt-in status."""
        regions = [
            {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "unknown-region", "OptInStatus": "unknown-status"},
        ]

        result = filter_regions_by_opt_in_status(regions)

        assert "us-east-1" in result
        assert "unknown-region" not in result


class TestValidOptInStatuses:
    """Test the VALID_OPT_IN_STATUSES constant."""

    def test_valid_statuses_contains_expected_values(self):
        """Test that valid statuses include expected values."""
        assert "opt-in-not-required" in VALID_OPT_IN_STATUSES
        assert "opted-in" in VALID_OPT_IN_STATUSES

    def test_valid_statuses_excludes_not_opted_in(self):
        """Test that not-opted-in is not in valid statuses."""
        assert "not-opted-in" not in VALID_OPT_IN_STATUSES

    def test_valid_statuses_is_frozenset(self):
        """Test that valid statuses is immutable."""
        assert isinstance(VALID_OPT_IN_STATUSES, frozenset)


class TestRegionDiscoveryError:
    """Test RegionDiscoveryError exception."""

    def test_error_message(self):
        """Test error message is preserved."""
        error = RegionDiscoveryError("Test error message")
        assert str(error) == "Test error message"

    def test_error_inheritance(self):
        """Test error inherits from Exception."""
        error = RegionDiscoveryError("Test")
        assert isinstance(error, Exception)
