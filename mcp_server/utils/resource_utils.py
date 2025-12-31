"""
Shared utilities for AWS resource operations.

This module contains common functions used across multiple services
for fetching and processing AWS resources.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def fetch_resources_by_type(
    aws_client,
    resource_type: str,
    filters: Optional[dict] = None
) -> list[dict]:
    """
    Fetch resources of a specific type from AWS.
    
    Args:
        aws_client: AWS client instance with resource fetching methods
        resource_type: Type of resource (e.g., "ec2:instance", "rds:db")
        filters: Optional filters for the query
    
    Returns:
        List of resource dictionaries with tags
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


def extract_account_from_arn(arn: str) -> str:
    """
    Extract AWS account ID from an ARN.
    
    ARN format: arn:aws:service:region:account-id:resource
    
    Args:
        arn: AWS ARN string
    
    Returns:
        Account ID or "unknown" if not found
    """
    if not arn:
        return "unknown"
    
    parts = arn.split(":")
    if len(parts) >= 5:
        return parts[4] or "unknown"
    
    return "unknown"