"""MCP tool for suggesting tags for AWS resources."""

import logging
import re
from typing import Optional

from ..models.suggestions import TagSuggestion
from ..clients.aws_client import AWSClient
from ..services.policy_service import PolicyService
from ..services.suggestion_service import SuggestionService

logger = logging.getLogger(__name__)


class SuggestTagsResult:
    """Result from the suggest_tags tool."""
    
    def __init__(
        self,
        resource_arn: str,
        resource_type: str,
        suggestions: list[TagSuggestion],
        current_tags: dict[str, str],
    ):
        self.resource_arn = resource_arn
        self.resource_type = resource_type
        self.suggestions = suggestions
        self.current_tags = current_tags
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "resource_arn": self.resource_arn,
            "resource_type": self.resource_type,
            "suggestions": [
                {
                    "tag_key": s.tag_key,
                    "suggested_value": s.suggested_value,
                    "confidence": s.confidence,
                    "reasoning": s.reasoning,
                }
                for s in self.suggestions
            ],
            "current_tags": self.current_tags,
            "suggestion_count": len(self.suggestions),
        }


async def suggest_tags(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_arn: str,
) -> SuggestTagsResult:
    """
    Suggest appropriate tags for an AWS resource.
    
    This tool analyzes a resource's metadata, naming patterns, VPC context,
    IAM role associations, and similar resources to suggest appropriate tag
    values. Each suggestion includes a confidence score and reasoning.
    
    Args:
        aws_client: AWSClient instance for fetching resource details
        policy_service: PolicyService for policy configuration
        resource_arn: AWS ARN of the resource to suggest tags for
                     (e.g., "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0")
    
    Returns:
        SuggestTagsResult containing:
        - resource_arn: The ARN of the resource
        - resource_type: Type of the resource
        - suggestions: List of TagSuggestion objects with confidence and reasoning
        - current_tags: Current tags on the resource
        - suggestion_count: Number of suggestions generated
    
    Raises:
        ValueError: If resource_arn is empty or invalid
    
    Requirements: 5.1, 5.2, 5.3
    
    Example:
        >>> result = await suggest_tags(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
        ... )
        >>> for suggestion in result.suggestions:
        ...     print(f"{suggestion.tag_key}: {suggestion.suggested_value} "
        ...           f"(confidence: {suggestion.confidence})")
        ...     print(f"  Reasoning: {suggestion.reasoning}")
    """
    # Validate inputs
    if not resource_arn:
        raise ValueError("resource_arn cannot be empty")
    
    if not _is_valid_arn(resource_arn):
        raise ValueError(
            f"Invalid ARN format: {resource_arn}. "
            f"ARNs must follow the format: arn:aws:service:region:account:resource"
        )
    
    logger.info(f"Generating tag suggestions for resource: {resource_arn}")
    
    # Parse the ARN to extract resource details
    parsed = _parse_arn(resource_arn)
    resource_type = parsed["resource_type"]
    resource_id = parsed["resource_id"]
    region = parsed["region"]
    
    # Fetch the resource's current tags and metadata
    resource_data = await _fetch_resource_data(
        aws_client, resource_arn, resource_type, resource_id
    )
    
    current_tags = resource_data.get("tags", {})
    resource_name = resource_data.get("name", resource_id)
    vpc_name = resource_data.get("vpc_name")
    iam_role = resource_data.get("iam_role")
    
    # Fetch similar resources for pattern analysis
    similar_resources = await _fetch_similar_resources(
        aws_client, resource_type, region, resource_id
    )
    
    # Initialize suggestion service and generate suggestions
    suggestion_service = SuggestionService(policy_service)
    
    suggestions = await suggestion_service.suggest_tags(
        resource_arn=resource_arn,
        resource_type=resource_type,
        resource_name=resource_name,
        current_tags=current_tags,
        vpc_name=vpc_name,
        iam_role=iam_role,
        similar_resources=similar_resources,
    )
    
    logger.info(
        f"Generated {len(suggestions)} tag suggestions for {resource_id}"
    )
    
    return SuggestTagsResult(
        resource_arn=resource_arn,
        resource_type=resource_type,
        suggestions=suggestions,
        current_tags=current_tags,
    )


