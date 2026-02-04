# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Region discovery service for multi-region scanning.

This module provides functionality to discover all enabled AWS regions
for an account using the EC2 DescribeRegions API. Results are cached
to minimize API calls.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import boto3

from ..clients.cache import RedisCache

logger = logging.getLogger(__name__)

# Cache key for enabled regions
ENABLED_REGIONS_CACHE_KEY = "enabled_regions"

# Valid opt-in statuses for enabled regions
VALID_OPT_IN_STATUSES = frozenset(["opt-in-not-required", "opted-in"])


@dataclass
class RegionDiscoveryResult:
    """Result from region discovery operation.

    Contains the list of enabled regions along with metadata about
    whether discovery succeeded or fell back to the default region.

    Attributes:
        regions: List of region codes (may be just default if fallback occurred)
        discovery_failed: True if API discovery failed and fell back to default
        discovery_error: Error message if discovery failed, None otherwise
    """

    regions: list[str]
    discovery_failed: bool = False
    discovery_error: str | None = None


class RegionDiscoveryError(Exception):
    """Raised when region discovery fails."""

    pass


class RegionDiscoveryService:
    """
    Discovers and caches enabled AWS regions.

    Uses EC2 DescribeRegions API to find all regions that are enabled
    for the account. Results are cached to minimize API calls.

    Requirements:
        1.1: Call EC2 DescribeRegions API to retrieve all enabled regions
        1.2: Exclude regions with "not-opted-in" status
        1.3: Fall back to default region on API failure
        1.4: Cache the list of enabled regions for a configurable TTL
    """

    def __init__(
        self,
        ec2_client: "boto3.client",
        cache: RedisCache,
        cache_ttl: int = 3600,
        default_region: str = "us-east-1",
    ):
        """
        Initialize with EC2 client and cache.

        Args:
            ec2_client: boto3 EC2 client for calling DescribeRegions API
            cache: Redis cache instance for caching region list
            cache_ttl: Time-to-live for cached region list in seconds (default: 1 hour)
            default_region: Default region to fall back to on API failure
        """
        self.ec2_client = ec2_client
        self.cache = cache
        self.cache_ttl = cache_ttl
        self.default_region = default_region

    async def get_enabled_regions(self) -> list[str]:
        """
        Get list of all enabled AWS regions.

        Returns cached results if available and fresh.
        Falls back to default region on API failure.

        The method filters regions by OptInStatus, including only:
        - "opt-in-not-required": Regions enabled by default (e.g., us-east-1)
        - "opted-in": Regions explicitly enabled by the account

        Regions with "not-opted-in" status are excluded.

        Returns:
            List of region codes (e.g., ["us-east-1", "us-west-2", ...])

        Requirements: 1.1, 1.2, 1.3, 1.4
        """
        result = await self.get_enabled_regions_with_status()
        return result.regions

    async def get_enabled_regions_with_status(self) -> RegionDiscoveryResult:
        """
        Get list of all enabled AWS regions with discovery status.

        This method is similar to get_enabled_regions() but returns
        additional metadata about whether discovery succeeded or
        fell back to the default region.

        Use this method when you need to know if region discovery
        failed and the results may be incomplete.

        Returns:
            RegionDiscoveryResult containing:
            - regions: List of region codes
            - discovery_failed: True if API call failed and fell back
            - discovery_error: Error message if discovery failed

        Requirements: 1.1, 1.2, 1.3, 1.4
        """
        # Try to get from cache first (Requirement 1.4)
        cached_regions = await self._get_from_cache()
        if cached_regions is not None:
            logger.info(f"Returning {len(cached_regions)} cached enabled regions")
            return RegionDiscoveryResult(regions=cached_regions)

        # Cache miss - call EC2 DescribeRegions API (Requirement 1.1)
        try:
            regions = await self._discover_regions()

            # Cache the result (Requirement 1.4)
            await self._cache_regions(regions)

            logger.info(f"Discovered {len(regions)} enabled regions")
            return RegionDiscoveryResult(regions=regions)

        except Exception as e:
            # Fall back to default region on failure (Requirement 1.3)
            error_msg = str(e)
            logger.warning(
                f"Region discovery failed: {error_msg}. "
                f"Falling back to default region: {self.default_region}"
            )
            return RegionDiscoveryResult(
                regions=[self.default_region],
                discovery_failed=True,
                discovery_error=error_msg,
            )

    async def _discover_regions(self) -> list[str]:
        """
        Call EC2 DescribeRegions API and filter by opt-in status.

        Returns:
            List of enabled region codes

        Raises:
            RegionDiscoveryError: If the API call fails

        Requirements: 1.1, 1.2
        """
        try:
            # Run boto3 call in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.ec2_client.describe_regions(AllRegions=True),
            )

            # Filter regions by opt-in status (Requirement 1.2)
            enabled_regions = []
            for region_info in response.get("Regions", []):
                region_name = region_info.get("RegionName", "")
                opt_in_status = region_info.get("OptInStatus", "")

                # Include only regions that are enabled
                if opt_in_status in VALID_OPT_IN_STATUSES:
                    enabled_regions.append(region_name)
                else:
                    logger.debug(
                        f"Excluding region {region_name} with opt-in status: {opt_in_status}"
                    )

            # Sort for consistent ordering
            enabled_regions.sort()

            return enabled_regions

        except Exception as e:
            raise RegionDiscoveryError(f"Failed to discover regions: {str(e)}") from e

    async def _get_from_cache(self) -> list[str] | None:
        """
        Retrieve enabled regions from cache.

        Returns:
            List of region codes if found and valid, None otherwise
        """
        try:
            cached_data = await self.cache.get(ENABLED_REGIONS_CACHE_KEY)

            if cached_data is None:
                logger.debug("Cache miss for enabled regions")
                return None

            # Validate cached data is a list of strings
            if isinstance(cached_data, list) and all(isinstance(r, str) for r in cached_data):
                logger.debug(f"Cache hit for enabled regions: {len(cached_data)} regions")
                return cached_data

            logger.warning("Invalid cached data format for enabled regions")
            return None

        except Exception as e:
            logger.warning(f"Failed to retrieve regions from cache: {str(e)}")
            return None

    async def _cache_regions(self, regions: list[str]) -> None:
        """
        Cache the list of enabled regions.

        Args:
            regions: List of region codes to cache
        """
        try:
            await self.cache.set(ENABLED_REGIONS_CACHE_KEY, regions, ttl=self.cache_ttl)
            logger.debug(f"Cached {len(regions)} enabled regions with TTL {self.cache_ttl}s")

        except Exception as e:
            logger.warning(f"Failed to cache regions: {str(e)}")
            # Don't raise - caching failure shouldn't break the operation

    async def invalidate_cache(self) -> bool:
        """
        Invalidate the cached region list.

        This should be called when:
        - Region configuration changes
        - A new region is enabled/disabled
        - Cache needs to be refreshed

        Returns:
            True if cache was invalidated, False if cache unavailable
        """
        try:
            result = await self.cache.delete(ENABLED_REGIONS_CACHE_KEY)
            if result:
                logger.info("Invalidated enabled regions cache")
            else:
                logger.debug("No cached regions to invalidate")
            return result

        except Exception as e:
            logger.warning(f"Failed to invalidate regions cache: {str(e)}")
            return False


def filter_regions_by_opt_in_status(
    regions: list[dict[str, str]],
) -> list[str]:
    """
    Filter a list of region info dictionaries by opt-in status.

    This is a pure function that can be used for testing and validation.
    It filters regions to include only those with valid opt-in statuses:
    - "opt-in-not-required": Regions enabled by default
    - "opted-in": Regions explicitly enabled by the account

    Args:
        regions: List of region info dictionaries with "RegionName" and "OptInStatus" keys

    Returns:
        List of region codes that are enabled

    Requirements: 1.2
    """
    enabled_regions = []
    for region_info in regions:
        region_name = region_info.get("RegionName", "")
        opt_in_status = region_info.get("OptInStatus", "")

        # Only include regions with valid name and opt-in status
        if region_name and opt_in_status in VALID_OPT_IN_STATUSES:
            enabled_regions.append(region_name)

    return sorted(enabled_regions)
