# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Compliance service with violation caching."""

import hashlib
import json
import logging

from ..clients.aws_client import AWSClient
from ..clients.cache import RedisCache
from ..models.compliance import ComplianceResult
from ..models.violations import Violation
from ..services.policy_service import PolicyService
from ..utils.resource_type_config import get_resource_type_config
from ..utils.resource_utils import extract_account_from_arn, fetch_resources_by_type

logger = logging.getLogger(__name__)


class ComplianceService:
    """
    Service for checking tag compliance with caching support.

    Orchestrates resource scanning, policy validation, and violation detection.
    Caches compliance results to minimize AWS API calls and improve performance.
    """

    def __init__(
        self,
        cache: RedisCache,
        aws_client: AWSClient,
        policy_service: PolicyService,
        cache_ttl: int = 3600,
    ):
        """
        Initialize compliance service.

        Args:
            cache: Redis cache instance for caching compliance results
            aws_client: AWS client for fetching resources
            policy_service: Policy service for validation rules
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
        """
        self.cache = cache
        self.aws_client = aws_client
        self.policy_service = policy_service
        self.cache_ttl = cache_ttl

    def _generate_cache_key(
        self, resource_types: list[str], filters: dict | None = None, severity: str = "all"
    ) -> str:
        """
        Generate a deterministic cache key from query parameters.

        Args:
            resource_types: List of resource types to check
            filters: Optional filters (region, account_id, etc.)
            severity: Severity filter

        Returns:
            SHA256 hash of the normalized query parameters
        """
        # Normalize parameters for consistent hashing
        normalized = {
            "resource_types": sorted(resource_types),
            "filters": filters or {},
            "severity": severity,
        }

        # Create deterministic JSON string
        json_str = json.dumps(normalized, sort_keys=True)

        # Generate hash
        hash_obj = hashlib.sha256(json_str.encode())
        cache_key = f"compliance:{hash_obj.hexdigest()}"

        return cache_key

    async def check_compliance(
        self,
        resource_types: list[str],
        filters: dict | None = None,
        severity: str = "all",
        force_refresh: bool = False,
    ) -> ComplianceResult:
        """
        Check tag compliance for AWS resources with caching.

        This method implements the caching strategy:
        1. Generate cache key from query parameters
        2. Check cache for existing results (unless force_refresh=True)
        3. If cache hit and fresh, return cached results
        4. If cache miss, scan resources and validate against policy
        5. Cache the new results before returning

        Args:
            resource_types: List of resource types to check (e.g., ["ec2:instance"])
            filters: Optional filters for region, account_id
            severity: Filter by severity ("errors_only", "warnings_only", "all")
            force_refresh: If True, bypass cache and force new scan

        Returns:
            ComplianceResult with score, violations, and cost impact
        """
        # Generate cache key
        cache_key = self._generate_cache_key(resource_types, filters, severity)

        # Try to get from cache (unless force_refresh)
        if not force_refresh:
            cached_result = await self._get_from_cache(cache_key)
            if cached_result is not None:
                logger.info(f"Returning cached compliance result for key: {cache_key}")
                return cached_result

        # Cache miss or force refresh - perform actual scan
        logger.info("Cache miss or force refresh - scanning resources")
        result = await self._scan_and_validate(resource_types, filters, severity)

        # Cache the result
        await self._cache_result(cache_key, result)

        return result

    async def _get_from_cache(self, cache_key: str) -> ComplianceResult | None:
        """
        Retrieve compliance result from cache.

        Args:
            cache_key: Cache key to retrieve

        Returns:
            ComplianceResult if found and valid, None otherwise
        """
        try:
            cached_data = await self.cache.get(cache_key)

            if cached_data is None:
                return None

            # Deserialize to ComplianceResult
            result = ComplianceResult(**cached_data)
            return result

        except Exception as e:
            logger.warning(f"Failed to retrieve from cache: {str(e)}")
            return None

    async def _cache_result(self, cache_key: str, result: ComplianceResult) -> None:
        """
        Cache a compliance result.

        Args:
            cache_key: Cache key to store under
            result: ComplianceResult to cache
        """
        try:
            # Serialize to dict for caching
            result_dict = result.model_dump(mode="json")

            # Store in cache with TTL
            await self.cache.set(cache_key, result_dict, ttl=self.cache_ttl)
            logger.info(f"Cached compliance result with key: {cache_key}")

        except Exception as e:
            logger.warning(f"Failed to cache result: {str(e)}")
            # Don't raise - caching failure shouldn't break the operation

    async def _scan_and_validate(
        self, resource_types: list[str], filters: dict | None, severity: str
    ) -> ComplianceResult:
        """
        Scan resources and validate against policy.

        This is the actual compliance checking logic that runs when
        cache is unavailable or stale.

        Orchestrates:
        1. Resource scanning across all specified resource types
        2. Filtering by region, account, and resource type
        3. Policy validation for each resource
        4. Compliance score calculation
        5. Violation aggregation and severity filtering

        Args:
            resource_types: List of resource types to check
            filters: Optional filters (region, account_id, etc.)
            severity: Severity filter ("errors_only", "warnings_only", "all")

        Returns:
            ComplianceResult with violations

        Requirements: 1.1, 1.2, 1.3, 1.4
        """
        logger.info(
            f"Scanning resources: {resource_types}, filters: {filters}, severity: {severity}"
        )

        # Collect all resources across resource types
        all_resources = []

        for resource_type in resource_types:
            try:
                resources = await self._fetch_resources_by_type(resource_type, filters)
                all_resources.extend(resources)
                logger.info(f"Fetched {len(resources)} resources of type {resource_type}")
            except Exception as e:
                logger.error(f"Failed to fetch resources of type {resource_type}: {str(e)}")
                # Continue with other resource types even if one fails
                continue

        logger.info(f"Total resources fetched before filtering: {len(all_resources)}")

        # Filter out free resources (VPC, Subnet, Security Group, etc.)
        # These are taggable but have no direct cost, so we exclude them from compliance scans
        config = get_resource_type_config()
        filtered_by_cost = []
        free_resource_count = 0

        for resource in all_resources:
            resource_type = resource.get("resource_type", "")
            if config.is_free_resource(resource_type):
                free_resource_count += 1
                continue
            filtered_by_cost.append(resource)

        if free_resource_count > 0:
            logger.info(
                f"Excluded {free_resource_count} free resources (VPC, Subnet, Security Group, etc.)"
            )

        # Apply post-fetch filters (region, account_id)
        filtered_resources = self._apply_resource_filters(filtered_by_cost, filters)
        logger.info(f"Total resources after filtering: {len(filtered_resources)}")

        # Validate each resource against policy and collect violations
        all_violations = []
        compliant_count = 0

        for resource in filtered_resources:
            violations = self.policy_service.validate_resource_tags(
                resource_id=resource["resource_id"],
                resource_type=resource["resource_type"],
                region=resource["region"],
                tags=resource["tags"],
                cost_impact=resource.get("cost_impact", 0.0),
            )

            if violations:
                all_violations.extend(violations)
            else:
                compliant_count += 1

        logger.info(
            f"Found {len(all_violations)} violations across {len(filtered_resources)} resources"
        )

        # Apply severity filter to violations
        filtered_violations = self._filter_by_severity(all_violations, severity)

        # Calculate compliance score
        total_resources = len(filtered_resources)
        compliance_score = self._calculate_compliance_score(compliant_count, total_resources)

        # Calculate cost attribution gap (sum of cost impacts from violations)
        cost_attribution_gap = sum(v.cost_impact_monthly for v in all_violations)

        return ComplianceResult(
            compliance_score=compliance_score,
            total_resources=total_resources,
            compliant_resources=compliant_count,
            violations=filtered_violations,
            cost_attribution_gap=cost_attribution_gap,
        )

    def _apply_resource_filters(self, resources: list[dict], filters: dict | None) -> list[dict]:
        """
        Apply filters to resources after fetching.

        Supports filtering by:
        - region: Filter resources by AWS region
        - account_id: Filter resources by AWS account ID

        Args:
            resources: List of resource dictionaries
            filters: Optional filters dictionary

        Returns:
            Filtered list of resources

        Requirements: 1.3 - Filter by region and account
        """
        if not filters:
            return resources

        filtered = resources

        # Filter by region
        if "region" in filters and filters["region"]:
            region_filter = filters["region"]
            # Support both single region string and list of regions
            if isinstance(region_filter, str):
                region_filter = [region_filter]

            filtered = [r for r in filtered if r.get("region") in region_filter]
            logger.info(f"Filtered to {len(filtered)} resources in regions: {region_filter}")

        # Filter by account_id
        if "account_id" in filters and filters["account_id"]:
            account_filter = filters["account_id"]
            # Support both single account string and list of accounts
            if isinstance(account_filter, str):
                account_filter = [account_filter]

            filtered = [
                r for r in filtered if extract_account_from_arn(r.get("arn", "")) in account_filter
            ]
            logger.info(f"Filtered to {len(filtered)} resources in accounts: {account_filter}")

        return filtered

    async def _fetch_resources_by_type(
        self, resource_type: str, filters: dict | None
    ) -> list[dict]:
        """
        Fetch resources of a specific type from AWS.

        Args:
            resource_type: Type of resource (e.g., "ec2:instance", "rds:db")
            filters: Optional filters for the query

        Returns:
            List of resource dictionaries with tags
        """
        return await fetch_resources_by_type(self.aws_client, resource_type, filters)

    def _calculate_compliance_score(self, compliant_resources: int, total_resources: int) -> float:
        """
        Calculate compliance score as ratio of compliant to total resources.

        When total resources is zero, returns 1.0 (fully compliant by default).

        Args:
            compliant_resources: Number of compliant resources
            total_resources: Total number of resources scanned

        Returns:
            Compliance score between 0.0 and 1.0

        Requirements: 1.1 - Compliance score calculation
        """
        if total_resources == 0:
            return 1.0

        return compliant_resources / total_resources

    def _filter_by_severity(self, violations: list[Violation], severity: str) -> list[Violation]:
        """
        Filter violations by severity level.

        Args:
            violations: List of all violations
            severity: Severity filter ("errors_only", "warnings_only", "all")

        Returns:
            Filtered list of violations

        Requirements: 1.4 - Support filtering by severity level
        """
        if severity == "all":
            return violations

        from ..models.enums import Severity

        if severity == "errors_only":
            return [v for v in violations if v.severity == Severity.ERROR]
        elif severity == "warnings_only":
            return [v for v in violations if v.severity == Severity.WARNING]
        else:
            # Unknown severity filter, return all
            logger.warning(f"Unknown severity filter: {severity}, returning all violations")
            return violations

    async def invalidate_cache(
        self, resource_types: list[str] | None = None, filters: dict | None = None
    ) -> bool:
        """
        Invalidate cached compliance results.

        This should be called when:
        - A new compliance scan is triggered
        - Resources are modified
        - Policy is updated

        Args:
            resource_types: If specified, only invalidate cache for these types
            filters: If specified, only invalidate cache matching these filters

        Returns:
            True if cache was invalidated, False if cache unavailable
        """
        if resource_types is None and filters is None:
            # Clear all compliance cache entries
            # For now, we'll clear the entire cache
            # In production, we'd use key patterns like "compliance:*"
            logger.info("Invalidating all compliance cache entries")
            return await self.cache.clear()
        else:
            # Invalidate specific cache entry
            cache_key = self._generate_cache_key(
                resource_types or [], filters, "all"  # Default severity for invalidation
            )
            logger.info(f"Invalidating cache for key: {cache_key}")
            return await self.cache.delete(cache_key)