def _is_valid_arn(arn: str) -> bool:
    """
    Check if a string is a valid AWS ARN format.
    
    Args:
        arn: String to validate
    
    Returns:
        True if valid ARN format, False otherwise
    """
    if not arn or not isinstance(arn, str):
        return False
    
    # Basic ARN pattern
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
    parts = arn.split(":")
    
    if len(parts) < 6:
        raise ValueError(f"Invalid ARN format: {arn}")
    
    service = parts[2]
    region = parts[3] or "global"
    account = parts[4]
    resource = ":".join(parts[5:])
    
    resource_type = _service_to_resource_type(service, resource)
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
    if service == "ec2":
        if resource.startswith("instance/"):
            return "ec2:instance"
        return "ec2:instance"
    
    elif service == "rds":
        if resource.startswith("db:"):
            return "rds:db"
        return "rds:db"
    
    elif service == "s3":
        return "s3:bucket"
    
    elif service == "lambda":
        if resource.startswith("function:"):
            return "lambda:function"
        return "lambda:function"
    
    elif service == "ecs":
        if "service/" in resource:
            return "ecs:service"
        return "ecs:service"
    
    return f"{service}:unknown"


def _extract_resource_id(resource: str) -> str:
    """
    Extract the resource ID from the resource part of an ARN.
    
    Args:
        resource: Resource part of ARN
    
    Returns:
        Resource ID string
    """
    if "/" in resource:
        parts = resource.split("/")
        return parts[-1]
    
    elif ":" in resource:
        parts = resource.split(":")
        return parts[-1]
    
    return resource


async def _fetch_resource_data(
    aws_client: AWSClient,
    arn: str,
    resource_type: str,
    resource_id: str,
) -> dict:
    """
    Fetch detailed data for a specific resource.
    
    Args:
        aws_client: AWSClient instance
        arn: Full ARN of the resource
        resource_type: Type of resource
        resource_id: Resource identifier
    
    Returns:
        Dictionary with resource data including tags, name, vpc_name, iam_role
    """
    result = {
        "tags": {},
        "name": resource_id,
        "vpc_name": None,
        "iam_role": None,
    }
    
    try:
        if resource_type == "ec2:instance":
            resources = await aws_client.get_ec2_instances({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    result["tags"] = resource.get("tags", {})
                    result["name"] = resource.get("tags", {}).get("Name", resource_id)
                    # VPC and IAM role would need additional API calls
                    # For now, extract from tags if available
                    result["vpc_name"] = resource.get("tags", {}).get("VPC")
                    break
        
        elif resource_type == "rds:db":
            resources = await aws_client.get_rds_instances({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    result["tags"] = resource.get("tags", {})
                    result["name"] = resource_id
                    break
        
        elif resource_type == "s3:bucket":
            resources = await aws_client.get_s3_buckets({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    result["tags"] = resource.get("tags", {})
                    result["name"] = resource_id
                    break
        
        elif resource_type == "lambda:function":
            resources = await aws_client.get_lambda_functions({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    result["tags"] = resource.get("tags", {})
                    result["name"] = resource_id
                    break
        
        elif resource_type == "ecs:service":
            resources = await aws_client.get_ecs_services({})
            for resource in resources:
                if resource["resource_id"] == resource_id:
                    result["tags"] = resource.get("tags", {})
                    result["name"] = resource_id
                    break
    
    except Exception as e:
        logger.warning(f"Error fetching resource data for {arn}: {str(e)}")
    
    return result


async def _fetch_similar_resources(
    aws_client: AWSClient,
    resource_type: str,
    region: str,
    exclude_resource_id: str,
) -> list[dict]:
    """
    Fetch similar resources for pattern analysis.
    
    Args:
        aws_client: AWSClient instance
        resource_type: Type of resource to find similar ones
        region: Region to search in
        exclude_resource_id: Resource ID to exclude from results
    
    Returns:
        List of similar resources with their tags
    """
    similar = []
    
    try:
        if resource_type == "ec2:instance":
            resources = await aws_client.get_ec2_instances({})
        elif resource_type == "rds:db":
            resources = await aws_client.get_rds_instances({})
        elif resource_type == "s3:bucket":
            resources = await aws_client.get_s3_buckets({})
        elif resource_type == "lambda:function":
            resources = await aws_client.get_lambda_functions({})
        elif resource_type == "ecs:service":
            resources = await aws_client.get_ecs_services({})
        else:
            return []
        
        # Filter to same type and exclude the target resource
        for resource in resources:
            if resource["resource_id"] != exclude_resource_id:
                # Only include resources that have tags
                if resource.get("tags"):
                    similar.append({
                        "resource_id": resource["resource_id"],
                        "tags": resource.get("tags", {}),
                    })
        
        # Limit to 10 similar resources
        return similar[:10]
    
    except Exception as e:
        logger.warning(f"Error fetching similar resources: {str(e)}")
        return []
