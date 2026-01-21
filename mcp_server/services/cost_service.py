# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Cost attribution service for calculating tagging gaps."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ..clients.aws_client import AWSClient
from ..services.policy_service import PolicyService
from ..utils.resource_type_config import get_unattributable_services
from ..utils.resource_utils import fetch_resources_by_type, extract_account_from_arn, expand_all_to_supported_types

logger = logging.getLogger(__name__)


# UNATTRIBUTABLE_SERVICES is now loaded from config/resource_types.json
# Use get_unattributable_services() to get the current list


class CostAttributionResult:
    """Result of cost attribution analysis."""
    
    def __init__(
        self,
        total_spend: float,
        attributable_spend: float,
        attribution_gap: float,
        attribution_gap_percentage: float,
        breakdown: Optional[dict[str, dict[str, float]]] = None,
        total_resources_scanned: int = 0,
        total_resources_compliant: int = 0,
        total_resources_non_compliant: int = 0,
        unattributable_services: Optional[dict[str, float]] = None,
        taggable_spend: Optional[float] = None
    ):
        """
        Initialize cost attribution result.
        
        Args:
            total_spend: Total cloud spend for the period (ALL services)
            attributable_spend: Spend from resources with proper tags
            attribution_gap: Dollar amount that cannot be attributed (taggable_spend - attributable)
            attribution_gap_percentage: Gap as percentage of taggable spend
            breakdown: Optional breakdown by grouping dimension
            total_resources_scanned: Total number of resources scanned
            total_resources_compliant: Number of resources with proper tags
            total_resources_non_compliant: Number of resources missing required tags
            unattributable_services: Services with costs but no taggable resources (Bedrock API, Tax, etc.)
            taggable_spend: Spend from services that have taggable resources
        """
        self.total_spend = total_spend
        self.attributable_spend = attributable_spend
        self.attribution_gap = attribution_gap
        self.attribution_gap_percentage = attribution_gap_percentage
        self.breakdown = breakdown or {}
        self.total_resources_scanned = total_resources_scanned
        self.total_resources_compliant = total_resources_compliant
        self.total_resources_non_compliant = total_resources_non_compliant
        self.unattributable_services = unattributable_services or {}
        self.taggable_spend = taggable_spend if taggable_spend is not None else total_spend


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
        1. Expand "all" to all supported resource types (if specified)
        2. Fetch all resources of specified types individually
        3. Get cost data from Cost Explorer for the time period
        4. Map costs to resources (per-resource for EC2/RDS, service average for others)
        5. Validate each resource's tags against policy
        6. Calculate total spend vs. attributable spend
        7. If grouping specified, break down gap by dimension
        
        When resource_types includes "all":
        - Expands to scan ALL 30+ supported resource types individually
        - This catches resources with ZERO tags (unlike the Tagging API)
        - Uses total account spend from Cost Explorer for accurate gap calculation
        
        Args:
            resource_types: List of resource types to analyze (e.g., ["ec2:instance"])
                           Use ["all"] to analyze all supported resource types
            time_period: Time period for cost data (e.g., {"Start": "2025-01-01", "End": "2025-01-31"})
            group_by: Optional grouping dimension ("resource_type", "region", "account", "service")
            filters: Optional filters for region, account_id
        
        Returns:
            CostAttributionResult with total spend, attributable spend, and gap
        
        Requirements: 4.1, 4.2, 4.3, 17.3
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
        
        # Expand "all" to all supported resource types
        # This ensures we scan each type individually to catch resources with zero tags
        expanded_resource_types = expand_all_to_supported_types(resource_types)
        use_all_resources = "all" in resource_types
        
        if use_all_resources:
            logger.info(f"Expanded 'all' to {len(expanded_resource_types)} resource types")
        
        # Use the comprehensive calculation that scans all types individually
        return await self._calculate_attribution_gap_comprehensive(
            resource_types=expanded_resource_types,
            time_period=time_period,
            group_by=group_by,
            filters=filters,
            use_total_account_spend=use_all_resources
        )
    
    async def _calculate_attribution_gap_comprehensive(
        self,
        resource_types: list[str],
        time_period: dict[str, str],
        group_by: Optional[str] = None,
        filters: Optional[dict] = None,
        use_total_account_spend: bool = False
    ) -> CostAttributionResult:
        """
        Calculate cost attribution gap by scanning each resource type individually.
        
        This method scans each resource type via its individual API, which catches
        resources with ZERO tags (unlike the Tagging API which only returns tagged resources).
        
        Args:
            resource_types: List of specific resource types to analyze
            time_period: Time period for cost data
            group_by: Optional grouping dimension
            filters: Optional filters
            use_total_account_spend: If True, use total account spend for gap calculation
        
        Returns:
            CostAttributionResult with spend and gap
        """
        logger.info(f"Scanning {len(resource_types)} resource types individually")
        
        # Fetch all resources grouped by type
        resources_by_type: dict[str, list[dict]] = {}
        all_resources = []
        
        for resource_type in resource_types:
            try:
                resources = await self._fetch_resources_by_type(resource_type, filters)
                resources_by_type[resource_type] = resources
                all_resources.extend(resources)
                if resources:
                    logger.info(f"Fetched {len(resources)} resources of type {resource_type}")
            except Exception as e:
                logger.warning(f"Failed to fetch resources of type {resource_type}: {str(e)}")
                resources_by_type[resource_type] = []
                continue
        
        logger.info(f"Total resources fetched: {len(all_resources)}")
        
        # Get cost data
        if use_total_account_spend:
            # Use total account spend for "all" - captures ALL services
            total_spend, service_breakdown = await self.aws_client.get_total_account_spend(
                time_period=time_period
            )
            logger.info(f"Total account spend: ${total_spend:.2f} across {len(service_breakdown)} services")
            service_costs = service_breakdown
        else:
            # Get service-level costs only for specified types
            _, service_costs, _, _ = await self.aws_client.get_cost_data_by_resource(
                time_period=time_period
            )
            # Calculate total spend only for tracked services
            total_spend = 0.0
            for resource_type in resource_types:
                service_name = self.aws_client.get_service_name_for_resource_type(resource_type)
                total_spend += service_costs.get(service_name, 0.0)
            logger.info(f"Total spend for tracked services: ${total_spend:.2f}")
        
        # Get per-resource costs where available (by Name tag)
        resource_costs, _, costs_by_name, cost_source = await self.aws_client.get_cost_data_by_resource(
            time_period=time_period
        )
        
        logger.info(f"Cost source: {cost_source}, costs by name: {len(costs_by_name)}")
        
        # Build a case-insensitive lookup for costs_by_name
        # Also aggregate costs for similar names (e.g., "Agent Smith" and "agent-smith")
        costs_by_name_lower: dict[str, float] = {}
        for name, cost in costs_by_name.items():
            # Normalize: lowercase and replace spaces with hyphens
            normalized = name.lower().replace(" ", "-")
            costs_by_name_lower[normalized] = costs_by_name_lower.get(normalized, 0) + cost
        
        logger.info(f"Normalized costs by name: {costs_by_name_lower}")
        
        # Build resource cost map - distribute service costs among resources
        resource_cost_map: dict[str, float] = {}
        
        for resource_type, resources in resources_by_type.items():
            service_name = self.aws_client.get_service_name_for_resource_type(resource_type)
            service_total = service_costs.get(service_name, 0.0)
            
            if resource_type in ["ec2:instance", "rds:db"]:
                # STEP 1: Try to assign actual costs from Cost Explorer by Name tag
                resources_with_costs = []
                resources_without_costs = []
                
                for resource in resources:
                    rid = resource["resource_id"]
                    name_tag = resource.get("tags", {}).get("Name", "")
                    
                    # Check if we have cost data for this resource by Name tag
                    # Use case-insensitive matching with normalized names
                    normalized_name = name_tag.lower().replace(" ", "-") if name_tag else ""
                    
                    if normalized_name and normalized_name in costs_by_name_lower:
                        resource_cost_map[rid] = costs_by_name_lower[normalized_name]
                        resources_with_costs.append(resource)
                        logger.info(f"Assigned ${costs_by_name_lower[normalized_name]:.2f} to {rid} via Name tag '{name_tag}'")
                    else:
                        resources_without_costs.append(resource)

                # STEP 2: Handle resources without Cost Explorer data
                if resources_without_costs:
                    known_costs = sum(
                        resource_cost_map.get(r["resource_id"], 0)
                        for r in resources
                    )
                    remaining = max(0, service_total - known_costs)

                    if resource_type == "ec2:instance":
                        # State-aware cost distribution for EC2
                        stopped_instances = [
                            r for r in resources_without_costs
                            if r.get("instance_state") in [
                                "stopped", "stopping", "terminated", "shutting-down"
                            ]
                        ]
                        running_instances = [
                            r for r in resources_without_costs
                            if r.get("instance_state") not in [
                                "stopped", "stopping", "terminated", "shutting-down"
                            ]
                        ]

                        # Assign $0 to stopped instances (compute only)
                        for resource in stopped_instances:
                            resource_cost_map[resource["resource_id"]] = 0.0

                        # Distribute remaining cost among running instances only
                        if running_instances:
                            per_running = remaining / len(running_instances)
                            for resource in running_instances:
                                resource_cost_map[resource["resource_id"]] = per_running
                        elif remaining > 0:
                            # Edge case: No running instances but service has costs
                            # This suggests Cost Explorer data is incomplete
                            # Distribute proportionally as fallback
                            logger.warning(
                                f"EC2 service has ${remaining:.2f} costs but no running instances found. "
                                "This may indicate incomplete Cost Explorer data or other EC2 costs (NAT, EBS, etc.)."
                            )
                            per_resource = remaining / len(resources_without_costs)
                            for resource in resources_without_costs:
                                resource_cost_map[resource["resource_id"]] = per_resource
                    else:
                        # RDS: keep equal distribution (no state awareness for RDS yet)
                        per_resource = remaining / len(resources_without_costs)
                        for resource in resources_without_costs:
                            resource_cost_map[resource["resource_id"]] = per_resource
            else:
                # Distribute service total evenly among resources
                if resources and service_total > 0:
                    per_resource = service_total / len(resources)
                    for resource in resources:
                        resource_cost_map[resource["resource_id"]] = per_resource
        
        # Validate resources and calculate attributable spend
        attributable_spend = 0.0
        total_resources_scanned = len(all_resources)
        total_resources_compliant = 0
        total_resources_non_compliant = 0
        
        # Track breakdown by grouping dimension
        breakdown: dict[str, dict] = {}
        
        # Always track by resource_type for notes generation
        type_breakdown: dict[str, dict] = {}
        for resource_type in resource_types:
            type_breakdown[resource_type] = {
                "total": 0.0,
                "attributable": 0.0,
                "gap": 0.0,
                "resources_scanned": 0,
                "resources_compliant": 0,
                "resources_non_compliant": 0
            }
        
        for resource in all_resources:
            # Validate resource tags against policy
            violations = self.policy_service.validate_resource_tags(
                resource_id=resource["resource_id"],
                resource_type=resource["resource_type"],
                region=resource["region"],
                tags=resource["tags"],
                cost_impact=0.0
            )
            
            resource_cost = resource_cost_map.get(resource["resource_id"], 0.0)
            is_attributable = len(violations) == 0
            
            if is_attributable:
                attributable_spend += resource_cost
                total_resources_compliant += 1
            else:
                total_resources_non_compliant += 1
            
            # Track by resource type
            rt = resource["resource_type"]
            if rt in type_breakdown:
                type_breakdown[rt]["total"] += resource_cost
                type_breakdown[rt]["resources_scanned"] += 1
                if is_attributable:
                    type_breakdown[rt]["attributable"] += resource_cost
                    type_breakdown[rt]["resources_compliant"] += 1
                else:
                    type_breakdown[rt]["gap"] += resource_cost
                    type_breakdown[rt]["resources_non_compliant"] += 1
            
            # Track breakdown if grouping specified
            if group_by:
                group_key = self._get_group_key(resource, group_by)
                
                if group_key not in breakdown:
                    breakdown[group_key] = {
                        "total": 0.0,
                        "attributable": 0.0,
                        "gap": 0.0,
                        "resources_scanned": 0,
                        "resources_compliant": 0,
                        "resources_non_compliant": 0
                    }
                
                breakdown[group_key]["total"] += resource_cost
                breakdown[group_key]["resources_scanned"] += 1
                
                if is_attributable:
                    breakdown[group_key]["attributable"] += resource_cost
                    breakdown[group_key]["resources_compliant"] += 1
                else:
                    breakdown[group_key]["gap"] += resource_cost
                    breakdown[group_key]["resources_non_compliant"] += 1
        
        # Add notes to breakdown
        if group_by == "resource_type":
            for rt, data in breakdown.items():
                data["note"] = self._generate_spend_note(data)
        elif group_by:
            for key, data in breakdown.items():
                data["note"] = self._generate_spend_note(data)
        
        # If no group_by specified, use type_breakdown
        if not group_by:
            for rt, data in type_breakdown.items():
                data["note"] = self._generate_spend_note(data)
            breakdown = type_breakdown
        
        # Separate unattributable services (costs with no taggable resources)
        # These should NOT be included in the attribution gap calculation
        unattributable_services_result: dict[str, float] = {}
        unattributable_total = 0.0
        
        if use_total_account_spend:
            # Get unattributable services from config
            unattributable_list = get_unattributable_services()
            for service_name, service_cost in service_costs.items():
                if service_name in unattributable_list and service_cost > 0:
                    unattributable_services_result[service_name] = service_cost
                    unattributable_total += service_cost
                    logger.info(f"Unattributable service: {service_name} = ${service_cost:.2f}")
        
        # Calculate taggable spend (total minus unattributable)
        taggable_spend = total_spend - unattributable_total
        
        # Calculate attribution gap based on TAGGABLE spend only
        # Gap = taggable_spend - attributable_spend
        attribution_gap = taggable_spend - attributable_spend
        attribution_gap_percentage = (attribution_gap / taggable_spend * 100) if taggable_spend > 0 else 0.0
        
        logger.info(f"Total spend: ${total_spend:.2f}, Unattributable: ${unattributable_total:.2f}, Taggable: ${taggable_spend:.2f}")
        logger.info(f"Attribution gap: ${attribution_gap:.2f} ({attribution_gap_percentage:.1f}%) of taggable spend")
        logger.info(f"Resources: {total_resources_scanned} scanned, {total_resources_compliant} compliant, {total_resources_non_compliant} non-compliant")
        
        return CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=attributable_spend,
            attribution_gap=attribution_gap,
            attribution_gap_percentage=attribution_gap_percentage,
            breakdown=breakdown if breakdown else None,
            total_resources_scanned=total_resources_scanned,
            total_resources_compliant=total_resources_compliant,
            total_resources_non_compliant=total_resources_non_compliant,
            unattributable_services=unattributable_services_result if unattributable_services_result else None,
            taggable_spend=taggable_spend
        )
    
    async def _calculate_attribution_gap_all(
        self,
        time_period: dict[str, str],
        group_by: Optional[str] = None,
        filters: Optional[dict] = None
    ) -> CostAttributionResult:
        """
        Calculate cost attribution gap across ALL AWS services.
        
        Uses total account spend from Cost Explorer and Resource Groups Tagging API
        to capture costs from ALL services including Bedrock, CloudWatch, etc.
        
        Args:
            time_period: Time period for cost data
            group_by: Optional grouping dimension
            filters: Optional filters
        
        Returns:
            CostAttributionResult with total account spend and gap
        """
        logger.info("Calculating cost attribution gap for ALL resources")
        
        # Get total account spend across ALL services
        total_spend, service_breakdown = await self.aws_client.get_total_account_spend(
            time_period=time_period
        )
        
        logger.info(f"Total account spend: ${total_spend:.2f} across {len(service_breakdown)} services")
        
        # Get all tagged resources using Resource Groups Tagging API
        all_resources = await self.aws_client.get_all_tagged_resources()
        
        logger.info(f"Found {len(all_resources)} tagged resources via Resource Groups Tagging API")
        
        # Group resources by type for cost distribution
        resources_by_type: dict[str, list[dict]] = {}
        for resource in all_resources:
            rt = resource.get("resource_type", "unknown")
            if rt not in resources_by_type:
                resources_by_type[rt] = []
            resources_by_type[rt].append(resource)
        
        # Get per-resource costs where available (by Name tag)
        resource_costs, service_costs, costs_by_name, cost_source = await self.aws_client.get_cost_data_by_resource(
            time_period=time_period
        )
        
        # Build a case-insensitive lookup for costs_by_name
        costs_by_name_lower: dict[str, float] = {}
        for name, cost in costs_by_name.items():
            normalized = name.lower().replace(" ", "-")
            costs_by_name_lower[normalized] = costs_by_name_lower.get(normalized, 0) + cost
        
        # Build resource cost map - distribute service costs among resources
        resource_cost_map: dict[str, float] = {}
        
        for resource_type, resources in resources_by_type.items():
            service_name = self.aws_client.get_service_name_for_resource_type(resource_type)
            service_total = service_costs.get(service_name, 0.0)
            
            if resource_type in ["ec2:instance", "rds:db"]:
                # STEP 1: Try to assign actual costs from Cost Explorer by Name tag
                resources_with_costs = []
                resources_without_costs = []
                
                for resource in resources:
                    rid = resource["resource_id"]
                    name_tag = resource.get("tags", {}).get("Name", "")
                    normalized_name = name_tag.lower().replace(" ", "-") if name_tag else ""
                    
                    # Check if we have cost data for this resource by Name tag
                    if normalized_name and normalized_name in costs_by_name_lower:
                        resource_cost_map[rid] = costs_by_name_lower[normalized_name]
                        resources_with_costs.append(resource)
                    else:
                        resources_without_costs.append(resource)

                # STEP 2: Handle resources without Cost Explorer data
                if resources_without_costs:
                    known_costs = sum(
                        resource_cost_map.get(r["resource_id"], 0)
                        for r in resources
                    )
                    remaining = max(0, service_total - known_costs)

                    if resource_type == "ec2:instance":
                        # State-aware cost distribution for EC2
                        stopped_instances = [
                            r for r in resources_without_costs
                            if r.get("instance_state") in [
                                "stopped", "stopping", "terminated", "shutting-down"
                            ]
                        ]
                        running_instances = [
                            r for r in resources_without_costs
                            if r.get("instance_state") not in [
                                "stopped", "stopping", "terminated", "shutting-down"
                            ]
                        ]

                        # Assign $0 to stopped instances (compute only)
                        for resource in stopped_instances:
                            resource_cost_map[resource["resource_id"]] = 0.0

                        # Distribute remaining cost among running instances only
                        if running_instances:
                            per_running = remaining / len(running_instances)
                            for resource in running_instances:
                                resource_cost_map[resource["resource_id"]] = per_running
                        elif remaining > 0:
                            # Edge case: No running instances but service has costs
                            # This suggests Cost Explorer data is incomplete
                            # Distribute proportionally as fallback
                            logger.warning(
                                f"EC2 service has ${remaining:.2f} costs but no running instances found. "
                                "This may indicate incomplete Cost Explorer data or other EC2 costs (NAT, EBS, etc.)."
                            )
                            per_resource = remaining / len(resources_without_costs)
                            for resource in resources_without_costs:
                                resource_cost_map[resource["resource_id"]] = per_resource
                    else:
                        # RDS: keep equal distribution (no state awareness for RDS yet)
                        per_resource = remaining / len(resources_without_costs)
                        for resource in resources_without_costs:
                            resource_cost_map[resource["resource_id"]] = per_resource
            else:
                # Distribute service total evenly among resources
                if resources and service_total > 0:
                    per_resource = service_total / len(resources)
                    for resource in resources:
                        resource_cost_map[resource["resource_id"]] = per_resource
        
        # Validate resources and calculate attributable spend
        attributable_spend = 0.0
        total_resources_scanned = len(all_resources)
        total_resources_compliant = 0
        total_resources_non_compliant = 0
        
        # Track breakdown by grouping dimension
        breakdown: dict[str, dict] = {}
        
        for resource in all_resources:
            # Validate resource tags against policy
            violations = self.policy_service.validate_resource_tags(
                resource_id=resource["resource_id"],
                resource_type=resource["resource_type"],
                region=resource["region"],
                tags=resource["tags"],
                cost_impact=0.0
            )
            
            resource_cost = resource_cost_map.get(resource["resource_id"], 0.0)
            is_attributable = len(violations) == 0
            
            if is_attributable:
                attributable_spend += resource_cost
                total_resources_compliant += 1
            else:
                total_resources_non_compliant += 1
            
            # Track breakdown if grouping specified
            if group_by:
                group_key = self._get_group_key(resource, group_by)
                
                if group_key not in breakdown:
                    breakdown[group_key] = {
                        "total": 0.0,
                        "attributable": 0.0,
                        "gap": 0.0,
                        "resources_scanned": 0,
                        "resources_compliant": 0,
                        "resources_non_compliant": 0
                    }
                
                breakdown[group_key]["total"] += resource_cost
                breakdown[group_key]["resources_scanned"] += 1
                
                if is_attributable:
                    breakdown[group_key]["attributable"] += resource_cost
                    breakdown[group_key]["resources_compliant"] += 1
                else:
                    breakdown[group_key]["gap"] += resource_cost
                    breakdown[group_key]["resources_non_compliant"] += 1
        
        # Add notes to breakdown
        for key, data in breakdown.items():
            data["note"] = self._generate_spend_note(data)
        
        # Calculate attribution gap using TOTAL account spend
        # This captures costs from ALL services, not just those with tagged resources
        attribution_gap = total_spend - attributable_spend
        attribution_gap_percentage = (attribution_gap / total_spend * 100) if total_spend > 0 else 0.0
        
        # Add service breakdown note if there's a significant gap
        if attribution_gap > 0 and not breakdown:
            # Create a service-level breakdown showing where unattributed costs come from
            breakdown = {}
            for service_name, service_cost in sorted(service_breakdown.items(), key=lambda x: x[1], reverse=True):
                if service_cost > 0:
                    breakdown[service_name] = {
                        "total": service_cost,
                        "attributable": 0.0,  # Will be calculated below
                        "gap": 0.0,
                        "resources_scanned": 0,
                        "resources_compliant": 0,
                        "resources_non_compliant": 0,
                        "note": None
                    }
            
            # Distribute attributable spend back to services
            for resource in all_resources:
                violations = self.policy_service.validate_resource_tags(
                    resource_id=resource["resource_id"],
                    resource_type=resource["resource_type"],
                    region=resource["region"],
                    tags=resource["tags"],
                    cost_impact=0.0
                )
                
                if len(violations) == 0:
                    resource_cost = resource_cost_map.get(resource["resource_id"], 0.0)
                    service_name = self.aws_client.get_service_name_for_resource_type(resource["resource_type"])
                    if service_name in breakdown:
                        breakdown[service_name]["attributable"] += resource_cost
                        breakdown[service_name]["resources_compliant"] += 1
                    breakdown.get(service_name, {})["resources_scanned"] = breakdown.get(service_name, {}).get("resources_scanned", 0) + 1
            
            # Calculate gaps per service
            for service_name, data in breakdown.items():
                data["gap"] = data["total"] - data["attributable"]
                data["note"] = self._generate_spend_note(data) if data["resources_scanned"] > 0 else "No taggable resources found for this service"
        
        logger.info(f"Attribution gap (all services): ${attribution_gap:.2f} ({attribution_gap_percentage:.1f}%)")
        logger.info(f"Resources: {total_resources_scanned} scanned, {total_resources_compliant} compliant, {total_resources_non_compliant} non-compliant")
        
        return CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=attributable_spend,
            attribution_gap=attribution_gap,
            attribution_gap_percentage=attribution_gap_percentage,
            breakdown=breakdown if breakdown else None,
            total_resources_scanned=total_resources_scanned,
            total_resources_compliant=total_resources_compliant,
            total_resources_non_compliant=total_resources_non_compliant
        )
    
    async def _calculate_attribution_gap_specific(
        self,
        resource_types: list[str],
        time_period: dict[str, str],
        group_by: Optional[str] = None,
        filters: Optional[dict] = None
    ) -> CostAttributionResult:
        """
        Calculate cost attribution gap for specific resource types.
        
        Original implementation that only considers costs from specified services.
        
        Args:
            resource_types: List of specific resource types to analyze
            time_period: Time period for cost data
            group_by: Optional grouping dimension
            filters: Optional filters
        
        Returns:
            CostAttributionResult with spend and gap for specified types only
        """
        
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
        
        # Get cost data with per-resource granularity where available (by Name tag)
        resource_costs, service_costs, costs_by_name, cost_source = await self.aws_client.get_cost_data_by_resource(
            time_period=time_period
        )
        
        logger.info(f"Cost source: {cost_source}, costs by name: {len(costs_by_name)}, service costs: {len(service_costs)}")
        
        # Build a case-insensitive lookup for costs_by_name
        costs_by_name_lower: dict[str, float] = {}
        for name, cost in costs_by_name.items():
            normalized = name.lower().replace(" ", "-")
            costs_by_name_lower[normalized] = costs_by_name_lower.get(normalized, 0) + cost
        
        # Calculate costs for each resource
        # For EC2/RDS: use actual per-resource costs from Cost Explorer (by Name tag)
        # For S3/Lambda/ECS: distribute service total among resources of that type
        resource_cost_map: dict[str, float] = {}
        
        for resource_type, resources in resources_by_type.items():
            service_name = self.aws_client.get_service_name_for_resource_type(resource_type)
            service_total = service_costs.get(service_name, 0.0)
            
            if resource_type in ["ec2:instance", "rds:db"]:
                # Use per-resource costs where available (by Name tag)
                resources_with_costs = []
                resources_without_costs = []
                
                for resource in resources:
                    rid = resource["resource_id"]
                    name_tag = resource.get("tags", {}).get("Name", "")
                    normalized_name = name_tag.lower().replace(" ", "-") if name_tag else ""
                    
                    if normalized_name and normalized_name in costs_by_name_lower:
                        resource_cost_map[rid] = costs_by_name_lower[normalized_name]
                        resources_with_costs.append(resource)
                    else:
                        resources_without_costs.append(resource)
                
                # Fallback: distribute remaining cost among resources without specific costs
                if resources_without_costs:
                    known_costs = sum(resource_cost_map.get(r["resource_id"], 0) for r in resources)
                    remaining = max(0, service_total - known_costs)
                    per_resource = remaining / len(resources_without_costs)
                    for resource in resources_without_costs:
                        resource_cost_map[resource["resource_id"]] = per_resource
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
        
        # Track resource counts
        total_resources_scanned = len(all_resources)
        total_resources_compliant = 0
        total_resources_non_compliant = 0
        
        # Track breakdown by grouping dimension if specified
        breakdown: dict[str, dict[str, float]] = {}
        
        # Always track by resource_type for notes generation
        type_breakdown: dict[str, dict] = {}
        for resource_type in resource_types:
            type_breakdown[resource_type] = {
                "total": 0.0,
                "attributable": 0.0,
                "gap": 0.0,
                "resources_scanned": 0,
                "resources_compliant": 0,
                "resources_non_compliant": 0
            }
        
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
                total_resources_compliant += 1
            else:
                non_attributable_spend += resource_cost
                total_resources_non_compliant += 1
            
            # Track by resource type for notes
            rt = resource["resource_type"]
            type_breakdown[rt]["total"] += resource_cost
            type_breakdown[rt]["resources_scanned"] += 1
            if is_attributable:
                type_breakdown[rt]["attributable"] += resource_cost
                type_breakdown[rt]["resources_compliant"] += 1
            else:
                type_breakdown[rt]["gap"] += resource_cost
                type_breakdown[rt]["resources_non_compliant"] += 1
            
            # Track breakdown if grouping specified
            if group_by:
                group_key = self._get_group_key(resource, group_by)
                
                if group_key not in breakdown:
                    breakdown[group_key] = {
                        "total": 0.0,
                        "attributable": 0.0,
                        "gap": 0.0,
                        "resources_scanned": 0,
                        "resources_compliant": 0,
                        "resources_non_compliant": 0
                    }
                
                breakdown[group_key]["total"] += resource_cost
                breakdown[group_key]["resources_scanned"] += 1
                
                if is_attributable:
                    breakdown[group_key]["attributable"] += resource_cost
                    breakdown[group_key]["resources_compliant"] += 1
                else:
                    breakdown[group_key]["gap"] += resource_cost
                    breakdown[group_key]["resources_non_compliant"] += 1
        
        # Add notes to breakdown for $0 spend cases
        if group_by == "resource_type":
            for rt, data in breakdown.items():
                data["note"] = self._generate_spend_note(data)
        else:
            # If grouping by something else, still use type_breakdown for notes
            for rt, data in type_breakdown.items():
                data["note"] = self._generate_spend_note(data)
        
        # If no group_by specified, use type_breakdown as the breakdown
        if not group_by:
            breakdown = type_breakdown
        
        # Calculate attribution gap
        attribution_gap = total_spend - attributable_spend
        attribution_gap_percentage = (attribution_gap / total_spend * 100) if total_spend > 0 else 0.0
        
        logger.info(f"Attribution gap: ${attribution_gap:.2f} ({attribution_gap_percentage:.1f}%)")
        logger.info(f"Resources: {total_resources_scanned} scanned, {total_resources_compliant} compliant, {total_resources_non_compliant} non-compliant")
        
        return CostAttributionResult(
            total_spend=total_spend,
            attributable_spend=attributable_spend,
            attribution_gap=attribution_gap,
            attribution_gap_percentage=attribution_gap_percentage,
            breakdown=breakdown if breakdown else None,
            total_resources_scanned=total_resources_scanned,
            total_resources_compliant=total_resources_compliant,
            total_resources_non_compliant=total_resources_non_compliant
        )
    
    def _generate_spend_note(self, data: dict) -> Optional[str]:
        """
        Generate a clarification note for $0 spend cases.
        
        Helps distinguish between:
        - No resources found for this type
        - Resources exist but have $0 cost in the period
        - Resources are actually compliant
        
        Args:
            data: Breakdown data with total, resources_scanned, etc.
        
        Returns:
            Clarification note or None if not needed
        """
        total = data.get("total", 0.0)
        resources_scanned = data.get("resources_scanned", 0)
        resources_compliant = data.get("resources_compliant", 0)
        resources_non_compliant = data.get("resources_non_compliant", 0)
        
        if resources_scanned == 0:
            return "No resources found for this type"
        
        if total == 0.0:
            if resources_non_compliant > 0:
                return f"{resources_non_compliant} resource(s) found but $0 cost reported - may need Cost Allocation Tags or resources are in free tier"
            else:
                return f"{resources_scanned} resource(s) found with $0 cost - may be in free tier or newly created"
        
        # If there's spend but 0% gap, clarify it's actually compliant
        if resources_non_compliant == 0 and resources_scanned > 0:
            return f"All {resources_scanned} resource(s) are properly tagged"
        
        return None
    
    def _get_group_key(self, resource: dict, group_by: str) -> str:
        """
        Extract grouping key from resource.
        
        Args:
            resource: Resource dictionary
            group_by: Grouping dimension ("resource_type", "region", "account", "service")
        
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
        elif group_by == "service":
            # Extract service from resource_type (e.g., "ec2:instance" -> "ec2")
            resource_type = resource.get("resource_type", "unknown")
            if ":" in resource_type:
                return resource_type.split(":")[0]
            return resource_type
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
