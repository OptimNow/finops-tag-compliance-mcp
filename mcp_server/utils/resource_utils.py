# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""
Shared utilities for AWS resource operations.

This module contains common functions used across multiple services
for fetching and processing AWS resources.

Resource type configuration is loaded from config/resource_types.json
for easy maintenance. See ResourceTypeConfig for details.
"""

import logging

from .resource_type_config import (
    get_supported_resource_types as _get_supported,
)
from .resource_type_config import (
    get_tagging_api_resource_types as _get_tagging_api,
)

logger = logging.getLogger(__name__)

# Resource types that have dedicated service API fetchers.
# These APIs return ALL resources (including untagged), unlike the
# Resource Groups Tagging API which only returns resources with ≥1 tag.
DIRECT_FETCHER_TYPES = frozenset({
    "ec2:instance",
    "rds:db",
    "s3:bucket",
    "lambda:function",
    "ecs:service",
    "opensearch:domain",
})


# Re-export for backward compatibility
# These now load from config/resource_types.json
def get_supported_resource_types() -> list[str]:
    """
    Get list of resource types that generate direct costs.

    These are scanned for compliance and cost attribution.
    Loaded from config/resource_types.json.

    Returns:
        List of supported resource type strings
    """
    return _get_supported()


def get_tagging_api_resource_types() -> list[str]:
    """
    Get list of resource types discoverable via Resource Groups Tagging API.

    Loaded from config/resource_types.json.

    Returns:
        List of resource type strings
    """
    return _get_tagging_api()


def expand_all_to_supported_types(resource_types: list[str]) -> list[str]:
    """
    Expand "all" to the full list of supported resource types.

    When users specify "all", we expand it to scan all supported resource types
    individually. This catches resources with ZERO tags (unlike the Tagging API
    which only returns resources with at least one tag).

    Args:
        resource_types: List of resource types, may contain "all"

    Returns:
        Expanded list with "all" replaced by all supported types
    """
    if "all" not in resource_types:
        return resource_types

    # Get current supported types from config
    supported = get_supported_resource_types()

    # Start with all supported types
    expanded = set(supported)

    # Add any other specific types that were requested alongside "all"
    for rt in resource_types:
        if rt != "all":
            expanded.add(rt)

    return list(expanded)


async def fetch_resources_by_type(
    aws_client, resource_type: str, filters: dict | None = None
) -> list[dict]:
    """
    Fetch resources of a specific type from AWS.

    Supports two modes:
    1. Individual service APIs (ec2:instance, rds:db, etc.) - more detailed info
    2. Resource Groups Tagging API (fallback for unsupported types)

    NOTE: "all" should be expanded BEFORE calling this function using
    expand_all_to_supported_types(). This function handles individual types.

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
        "opensearch:domain": aws_client.get_opensearch_domains,
    }

    fetcher = resource_fetchers.get(resource_type)
    if not fetcher:
        # Try Resource Groups Tagging API for types without direct fetchers
        logger.info(f"Resource type {resource_type} not in direct fetchers, trying Tagging API")
        return await fetch_resources_via_tagging_api(aws_client, [resource_type], filters)

    try:
        resources = await fetcher(filters)
        return resources
    except Exception as e:
        logger.error(f"Failed to fetch {resource_type}: {str(e)}")
        raise


async def fetch_all_resources_via_tagging_api(
    aws_client, filters: dict | None = None
) -> list[dict]:
    """
    Fetch all taggable resources using AWS Resource Groups Tagging API.

    This method discovers resources across 50+ AWS services in a single API call,
    providing comprehensive coverage without needing individual service API calls.

    Args:
        aws_client: AWS client instance
        filters: Optional filters (tag_filters supported)

    Returns:
        List of resource dictionaries with tags
    """
    logger.info("Fetching all resources via Resource Groups Tagging API")

    try:
        # Build tag filters if provided
        tag_filters = None
        if filters and "tag_filters" in filters:
            tag_filters = filters["tag_filters"]

        resources = await aws_client.get_all_tagged_resources(
            resource_type_filters=None, tag_filters=tag_filters  # No filter = all resource types
        )

        logger.info(f"Discovered {len(resources)} resources via Tagging API")
        return resources

    except Exception as e:
        logger.error(f"Failed to fetch resources via Tagging API: {str(e)}")
        raise


async def fetch_resources_via_tagging_api(
    aws_client, resource_types: list[str], filters: dict | None = None
) -> list[dict]:
    """
    Fetch specific resource types using AWS Resource Groups Tagging API.

    This is useful for resource types not supported by individual service APIs
    (e.g., DynamoDB tables, SNS topics, SQS queues).

    Args:
        aws_client: AWS client instance
        resource_types: List of resource types to fetch
        filters: Optional filters

    Returns:
        List of resource dictionaries with tags
    """
    logger.info(f"Fetching {resource_types} via Resource Groups Tagging API")

    try:
        # Build tag filters if provided
        tag_filters = None
        if filters and "tag_filters" in filters:
            tag_filters = filters["tag_filters"]

        resources = await aws_client.get_all_tagged_resources(
            resource_type_filters=resource_types, tag_filters=tag_filters
        )

        logger.info(f"Discovered {len(resources)} resources of types {resource_types}")
        return resources

    except Exception as e:
        logger.error(f"Failed to fetch resources via Tagging API: {str(e)}")
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
