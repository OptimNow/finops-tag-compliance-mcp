# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Cost attribution service for calculating tagging gaps."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ..clients.aws_client import AWSClient
from ..services.policy_service import PolicyService
from ..utils.resource_utils import fetch_resources_by_type, extract_account_from_arn

logger = logging.getLogger(__name__)


class CostAttributionResult:
    """Result of cost attribution analysis."""
    
    def __init__(
        self,
        total_spend: float,
        attributable_spend: float,
        attribution_gap: float,
        attribution_gap_percentage: float,
        breakdown: Optional[dict[str, dict[str, float]]] = None
    ):
        """
        Initialize cost attribution result.
        
        Args:
            total_spend: Total cloud spend for the period
            attributable_spend: Spend from resources with proper tags
            attribution_gap: Dollar amount that cannot be attributed (total - attributable)
            attribution_gap_percentage: Gap as percentage of total spend
            breakdown: Optional breakdown by grouping dimension
        """
        self.total_spend = total_spend
        self.attributable_spend = attributable_spend
        self.attribution_gap = attribution_gap
        self.attribution_gap_percentage = attribution_gap_percentage
        self.breakdown = breakdown or {}


class CostService:
    """
    Service for calculating cost attribution gaps.
    
    Integrates with AWS Cost Explorer to determine how much cloud spend
    cannot be allocated to teams/projects due to missing or invalid tags.
    
    Requirements: 4.1, 4.2, 4.3
    """
    
    def __init__(
        self,
        aws_client: AWSClient,
        policy_service: PolicyService
    ):
        """
        Initialize cost service.
        
        Args:
            aws_client: AWS client for fetching resources and cost data
            policy_service: Policy service for tag validation
        """
        self.aws_client = aws_client
        self.policy_service = policy_service
    
    async def calculate_attribution_gap(
        self,
        resource_types: list[str],
        time_period: Optional[dict[str, str]] = None,
        group_by: Optional[str] = None,
        filters: Optional[dict] = None
    ) -> CostAttributionResult:
        """
        Calculate cost attribution gap for specified resources.
        
        The attribution gap is the dollar amount of cloud spend that cannot
        be allocated to teams/projects because resources lack proper tags.
        
        Process:
        1. Fetch all resources of specified types
        2. Get cost data from Cost Explorer for the time period
        3. Map costs to resources (per-resource for EC2/RDS, service average for others)
        4. Validate each resource's tags against policy
        5. Calculate total spend vs. attributable spend
        6. If grouping specified, break down gap by dimension
        
        Args:
            resource_types: List of resource types to analyze (e.g., ["ec2:instance"])
            time_period: Time period for cost data (e.g., {"Start": "2025-01-01", "End": "2025-01-31"})
            group_by: Optional grouping dimension ("resource_type", "region", "account")
            filters: Optional filters for region, account_id
        
        Returns:
            CostAttributionResult with total spend, attributable spend, and gap
        
        Requirements: 4.1, 4.2, 4.3
        """
        logger.info(f"Calculating cost attribution gap for {resource_types}")
        
        # Default to last 30 days if no time period specified
        if not time_period:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            time_period = {
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d")
            }
        
        # Fetch all resources grouped by type
        resources_by_type: dict[str, list[dict]] = {}
        all_resources = []
        for resource_type in resource_types:
            try:
                resources = await self._fetch_resources_by_type(resource_type, filters)
                resources_by_type[resource_type] = resources
                all_resources.extend(resources)
                logger.info(f"Fetched {len(resources)} resources of type {resource_type}")
            except Exception as e:
                logger.error(f"Failed to fetch resources of type {resource_type}: {str(e)}")
                resources_by_type[resource_type] = []
                continue
        
        logger.info(f"Total resources fetched: {len(all_resources)}")
        
        # Get cost data with per-resource granularity where available
        resource_costs, service_costs, cost_source = await self.aws_client.get_cost_data_by_resource(
            time_period=time_period
        )
        
        logger.info(f"Cost source: {cost_source}, per-resource costs: {len(resource_costs)}, service costs: {len(service_costs)}")
        
        # Calculate costs for each resource
        # For EC2/RDS: use actual per-resource costs from Cost Explorer
        # For S3/Lambda/ECS: distribute service total among resources of that type
        resource_cost_map: dict[str, float] = {}
        
        for resource_type, resources in resources_by_type.items():
            service_name = self.aws_client.get_service_name_for_resource_type(resource_type)
            service_total = service_costs.get(service_name, 0.0)
            
            if resource_type in ["ec2:instance", "rds:db"]:
                # Use per-resource costs where available
                for resource in resources:
                    rid = resource["resource_id"]
                    if rid in resource_costs:
                        resource_cost_map[rid] = resource_costs[rid]
                    elif resources:
                        # Fallback: distribute service total among resources without specific costs
                        resources_without_costs = [r for r in resources if r["resource_id"] not in resource_costs]
                        if resources_without_costs:
                            # Calculate remaining cost after subtracting known per-resource costs
                            known_costs = sum(resource_costs.get(r["resource_id"], 0) for r in resources)
                            remaining = max(0, service_total - known_costs)
                            per_resource = remaining / len(resources_without_costs)
                            if rid not in resource_costs:
                                resource_cost_map[rid] = per_resource
            else:
                # For S3, Lambda, ECS: distribute service total evenly among resources
                if resources:
                    per_resource = service_total / len(resources)
                    for resource in resources:
                        resource_cost_map[resource["resource_id"]] = per_resource
        
        # Calculate total spend ONLY for the services we're tracking
        # This prevents costs from untracked services (OpenSearch, etc.) from inflating the gap
        total_spend = 0.0
        for resource_type in resource_types:
            service_name = self.aws_client.get_service_name_for_resource_type(resource_type)
            total_spend += service_costs.get(service_name, 0.0)
        
        logger.info(f"Total spend for tracked services: ${total_spend:.2f}")
        
        # Validate resources and calculate attributable spend
        attributable_spend = 0.0
        non_attributable_spend = 0.0
        
        # Track breakdown by grouping dimension if specified
        breakdown: dict[str, dict[str, float]] = {}
        
        for resource in all_resources:
            # Validate resource tags against policy
            violations = self.policy_service.validate_resource_tags(
                resource_id=resource["resource_id"],
                resource_type=resource["resource_type"],
                region=resource["region"],
                tags=resource["tags"],
                cost_impact=0.0  # We'll calculate cost separately
            )
            
            # Get the actual cost for this resource
            resource_cost = resource_cost_map.get(resource["resource_id"], 0.0)
            
            # If resource has no violations, it's properly tagged and attributable
            is_attributable = len(violations) == 0
            
            if is_attributable:
                attributable_spend += resource_cost
            else:
                non_attributable_spend += resource_cost
            
            # Track breakdown if grouping specified
            if group_by:
                group_key = self._get_group_key(resource, group_by)
                
                if group_key not in breakdown:
                    breakdown[group_key] = {
                        "total": 0.0,
                        "attributable": 0.0,
                        "gap": 0.0
                    }
                
                breakdown[group_key]["total"] += resource_cost
                
                if is_attributable:
                    breakdown[group_key]["attributable"] += resource_cost
                else:
                    breakdown[group_key]["gap"] += resource_cost
        
        # Calculate attribution gap
        attribution_gap = total_spend - attributable_spend
        attribution_gap_percentage = (attribution_gap / total_spend * 100) if total_spend > 0 else 0.0
        
        logger.info(f"Attribution gap: ${attribution_gap:.2f} ({attribution_gap_percentage:.1f}%)")
        
        return CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=attributable_spend,
            attribution_gap=attribution_gap,
            attribution_gap_percentage=attribution_gap_percentage,
            breakdown=breakdown if group_by else None
        )
    
    def _get_group_key(self, resource: dict, group_by: str) -> str:
        """
        Extract grouping key from resource.
        
        Args:
            resource: Resource dictionary
            group_by: Grouping dimension ("resource_type", "region", "account")
        
        Returns:
            Group key string
        """
        if group_by == "resource_type":
            return resource.get("resource_type", "unknown")
        elif group_by == "region":
            return resource.get("region", "unknown")
        elif group_by == "account":
            # Extract account from ARN
            arn = resource.get("arn", "")
            return extract_account_from_arn(arn)
        else:
            return "unknown"
    
    async def _fetch_resources_by_type(
        self,
        resource_type: str,
        filters: Optional[dict]
    ) -> list[dict]:
        """
        Fetch resources of a specific type from AWS.
        
        Args:
            resource_type: Type of resource (e.g., "ec2:instance", "rds:db")
            filters: Optional filters for the query
        
        Returns:
            List of resource dictionaries with tags
        """
        return await fetch_resources_by_type(self.aws_client, resource_type, filters)
