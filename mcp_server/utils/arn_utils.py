# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Shared ARN parsing and validation utilities.

This module centralizes ARN handling logic used across multiple tools
to ensure consistent behavior and eliminate code duplication.
"""

import re
from typing import Optional


# ARN validation pattern - supports standard AWS ARN formats including:
# - S3 buckets with empty region/account fields
# - Resources with colons in their identifiers
ARN_PATTERN = re.compile(r"^arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:[0-9]*:.+")


def is_valid_arn(arn: Optional[str]) -> bool:
    """
    Validate if a string is a valid AWS ARN format.

    Supports various ARN formats including:
    - Standard: arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0
    - S3: arn:aws:s3:::bucket-name (empty region and account)
    - Global services: arn:aws:iam::123456789012:role/role-name

    Args:
        arn: String to validate

    Returns:
        True if valid ARN format, False otherwise
    """
    if not arn or not isinstance(arn, str):
        return False

    return bool(ARN_PATTERN.match(arn))


def parse_arn(arn: str) -> dict[str, str]:
    """
    Parse an AWS ARN into its components.

    ARN format: arn:partition:service:region:account:resource

    Args:
        arn: AWS ARN string

    Returns:
        Dictionary with parsed ARN components:
        - partition: AWS partition (aws, aws-cn, aws-us-gov)
        - service: AWS service name (ec2, s3, rds, etc.)
        - region: AWS region (may be empty for global services like S3)
        - account: AWS account ID (may be empty for some services)
        - resource: Full resource part of ARN
        - resource_type: Our internal resource type format (e.g., "ec2:instance")
        - resource_id: Resource identifier extracted from resource part

    Raises:
        ValueError: If ARN format is invalid

    Example:
        >>> parse_arn("arn:aws:ec2:us-east-1:123456789012:instance/i-abc123")
        {
            'partition': 'aws',
            'service': 'ec2',
            'region': 'us-east-1',
            'account': '123456789012',
            'resource': 'instance/i-abc123',
            'resource_type': 'ec2:instance',
            'resource_id': 'i-abc123'
        }
    """
    parts = arn.split(":")

    if len(parts) < 6:
        raise ValueError(f"Invalid ARN format: {arn}")

    partition = parts[1]
    service = parts[2]
    region = parts[3] or "global"  # S3 buckets and IAM have empty region
    account = parts[4]
    resource = ":".join(parts[5:])  # Resource may contain colons

    # Map AWS service to our internal resource type
    resource_type = service_to_resource_type(service, resource)

    # Extract resource ID from resource part
    resource_id = extract_resource_id(resource)

    return {
        "partition": partition,
        "service": service,
        "region": region,
        "account": account,
        "resource": resource,
        "resource_type": resource_type,
        "resource_id": resource_id,
    }


def service_to_resource_type(service: str, resource: str) -> str:
    """
    Map AWS service and resource to our internal resource type format.

    Args:
        service: AWS service name (e.g., "ec2", "s3", "rds")
        resource: Resource part of ARN (e.g., "instance/i-123", "db:mydb")

    Returns:
        Resource type string (e.g., "ec2:instance", "s3:bucket", "rds:db")
    """
    if service == "ec2":
        if resource.startswith("instance/"):
            return "ec2:instance"
        elif resource.startswith("volume/"):
            return "ec2:volume"
        elif resource.startswith("vpc/"):
            return "ec2:vpc"
        elif resource.startswith("subnet/"):
            return "ec2:subnet"
        elif resource.startswith("security-group/"):
            return "ec2:security-group"
        elif resource.startswith("natgateway/"):
            return "ec2:natgateway"
        return "ec2:instance"  # Default for EC2

    elif service == "rds":
        if resource.startswith("db:") or resource.startswith("db/"):
            return "rds:db"
        elif resource.startswith("cluster:"):
            return "rds:cluster"
        return "rds:db"  # Default for RDS

    elif service == "s3":
        return "s3:bucket"

    elif service == "lambda":
        if resource.startswith("function:"):
            return "lambda:function"
        return "lambda:function"  # Default for Lambda

    elif service == "ecs":
        if "service/" in resource:
            return "ecs:service"
        elif "cluster/" in resource:
            return "ecs:cluster"
        elif "task-definition/" in resource:
            return "ecs:task-definition"
        return "ecs:service"  # Default for ECS

    elif service == "eks":
        if "cluster/" in resource:
            return "eks:cluster"
        elif "nodegroup/" in resource:
            return "eks:nodegroup"
        return "eks:cluster"

    elif service == "dynamodb":
        if resource.startswith("table/"):
            return "dynamodb:table"
        return "dynamodb:table"

    elif service == "elasticache":
        if "cluster:" in resource:
            return "elasticache:cluster"
        return "elasticache:cluster"

    elif service == "es" or service == "opensearch":
        return "opensearch:domain"

    elif service == "sagemaker":
        if "endpoint/" in resource:
            return "sagemaker:endpoint"
        elif "notebook-instance/" in resource:
            return "sagemaker:notebook-instance"
        return "sagemaker:endpoint"

    elif service == "bedrock":
        if "agent/" in resource:
            return "bedrock:agent"
        elif "knowledge-base/" in resource:
            return "bedrock:knowledge-base"
        return "bedrock:agent"

    elif service == "elasticfilesystem":
        return "elasticfilesystem:file-system"

    elif service == "fsx":
        return "fsx:file-system"

    elif service == "redshift":
        return "redshift:cluster"

    elif service == "kinesis":
        return "kinesis:stream"

    elif service == "glue":
        if "job/" in resource:
            return "glue:job"
        return "glue:job"

    elif service == "elasticloadbalancing":
        if "loadbalancer/" in resource:
            return "elasticloadbalancing:loadbalancer"
        elif "targetgroup/" in resource:
            return "elasticloadbalancing:targetgroup"
        return "elasticloadbalancing:loadbalancer"

    # Unknown service - return as service:unknown
    return f"{service}:unknown"


def extract_resource_id(resource: str) -> str:
    """
    Extract the resource ID from the resource part of an ARN.

    Handles various AWS resource formats:
    - type/id: instance/i-1234567890abcdef0
    - type/subtype/id: service/cluster-name/service-name
    - type:id: function:my-function
    - just id: bucket-name

    Args:
        resource: Resource part of ARN

    Returns:
        Resource ID string

    Example:
        >>> extract_resource_id("instance/i-1234567890abcdef0")
        'i-1234567890abcdef0'
        >>> extract_resource_id("function:my-function")
        'my-function'
        >>> extract_resource_id("bucket-name")
        'bucket-name'
    """
    if "/" in resource:
        # Format: type/id or type/subtype/id
        parts = resource.split("/")
        return parts[-1]

    elif ":" in resource:
        # Format: type:id
        parts = resource.split(":")
        return parts[-1]

    # Just the resource ID (e.g., S3 bucket name)
    return resource


def get_account_from_arn(arn: str) -> str:
    """
    Extract the AWS account ID from an ARN.

    Args:
        arn: AWS ARN string

    Returns:
        AWS account ID or empty string if not present
    """
    try:
        parsed = parse_arn(arn)
        return parsed.get("account", "")
    except ValueError:
        return ""


def get_region_from_arn(arn: str) -> str:
    """
    Extract the AWS region from an ARN.

    Args:
        arn: AWS ARN string

    Returns:
        AWS region or "global" if not present
    """
    try:
        parsed = parse_arn(arn)
        return parsed.get("region", "global")
    except ValueError:
        return "global"
