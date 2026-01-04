# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for validating resource tags against policy."""

import logging
import re
from datetime import datetime, UTC
from typing import Optional

from ..models.validation import ResourceValidationResult, ValidateResourceTagsResult
from ..models.violations import Violation
from ..clients.aws_client import AWSClient
from ..services.policy_service import PolicyService

logger = logging.getLogger(__name__)


async def validate_resource_tags(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_arns: list[str],
) -> ValidateResourceTagsResult:
    """
    Validate specific resources against the tagging policy.
    
    This tool validates one or more resources by their ARNs against the
    organization's tagging policy. It returns detailed violation information
    including missing tags, invalid values, and format violations.
    
    Args:
        aws_client: AWSClient instance for fetching resource details
        policy_service: PolicyService for policy validation
        resource_arns: List of AWS resource ARNs to validate
                      (e.g., ["arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"])
    
    Returns:
        ValidateResourceTagsResult containing:
        - total_resources: Total number of resources validated
        - compliant_resources: Number of compliant resources
        - non_compliant_resources: Number of non-compliant resources
        - results: List of ResourceValidationResult for each resource
        - validation_timestamp: When the validation was performed
    
    Raises:
        ValueError: If resource_arns is empty or contains invalid ARNs
    
    Requirements: 3.1, 3.2, 3.3, 3.4
    
    Example:
        >>> result = await validate_resource_tags(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_arns=[
        ...         "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
        ...         "arn:aws:s3:::my-bucket"
        ...     ]
        ... )
        >>> for r in result.results:
        ...     status = "compliant" if r.is_compliant else "non-compliant"
        ...     print(f"{r.resource_id}: {status}")
    """
    # Validate inputs
    if not resource_arns:
        raise ValueError("resource_arns cannot be empty")
    
    # Validate ARN format
    invalid_arns = [arn for arn in resource_arns if not _is_valid_arn(arn)]
    if invalid_arns:
        raise ValueError(
            f"Invalid ARN format: {invalid_arns}. "
            f"ARNs must follow the format: arn:aws:service:region:account:resource"
        )
    
    logger.info(f"Validating {len(resource_arns)} resources against tagging policy")
    
    results: list[ResourceValidationResult] = []
    compliant_count = 0
    
    for arn in resource_arns:
        try:
            # Parse the ARN to extract resource details
            parsed = _parse_arn(arn)
            resource_type = parsed["resource_type"]
            resource_id = parsed["resource_id"]
            region = parsed["region"]
            
            # Fetch the resource's current tags
            tags = await _fetch_resource_tags(aws_client, arn, resource_type, resource_id)
            
            # Validate against policy
            violations = policy_service.validate_resource_tags(
                resource_id=resource_id,
                resource_type=resource_type,
                region=region,
                tags=tags,
                cost_impact=0.0,  # Cost impact not calculated for individual validation
            )
            
            is_compliant = len(violations) == 0
            if is_compliant:
                compliant_count += 1
            
            result = ResourceValidationResult(
                resource_arn=arn,
                resource_id=resource_id,
                resource_type=resource_type,
                region=region,
                is_compliant=is_compliant,
                violations=violations,
                current_tags=tags,
            )
            results.append(result)
            
            logger.debug(
                f"Validated {resource_id}: {'compliant' if is_compliant else 'non-compliant'} "
                f"({len(violations)} violations)"
            )
        
        except Exception as e:
            logger.error(f"Failed to validate resource {arn}: {str(e)}")
            # Create a result with error information
            parsed = _parse_arn(arn) if _is_valid_arn(arn) else {
                "resource_type": "unknown",
                "resource_id": arn,
                "region": "unknown"
            }
            
            result = ResourceValidationResult(
                resource_arn=arn,
                resource_id=parsed["resource_id"],
                resource_type=parsed["resource_type"],
                region=parsed["region"],
                is_compliant=False,
                violations=[],
                current_tags={},
            )
            results.append(result)
    
    non_compliant_count = len(results) - compliant_count
    
    logger.info(
        f"Validation complete: {compliant_count} compliant, "
        f"{non_compliant_count} non-compliant out of {len(results)} resources"
    )
    
    return ValidateResourceTagsResult(
        total_resources=len(results),
        compliant_resources=compliant_count,
        non_compliant_resources=non_compliant_count,
        results=results,
        validation_timestamp=datetime.now(UTC),
    )


