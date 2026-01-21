# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for validating resource tags against policy."""

import logging
from datetime import datetime, UTC

from ..models.validation import ResourceValidationResult, ValidateResourceTagsResult
from ..clients.aws_client import AWSClient
from ..services.policy_service import PolicyService
from ..utils.arn_utils import is_valid_arn, parse_arn

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
    invalid_arns = [arn for arn in resource_arns if not is_valid_arn(arn)]
    if invalid_arns:
        raise ValueError(
            f"Invalid ARN format: {invalid_arns}. "
            f"ARNs must follow the format: arn:aws:service:region:account:resource"
        )

    logger.info(f"Validating {len(resource_arns)} resources against tagging policy")

    # Efficiently fetch tags for all ARNs in batch using Resource Groups Tagging API
    tags_by_arn = await aws_client.get_tags_for_arns(resource_arns)

    results: list[ResourceValidationResult] = []
    compliant_count = 0

    for arn in resource_arns:
        try:
            # Parse the ARN to extract resource details
            parsed = parse_arn(arn)
            resource_type = parsed["resource_type"]
            resource_id = parsed["resource_id"]
            region = parsed["region"]

            # Get tags from batch fetch (empty dict if not found)
            tags = tags_by_arn.get(arn, {})

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
            try:
                parsed = parse_arn(arn)
            except ValueError:
                parsed = {"resource_type": "unknown", "resource_id": arn, "region": "unknown"}

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
