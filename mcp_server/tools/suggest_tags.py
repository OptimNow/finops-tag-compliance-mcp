# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for suggesting tags for AWS resources."""

import logging
from typing import Optional

from pydantic import BaseModel, Field

from ..models.suggestions import TagSuggestion
from ..clients.aws_client import AWSClient
from ..services.policy_service import PolicyService
from ..services.suggestion_service import SuggestionService
from ..utils.arn_utils import is_valid_arn, parse_arn

logger = logging.getLogger(__name__)


class SuggestTagsResult(BaseModel):
    """Result from the suggest_tags tool."""

    resource_arn: str = Field(..., description="ARN of the resource")
    resource_type: str = Field(..., description="Type of the resource (e.g., ec2:instance)")
    suggestions: list[TagSuggestion] = Field(
        default_factory=list, description="List of tag suggestions"
    )
    current_tags: dict[str, str] = Field(
        default_factory=dict, description="Current tags on the resource"
    )
    suggestion_count: int = Field(0, description="Number of suggestions generated")

    def model_post_init(self, __context) -> None:
        """Compute suggestion_count after initialization."""
        object.__setattr__(self, "suggestion_count", len(self.suggestions))


async def suggest_tags(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_arn: str,
    suggestion_service: Optional[SuggestionService] = None,
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
        suggestion_service: Optional injected SuggestionService instance. If not provided,
                           one will be created internally using policy_service.

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

    if not is_valid_arn(resource_arn):
        raise ValueError(
            f"Invalid ARN format: {resource_arn}. "
            f"ARNs must follow the format: arn:aws:service:region:account:resource"
        )

    logger.info(f"Generating tag suggestions for resource: {resource_arn}")

    # Parse the ARN to extract resource details
    parsed = parse_arn(resource_arn)
    resource_type = parsed["resource_type"]
    resource_id = parsed["resource_id"]
    region = parsed["region"]

    # Fetch the resource's current tags efficiently using Resource Groups Tagging API
    tags_by_arn = await aws_client.get_tags_for_arns([resource_arn])
    current_tags = tags_by_arn.get(resource_arn, {})

    # Get resource name from tags or use resource_id
    resource_name = current_tags.get("Name", resource_id)

    # Fetch additional metadata (VPC, IAM role) if needed
    resource_data = await _fetch_resource_metadata(
        aws_client, resource_arn, resource_type, resource_id
    )
    vpc_name = resource_data.get("vpc_name")
    iam_role = resource_data.get("iam_role")

    # Fetch similar resources for pattern analysis
    similar_resources = await _fetch_similar_resources(
        aws_client, resource_type, region, resource_id
    )

    # Use injected service or create one
    service = suggestion_service
    if service is None:
        service = SuggestionService(policy_service)

    suggestions = await service.suggest_tags(
        resource_arn=resource_arn,
        resource_type=resource_type,
        resource_name=resource_name,
        current_tags=current_tags,
        vpc_name=vpc_name,
        iam_role=iam_role,
        similar_resources=similar_resources,
    )

    logger.info(f"Generated {len(suggestions)} tag suggestions for {resource_id}")

    return SuggestTagsResult(
        resource_arn=resource_arn,
        resource_type=resource_type,
        suggestions=suggestions,
        current_tags=current_tags,
    )


async def _fetch_resource_metadata(
    aws_client: AWSClient,
    arn: str,
    resource_type: str,
    resource_id: str,
) -> dict:
    """
    Fetch additional metadata (VPC, IAM role) for a resource.

    This only fetches metadata that can't be obtained from tags.
    Tags are fetched separately via get_tags_for_arns for efficiency.

    Args:
        aws_client: AWSClient instance
        arn: Full ARN of the resource
        resource_type: Type of resource
        resource_id: Resource identifier

    Returns:
        Dictionary with vpc_name and iam_role if available
    """
    result = {
        "vpc_name": None,
        "iam_role": None,
    }

    # For now, we don't have efficient ways to get VPC/IAM info
    # without listing all resources. This could be enhanced with
    # specific EC2 describe_instances calls with instance-id filter.
    # Leaving as placeholder for future optimization.

    return result


async def _fetch_similar_resources(
    aws_client: AWSClient,
    resource_type: str,
    region: str,
    exclude_resource_id: str,
) -> list[dict]:
    """
    Fetch similar resources for pattern analysis.

    Uses the Resource Groups Tagging API to efficiently fetch
    resources of the same type for tag pattern analysis.

    Args:
        aws_client: AWSClient instance
        resource_type: Type of resource to find similar ones
        region: Region to search in
        exclude_resource_id: Resource ID to exclude from results

    Returns:
        List of similar resources with their tags (max 10)
    """
    try:
        # Use Resource Groups Tagging API to fetch resources of the same type
        resources = await aws_client.get_all_tagged_resources(
            resource_type_filters=[resource_type]
        )

        similar = []
        for resource in resources:
            if resource["resource_id"] != exclude_resource_id:
                # Only include resources that have tags
                if resource.get("tags"):
                    similar.append({
                        "resource_id": resource["resource_id"],
                        "tags": resource.get("tags", {}),
                    })

            # Limit to 10 similar resources for performance
            if len(similar) >= 10:
                break

        return similar

    except Exception as e:
        logger.warning(f"Error fetching similar resources: {str(e)}")
        return []