def _is_valid_arn(arn: str) -> bool:
    """
    Check if a string is a valid AWS ARN format.
    
    Args:
        arn: String to validate
    
    Returns:
        True if valid ARN format, False otherwise
    """
    # ARN format: arn:partition:service:region:account:resource
    # Some variations:
    # - arn:aws:s3:::bucket-name (S3 buckets have no region/account)
    # - arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0
    
    if not arn or not isinstance(arn, str):
        return False
    
    # Basic ARN pattern - supports S3 buckets with empty account field
    arn_pattern = r'^arn:aws[a-z-]*:[a-z0-9-]+:[a-z0-9-]*:[0-9]*:.+'
    return bool(re.match(arn_pattern, arn))


def _parse_arn(arn: str) -> dict[str, str]:
    """
    Parse an AWS ARN into its components.
    
    Args:
        arn: AWS ARN string
    
    Returns:
        Dictionary with parsed ARN components
    """
    # ARN format: arn:partition:service:region:account:resource
    parts = arn.split(":")
    
    if len(parts) < 6:
        raise ValueError(f"Invalid ARN format: {arn}")
    
    service = parts[2]
    region = parts[3] or "global"  # S3 buckets have empty region
    account = parts[4]
    resource = ":".join(parts[5:])  # Resource may contain colons
    
    # Map AWS service to resource type
    resource_type = _service_to_resource_type(service, resource)
    
    # Extract resource ID from resource part
    resource_id = _extract_resource_id(resource)
    
    return {
        "service": service,
        "region": region,
        "account": account,
        "resource": resource,
        "resource_type": resource_type,
        "resource_id": resource_id,
    }


def _service_to_resource_type(service: str, resource: str) -> str:
    """
    Map AWS service and resource to our resource type format.
    
    Args:
        service: AWS service name (e.g., "ec2", "s3")
        resource: Resource part of ARN
    
    Returns:
        Resource type string (e.g., "ec2:instance", "s3:bucket")
    """
    # Handle specific resource types based on service and resource pattern
    if service == "ec2":
        if resource.startswith("instance/"):
            return "ec2:instance"
        # Could add more EC2 resource types here
        return "ec2:instance"  # Default for EC2
    
    elif service == "rds":
        if resource.startswith("db:"):
            return "rds:db"
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
        return "ecs:service"  # Default for ECS
    
    # Unknown service - return as-is
    return f"{service}:unknown"


def _extract_resource_id(resource: str) -> str:
    """
    Extract the resource ID from the resource part of an ARN.
    
    Args:
        resource: Resource part of ARN (e.g., "instance/i-1234567890abcdef0")
    
    Returns:
        Resource ID string
    """
    # Handle different resource formats
    if "/" in resource:
        # Format: type/id or type/subtype/id
        parts = resource.split("/")
        return parts[-1]
    
    elif ":" in resource:
        # Format: type:id
        parts = resource.split(":")
        return parts[-1]
    
    # Just the resource ID
    return resource


async def _fetch_resource_tags(
    aws_client: AWSClient,
    arn: str,
    resource_type: str,
    resource_id: str,
) -> dict[str, str]:
    """
    Fetch tags for a specific resource.
    
    Args:
        aws_client: AWSClient instance
        arn: Full ARN of the resource
        resource_type: Type of resource (e.g., "ec2:instance")
        resource_id: Resource identifier
    
    Returns:
        Dictionary of tag key-value pairs
    """
    try:
        if resource_type == "ec2:instance":
            # Fetch EC2 instance tags
            resources = await aws_client.get_ec2_instances({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    return resource.get("tags", {})
        
        elif resource_type == "rds:db":
            # Fetch RDS instance tags
            resources = await aws_client.get_rds_instances({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    return resource.get("tags", {})
        
        elif resource_type == "s3:bucket":
            # Fetch S3 bucket tags
            resources = await aws_client.get_s3_buckets({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    return resource.get("tags", {})
        
        elif resource_type == "lambda:function":
            # Fetch Lambda function tags
            resources = await aws_client.get_lambda_functions({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    return resource.get("tags", {})
        
        elif resource_type == "ecs:service":
            # Fetch ECS service tags
            resources = await aws_client.get_ecs_services({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    return resource.get("tags", {})
        
        # Resource not found or unsupported type
        logger.warning(f"Could not fetch tags for resource {resource_id} of type {resource_type}")
        return {}
    
    except Exception as e:
        logger.error(f"Error fetching tags for {arn}: {str(e)}")
        return {}
