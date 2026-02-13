# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for finding untagged resources.

This module provides the find_untagged_resources tool for discovering AWS resources
that are missing required tags according to the organization's tagging policy.

Supports both single-region and multi-region scanning modes:
- Single-region: Uses AWSClient directly (backward compatible)
- Multi-region: Uses MultiRegionScanner for parallel scanning across regions

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 17.3, 17.4
"""

import asyncio
import logging
from datetime import datetime

from ..clients.aws_client import AWSClient
from ..models.policy import TagPolicy
from ..models.untagged import UntaggedResource, UntaggedResourcesResult
from ..services.multi_region_scanner import MultiRegionScanner
from ..services.policy_service import PolicyService
from ..utils.resource_utils import (
    fetch_resources_by_type,
    get_supported_resource_types,
)

logger = logging.getLogger(__name__)


async def find_untagged_resources(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_types: list[str],
    regions: list[str] | None = None,
    min_cost_threshold: float | None = None,
    include_costs: bool = False,
    multi_region_scanner: MultiRegionScanner | None = None,
) -> UntaggedResourcesResult:
    """
    Find resources with no tags or missing required tags.

    This tool searches for resources that are completely untagged or missing
    critical required tags. It includes resource age to help prioritize remediation.

    Supports two scanning modes:
    - **Single-region mode** (default): Uses AWSClient directly to scan
      resources in the configured AWS region. This is the backward-compatible
      behavior when multi_region_scanner is not provided.
    - **Multi-region mode**: When multi_region_scanner is provided and multi-region
      scanning is enabled, scans resources across all enabled AWS regions in parallel.
      Resources from all regions are aggregated into a single result.

    Args:
        aws_client: AWSClient instance for fetching resources (used in single-region mode)
        policy_service: PolicyService for determining required tags
        resource_types: List of resource types to search (e.g., ["ec2:instance", "rds:db"])
                       Supported types: ec2:instance, rds:db, s3:bucket,
                       lambda:function, ecs:service, opensearch:domain
                       Special value: ["all"] - scan ALL taggable resources (50+ types)
                       using AWS Resource Groups Tagging API
        regions: Optional list of AWS regions to search. If None, searches current region
                 (single-region mode) or all enabled regions (multi-region mode).
                 In multi-region mode, this acts as a filter for which regions to scan.
        min_cost_threshold: Optional minimum monthly cost threshold in USD.
                           Only return resources with estimated cost >= this value.
                           Implies include_costs=True.
        include_costs: Whether to include cost estimates. Defaults to False.
                      Set to True only when user explicitly asks about costs.
                      Note: EC2/RDS have accurate per-resource costs from Cost Explorer.
                      S3/Lambda/ECS costs are rough estimates (service total / resource count).
        multi_region_scanner: Optional MultiRegionScanner for multi-region scanning.
                             When provided and multi-region is enabled, scans resources
                             across all enabled AWS regions in parallel.
                             When None or multi-region is disabled, falls back to
                             single-region scanning using aws_client.
                             Requirements: 3.1

    Returns:
        UntaggedResourcesResult containing:
        - total_untagged: Count of untagged/partially tagged resources
        - resources: List of UntaggedResource objects with details
        - total_monthly_cost: Sum of estimated monthly costs (0 if include_costs=False)
        - scan_timestamp: When the scan was performed

    Raises:
        ValueError: If resource_types is empty or contains invalid types

    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 17.3, 17.4

    Example:
        >>> result = await find_untagged_resources(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_types=["ec2:instance", "s3:bucket"],
        ...     regions=["us-east-1", "us-west-2"]
        ... )
        >>> print(f"Found {result.total_untagged} untagged resources")

        # Scan ALL taggable resources (50+ types):
        >>> result = await find_untagged_resources(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_types=["all"]
        ... )
        >>> print(f"Found {result.total_untagged} untagged resources across all services")

        # Multi-region scan across all enabled regions:
        >>> result = await find_untagged_resources(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_types=["ec2:instance"],
        ...     multi_region_scanner=scanner,
        ... )
        >>> print(f"Found {result.total_untagged} untagged resources across all regions")

        # With costs (only when user asks about cost impact):
        >>> result = await find_untagged_resources(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_types=["ec2:instance"],
        ...     include_costs=True
        ... )
        >>> print(f"Total cost impact: ${result.total_monthly_cost:.2f}/month")
    """
    # Validate inputs
    if not resource_types:
        raise ValueError("resource_types cannot be empty")

    # Check for "all" special value
    use_tagging_api = "all" in resource_types

    # Validate resource types (unless using "all")
    if not use_tagging_api:
        valid_types = set(get_supported_resource_types())
        invalid_types = [rt for rt in resource_types if rt not in valid_types]
        if invalid_types:
            raise ValueError(
                f"Invalid resource types: {invalid_types}. "
                f"Valid types are: {sorted(valid_types)} or use ['all'] for comprehensive scan."
            )

    # Determine whether to use multi-region scanning
    # Requirements 3.1: Use multi-region scanner when provided and enabled
    # Multi-region scanning works with both specific resource types AND "all" mode
    use_multi_region = (
        multi_region_scanner is not None
        and multi_region_scanner.multi_region_enabled
    )

    logger.info(
        f"Finding untagged resources for types={resource_types}, "
        f"regions={regions}, min_cost={min_cost_threshold}, include_costs={include_costs}, "
        f"multi_region={'enabled' if use_multi_region else 'disabled'}"
    )

    # If min_cost_threshold is set, we need costs to filter
    if min_cost_threshold is not None:
        include_costs = True

    # Get the tagging policy to know what required tags to check for
    policy = policy_service.get_policy()

    # Collect all resources across resource types
    all_resources = []

    # Determine which resource types to scan
    types_to_scan = ["all"] if use_tagging_api else resource_types

    if use_multi_region:
        # Multi-region scanning mode
        # Use the scanner's client factory to fetch resources from all enabled regions
        logger.info("Using multi-region scanner for resource discovery")
        all_resources = await _fetch_resources_multi_region(
            multi_region_scanner=multi_region_scanner,
            resource_types=types_to_scan,
            regions=regions,
        )
    else:
        # Single-region scanning mode (backward compatible)
        if multi_region_scanner is not None and not multi_region_scanner.multi_region_enabled:
            logger.info(
                "Multi-region scanner provided but multi-region is disabled. "
                "Falling back to single-region mode."
            )
        
        for resource_type in types_to_scan:
            try:
                # Fetch resources using shared utility
                filters = {}
                if regions:
                    # For now, we only support the current region
                    # Multi-region support would require creating multiple AWS clients
                    filters["region"] = regions[0] if regions else None

                resources = await fetch_resources_by_type(aws_client, resource_type, filters)
                all_resources.extend(resources)
                logger.info(f"Fetched {len(resources)} resources of type {resource_type}")

            except Exception as e:
                logger.error(f"Failed to fetch resources of type {resource_type}: {str(e)}")
                # Continue with other resource types even if one fails
                continue

    logger.info(f"Total resources fetched: {len(all_resources)}")

    # Filter out terminated/shutting-down instances (safety net for Tagging API path).
    # The EC2 direct API already filters these, but the Resource Groups Tagging API
    # may still return recently-terminated resources without state information.
    filtered_resources = []
    terminated_count = 0

    for resource in all_resources:
        state = resource.get("instance_state", "")
        if state and state.lower() in ("terminated", "shutting-down"):
            terminated_count += 1
            continue
        filtered_resources.append(resource)

    if terminated_count > 0:
        logger.info(
            f"Excluded {terminated_count} terminated/shutting-down resources"
        )

    all_resources = filtered_resources

    # Get cost data only if requested
    if include_costs:
        resource_ids = [r["resource_id"] for r in all_resources]
        cost_data, cost_sources = await _get_cost_estimates(aws_client, resource_ids, all_resources)
        # Track all cost sources for accurate reporting (not just filtered results)
        all_cost_sources_used = set(cost_sources.values()) if cost_sources else set()
    else:
        cost_data = {}
        cost_sources = {}
        all_cost_sources_used = set()

    # Find untagged or partially tagged resources
    untagged_resources = []

    for resource in all_resources:
        resource_id = resource["resource_id"]
        resource_type = resource["resource_type"]
        tags = resource.get("tags", {})

        # Determine which required tags apply to this resource type
        required_tags = _get_required_tags_for_resource(policy, resource_type)

        # Check if resource has no tags or is missing required tags
        missing_tags = []

        if not tags:
            # Completely untagged - all required tags are missing
            missing_tags = required_tags
        else:
            # Check for missing required tags
            for required_tag in required_tags:
                if required_tag not in tags:
                    missing_tags.append(required_tag)

        # If there are missing tags, this is an untagged/partially tagged resource
        if missing_tags:
            # Calculate resource age (only if created_at is available)
            created_at = resource.get("created_at")
            age_days = _calculate_age_days(created_at) if created_at else 0
            
            # Get cost estimate and source (only if costs requested)
            monthly_cost = cost_data.get(resource_id, None) if include_costs else None
            cost_source = cost_sources.get(resource_id, None) if include_costs else None

            # Apply cost threshold filter if specified
            if min_cost_threshold is not None:
                actual_cost = monthly_cost if monthly_cost is not None else 0.0
                if actual_cost < min_cost_threshold:
                    continue

            untagged_resource = UntaggedResource(
                resource_id=resource_id,
                resource_type=resource_type,
                region=resource.get("region", "unknown"),
                arn=resource.get("arn", ""),
                current_tags=tags,
                missing_required_tags=missing_tags,
                monthly_cost_estimate=monthly_cost,
                cost_source=cost_source,
                age_days=age_days,
                created_at=created_at,
                instance_state=resource.get("instance_state"),
                instance_type=resource.get("instance_type"),
            )

            untagged_resources.append(untagged_resource)

    # Calculate total cost (only if costs were requested)
    if include_costs:
        total_cost = sum(r.monthly_cost_estimate or 0.0 for r in untagged_resources)

        # Determine cost data note based on ALL sources used during scan (not just filtered results)
        # This prevents false "Cost Explorer not enabled" messages when cost threshold filters out all resources
        if "actual" in all_cost_sources_used:
            if "stopped" in all_cost_sources_used or "estimated" in all_cost_sources_used:
                cost_note = (
                    "EC2 costs: Actual per-resource values from Cost Explorer where available. "
                    "Instances without Cost Explorer data: running instances share remaining costs, "
                    "stopped instances assigned $0 (compute only). "
                    "RDS costs are actual per-resource values. "
                    "S3/Lambda/ECS costs are estimates (service total ÷ resource count)."
                )
            else:
                cost_note = (
                    "EC2/RDS costs are actual per-resource values from Cost Explorer. "
                    "S3/Lambda/ECS costs are estimates (service total ÷ resource count) since AWS doesn't provide per-resource granularity for these services."
                )
        elif "stopped" in all_cost_sources_used or (
            "estimated" in all_cost_sources_used
            and any("ec2" in str(r.get("resource_type", "")) for r in resources)
        ):
            cost_note = (
                "EC2 costs are state-aware estimates: running instances share service total, "
                "stopped instances assigned $0 (compute only). "
                "Cost Explorer per-resource data not available. "
                "Other service costs are estimates (service total ÷ resource count)."
            )
        elif "estimated" in all_cost_sources_used:
            cost_note = (
                "Costs are estimates (service total ÷ resource count). "
                "AWS Cost Explorer doesn't provide per-resource granularity for S3, Lambda, or ECS."
            )
        else:
            cost_note = (
                "Cost data unavailable. "
                "Ensure Cost Explorer is enabled in your AWS account (takes 24-48 hours after activation)."
            )
    else:
        total_cost = 0.0
        cost_note = None

    logger.info(
        f"Found {len(untagged_resources)} untagged resources "
        f"with total cost ${total_cost:.2f}/month"
    )

    return UntaggedResourcesResult(
        total_untagged=len(untagged_resources),
        resources=untagged_resources,
        total_monthly_cost=total_cost,
        cost_data_note=cost_note,
        scan_timestamp=datetime.now(),
    )


async def _get_cost_estimates(
    aws_client: AWSClient, resource_ids: list[str], resources: list[dict]
) -> tuple[dict[str, float], dict[str, str]]:
    """
    Get cost estimates for resources with source tracking.

    Uses per-resource costs from Cost Explorer where available (EC2, RDS),
    and service-level averages for other resource types (S3, Lambda, ECS).

    Args:
        aws_client: AWSClient instance
        resource_ids: List of resource IDs
        resources: List of resource dictionaries with resource_type info

    Returns:
        Tuple of:
        - cost_data: Dictionary mapping resource IDs to monthly cost estimates
        - cost_sources: Dictionary mapping resource IDs to cost source type
    """
    if not resource_ids:
        return {}, {}

    cost_data: dict[str, float] = {}
    cost_sources: dict[str, str] = {}

    try:
        # Get per-resource and service-level costs (4-tuple: resource_costs, service_costs, costs_by_name, cost_source)
        resource_costs, service_costs, costs_by_name, base_source = (
            await aws_client.get_cost_data_by_resource()
        )

        # Count resources by service for averaging
        resources_by_service: dict[str, list[str]] = {}
        resource_type_map: dict[str, str] = {}

        for resource in resources:
            rid = resource["resource_id"]
            rtype = resource["resource_type"]
            resource_type_map[rid] = rtype
            service_name = aws_client.get_service_name_for_resource_type(rtype)

            if service_name not in resources_by_service:
                resources_by_service[service_name] = []
            resources_by_service[service_name].append(rid)

        # Assign costs to each resource with state-aware logic for EC2
        for rid in resource_ids:
            rtype = resource_type_map.get(rid, "")

            # Check if we have actual per-resource cost
            if rid in resource_costs:
                cost_data[rid] = resource_costs[rid]
                cost_sources[rid] = "actual"
            else:
                # Use service-level average with state awareness for EC2
                service_name = aws_client.get_service_name_for_resource_type(rtype)
                service_total = service_costs.get(service_name, 0.0)

                if rtype == "ec2:instance":
                    # State-aware distribution for EC2
                    resource_obj = next((r for r in resources if r["resource_id"] == rid), None)
                    instance_state = resource_obj.get("instance_state") if resource_obj else None

                    if instance_state in ["stopped", "stopping", "terminated", "shutting-down"]:
                        # Stopped instances get $0 (compute only)
                        cost_data[rid] = 0.0
                        cost_sources[rid] = "stopped"
                    else:
                        # Distribute among running instances only
                        ec2_resources = resources_by_service.get(service_name, [])
                        running_count = sum(
                            1
                            for r_id in ec2_resources
                            if next((r for r in resources if r["resource_id"] == r_id), {}).get(
                                "instance_state"
                            )
                            not in ["stopped", "stopping", "terminated", "shutting-down"]
                        )

                        if running_count > 0:
                            cost_data[rid] = service_total / running_count
                            cost_sources[rid] = "estimated"
                        else:
                            cost_data[rid] = 0.0
                            cost_sources[rid] = "estimated"
                else:
                    # Other resource types: use service average
                    resource_count = len(resources_by_service.get(service_name, [rid]))

                    if service_total > 0 and resource_count > 0:
                        cost_data[rid] = service_total / resource_count
                        cost_sources[rid] = "estimated"
                    else:
                        cost_data[rid] = 0.0
                        cost_sources[rid] = "estimated"

        return cost_data, cost_sources

    except Exception as e:
        logger.warning(f"Failed to fetch cost data: {str(e)}")
        # Return zero costs with estimated source if cost data unavailable
        return (dict.fromkeys(resource_ids, 0.0), dict.fromkeys(resource_ids, "estimated"))


def _get_required_tags_for_resource(policy: TagPolicy, resource_type: str) -> list[str]:
    """
    Get list of required tag names that apply to a resource type.

    Args:
        policy: Tagging policy (TagPolicy model)
        resource_type: Type of resource (e.g., "ec2:instance")

    Returns:
        List of required tag names
    """
    required_tags = []

    for tag in policy.required_tags:
        applies_to = tag.applies_to

        # If applies_to is empty or contains this resource type
        if not applies_to or resource_type in applies_to:
            required_tags.append(tag.name)

    return required_tags


def _calculate_age_days(created_at: datetime | None) -> int:
    """
    Calculate resource age in days.

    Args:
        created_at: When the resource was created

    Returns:
        Age in days, or 0 if created_at is None
    """
    if not created_at:
        return 0

    # Handle both datetime objects and strings
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            return 0

    # Calculate age
    now = datetime.now(created_at.tzinfo) if created_at.tzinfo else datetime.now()
    age = now - created_at

    return age.days


async def _fetch_resources_multi_region(
    multi_region_scanner: MultiRegionScanner,
    resource_types: list[str],
    regions: list[str] | None = None,
) -> list[dict]:
    """
    Fetch resources from multiple regions using the multi-region scanner.

    Uses the scanner's region discovery and client factory to fetch resources
    from all enabled regions in parallel.

    Args:
        multi_region_scanner: MultiRegionScanner instance with region discovery
                             and client factory
        resource_types: List of resource types to fetch
        regions: Optional list of regions to filter (if None, scans all enabled)

    Returns:
        List of resource dictionaries from all regions, each with a 'region' attribute

    Requirements: 3.1
    """
    # Get enabled regions from the scanner's region discovery service
    enabled_regions = await multi_region_scanner.region_discovery.get_enabled_regions()
    
    # Apply region filter if provided
    if regions:
        # Filter to only requested regions that are enabled
        regions_to_scan = [r for r in regions if r in enabled_regions]
        if not regions_to_scan:
            logger.warning(
                f"No valid regions to scan. Requested: {regions}, Enabled: {enabled_regions}"
            )
            return []
    else:
        regions_to_scan = enabled_regions
    
    logger.info(f"Fetching resources from {len(regions_to_scan)} regions: {regions_to_scan}")
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(multi_region_scanner.max_concurrent_regions)
    
    async def fetch_from_region(region: str) -> list[dict]:
        """Fetch resources from a single region with concurrency control."""
        async with semaphore:
            try:
                # Get regional client from the factory
                client = multi_region_scanner.client_factory.get_client(region)
                
                # Fetch resources for each type
                region_resources = []
                for resource_type in resource_types:
                    try:
                        resources = await fetch_resources_by_type(client, resource_type, {})
                        # Ensure each resource has the region attribute
                        for resource in resources:
                            resource["region"] = region
                        region_resources.extend(resources)
                        logger.debug(
                            f"Fetched {len(resources)} {resource_type} resources from {region}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch {resource_type} from {region}: {str(e)}"
                        )
                        # Continue with other resource types
                        continue
                
                logger.info(
                    f"Fetched {len(region_resources)} total resources from region {region}"
                )
                return region_resources
                
            except Exception as e:
                logger.error(f"Failed to fetch resources from region {region}: {str(e)}")
                return []
    
    # Fetch from all regions in parallel
    tasks = [fetch_from_region(region) for region in regions_to_scan]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Aggregate results, handling any exceptions
    all_resources = []
    for i, result in enumerate(results):
        region = regions_to_scan[i]
        if isinstance(result, Exception):
            logger.error(f"Region {region} fetch failed with exception: {result}")
        elif isinstance(result, list):
            all_resources.extend(result)
    
    logger.info(
        f"Multi-region fetch complete: {len(all_resources)} resources "
        f"from {len(regions_to_scan)} regions"
    )
    
    return all_resources
