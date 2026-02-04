# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for validating resource tags against policy."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..clients.aws_client import AWSClient
from ..models.validation import ResourceValidationResult, ValidateResourceTagsResult
from ..services.policy_service import PolicyService
from ..utils.arn_utils import is_valid_arn, parse_arn

if TYPE_CHECKING:
    from ..services.multi_region_scanner import MultiRegionScanner

logger = logging.getLogger(__name__)


async def _fetch_tags_for_region(
    region: str,
    region_arns: list[str],
    multi_region_scanner: MultiRegionScanner,
) -> tuple[str, dict[str, dict[str, str]]]:
    """
    Fetch tags for ARNs from a single region.

    This is a helper function designed to be run in parallel with asyncio.gather.

    Args:
        region: AWS region code
        region_arns: List of AWS ARNs in this region
        multi_region_scanner: MultiRegionScanner with client_factory for regional clients

    Returns:
        Tuple of (region, tags_dict) for merging results
    """
    try:
        # Get regional client from the scanner's client factory
        regional_client = multi_region_scanner.client_factory.get_client(region)

        # Fetch tags for ARNs in this region
        region_tags = await regional_client.get_tags_for_arns(region_arns)

        logger.debug(f"Fetched tags for {len(region_tags)} resources from region {region}")
        return (region, region_tags)

    except Exception as e:
        logger.error(f"Failed to fetch tags from region {region}: {e}")
        # Return empty dict - partial results are better than none
        return (region, {})


async def _fetch_tags_multi_region(
    resource_arns: list[str],
    multi_region_scanner: MultiRegionScanner,
) -> dict[str, dict[str, str]]:
    """
    Fetch tags for ARNs from multiple regions in parallel.

    Groups ARNs by region and fetches tags from each region using
    the appropriate regional client. Regions are fetched in parallel
    using asyncio.gather for better performance.

    Args:
        resource_arns: List of AWS ARNs to fetch tags for
        multi_region_scanner: MultiRegionScanner with client_factory for regional clients

    Returns:
        Dictionary mapping ARN to tag dictionary
    """
    import asyncio

    # Group ARNs by region
    arns_by_region: dict[str, list[str]] = defaultdict(list)

    for arn in resource_arns:
        try:
            parsed = parse_arn(arn)
            region = parsed["region"]
            # Handle global resources (like S3) - use default region
            if region == "global":
                region = multi_region_scanner.default_region
            arns_by_region[region].append(arn)
        except ValueError:
            # Invalid ARN - will be handled later in validation
            logger.warning(f"Could not parse region from ARN: {arn}")
            continue

    logger.info(f"Fetching tags from {len(arns_by_region)} regions in parallel: {list(arns_by_region.keys())}")

    # Fetch tags from all regions in parallel using asyncio.gather
    fetch_tasks = [
        _fetch_tags_for_region(region, region_arns, multi_region_scanner)
        for region, region_arns in arns_by_region.items()
    ]

    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    # Merge results from all regions
    all_tags: dict[str, dict[str, str]] = {}

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Unexpected error fetching tags: {result}")
            continue
        region, region_tags = result
        all_tags.update(region_tags)

    return all_tags


async def validate_resource_tags(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_arns: list[str],
    multi_region_scanner: MultiRegionScanner | None = None,
) -> ValidateResourceTagsResult:
    """
    Validate specific resources against the tagging policy.

    This tool validates one or more resources by their ARNs against the
    organization's tagging policy. It returns detailed violation information
    including missing tags, invalid values, and format violations.
    
    Multi-Region Support:
        When multi_region_scanner is provided, the tool can validate ARNs from
        any region by automatically routing requests to the appropriate regional
        AWS client. ARNs are grouped by region and tags are fetched from each
        region in parallel.
        
        When multi_region_scanner is None, the tool falls back to single-region
        behavior using the provided aws_client (backward compatible).

    Args:
        aws_client: AWSClient instance for fetching resource details (used when
                   multi_region_scanner is None, or as fallback)
        policy_service: PolicyService for policy validation
        resource_arns: List of AWS resource ARNs to validate
                      (e.g., ["arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"])
        multi_region_scanner: Optional MultiRegionScanner for multi-region support.
                             When provided, ARNs from any region can be validated.
                             When None, only ARNs from the aws_client's region are supported.

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
        >>> # Single-region mode (backward compatible)
        >>> result = await validate_resource_tags(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_arns=[
        ...         "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
        ...         "arn:aws:s3:::my-bucket"
        ...     ]
        ... )
        
        >>> # Multi-region mode
        >>> result = await validate_resource_tags(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_arns=[
        ...         "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
        ...         "arn:aws:ec2:eu-west-1:123456789012:instance/i-abcdef1234567890"
        ...     ],
        ...     multi_region_scanner=scanner
        ... )
        >>> for r in result.results:
        ...     status = "compliant" if r.is_compliant else "non-compliant"
        ...     print(f"{r.resource_id} ({r.region}): {status}")
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

    # Fetch tags for all ARNs
    # Use multi-region scanner if provided, otherwise fall back to single-region
    if multi_region_scanner is not None:
        logger.info("Using multi-region scanner for tag fetching")
        tags_by_arn = await _fetch_tags_multi_region(resource_arns, multi_region_scanner)
    else:
        # Efficiently fetch tags for all ARNs in batch using Resource Groups Tagging API
        # This is the backward-compatible single-region mode
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
        validation_timestamp=datetime.now(timezone.utc),
    )
