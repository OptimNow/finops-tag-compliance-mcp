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
# These are the HIGH-VALUE resource types that typically drive cloud costs
# When "all" is specified, we scan ALL of these types individually
# 
# EXCLUDED (free or negligible cost resources):
# - ec2:vpc, ec2:subnet, ec2:security-group - FREE
# - logs:log-group - FREE (costs are on ingestion/storage)
# - cloudwatch:alarm - Nearly free ($0.10/alarm after first 10)
# - sns:topic, sqs:queue - FREE (costs are on messages)
# - ecr:repository - FREE (costs are on storage)
# - glue:database - FREE (costs are on jobs/crawlers)
# - athena:workgroup - FREE (costs are on queries)
#
SUPPORTED_RESOURCE_TYPES = [
    # Compute (40-60% of typical spend)
    "ec2:instance",
    "ec2:volume",
    "ec2:elastic-ip",      # $3.65/month if not attached to running instance
    "ec2:snapshot",        # Cost per GB stored
    "lambda:function",
    "ecs:cluster",
    "ecs:service",
    "ecs:task-definition",
    "eks:cluster",
    "eks:nodegroup",
    # Storage (10-20% of typical spend)
    "s3:bucket",
    "elasticfilesystem:file-system",
    "fsx:file-system",
    # Database (15-25% of typical spend)
    "rds:db",
    "dynamodb:table",
    "elasticache:cluster",
    "redshift:cluster",
    # AI/ML (Growing rapidly)
    "sagemaker:endpoint",
    "sagemaker:notebook-instance",
    "bedrock:agent",
    "bedrock:knowledge-base",
    # Networking (cost-generating resources only)
    "elasticloadbalancing:loadbalancer",
    "elasticloadbalancing:targetgroup",
    "ec2:natgateway",      # ~$32/month + data transfer
    # Analytics (cost-generating only)
    "kinesis:stream",
    "glue:job",
    "glue:crawler",
    "opensearch:domain",
    # Identity & Security (with meaningful costs)
    "cognito-idp:userpool",
    "secretsmanager:secret",  # $0.40/month per secret
    "kms:key",                # $1/month per key
]


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
    
    # Start with all supported types
    expanded = set(SUPPORTED_RESOURCE_TYPES)
    
    # Add any other specific types that were requested alongside "all"
    for rt in resource_types:
        if rt != "all":
            expanded.add(rt)
    
    return list(expanded)

# Resource types that can be discovered via Resource Groups Tagging API
# This is a much larger set including DynamoDB, SNS, SQS, etc.
# NOTE: This API only returns resources that have at least one tag!
TAGGING_API_RESOURCE_TYPES = [
    # Compute (40-60% of typical spend)
    "ec2:instance",
    "ec2:volume",
    "ec2:elastic-ip",
    "ec2:snapshot",
    "ec2:vpc",
    "ec2:subnet",
    "ec2:security-group",
    "ec2:natgateway",
    "lambda:function",
    "ecs:cluster",
    "ecs:service",
    "ecs:task-definition",
    "eks:cluster",
    "eks:nodegroup",
    # Storage (10-20% of typical spend)
    "s3:bucket",
    "elasticfilesystem:file-system",
    "fsx:file-system",
    # Database (15-25% of typical spend)
    "rds:db",
    "rds:cluster",
    "dynamodb:table",
    "elasticache:cluster",
    "elasticache:replicationgroup",
    "redshift:cluster",
    # AI/ML (Growing rapidly)
    "sagemaker:endpoint",
    "sagemaker:notebook-instance",
    "bedrock:agent",
    "bedrock:knowledge-base",
    # Networking (Often overlooked)
    "elasticloadbalancing:loadbalancer",
    "elasticloadbalancing:targetgroup",
    # Analytics (Data & streaming)
    "kinesis:stream",
    "glue:database",
    "glue:table",
    "glue:crawler",
    "glue:job",
    "athena:workgroup",
    "opensearch:domain",
    "emr:cluster",
    # Identity & Security
    "cognito-idp:userpool",
    "cognito-identity:identitypool",
    "secretsmanager:secret",
    "kms:key",
    # Monitoring & Logging
    "logs:log-group",
    "cloudwatch:alarm",
    # Messaging
    "sns:topic",
    "sqs:queue",
    # Containers
    "ecr:repository",
    # API Gateway
    "apigateway:restapi",
    # CDN
    "cloudfront:distribution",
    # DNS
    "route53:hostedzone",
    # Orchestration
    "stepfunctions:statemachine",
    # CI/CD
    "codebuild:project",
    "codepipeline:pipeline",
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