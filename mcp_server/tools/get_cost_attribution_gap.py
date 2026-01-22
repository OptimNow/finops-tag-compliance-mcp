# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""MCP tool for calculating cost attribution gap."""

import logging
from datetime import datetime, timedelta

from ..clients.aws_client import AWSClient
from ..models.cost_attribution import CostAttributionGapResult, CostBreakdown
from ..services.cost_service import CostService
from ..services.policy_service import PolicyService

logger = logging.getLogger(__name__)


async def get_cost_attribution_gap(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_types: list[str],
    time_period: dict[str, str] | None = None,
    group_by: str | None = None,
    filters: dict | None = None,
    cost_service: CostService | None = None,
) -> CostAttributionGapResult:
    """
    Calculate the cost attribution gap - the financial impact of tagging gaps.

    This tool analyzes cloud spend and determines how much cannot be allocated
    to teams/projects due to missing or invalid resource tags. This is critical
    for FinOps teams to quantify the business impact of poor tagging practices.

    Args:
        aws_client: AWSClient instance for fetching resources and cost data
        policy_service: PolicyService for tag validation
        resource_types: List of resource types to analyze (e.g., ["ec2:instance", "rds:db"])
                       Supported types: ec2:instance, rds:db, s3:bucket,
                       lambda:function, ecs:service
        time_period: Optional time period for cost analysis.
                    Format: {"Start": "YYYY-MM-DD", "End": "YYYY-MM-DD"}
                    Defaults to last 30 days if not specified.
        group_by: Optional grouping dimension for breakdown analysis.
                 Valid values: "resource_type", "region", "account"
                 When specified, returns gap breakdown by that dimension.
        filters: Optional filters for region or account_id
        cost_service: Optional injected CostService instance. If not provided, one will
                     be created internally using aws_client and policy_service.

    Returns:
        CostAttributionGapResult containing:
        - total_spend: Total cloud spend for the period
        - attributable_spend: Spend from properly tagged resources
        - attribution_gap: Dollar amount that cannot be attributed
        - attribution_gap_percentage: Gap as percentage of total
        - breakdown: Optional breakdown by grouping dimension
        - scan_timestamp: When the analysis was performed

    Raises:
        ValueError: If resource_types is empty or contains invalid types
        ValueError: If group_by is invalid
        ValueError: If time_period format is invalid

    Requirements: 4.1, 4.2, 4.3, 4.5

    Example:
        >>> result = await get_cost_attribution_gap(
        ...     aws_client=client,
        ...     policy_service=policy,
        ...     resource_types=["ec2:instance", "rds:db"],
        ...     time_period={"Start": "2025-01-01", "End": "2025-01-31"},
        ...     group_by="resource_type"
        ... )
        >>> print(f"Attribution gap: ${result.attribution_gap:.2f}")
        >>> print(f"Gap percentage: {result.attribution_gap_percentage:.1f}%")
    """
    # Validate inputs
    if not resource_types:
        raise ValueError("resource_types cannot be empty")

    # Validate resource types
    # "all" uses Resource Groups Tagging API + total account spend from Cost Explorer
    valid_types = {
        "all",
        "ec2:instance",
        "rds:db",
        "s3:bucket",
        "lambda:function",
        "ecs:service",
        "opensearch:domain",
    }

    invalid_types = [rt for rt in resource_types if rt not in valid_types]
    if invalid_types:
        raise ValueError(
            f"Invalid resource types: {invalid_types}. " f"Valid types are: {sorted(valid_types)}"
        )

    # Validate group_by if specified
    if group_by is not None:
        valid_groupings = {"resource_type", "region", "account"}
        if group_by not in valid_groupings:
            raise ValueError(
                f"Invalid group_by: {group_by}. " f"Valid values are: {sorted(valid_groupings)}"
            )

    # Validate and normalize time_period
    if time_period:
        if "Start" not in time_period or "End" not in time_period:
            raise ValueError(
                "time_period must contain 'Start' and 'End' keys with YYYY-MM-DD format"
            )

        # Validate date format
        try:
            datetime.strptime(time_period["Start"], "%Y-%m-%d")
            datetime.strptime(time_period["End"], "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Invalid date format in time_period: {str(e)}")
    else:
        # Default to last 30 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        time_period = {
            "Start": start_date.strftime("%Y-%m-%d"),
            "End": end_date.strftime("%Y-%m-%d"),
        }

    logger.info(
        f"Calculating cost attribution gap for types={resource_types}, "
        f"period={time_period}, group_by={group_by}"
    )

    # Use injected service or create one
    service = cost_service
    if service is None:
        service = CostService(aws_client=aws_client, policy_service=policy_service)

    result = await service.calculate_attribution_gap(
        resource_types=resource_types, time_period=time_period, group_by=group_by, filters=filters
    )

    # Convert CostAttributionResult to CostAttributionGapResult (Pydantic model)
    breakdown_dict = None
    if result.breakdown:
        breakdown_dict = {
            key: CostBreakdown(
                total=value["total"],
                attributable=value["attributable"],
                gap=value["gap"],
                resources_scanned=value.get("resources_scanned", 0),
                resources_compliant=value.get("resources_compliant", 0),
                resources_non_compliant=value.get("resources_non_compliant", 0),
                note=value.get("note"),
            )
            for key, value in result.breakdown.items()
        }

    return CostAttributionGapResult(
        total_spend=result.total_spend,
        taggable_spend=result.taggable_spend,
        attributable_spend=result.attributable_spend,
        attribution_gap=result.attribution_gap,
        attribution_gap_percentage=result.attribution_gap_percentage,
        time_period=time_period,
        breakdown=breakdown_dict,
        unattributable_services=result.unattributable_services,
        total_resources_scanned=result.total_resources_scanned,
        total_resources_compliant=result.total_resources_compliant,
        total_resources_non_compliant=result.total_resources_non_compliant,
        scan_timestamp=datetime.now(),
    )
