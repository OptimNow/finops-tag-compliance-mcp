# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Multi-region scanner service for orchestrating parallel resource scanning.

This module provides the MultiRegionScanner class that orchestrates scanning
resources across all enabled AWS regions in parallel, handles failures gracefully,
and aggregates results into a unified compliance report.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3
"""

import asyncio
import logging
import random
import time
from typing import Callable

from ..clients.aws_client import AWSClient
from ..clients.regional_client_factory import RegionalClientFactory
from ..models.multi_region import (
    GLOBAL_RESOURCE_TYPES,
    MultiRegionComplianceResult,
    RegionalScanResult,
    RegionalSummary,
    RegionScanMetadata,
)
from ..models.violations import Violation
from ..utils.resource_utils import expand_all_to_supported_types
from .compliance_service import ComplianceService
from .region_discovery_service import RegionDiscoveryService

logger = logging.getLogger(__name__)

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_SECONDS = 1.0
DEFAULT_MAX_DELAY_SECONDS = 30.0

# Resource type chunking configuration for "all" mode
# When scanning "all" resource types, we chunk them to avoid overwhelming AWS APIs
DEFAULT_RESOURCE_TYPE_CHUNK_SIZE = 15  # Scan 15 resource types at a time per region
ALL_MODE_TIMEOUT_MULTIPLIER = 3  # 3x timeout when scanning "all" resource types
ALL_MODE_DEFAULT_TIMEOUT_SECONDS = 180  # 3 minutes per region for "all" mode
ALL_MODE_MAX_CONCURRENT_REGIONS = 8  # Increased concurrency for "all" mode

# Transient error codes that should trigger retries
TRANSIENT_ERROR_CODES = frozenset([
    "Throttling",
    "ThrottlingException",
    "RequestLimitExceeded",
    "ServiceUnavailable",
    "InternalError",
    "InternalServiceError",
])


class MultiRegionScanError(Exception):
    """Error during multi-region scanning.
    
    Raised when all regions fail to scan or when critical errors occur.
    May contain partial results from regions that succeeded.
    """

    def __init__(
        self,
        message: str,
        failed_regions: list[str],
        partial_results: MultiRegionComplianceResult | None = None,
    ):
        """
        Initialize multi-region scan error.
        
        Args:
            message: Error description
            failed_regions: List of regions that failed to scan
            partial_results: Partial results from successful regions, if any
        """
        super().__init__(message)
        self.failed_regions = failed_regions
        self.partial_results = partial_results


class InvalidRegionFilterError(Exception):
    """Error when region filter contains invalid or disabled regions.
    
    Raised when a user specifies regions in the filter that are not
    enabled or available in the AWS account.
    
    Requirements: 6.3
    """

    def __init__(
        self,
        message: str,
        invalid_regions: list[str],
        enabled_regions: list[str],
    ):
        """
        Initialize invalid region filter error.
        
        Args:
            message: Error description
            invalid_regions: List of regions that are invalid/disabled
            enabled_regions: List of regions that are actually enabled
        """
        super().__init__(message)
        self.invalid_regions = invalid_regions
        self.enabled_regions = enabled_regions


class MultiRegionScanner:
    """
    Orchestrates multi-region resource scanning.
    
    Scans resources across all enabled regions in parallel,
    handles failures gracefully, and aggregates results.
    
    This class implements:
    - Parallel execution with configurable concurrency (Requirement 3.2)
    - Retry logic with exponential backoff (Requirement 3.4)
    - Graceful handling of partial failures (Requirement 3.5)
    - Result aggregation with region metadata (Requirements 4.1-4.5)
    - Global resource deduplication (Requirements 5.1-5.3)
    - Disabled mode for single-region scanning (Requirements 7.1, 7.4)
    """

    def __init__(
        self,
        region_discovery: RegionDiscoveryService,
        client_factory: RegionalClientFactory,
        compliance_service_factory: Callable[[AWSClient], ComplianceService],
        max_concurrent_regions: int = 5,
        region_timeout_seconds: int = 60,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
        max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
        allowed_regions: list[str] | None = None,
        default_region: str = "us-east-1",
    ):
        """
        Initialize with dependencies and configuration.

        Args:
            region_discovery: Service for discovering enabled regions
            client_factory: Factory for creating regional AWS clients
            compliance_service_factory: Factory function that creates a ComplianceService
                                       given an AWSClient
            max_concurrent_regions: Maximum regions to scan in parallel (default: 5)
            region_timeout_seconds: Timeout for scanning a single region (default: 60)
            max_retries: Maximum retry attempts for transient errors (default: 3)
            base_delay_seconds: Base delay for exponential backoff (default: 1.0)
            max_delay_seconds: Maximum delay between retries (default: 30.0)
            allowed_regions: Optional list of regions to restrict scanning to.
                            If None, all enabled regions in the account are scanned.
                            If set, only these regions will be scanned (must be enabled).
            default_region: Default AWS region for API calls (default: "us-east-1")
        """
        self.region_discovery = region_discovery
        self.client_factory = client_factory
        self.compliance_service_factory = compliance_service_factory
        self.max_concurrent_regions = max_concurrent_regions
        self.region_timeout_seconds = region_timeout_seconds
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.allowed_regions = allowed_regions
        self.default_region = default_region

        if allowed_regions:
            logger.info(
                f"MultiRegionScanner initialized: allowed_regions={allowed_regions}, "
                f"max_concurrent={max_concurrent_regions}, "
                f"timeout={region_timeout_seconds}s, max_retries={max_retries}"
            )
        else:
            logger.info(
                f"MultiRegionScanner initialized: all enabled regions, "
                f"max_concurrent={max_concurrent_regions}, "
                f"timeout={region_timeout_seconds}s, max_retries={max_retries}"
            )

    @property
    def multi_region_enabled(self) -> bool:
        """Backward-compatible property. Multi-region is always enabled."""
        return True

    async def scan_all_regions(
        self,
        resource_types: list[str],
        filters: dict | None = None,
        severity: str = "all",
        force_refresh: bool = False,
    ) -> MultiRegionComplianceResult:
        """
        Scan resources across all enabled regions.

        Executes region scans in parallel with configurable concurrency.
        Aggregates results and handles partial failures.

        Region selection priority:
        1. User query filter (filters.regions) - most specific
        2. Infrastructure setting (allowed_regions) - restricts available regions
        3. All enabled regions in the account - default behavior

        Args:
            resource_types: Resource types to scan (e.g., ["ec2:instance", "rds:db"])
            filters: Optional filters (may include region filter from user query)
            severity: Severity filter for violations ("all", "errors_only", "warnings_only")
            force_refresh: If True, bypass cache and perform fresh scan (default: False)

        Returns:
            Aggregated compliance result from all regions

        Raises:
            MultiRegionScanError: If all regions fail to scan
            InvalidRegionFilterError: If user requests regions not in allowed list
        """
        logger.info(
            f"Starting multi-region scan: resource_types={resource_types}, "
            f"filters={filters}, severity={severity}, allowed_regions={self.allowed_regions}"
        )

        # Check if this is an "all" mode scan - expand and handle specially
        is_all_mode = "all" in resource_types
        if is_all_mode:
            # Expand "all" to supported types BEFORE separating global/regional
            expanded_types = expand_all_to_supported_types(resource_types)
            logger.info(
                f"'all' mode detected: expanded to {len(expanded_types)} resource types. "
                f"Using extended timeout ({ALL_MODE_TIMEOUT_MULTIPLIER}x) and chunking."
            )
            resource_types = expanded_types

        # Separate global and regional resource types (Requirement 5.2)
        global_types = [rt for rt in resource_types if self._is_global_resource_type(rt)]
        regional_types = [rt for rt in resource_types if not self._is_global_resource_type(rt)]

        logger.info(f"Global resource types: {global_types}, Regional types: {regional_types}")

        # Determine regions to scan
        # Step 1: Get enabled regions from AWS (with status to detect fallback)
        discovery_result = await self.region_discovery.get_enabled_regions_with_status()
        enabled_regions = discovery_result.regions

        if discovery_result.discovery_failed:
            logger.warning(
                f"Region discovery failed and fell back to default region. "
                f"Results may be incomplete. Error: {discovery_result.discovery_error}"
            )
        else:
            logger.info(f"Discovered {len(enabled_regions)} enabled regions in account")

        # Step 2: Apply infrastructure restriction (allowed_regions setting)
        if self.allowed_regions:
            # Validate that all allowed_regions are actually enabled
            invalid_allowed = [r for r in self.allowed_regions if r not in enabled_regions]
            if invalid_allowed:
                logger.warning(
                    f"Some allowed_regions are not enabled in the account: {invalid_allowed}"
                )
            # Restrict to allowed regions that are also enabled
            available_regions = [r for r in self.allowed_regions if r in enabled_regions]
            logger.info(f"Restricted to allowed regions: {available_regions}")
        else:
            available_regions = enabled_regions

        # Step 3: Apply user query filter (filters.regions)
        regions_to_scan = self._apply_region_filter(available_regions, filters)
        logger.info(f"Regions to scan after user filter: {regions_to_scan}")

        # Track skipped regions (available but not scanned due to user filter)
        skipped_regions = [r for r in available_regions if r not in regions_to_scan]
        
        # Scan global resources once (Requirement 5.1)
        # Global resources (S3, IAM, CloudFront, Route53) are not region-specific.
        # We use us-east-1 as the API endpoint but report them as "global" region.
        global_result: RegionalScanResult | None = None
        if global_types:
            # Always use us-east-1 for global resource API calls (standard AWS practice)
            global_api_region = "us-east-1"
            logger.info(f"Scanning global resources via {global_api_region} API (will be reported as 'global')")
            global_result = await self._scan_region(
                region=global_api_region,
                resource_types=global_types,
                filters=filters,
                severity=severity,
                extended_timeout=is_all_mode,  # Use extended timeout for "all" mode
                force_refresh=force_refresh,
            )
            # Override the region to "global" for proper attribution
            # Global resources don't belong to any specific region
            global_result = RegionalScanResult(
                region="global",  # Report as "global", not the API region
                success=global_result.success,
                resources=global_result.resources,
                violations=global_result.violations,
                compliant_count=global_result.compliant_count,
                non_compliant_count=global_result.non_compliant_count,
                error_message=global_result.error_message,
                scan_duration_ms=global_result.scan_duration_ms,
            )
            # Mark resources as global
            for resource in global_result.resources:
                resource["is_global"] = True
                resource["region"] = "global"
            # Update violation regions to "global" as well
            for violation in global_result.violations:
                violation.region = "global"
        
        # Scan regional resources in parallel (Requirement 3.2)
        # For "all" mode, chunk resource types to avoid overwhelming AWS APIs
        regional_results: list[RegionalScanResult] = []
        if regional_types and regions_to_scan:
            if is_all_mode and len(regional_types) > DEFAULT_RESOURCE_TYPE_CHUNK_SIZE:
                # Chunk resource types for "all" mode
                regional_results = await self._scan_regions_chunked(
                    regions=regions_to_scan,
                    resource_types=regional_types,
                    filters=filters,
                    severity=severity,
                    chunk_size=DEFAULT_RESOURCE_TYPE_CHUNK_SIZE,
                    force_refresh=force_refresh,
                )
            else:
                regional_results = await self._scan_regions_parallel(
                    regions=regions_to_scan,
                    resource_types=regional_types,
                    filters=filters,
                    severity=severity,
                    extended_timeout=is_all_mode,  # Use extended timeout for "all" mode
                    force_refresh=force_refresh,
                )
        
        # Combine global and regional results
        # Global resources are always added as a separate "global" region entry
        # since they don't belong to any specific AWS region
        all_results = regional_results.copy()
        if global_result:
            # Global result has region="global", so it will always be separate
            # from regional results (which have regions like "us-east-1")
            all_results.append(global_result)
            logger.info(
                f"Added global resources: {global_result.compliant_count} compliant, "
                f"{global_result.non_compliant_count} non-compliant"
            )
        
        # Aggregate results (Requirements 4.1-4.5)
        aggregated = self._aggregate_results(
            regional_results=all_results,
            skipped_regions=skipped_regions,
            global_result=global_result,
            discovery_failed=discovery_result.discovery_failed,
            discovery_error=discovery_result.discovery_error,
        )
        
        # Check if all regions failed
        if (
            aggregated.region_metadata.total_regions > 0
            and len(aggregated.region_metadata.successful_regions) == 0
        ):
            # Provide helpful error message
            error_msg = "All regions failed to scan"
            if is_all_mode:
                error_msg += (
                    ". The 'all' resource type scan timed out across all regions. "
                    "Try scanning specific resource types instead: "
                    "['ec2:instance', 's3:bucket', 'lambda:function', 'rds:db', 'dynamodb:table']"
                )
            raise MultiRegionScanError(
                message=error_msg,
                failed_regions=aggregated.region_metadata.failed_regions,
                partial_results=aggregated,
            )
        
        logger.info(
            f"Multi-region scan complete: {aggregated.total_resources} resources, "
            f"score={aggregated.compliance_score:.2%}, "
            f"successful_regions={len(aggregated.region_metadata.successful_regions)}, "
            f"failed_regions={len(aggregated.region_metadata.failed_regions)}"
        )
        
        return aggregated

    async def _scan_regions_parallel(
        self,
        regions: list[str],
        resource_types: list[str],
        filters: dict | None,
        severity: str,
        extended_timeout: bool = False,
        force_refresh: bool = False,
    ) -> list[RegionalScanResult]:
        """
        Scan multiple regions in parallel with concurrency control.

        Uses asyncio.Semaphore to limit concurrent scans.

        Args:
            regions: List of regions to scan
            resource_types: Resource types to scan
            filters: Optional filters
            severity: Severity filter
            extended_timeout: Use extended timeout for "all" mode scanning

        Returns:
            List of regional scan results

        Requirement: 3.2
        """
        # Use higher concurrency for "all" mode (extended_timeout indicates this)
        concurrency = (
            ALL_MODE_MAX_CONCURRENT_REGIONS if extended_timeout
            else self.max_concurrent_regions
        )
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(concurrency)

        async def scan_with_semaphore(region: str) -> RegionalScanResult:
            async with semaphore:
                return await self._scan_region(
                    region, resource_types, filters, severity, extended_timeout, force_refresh
                )

        # Create tasks for all regions
        tasks = [scan_with_semaphore(region) for region in regions]

        # Execute all tasks in parallel, collecting results even if some fail
        # return_exceptions=True ensures we get results from all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results, converting exceptions to failed RegionalScanResult
        processed_results: list[RegionalScanResult] = []
        for i, result in enumerate(results):
            region = regions[i]
            if isinstance(result, Exception):
                # Convert exception to failed result
                logger.error(f"Region {region} scan failed with exception: {result}")
                processed_results.append(
                    RegionalScanResult(
                        region=region,
                        success=False,
                        error_message=str(result),
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    async def _scan_regions_chunked(
        self,
        regions: list[str],
        resource_types: list[str],
        filters: dict | None,
        severity: str,
        chunk_size: int = DEFAULT_RESOURCE_TYPE_CHUNK_SIZE,
        force_refresh: bool = False,
    ) -> list[RegionalScanResult]:
        """
        Scan regions with resource types chunked to avoid overwhelming AWS APIs.

        For "all" mode with 50+ resource types, this method:
        1. Splits resource types into chunks of `chunk_size`
        2. Scans each chunk across all regions in parallel (with higher concurrency)
        3. Merges results for each region

        This prevents AWS API rate limiting and timeouts when scanning
        many resource types across many regions.

        Note: This method always uses extended timeout since it's only called
        for "all" mode scanning with many resource types.

        Args:
            regions: List of regions to scan
            resource_types: Resource types to scan (may be 50+)
            filters: Optional filters
            severity: Severity filter
            chunk_size: Number of resource types per chunk

        Returns:
            List of merged regional scan results
        """
        # Split resource types into chunks
        chunks = [
            resource_types[i : i + chunk_size]
            for i in range(0, len(resource_types), chunk_size)
        ]
        logger.info(
            f"Chunked {len(resource_types)} resource types into {len(chunks)} chunks "
            f"of up to {chunk_size} types each. Using extended timeout ({ALL_MODE_DEFAULT_TIMEOUT_SECONDS}s) "
            f"and increased concurrency ({ALL_MODE_MAX_CONCURRENT_REGIONS} regions)."
        )

        # Initialize results dictionary keyed by region
        merged_results: dict[str, RegionalScanResult] = {}

        # Process each chunk sequentially to avoid overwhelming AWS
        for chunk_idx, chunk in enumerate(chunks):
            logger.info(
                f"Processing chunk {chunk_idx + 1}/{len(chunks)}: "
                f"{len(chunk)} resource types ({chunk[:3]}...)"
            )

            # Scan this chunk across all regions in parallel
            # Use extended timeout since this is "all" mode
            chunk_results = await self._scan_regions_parallel(
                regions=regions,
                resource_types=chunk,
                filters=filters,
                severity=severity,
                extended_timeout=True,
                force_refresh=force_refresh,
            )

            # Merge chunk results into accumulated results
            for result in chunk_results:
                if result.region not in merged_results:
                    # First chunk for this region - use result directly
                    merged_results[result.region] = result
                else:
                    # Merge with existing result for this region
                    existing = merged_results[result.region]
                    merged_results[result.region] = RegionalScanResult(
                        region=result.region,
                        success=existing.success and result.success,
                        resources=existing.resources + result.resources,
                        violations=existing.violations + result.violations,
                        compliant_count=existing.compliant_count + result.compliant_count,
                        non_compliant_count=existing.non_compliant_count + result.non_compliant_count,
                        error_message=existing.error_message or result.error_message,
                        scan_duration_ms=existing.scan_duration_ms + result.scan_duration_ms,
                    )

            # Small delay between chunks to be nice to AWS APIs
            if chunk_idx < len(chunks) - 1:
                await asyncio.sleep(0.5)

        logger.info(f"Chunked scan complete: merged results for {len(merged_results)} regions")
        return list(merged_results.values())

    async def _scan_region(
        self,
        region: str,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
        extended_timeout: bool = False,
        force_refresh: bool = False,
    ) -> RegionalScanResult:
        """
        Scan a single region with retry logic.

        Implements exponential backoff with jitter for transient errors.
        Returns result or error information on failure.

        Args:
            region: AWS region code to scan
            resource_types: Resource types to scan
            filters: Optional filters
            severity: Severity filter
            extended_timeout: Use extended timeout for "all" mode scanning
            force_refresh: If True, bypass cache and perform fresh scan

        Returns:
            RegionalScanResult with success status and data or error

        Requirements: 3.3, 3.4
        """
        start_time = time.time()
        last_error: Exception | None = None

        # Use extended timeout for "all" mode to handle many resource types
        timeout_seconds = (
            ALL_MODE_DEFAULT_TIMEOUT_SECONDS if extended_timeout
            else self.region_timeout_seconds
        )

        for attempt in range(self.max_retries + 1):
            try:
                # Apply timeout to the scan operation
                result = await asyncio.wait_for(
                    self._execute_region_scan(region, resource_types, filters, severity, force_refresh),
                    timeout=timeout_seconds,
                )

                # Calculate duration
                duration_ms = int((time.time() - start_time) * 1000)
                result.scan_duration_ms = duration_ms

                return result

            except asyncio.TimeoutError:
                # Provide helpful error message with suggestion
                timeout_msg = f"Region {region} scan timed out after {timeout_seconds}s"
                if extended_timeout:
                    timeout_msg += (
                        ". The 'all' resource type scan is taking too long. "
                        "Try scanning specific resource types instead: "
                        "['ec2:instance', 's3:bucket', 'lambda:function', 'rds:db']"
                    )
                last_error = asyncio.TimeoutError(timeout_msg)
                logger.warning(f"Region {region} scan timed out (attempt {attempt + 1})")
                
            except Exception as e:
                last_error = e
                
                # Check if this is a transient error that should be retried
                if self._is_transient_error(e) and attempt < self.max_retries:
                    delay = self._calculate_backoff_delay(attempt)
                    logger.warning(
                        f"Region {region} scan failed with transient error "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    # Non-transient error or max retries reached
                    logger.error(
                        f"Region {region} scan failed "
                        f"(attempt {attempt + 1}/{self.max_retries + 1}): {e}"
                    )
                    break
        
        # All retries exhausted - return failed result
        duration_ms = int((time.time() - start_time) * 1000)
        return RegionalScanResult(
            region=region,
            success=False,
            error_message=str(last_error) if last_error else "Unknown error",
            scan_duration_ms=duration_ms,
        )

    async def _execute_region_scan(
        self,
        region: str,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
        force_refresh: bool = False,
    ) -> RegionalScanResult:
        """
        Execute the actual scan for a single region.

        Creates a regional client and compliance service, then performs the scan.

        Args:
            region: AWS region code
            resource_types: Resource types to scan
            filters: Optional filters
            severity: Severity filter
            force_refresh: If True, bypass cache and perform fresh scan

        Returns:
            RegionalScanResult with resources and violations
            
        Requirement: 3.3 (empty results are successful)
        """
        logger.debug(f"Executing scan for region {region}: {resource_types}")
        
        # Get regional client
        client = self.client_factory.get_client(region)
        
        # Create compliance service for this region
        compliance_service = self.compliance_service_factory(client)
        
        # Strip region filter from filters before passing to regional compliance service
        # The region is already determined by which regional client we're using.
        # Passing the region filter would cause the AWS client to return empty results
        # when the filter region doesn't match the client's region.
        regional_filters = self._strip_region_filter(filters)
        
        # Execute compliance check
        # Use cache by default (force_refresh=False) for faster repeated scans
        compliance_result = await compliance_service.check_compliance(
            resource_types=resource_types,
            filters=regional_filters,
            severity=severity,
            force_refresh=force_refresh,
        )
        
        # Convert to RegionalScanResult
        # Build unique resource list from violations (one entry per resource, not per violation)
        # A resource with 3 missing tags should be counted as 1 resource, not 3
        resources_with_region = []
        seen_resource_ids: set[str] = set()

        for violation in compliance_result.violations:
            resource_id = violation.resource_id
            if resource_id not in seen_resource_ids:
                seen_resource_ids.add(resource_id)
                resource_dict = {
                    "resource_id": resource_id,
                    "resource_type": violation.resource_type,
                    "region": region,  # Add region attribute
                    "arn": resource_id,  # ARN is typically the resource_id
                }
                resources_with_region.append(resource_dict)

        # Calculate unique non-compliant resources (resources with at least one violation)
        non_compliant_count = len(seen_resource_ids)

        # Build resource list from violations (resources with issues)
        # and add compliant resources count
        return RegionalScanResult(
            region=region,
            success=True,  # Requirement 3.3: zero resources is successful
            resources=resources_with_region,
            violations=compliance_result.violations,
            compliant_count=compliance_result.compliant_resources,
            non_compliant_count=non_compliant_count,  # Track unique non-compliant resources
            error_message=None,
        )

    def _aggregate_results(
        self,
        regional_results: list[RegionalScanResult],
        skipped_regions: list[str] | None = None,
        global_result: RegionalScanResult | None = None,
        discovery_failed: bool = False,
        discovery_error: str | None = None,
    ) -> MultiRegionComplianceResult:
        """
        Aggregate results from multiple regions.

        Combines resources, violations, and calculates overall score.
        Ensures global resources appear exactly once (Requirement 5.3).

        Args:
            regional_results: List of results from regional scans
            skipped_regions: Regions that were skipped (filtered out)
            global_result: Result from global resource scan (if any)
            discovery_failed: True if region discovery failed and fell back to default
            discovery_error: Error message if region discovery failed

        Returns:
            Aggregated compliance result

        Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.3
        """
        skipped_regions = skipped_regions or []
        
        # Separate successful and failed results
        successful_results = [r for r in regional_results if r.success]
        failed_results = [r for r in regional_results if not r.success]
        
        # Collect all violations (Requirement 4.1)
        all_violations: list[Violation] = []
        seen_violation_ids: set[str] = set()  # For deduplication
        
        for result in successful_results:
            for violation in result.violations:
                # Deduplicate violations (especially for global resources)
                violation_key = f"{violation.resource_id}:{violation.tag_name}"
                if violation_key not in seen_violation_ids:
                    seen_violation_ids.add(violation_key)
                    all_violations.append(violation)
        
        # Calculate totals across all successful regions
        total_resources = 0
        total_compliant = 0
        total_cost_gap = 0.0
        
        # Track unique resources for global resource deduplication (Requirement 5.3)
        seen_resource_ids: set[str] = set()
        
        # Build regional breakdown (Requirement 4.5)
        regional_breakdown: dict[str, RegionalSummary] = {}
        
        for result in successful_results:
            # Skip global result in regional breakdown if it's marked
            is_global_scan = global_result is not None and result.region == global_result.region

            # Count resources, avoiding duplicates for global resources
            region_non_compliant_count = 0
            for resource in result.resources:
                resource_id = resource.get("resource_id", "")
                is_global = resource.get("is_global", False)

                if is_global:
                    # Global resources: only count once (Requirement 5.3)
                    if resource_id not in seen_resource_ids:
                        seen_resource_ids.add(resource_id)
                        region_non_compliant_count += 1
                else:
                    region_non_compliant_count += 1

            # Calculate region-specific metrics using UNIQUE resource counts
            # Use non_compliant_count from RegionalScanResult (unique resources with violations)
            # instead of counting violations (which inflates the count)
            region_compliant = result.compliant_count
            region_non_compliant = result.non_compliant_count if result.non_compliant_count > 0 else region_non_compliant_count
            region_total = region_compliant + region_non_compliant
            region_violation_count = len(result.violations)  # Keep for reporting

            # Calculate region compliance score
            if region_total > 0:
                region_score = region_compliant / region_total
            else:
                region_score = 1.0  # Empty region is fully compliant

            # Calculate region cost gap
            region_cost_gap = sum(v.cost_impact_monthly for v in result.violations)

            # Add to totals
            total_resources += region_total
            total_compliant += region_compliant
            total_cost_gap += region_cost_gap

            # Add to regional breakdown
            regional_breakdown[result.region] = RegionalSummary(
                region=result.region,
                total_resources=region_total,
                compliant_resources=region_compliant,
                compliance_score=region_score,
                violation_count=region_violation_count,
                cost_attribution_gap=region_cost_gap,
            )
        
        # Calculate overall compliance score (Requirement 4.3)
        if total_resources > 0:
            compliance_score = total_compliant / total_resources
        else:
            compliance_score = 1.0  # No resources means fully compliant
        
        # Build region metadata (Requirement 4.5)
        region_metadata = RegionScanMetadata(
            total_regions=len(regional_results),
            successful_regions=[r.region for r in successful_results],
            failed_regions=[r.region for r in failed_results],
            skipped_regions=skipped_regions,
            discovery_failed=discovery_failed,
            discovery_error=discovery_error,
        )
        
        return MultiRegionComplianceResult(
            compliance_score=compliance_score,
            total_resources=total_resources,
            compliant_resources=total_compliant,
            violations=all_violations,
            cost_attribution_gap=total_cost_gap,  # Requirement 4.4
            region_metadata=region_metadata,
            regional_breakdown=regional_breakdown,
        )

    def _is_global_resource_type(self, resource_type: str) -> bool:
        """
        Check if a resource type is global (not region-specific).
        
        Global resources like S3 buckets, IAM roles, and CloudFront distributions
        exist at the account level, not in specific regions.
        
        Args:
            resource_type: Resource type string (e.g., "s3:bucket", "ec2:instance")
            
        Returns:
            True if the resource type is global, False otherwise
            
        Requirement: 5.2
        """
        return resource_type.lower() in GLOBAL_RESOURCE_TYPES

    def _apply_region_filter(
        self,
        enabled_regions: list[str],
        filters: dict | None,
    ) -> list[str]:
        """
        Apply region filter to the list of enabled regions.
        
        Validates that all filtered regions are enabled/available.
        Raises InvalidRegionFilterError if any filtered region is not enabled.
        
        Args:
            enabled_regions: List of all enabled regions
            filters: Optional filters dict that may contain "regions" key
            
        Returns:
            Filtered list of regions to scan
            
        Raises:
            InvalidRegionFilterError: If filter contains invalid/disabled regions
            
        Requirements: 6.1, 6.2, 6.3, 6.4
        """
        # Requirement 6.4: When no region filter is provided, scan all enabled regions
        if not filters:
            return enabled_regions
        
        region_filter = filters.get("regions") or filters.get("region")
        if not region_filter:
            # Requirement 6.4: No region filter means scan all enabled regions
            return enabled_regions
        
        # Normalize to list
        if isinstance(region_filter, str):
            region_filter = [region_filter]
        
        # Convert enabled_regions to set for efficient lookup
        enabled_set = set(enabled_regions)
        
        # Requirement 6.3: Validate all filtered regions are enabled
        invalid_regions = [r for r in region_filter if r not in enabled_set]
        
        if invalid_regions:
            logger.error(
                f"Region filter contains invalid/disabled regions: {invalid_regions}. "
                f"Enabled regions: {enabled_regions}"
            )
            raise InvalidRegionFilterError(
                message=f"Invalid or disabled regions in filter: {invalid_regions}. "
                        f"Available regions: {enabled_regions}",
                invalid_regions=invalid_regions,
                enabled_regions=enabled_regions,
            )
        
        # Requirement 6.1, 6.2: Filter to only specified regions
        filtered = [r for r in region_filter if r in enabled_set]
        
        logger.info(f"Region filter applied: scanning {len(filtered)} regions: {filtered}")
        
        return filtered

    def _is_transient_error(self, error: Exception) -> bool:
        """
        Check if an error is transient and should trigger a retry.
        
        Args:
            error: The exception to check
            
        Returns:
            True if the error is transient, False otherwise
        """
        error_str = str(error)
        
        # Check for known transient error codes
        for code in TRANSIENT_ERROR_CODES:
            if code in error_str:
                return True
        
        # Check for common transient patterns
        transient_patterns = [
            "rate exceeded",
            "throttl",
            "service unavailable",
            "internal error",
            "connection reset",
            "timeout",
        ]
        
        error_lower = error_str.lower()
        return any(pattern in error_lower for pattern in transient_patterns)

    def _calculate_backoff_delay(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay with jitter.
        
        Uses the formula: min(max_delay, base_delay * 2^attempt) + random_jitter
        
        Args:
            attempt: Current attempt number (0-indexed)
            
        Returns:
            Delay in seconds before next retry
        """
        # Exponential backoff
        delay = self.base_delay_seconds * (2 ** attempt)
        
        # Cap at max delay
        delay = min(delay, self.max_delay_seconds)
        
        # Add jitter (0-25% of delay)
        jitter = random.uniform(0, delay * 0.25)
        
        return delay + jitter

    def _strip_region_filter(self, filters: dict | None) -> dict | None:
        """
        Strip region-related filters from the filters dict.
        
        When scanning a specific region with a regional client, we don't want
        to pass region filters to the compliance service because:
        1. The region is already determined by which regional client we're using
        2. The AWS client returns empty results if the filter region doesn't match
           its configured region
        
        This method removes 'region' and 'regions' keys from the filters dict
        while preserving other filters like 'account_id'.
        
        Args:
            filters: Original filters dict (may be None)
            
        Returns:
            New filters dict without region keys, or None if empty/None
        """
        if not filters:
            return None
        
        # Create a copy without region-related keys
        stripped = {k: v for k, v in filters.items() if k not in ("region", "regions")}
        
        # Return None if the stripped dict is empty
        return stripped if stripped else None
