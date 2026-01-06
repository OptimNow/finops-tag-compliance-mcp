# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""
Shared utilities for AWS resource operations.

This module contains common functions used across multiple services
for fetching and processing AWS resources.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Resource types supported by individual service APIs
SUPPORTED_RESOURCE_TYPES = [
    "ec2:instance",
    "rds:db",
    "s3:bucket",
    "lambda:function",
    "ecs:service",
    "opensearch:domain",
]

# Resource types that can be discovered via Resource Groups Tagging API
# This is a much larger set including DynamoDB, SNS, SQS, etc.
TAGGING_API_RESOURCE_TYPES = [
    "ec2:instance",
    "ec2:volume",
    "ec2:vpc",
    "ec2:subnet",
    "ec2:security-group",
    "ec2:snapshot",
    "rds:db",
    "rds:cluster",
    "s3:bucket",
    "lambda:function",
    "ecs:service",
    "ecs:cluster",
    "opensearch:domain",
    "dynamodb:table",
    "sns:topic",
    "sqs:queue",
    "elasticache:cluster",
    "elasticache:replicationgroup",
    "secretsmanager:secret",
    "kms:key",
    "ecr:repository",
    "efs:file-system",
    "elasticloadbalancing:loadbalancer",
    "elasticloadbalancing:targetgroup",
    "apigateway:restapi",
    "cloudfront:distribution",
    "route53:hostedzone",
    "kinesis:stream",
    "glue:database",
    "glue:table",
    "athena:workgroup",
    "redshift:cluster",
    "emr:cluster",
    "stepfunctions:statemachine",
    "codebuild:project",
    "codepipeline:pipeline",
    "logs:log-group",
    "cloudwatch:alarm",
]


async def fetch_resources_by_type(
    aws_client,
    resource_type: str,
    filters: Optional[dict] = None
) -> list[dict]:
    """
    Fetch resources of a specific type from AWS.
    
    Supports two modes:
    1. Individual service APIs (ec2:instance, rds:db, etc.) - more detailed info
    2. Resource Groups Tagging API ("all") - discovers 50+ resource types
    
    Args:
        aws_client: AWS client instance with resource fetching methods
        resource_type: Type of resource (e.g., "ec2:instance", "rds:db", "all")
        filters: Optional filters for the query
    
    Returns:
        List of resource dictionaries with tags
    """
    # Special case: "all" uses Resource Groups Tagging API
    if resource_type == "all":
        return await fetch_all_resources_via_tagging_api(aws_client, filters)
    
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
        # Try Resource Groups Tagging API for unknown types
        logger.info(f"Resource type {resource_type} not in direct fetchers, trying Tagging API")
        return await fetch_resources_via_tagging_api(aws_client, [resource_type], filters)
    
    try:
        resources = await fetcher(filters)
        return resources
    except Exception as e:
        logger.error(f"Failed to fetch {resource_type}: {str(e)}")
        raise


async def fetch_all_resources_via_tagging_api(
    aws_client,
    filters: Optional[dict] = None
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
            resource_type_filters=None,  # No filter = all resource types
            tag_filters=tag_filters
        )
        
        logger.info(f"Discovered {len(resources)} resources via Tagging API")
        return resources
    
    except Exception as e:
        logger.error(f"Failed to fetch resources via Tagging API: {str(e)}")
        raise


async def fetch_resources_via_tagging_api(
    aws_client,
    resource_types: list[str],
    filters: Optional[dict] = None
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
            resource_type_filters=resource_types,
            tag_filters=tag_filters
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


def get_supported_resource_types() -> list[str]:
    """
    Get list of resource types supported by individual service APIs.
    
    Returns:
        List of supported resource type strings
    """
    return SUPPORTED_RESOURCE_TYPES.copy()


def get_tagging_api_resource_types() -> list[str]:
    """
    Get list of resource types discoverable via Resource Groups Tagging API.
    
    Returns:
        List of resource type strings
    """
    return TAGGING_API_RESOURCE_TYPES.copy()