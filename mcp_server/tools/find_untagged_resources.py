# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for finding untagged resources."""

import logging
from datetime import datetime
from typing import Optional

from ..models.untagged import UntaggedResourcesResult, UntaggedResource
from ..models.policy import TagPolicy
from ..clients.aws_client import AWSClient
from ..services.policy_service import PolicyService
from ..utils.resource_utils import (
    fetch_resources_by_type,
    SUPPORTED_RESOURCE_TYPES,
    TAGGING_API_RESOURCE_TYPES,
)

logger = logging.getLogger(__name__)


async def find_untagged_resources(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_types: list[str],
    regions: Optional[list[str]] = None,
    min_cost_threshold: Optional[float] = None,
    include_costs: bool = False
) -> UntaggedResourcesResult:
    """
    Find resources with no tags or missing required tags.
    
    This tool searches for resources that are completely untagged or missing
    critical required tags. It includes resource age to help prioritize remediation.
    
    Args:
        aws_client: AWSClient instance for fetching resources
        policy_service: PolicyService for determining required tags
        resource_types: List of resource types to search (e.g., ["ec2:instance", "rds:db"])
                       Supported types: ec2:instance, rds:db, s3:bucket,
                       lambda:function, ecs:service, opensearch:domain
                       Special value: ["all"] - scan ALL taggable resources (50+ types)
                       using AWS Resource Groups Tagging API
        regions: Optional list of AWS regions to search. If None, searches current region.
        min_cost_threshold: Optional minimum monthly cost threshold in USD.
                           Only return resources with estimated cost >= this value.
                           Implies include_costs=True.
        include_costs: Whether to include cost estimates. Defaults to False.
                      Set to True only when user explicitly asks about costs.
                      Note: EC2/RDS have accurate per-resource costs from Cost Explorer.
                      S3/Lambda/ECS costs are rough estimates (service total / resource count).
    
    Returns:
        UntaggedResourcesResult containing:
        - total_untagged: Count of untagged/partially tagged resources
        - resources: List of UntaggedResource objects with details
        - total_monthly_cost: Sum of estimated monthly costs (0 if include_costs=False)
        - scan_timestamp: When the scan was performed
    
    Raises:
        ValueError: If resource_types is empty or contains invalid types
    
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 17.3, 17.4
    
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
        valid_types = set(SUPPORTED_RESOURCE_TYPES)
        invalid_types = [rt for rt in resource_types if rt not in valid_types]
        if invalid_types:
            raise ValueError(
                f"Invalid resource types: {invalid_types}. "
                f"Valid types are: {sorted(valid_types)} or use ['all'] for comprehensive scan."
            )
    
    logger.info(
        f"Finding untagged resources for types={resource_types}, "
        f"regions={regions}, min_cost={min_cost_threshold}, include_costs={include_costs}"
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
    
    for resource_type in types_to_scan:
        try:
            # Fetch resources using shared utility
            filters = {}
            if regions:
                # For now, we only support the current region
                # Multi-region support would require creating multiple AWS clients
                filters["region"] = regions[0] if regions else None
            
            resources = await fetch_resources_by_type(
                aws_client,
                resource_type,
                filters
            )
            all_resources.extend(resources)
            logger.info(f"Fetched {len(resources)} resources of type {resource_type}")
        
        except Exception as e:
            logger.error(f"Failed to fetch resources of type {resource_type}: {str(e)}")
            # Continue with other resource types even if one fails
            continue
    
    logger.info(f"Total resources fetched: {len(all_resources)}")
    
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
            # Calculate resource age
            age_days = _calculate_age_days(resource.get("created_at"))
            
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
                created_at=resource.get("created_at"),
                instance_state=resource.get("instance_state"),
                instance_type=resource.get("instance_type")
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
        elif "stopped" in all_cost_sources_used or ("estimated" in all_cost_sources_used and any("ec2" in str(r.get("resource_type", "")) for r in resources)):
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
        scan_timestamp=datetime.now()
    )


async def _get_cost_estimates(
    aws_client: AWSClient,
    resource_ids: list[str],
    resources: list[dict]
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
        resource_costs, service_costs, costs_by_name, base_source = await aws_client.get_cost_data_by_resource()
        
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
                            1 for r_id in ec2_resources
                            if next((r for r in resources if r["resource_id"] == r_id), {}).get("instance_state")
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
        return (
            {rid: 0.0 for rid in resource_ids},
            {rid: "estimated" for rid in resource_ids}
        )


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


def _calculate_age_days(created_at: Optional[datetime]) -> int:
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
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except Exception:
            return 0
    
    # Calculate age
    now = datetime.now(created_at.tzinfo) if created_at.tzinfo else datetime.now()
    age = now - created_at
    
    return age.days
