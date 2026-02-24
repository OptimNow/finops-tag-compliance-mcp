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
#
# As of v0.3.0, ALL cost-generating resource types have direct fetchers.
# This eliminates the Tagging API blind spot where completely untagged
# resources were silently skipped during compliance scans.
DIRECT_FETCHER_TYPES = frozenset({
    # Compute
    "ec2:instance",
    "ec2:volume",
    "ec2:elastic-ip",
    "ec2:snapshot",
    "ec2:natgateway",
    "lambda:function",
    "ecs:cluster",
    "ecs:service",
    "ecs:task-definition",
    "eks:cluster",
    "eks:nodegroup",
    # Storage
    "s3:bucket",
    "elasticfilesystem:file-system",
    "fsx:file-system",
    # Database
    "rds:db",
    "rds:cluster",
    "dynamodb:table",
    "elasticache:cluster",
    "elasticache:replicationgroup",
    "redshift:cluster",
    # AI/ML
    "sagemaker:endpoint",
    "sagemaker:notebook-instance",
    "bedrock:agent",
    "bedrock:knowledge-base",
    # Networking
    "elasticloadbalancing:loadbalancer",
    "elasticloadbalancing:targetgroup",
    # Analytics
    "kinesis:stream",
    "glue:job",
    "glue:crawler",
    "glue:table",
    "opensearch:domain",
    "emr:cluster",
    # Security
    "cognito-idp:userpool",
    "cognito-identity:identitypool",
    "secretsmanager:secret",
    "kms:key",
    # Application
    "apigateway:restapi",
    "cloudfront:distribution",
    "route53:hostedzone",
    "stepfunctions:statemachine",
    "codebuild:project",
    "codepipeline:pipeline",
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
    Fetch resources of a specific type from AWS using dedicated service APIs.

    Every cost-generating resource type has a direct fetcher that returns ALL
    resources including those with zero tags. The Resource Groups Tagging API
    is only used as a last-resort fallback for unknown/future resource types.

    NOTE: "all" should be expanded BEFORE calling this function using
    expand_all_to_supported_types(). This function handles individual types.

    Args:
        aws_client: AWS client instance with resource fetching methods
        resource_type: Type of resource (e.g., "ec2:instance", "rds:db")
        filters: Optional filters for the query

    Returns:
        List of resource dictionaries with tags
    """
    # Map resource types to AWS client methods.
    # All cost-generating types from config/resource_types.json are covered.
    resource_fetchers = {
        # Compute
        "ec2:instance": aws_client.get_ec2_instances,
        "ec2:volume": aws_client.get_ebs_volumes,
        "ec2:elastic-ip": aws_client.get_elastic_ips,
        "ec2:snapshot": aws_client.get_ebs_snapshots,
        "ec2:natgateway": aws_client.get_nat_gateways,
        "lambda:function": aws_client.get_lambda_functions,
        "ecs:cluster": aws_client.get_ecs_clusters,
        "ecs:service": aws_client.get_ecs_services,
        "ecs:task-definition": aws_client.get_ecs_task_definitions,
        "eks:cluster": aws_client.get_eks_clusters,
        "eks:nodegroup": aws_client.get_eks_nodegroups,
        # Storage
        "s3:bucket": aws_client.get_s3_buckets,
        "elasticfilesystem:file-system": aws_client.get_efs_file_systems,
        "fsx:file-system": aws_client.get_fsx_file_systems,
        # Database
        "rds:db": aws_client.get_rds_instances,
        "rds:cluster": aws_client.get_rds_clusters,
        "dynamodb:table": aws_client.get_dynamodb_tables,
        "elasticache:cluster": aws_client.get_elasticache_clusters,
        "elasticache:replicationgroup": aws_client.get_elasticache_replication_groups,
        "redshift:cluster": aws_client.get_redshift_clusters,
        # AI/ML
        "sagemaker:endpoint": aws_client.get_sagemaker_endpoints,
        "sagemaker:notebook-instance": aws_client.get_sagemaker_notebooks,
        "bedrock:agent": aws_client.get_bedrock_agents,
        "bedrock:knowledge-base": aws_client.get_bedrock_knowledge_bases,
        # Networking
        "elasticloadbalancing:loadbalancer": aws_client.get_load_balancers,
        "elasticloadbalancing:targetgroup": aws_client.get_target_groups,
        # Analytics
        "kinesis:stream": aws_client.get_kinesis_streams,
        "glue:job": aws_client.get_glue_jobs,
        "glue:crawler": aws_client.get_glue_crawlers,
        "glue:table": aws_client.get_glue_tables,
        "opensearch:domain": aws_client.get_opensearch_domains,
        "emr:cluster": aws_client.get_emr_clusters,
        # Security
        "cognito-idp:userpool": aws_client.get_cognito_user_pools,
        "cognito-identity:identitypool": aws_client.get_cognito_identity_pools,
        "secretsmanager:secret": aws_client.get_secrets,
        "kms:key": aws_client.get_kms_keys,
        # Application
        "apigateway:restapi": aws_client.get_api_gateways,
        "cloudfront:distribution": aws_client.get_cloudfront_distributions,
        "route53:hostedzone": aws_client.get_route53_hosted_zones,
        "stepfunctions:statemachine": aws_client.get_step_functions,
        "codebuild:project": aws_client.get_codebuild_projects,
        "codepipeline:pipeline": aws_client.get_codepipeline_pipelines,
    }

    fetcher = resource_fetchers.get(resource_type)
    if not fetcher:
        # Fallback for unknown/future resource types not yet in the map
        logger.warning(
            f"Resource type {resource_type} has no direct fetcher, "
            f"falling back to Tagging API (untagged resources will be missed)"
        )
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
