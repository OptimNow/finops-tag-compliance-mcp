#!/usr/bin/env python3
"""
Debug script for cost attribution gap analysis.
Run this locally to see detailed breakdown of cost calculations.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from mcp_server.clients.aws_client import AWSClient
from mcp_server.services.policy_service import PolicyService
from mcp_server.services.cost_service import CostService


async def debug_cost_attribution():
    """Debug cost attribution calculations."""
    
    print("=" * 80)
    print("COST ATTRIBUTION DEBUG")
    print("=" * 80)
    
    # Initialize services
    aws_client = AWSClient(region="us-east-1")
    policy_service = PolicyService(policy_path="policies/tagging_policy.json")
    cost_service = CostService(aws_client=aws_client, policy_service=policy_service)
    
    # Time period - current month
    end_date = datetime.now()
    # Use first day of current month for cleaner data
    start_date = end_date.replace(day=1)
    time_period = {
        "Start": start_date.strftime("%Y-%m-%d"),
        "End": end_date.strftime("%Y-%m-%d")
    }
    
    print(f"\nTime Period: {time_period['Start']} to {time_period['End']}")
    
    # Step 1: Get EC2 instances and their states
    print("\n" + "=" * 80)
    print("STEP 1: EC2 INSTANCES AND STATES")
    print("=" * 80)
    
    ec2_resources = await aws_client.get_ec2_instances({})
    print(f"\nFound {len(ec2_resources)} EC2 instances:")
    
    for r in ec2_resources:
        state = r.get("instance_state", "MISSING")
        instance_type = r.get("instance_type", "MISSING")
        tags = r.get("tags", {})
        compliant = len(policy_service.validate_resource_tags(
            resource_id=r["resource_id"],
            resource_type=r["resource_type"],
            region=r["region"],
            tags=tags,
            cost_impact=0.0
        )) == 0
        
        print(f"  - {r['resource_id']}: state={state}, type={instance_type}, compliant={compliant}")
        print(f"    Tags: {tags}")
    
    # Step 2: Get Cost Explorer data
    print("\n" + "=" * 80)
    print("STEP 2: COST EXPLORER DATA")
    print("=" * 80)
    
    resource_costs, service_costs, costs_by_name, cost_source = await aws_client.get_cost_data_by_resource(
        time_period=time_period
    )
    
    print(f"\nCost source: {cost_source}")
    print(f"\nService costs:")
    for service, cost in sorted(service_costs.items(), key=lambda x: x[1], reverse=True):
        if cost > 0:
            print(f"  - {service}: ${cost:.2f}")
    
    print(f"\nCosts by Name tag (RAW from Cost Explorer):")
    for name, cost in sorted(costs_by_name.items(), key=lambda x: x[1], reverse=True):
        if cost > 0:
            print(f"  - '{name}': ${cost:.2f}")
    
    # Step 2b: Try raw Cost Explorer call with Name tag to see exact format
    print("\n" + "-" * 40)
    print("RAW COST EXPLORER WITH Name TAG:")
    print("-" * 40)
    
    try:
        raw_response = aws_client.ce.get_cost_and_usage(
            TimePeriod=time_period,
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            Filter={
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": ["Amazon Elastic Compute Cloud - Compute"]
                }
            },
            GroupBy=[
                {"Type": "TAG", "Key": "Name"}
            ]
        )
        
        print(f"\nRaw response groups (exact format from API):")
        for result in raw_response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                keys = group.get("Keys", [])
                amount = float(group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0))
                if amount > 0:
                    print(f"  - Keys: {keys}, Amount: ${amount:.2f}")
    except Exception as e:
        print(f"  Error: {e}")
    
    # Step 2c: Show name matching analysis
    print("\n" + "-" * 40)
    print("NAME MATCHING ANALYSIS:")
    print("-" * 40)
    
    # Build normalized lookup
    costs_by_name_lower = {}
    for name, cost in costs_by_name.items():
        normalized = name.lower().replace(" ", "-")
        costs_by_name_lower[normalized] = costs_by_name_lower.get(normalized, 0) + cost
    
    print(f"\nNormalized costs_by_name_lower:")
    for name, cost in costs_by_name_lower.items():
        print(f"  - '{name}': ${cost:.2f}")
    
    print(f"\nEC2 Instance Name tags vs Cost Explorer names:")
    for r in ec2_resources:
        name_tag = r.get("tags", {}).get("Name", "")
        normalized_name = name_tag.lower().replace(" ", "-") if name_tag else ""
        matched_cost = costs_by_name_lower.get(normalized_name, None)
        
        print(f"  - Instance {r['resource_id']}:")
        print(f"      Name tag: '{name_tag}'")
        print(f"      Normalized: '{normalized_name}'")
        print(f"      Match in costs_by_name_lower: {matched_cost is not None}")
        if matched_cost is not None:
            print(f"      Matched cost: ${matched_cost:.2f}")
        else:
            # Try to find similar names
            similar = [k for k in costs_by_name_lower.keys() if normalized_name in k or k in normalized_name]
            if similar:
                print(f"      Similar names found: {similar}")
    
    # Step 3: Calculate cost distribution
    print("\n" + "=" * 80)
    print("STEP 3: COST DISTRIBUTION LOGIC")
    print("=" * 80)
    
    ec2_service_total = service_costs.get("Amazon Elastic Compute Cloud - Compute", 0.0)
    print(f"\nEC2 Service Total: ${ec2_service_total:.2f}")
    
    # Separate by state
    stopped_instances = [r for r in ec2_resources if r.get("instance_state") in ["stopped", "stopping", "terminated", "shutting-down"]]
    running_instances = [r for r in ec2_resources if r.get("instance_state") not in ["stopped", "stopping", "terminated", "shutting-down"]]
    
    print(f"\nStopped instances ({len(stopped_instances)}):")
    for r in stopped_instances:
        print(f"  - {r['resource_id']}: state={r.get('instance_state')}")
    
    print(f"\nRunning instances ({len(running_instances)}):")
    for r in running_instances:
        print(f"  - {r['resource_id']}: state={r.get('instance_state')}")
    
    # Check which have Cost Explorer data
    instances_with_costs = [r for r in ec2_resources if r["resource_id"] in resource_costs]
    instances_without_costs = [r for r in ec2_resources if r["resource_id"] not in resource_costs]
    
    print(f"\nInstances WITH Cost Explorer data ({len(instances_with_costs)}):")
    for r in instances_with_costs:
        print(f"  - {r['resource_id']}: ${resource_costs[r['resource_id']]:.2f}")
    
    print(f"\nInstances WITHOUT Cost Explorer data ({len(instances_without_costs)}):")
    for r in instances_without_costs:
        print(f"  - {r['resource_id']}: state={r.get('instance_state')}")
    
    # Calculate remaining cost to distribute
    known_costs = sum(resource_costs.get(r["resource_id"], 0) for r in ec2_resources)
    remaining = max(0, ec2_service_total - known_costs)
    
    print(f"\nKnown costs from Cost Explorer: ${known_costs:.2f}")
    print(f"Remaining to distribute: ${remaining:.2f}")
    
    # Step 4: Run full attribution calculation
    print("\n" + "=" * 80)
    print("STEP 4: FULL ATTRIBUTION CALCULATION")
    print("=" * 80)
    
    result = await cost_service.calculate_attribution_gap(
        resource_types=["ec2:instance"],
        time_period=time_period,
        group_by="resource_type"
    )
    
    print(f"\nTotal Spend: ${result.total_spend:.2f}")
    print(f"Attributable Spend: ${result.attributable_spend:.2f}")
    print(f"Attribution Gap: ${result.attribution_gap:.2f} ({result.attribution_gap_percentage:.1f}%)")
    print(f"Resources Scanned: {result.total_resources_scanned}")
    print(f"Resources Compliant: {result.total_resources_compliant}")
    print(f"Resources Non-Compliant: {result.total_resources_non_compliant}")
    
    if result.breakdown:
        print("\nBreakdown:")
        for key, data in result.breakdown.items():
            print(f"  {key}:")
            print(f"    Total: ${data.get('total', 0):.2f}")
            print(f"    Attributable: ${data.get('attributable', 0):.2f}")
            print(f"    Gap: ${data.get('gap', 0):.2f}")
            print(f"    Note: {data.get('note', 'N/A')}")
    
    print("\n" + "=" * 80)
    print("DEBUG COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(debug_cost_attribution())
