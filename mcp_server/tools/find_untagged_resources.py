"""MCP tool for finding untagged resources."""

import logging
from datetime import datetime
from typing import Optional

from ..models.untagged import UntaggedResourcesResult, UntaggedResource
from ..models.policy import TagPolicy
from ..clients.aws_client import AWSClient
from ..services.policy_service import PolicyService

logger = logging.getLogger(__name__)


async def find_untagged_resources(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_types: list[str],
    regions: Optional[list[str]] = None,
    min_cost_threshold: Optional[float] = None
) -> UntaggedResourcesResult:
    """
    Find resources with no tags or missing required tags.
    
    This tool searches for resources that are completely untagged or missing
    critical required tags. It includes cost estimates and resource age to help
    prioritize remediation efforts.
    
    Args:
        aws_client: AWSClient instance for fetching resources
        policy_service: PolicyService for determining required tags
        resource_types: List of resource types to search (e.g., ["ec2:instance", "rds:db"])
                       Supported types: ec2:instance, rds:db, s3:bucket,
                       lambda:function, ecs:service
        regions: Optional list of AWS regions to search. If None, searches current region.
        min_cost_threshold: Optional minimum monthly cost threshold in USD.
                           Only return resources with estimated cost >= this value.
    
    Returns:
        UntaggedResourcesResult containing:
        - total_untagged: Count of untagged/partially tagged resources
        - resources: List of UntaggedResource objects with details
        - total_monthly_cost: Sum of estimated monthly costs
        - scan_timestamp: When the scan was performed
    
    Raises:
        ValueError: If resource_types is empty or contains invalid types
    
    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
    
    Example:
        >>> result = await find_untagged_resources(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_types=["ec2:instance", "s3:bucket"],
        ...     regions=["us-east-1", "us-west-2"],
        ...     min_cost_threshold=100.0
        ... )
        >>> print(f"Found {result.total_untagged} untagged resources")
        >>> print(f"Total cost impact: ${result.total_monthly_cost:.2f}/month")
    """
    # Validate inputs
    if not resource_types:
        raise ValueError("resource_types cannot be empty")
    
    # Validate resource types
    valid_types = {
        "ec2:instance",
        "rds:db",
        "s3:bucket",
        "lambda:function",
        "ecs:service"
    }
    
    invalid_types = [rt for rt in resource_types if rt not in valid_types]
    if invalid_types:
        raise ValueError(
            f"Invalid resource types: {invalid_types}. "
            f"Valid types are: {sorted(valid_types)}"
        )
    
    logger.info(
        f"Finding untagged resources for types={resource_types}, "
        f"regions={regions}, min_cost={min_cost_threshold}"
    )
    
    # Get the tagging policy to know what required tags to check for
    policy = policy_service.get_policy()
    
    # Collect all resources across resource types
    all_resources = []
    
    for resource_type in resource_types:
        try:
            # Fetch resources of this type
            filters = {}
            if regions:
                # For now, we only support the current region
                # Multi-region support would require creating multiple AWS clients
                filters["region"] = regions[0] if regions else None
            
            resources = await _fetch_resources_by_type(
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
    
    # Get cost data for all resources
    resource_ids = [r["resource_id"] for r in all_resources]
    cost_data = await _get_cost_estimates(aws_client, resource_ids)
    
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
            
            # Get cost estimate
            monthly_cost = cost_data.get(resource_id, 0.0)
            
            # Apply cost threshold filter if specified
            if min_cost_threshold is not None and monthly_cost < min_cost_threshold:
                continue
            
            untagged_resource = UntaggedResource(
                resource_id=resource_id,
                resource_type=resource_type,
                region=resource.get("region", "unknown"),
                arn=resource.get("arn", ""),
                current_tags=tags,
                missing_required_tags=missing_tags,
                monthly_cost_estimate=monthly_cost,
                age_days=age_days,
                created_at=resource.get("created_at")
            )
            
            untagged_resources.append(untagged_resource)
    
    # Calculate total cost
    total_cost = sum(r.monthly_cost_estimate for r in untagged_resources)
    
    logger.info(
        f"Found {len(untagged_resources)} untagged resources "
        f"with total cost ${total_cost:.2f}/month"
    )
    
    return UntaggedResourcesResult(
        total_untagged=len(untagged_resources),
        resources=untagged_resources,
        total_monthly_cost=total_cost,
        scan_timestamp=datetime.now()
    )


async def _fetch_resources_by_type(
    aws_client: AWSClient,
    resource_type: str,
    filters: dict
) -> list[dict]:
    """
    Fetch resources of a specific type from AWS.
    
    Args:
        aws_client: AWSClient instance
        resource_type: Type of resource (e.g., "ec2:instance")
        filters: Filters for the query
    
    Returns:
        List of resource dictionaries
    """
    # Map resource types to AWS client methods
    resource_fetchers = {
        "ec2:instance": aws_client.get_ec2_instances,
        "rds:db": aws_client.get_rds_instances,
        "s3:bucket": aws_client.get_s3_buckets,
        "lambda:function": aws_client.get_lambda_functions,
        "ecs:service": aws_client.get_ecs_services,
    }
    
    fetcher = resource_fetchers.get(resource_type)
    if not fetcher:
        logger.warning(f"Unknown resource type: {resource_type}")
        return []
    
    try:
        resources = await fetcher(filters)
        return resources
    except Exception as e:
        logger.error(f"Failed to fetch {resource_type}: {str(e)}")
        raise


async def _get_cost_estimates(
    aws_client: AWSClient,
    resource_ids: list[str]
) -> dict[str, float]:
    """
    Get cost estimates for resources.
    
    Args:
        aws_client: AWSClient instance
        resource_ids: List of resource IDs
    
    Returns:
        Dictionary mapping resource IDs to monthly cost estimates
    """
    if not resource_ids:
        return {}
    
    try:
        cost_data = await aws_client.get_cost_data(
            resource_ids=resource_ids,
            time_period=None,  # Use default (last 30 days)
            granularity="MONTHLY"
        )
        return cost_data
    except Exception as e:
        logger.warning(f"Failed to fetch cost data: {str(e)}")
        # Return zero costs if cost data unavailable
        return {rid: 0.0 for rid in resource_ids}


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
