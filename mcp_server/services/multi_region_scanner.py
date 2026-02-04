# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
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
from .compliance_service import ComplianceService
from .region_discovery_service import RegionDiscoveryService

logger = logging.getLogger(__name__)

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_SECONDS = 1.0
DEFAULT_MAX_DELAY_SECONDS = 30.0

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
        multi_region_enabled: bool = True,
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
            multi_region_enabled: Enable multi-region scanning (default: True).
                                 When False, only the default region is scanned.
                                 Requirements: 7.1, 7.4
            default_region: Default AWS region to use when multi-region is disabled
                           (default: "us-east-1"). Requirements: 7.4
        """
        self.region_discovery = region_discovery
        self.client_factory = client_factory
        self.compliance_service_factory = compliance_service_factory
        self.max_concurrent_regions = max_concurrent_regions
        self.region_timeout_seconds = region_timeout_seconds
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.multi_region_enabled = multi_region_enabled
        self.default_region = default_region
        
        logger.info(
            f"MultiRegionScanner initialized: multi_region_enabled={multi_region_enabled}, "
            f"default_region={default_region}, max_concurrent={max_concurrent_regions}, "
            f"timeout={region_timeout_seconds}s, max_retries={max_retries}"
        )

    async def scan_all_regions(
        self,
        resource_types: list[str],
        filters: dict | None = None,
        severity: str = "all",
    ) -> MultiRegionComplianceResult:
        """
        Scan resources across all enabled regions.
        
        Executes region scans in parallel with configurable concurrency.
        Aggregates results and handles partial failures.
        
        When multi_region_enabled is False, only the default region is scanned,
        skipping region discovery entirely (Requirements 7.1, 7.4).
        
        Args:
            resource_types: Resource types to scan (e.g., ["ec2:instance", "rds:db"])
            filters: Optional filters (may include region filter)
            severity: Severity filter for violations ("all", "errors_only", "warnings_only")
            
        Returns:
            Aggregated compliance result from all regions
            
        Raises:
            MultiRegionScanError: If all regions fail to scan
            
        Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 7.1, 7.4
        """
        logger.info(
            f"Starting multi-region scan: resource_types={resource_types}, "
            f"filters={filters}, severity={severity}, multi_region_enabled={self.multi_region_enabled}"
        )
        
        # Separate global and regional resource types (Requirement 5.2)
        global_types = [rt for rt in resource_types if self._is_global_resource_type(rt)]
        regional_types = [rt for rt in resource_types if not self._is_global_resource_type(rt)]
        
        logger.info(f"Global resource types: {global_types}, Regional types: {regional_types}")
        
        # Determine regions to scan based on multi_region_enabled setting
        # Requirements 7.1, 7.4: When disabled, scan only the default region
        if not self.multi_region_enabled:
            logger.info(
                f"Multi-region scanning disabled. Scanning only default region: {self.default_region}"
            )
            enabled_regions = [self.default_region]
            regions_to_scan = [self.default_region]
            skipped_regions: list[str] = []
        else:
            # Get enabled regions (Requirement 3.1)
            enabled_regions = await self.region_discovery.get_enabled_regions()
            logger.info(f"Discovered {len(enabled_regions)} enabled regions")
            
            # Apply region filter if provided
            regions_to_scan = self._apply_region_filter(enabled_regions, filters)
            logger.info(f"Regions to scan after filtering: {regions_to_scan}")
            
            # Track skipped regions
            skipped_regions = [r for r in enabled_regions if r not in regions_to_scan]
        
        # Scan global resources once (Requirement 5.1)
        global_result: RegionalScanResult | None = None
        if global_types:
            # Use the first region (or default) for global resources
            global_region = regions_to_scan[0] if regions_to_scan else self.default_region
            logger.info(f"Scanning global resources from region: {global_region}")
            global_result = await self._scan_region(
                region=global_region,
                resource_types=global_types,
                filters=filters,
                severity=severity,
            )
            # Mark global resources with their actual region attribute
            for resource in global_result.resources:
                resource["is_global"] = True
        
        # Scan regional resources in parallel (Requirement 3.2)
        regional_results: list[RegionalScanResult] = []
        if regional_types and regions_to_scan:
            regional_results = await self._scan_regions_parallel(
                regions=regions_to_scan,
                resource_types=regional_types,
                filters=filters,
                severity=severity,
            )
        
        # Combine global and regional results
        # Only add global_result if its region is not already in regional_results
        # This prevents double-counting when scanning both global and regional resources
        all_results = regional_results.copy()
        if global_result:
            # Check if the global region is already represented in regional results
            regional_regions = {r.region for r in regional_results}
            if global_result.region not in regional_regions:
                # Add global result as a separate region entry
                all_results.append(global_result)
            else:
                # Merge global result into the existing regional result for that region
                for i, result in enumerate(all_results):
                    if result.region == global_result.region:
                        # Merge resources and violations from global scan
                        merged_resources = result.resources + global_result.resources
                        merged_violations = result.violations + global_result.violations
                        merged_compliant = result.compliant_count + global_result.compliant_count
                        all_results[i] = RegionalScanResult(
                            region=result.region,
                            success=result.success and global_result.success,
                            resources=merged_resources,
                            violations=merged_violations,
                            compliant_count=merged_compliant,
                            error_message=result.error_message or global_result.error_message,
                            scan_duration_ms=result.scan_duration_ms + global_result.scan_duration_ms,
                        )
                        break
        
        # Aggregate results (Requirements 4.1-4.5)
        aggregated = self._aggregate_results(
            regional_results=all_results,
            skipped_regions=skipped_regions,
            global_result=global_result,
        )
        
        # Check if all regions failed
        if (
            aggregated.region_metadata.total_regions > 0
            and len(aggregated.region_metadata.successful_regions) == 0
        ):
            raise MultiRegionScanError(
                message="All regions failed to scan",
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
    ) -> list[RegionalScanResult]:
        """
        Scan multiple regions in parallel with concurrency control.
        
        Uses asyncio.Semaphore to limit concurrent scans.
        
        Args:
            regions: List of regions to scan
            resource_types: Resource types to scan
            filters: Optional filters
            severity: Severity filter
            
        Returns:
            List of regional scan results
            
        Requirement: 3.2
        """
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent_regions)
        
        async def scan_with_semaphore(region: str) -> RegionalScanResult:
            async with semaphore:
                return await self._scan_region(region, resource_types, filters, severity)
        
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

    async def _scan_region(
        self,
        region: str,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
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
            
        Returns:
            RegionalScanResult with success status and data or error
            
        Requirements: 3.3, 3.4
        """
        start_time = time.time()
        last_error: Exception | None = None
        
        for attempt in range(self.max_retries + 1):
            try:
                # Apply timeout to the scan operation
                result = await asyncio.wait_for(
                    self._execute_region_scan(region, resource_types, filters, severity),
                    timeout=self.region_timeout_seconds,
                )
                
                # Calculate duration
                duration_ms = int((time.time() - start_time) * 1000)
                result.scan_duration_ms = duration_ms
                
                return result
                
            except asyncio.TimeoutError:
                last_error = asyncio.TimeoutError(
                    f"Region {region} scan timed out after {self.region_timeout_seconds}s"
                )
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
    ) -> RegionalScanResult:
        """
        Execute the actual scan for a single region.
        
        Creates a regional client and compliance service, then performs the scan.
        
        Args:
            region: AWS region code
            resource_types: Resource types to scan
            filters: Optional filters
            severity: Severity filter
            
        Returns:
            RegionalScanResult with resources and violations
            
        Requirement: 3.3 (empty results are successful)
        """
        logger.debug(f"Executing scan for region {region}: {resource_types}")
        
        # Get regional client
        client = self.client_factory.get_client(region)
        
        # Create compliance service for this region
        compliance_service = self.compliance_service_factory(client)
        
        # Execute compliance check
        compliance_result = await compliance_service.check_compliance(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
            force_refresh=True,  # Always fresh scan for multi-region
        )
        
        # Convert to RegionalScanResult
        # Add region attribute to each resource (Requirement 4.2)
        resources_with_region = []
        for violation in compliance_result.violations:
            resource_dict = {
                "resource_id": violation.resource_id,
                "resource_type": violation.resource_type,
                "region": region,  # Add region attribute
                "arn": violation.resource_id,  # ARN is typically the resource_id
            }
            resources_with_region.append(resource_dict)
        
        # Build resource list from violations (resources with issues)
        # and add compliant resources count
        return RegionalScanResult(
            region=region,
            success=True,  # Requirement 3.3: zero resources is successful
            resources=resources_with_region,
            violations=compliance_result.violations,
            compliant_count=compliance_result.compliant_resources,
            error_message=None,
        )

    def _aggregate_results(
        self,
        regional_results: list[RegionalScanResult],
        skipped_regions: list[str] | None = None,
        global_result: RegionalScanResult | None = None,
    ) -> MultiRegionComplianceResult:
        """
        Aggregate results from multiple regions.
        
        Combines resources, violations, and calculates overall score.
        Ensures global resources appear exactly once (Requirement 5.3).
        
        Args:
            regional_results: List of results from regional scans
            skipped_regions: Regions that were skipped (filtered out)
            global_result: Result from global resource scan (if any)
            
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
            region_resource_count = 0
            for resource in result.resources:
                resource_id = resource.get("resource_id", "")
                is_global = resource.get("is_global", False)
                
                if is_global:
                    # Global resources: only count once (Requirement 5.3)
                    if resource_id not in seen_resource_ids:
                        seen_resource_ids.add(resource_id)
                        region_resource_count += 1
                else:
                    region_resource_count += 1
            
            # Calculate region-specific metrics
            region_violations = [v for v in result.violations if v.resource_id not in seen_resource_ids or not is_global_scan]
            region_violation_count = len(result.violations)
            region_compliant = result.compliant_count
            region_total = region_compliant + region_violation_count
            
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
