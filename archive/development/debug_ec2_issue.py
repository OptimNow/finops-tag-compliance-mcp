#!/usr/bin/env python3
"""Debug script to test EC2 instance fetching in the MCP server.

Run this inside the Docker container to debug why EC2 instances aren't being found:
    docker exec -it mcp-server python /app/scripts/debug_ec2_issue.py
"""

import asyncio
import logging
import sys

# Configure logging to see all debug output
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


async def main():
    """Test EC2 instance fetching step by step."""
    print("=" * 60)
    print("EC2 Instance Fetching Debug Script")
    print("=" * 60)
    
    # Step 1: Check boto3 directly
    print("\n[Step 1] Testing boto3 directly...")
    try:
        import boto3
        ec2 = boto3.client("ec2", region_name="us-east-1")
        response = ec2.describe_instances()
        instances = []
        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instances.append({
                    "id": instance.get("InstanceId"),
                    "state": instance.get("State", {}).get("Name"),
                    "tags": {t["Key"]: t["Value"] for t in instance.get("Tags", [])},
                })
        print(f"  ✓ boto3 found {len(instances)} EC2 instances:")
        for inst in instances:
            name = inst["tags"].get("Name", "unnamed")
            print(f"    - {inst['id']} ({name}) - {inst['state']}")
    except Exception as e:
        print(f"  ✗ boto3 error: {e}")
        return
    
    # Step 2: Test AWSClient directly
    print("\n[Step 2] Testing AWSClient.get_ec2_instances()...")
    try:
        from mcp_server.clients.aws_client import AWSClient
        
        client = AWSClient(region="us-east-1")
        print(f"  AWSClient initialized with region: {client.region}")
        
        # Test with no filters
        print("  Testing with filters=None...")
        resources = await client.get_ec2_instances(filters=None)
        print(f"  ✓ Found {len(resources)} EC2 instances with filters=None")
        
        # Test with empty filters
        print("  Testing with filters={}...")
        resources = await client.get_ec2_instances(filters={})
        print(f"  ✓ Found {len(resources)} EC2 instances with filters={{}}")
        
        # Test with region filter matching
        print("  Testing with filters={'region': 'us-east-1'}...")
        resources = await client.get_ec2_instances(filters={"region": "us-east-1"})
        print(f"  ✓ Found {len(resources)} EC2 instances with region filter")
        
        for r in resources:
            print(f"    - {r['resource_id']} ({r['tags'].get('Name', 'unnamed')}) - {r.get('instance_state')}")
            
    except Exception as e:
        print(f"  ✗ AWSClient error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 3: Test fetch_resources_by_type
    print("\n[Step 3] Testing fetch_resources_by_type()...")
    try:
        from mcp_server.utils.resource_utils import fetch_resources_by_type
        from mcp_server.clients.aws_client import AWSClient
        
        client = AWSClient(region="us-east-1")
        resources = await fetch_resources_by_type(client, "ec2:instance", None)
        print(f"  ✓ fetch_resources_by_type found {len(resources)} EC2 instances")
        
    except Exception as e:
        print(f"  ✗ fetch_resources_by_type error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 4: Test ComplianceService
    print("\n[Step 4] Testing ComplianceService._scan_and_validate()...")
    try:
        from mcp_server.clients.aws_client import AWSClient
        from mcp_server.clients.cache import RedisCache
        from mcp_server.services.policy_service import PolicyService
        from mcp_server.services.compliance_service import ComplianceService
        
        # Initialize services
        client = AWSClient(region="us-east-1")
        
        # Try to connect to Redis, fall back to None
        try:
            cache = await RedisCache.create(redis_url="redis://redis:6379/0")
        except Exception:
            print("  (Redis not available, using None)")
            cache = None
        
        policy_service = PolicyService(policy_path="/app/policies/tagging_policy.json")
        
        compliance_service = ComplianceService(
            cache=cache,
            aws_client=client,
            policy_service=policy_service,
        )
        
        # Test scan
        result = await compliance_service._scan_and_validate(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        print(f"  ✓ ComplianceService found {result.total_resources} EC2 instances")
        print(f"    Compliance score: {result.compliance_score:.1%}")
        print(f"    Violations: {len(result.violations)}")
        
    except Exception as e:
        print(f"  ✗ ComplianceService error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 5: Check Redis cache
    print("\n[Step 5] Checking Redis cache for stale data...")
    try:
        from mcp_server.clients.cache import RedisCache
        
        try:
            cache = await RedisCache.create(redis_url="redis://redis:6379/0")
            print("  ✓ Connected to Redis")
            
            # Try to find compliance cache keys
            # Note: This is a simplified check - actual implementation may vary
            print("  Checking for cached compliance results...")
            print("  (If cached results show 0 resources, try force_refresh=True)")
            
            await cache.close()
        except Exception as e:
            print(f"  Redis not available: {e}")
            
    except Exception as e:
        print(f"  ✗ Cache check error: {e}")
    
    # Step 6: Test with force_refresh
    print("\n[Step 6] Testing ComplianceService with force_refresh=True...")
    try:
        from mcp_server.clients.aws_client import AWSClient
        from mcp_server.clients.cache import RedisCache
        from mcp_server.services.policy_service import PolicyService
        from mcp_server.services.compliance_service import ComplianceService
        
        # Initialize services
        client = AWSClient(region="us-east-1")
        
        # Try to connect to Redis, fall back to None
        try:
            cache = await RedisCache.create(redis_url="redis://redis:6379/0")
        except Exception:
            cache = None
        
        policy_service = PolicyService(policy_path="/app/policies/tagging_policy.json")
        
        compliance_service = ComplianceService(
            cache=cache,
            aws_client=client,
            policy_service=policy_service,
        )
        
        # Test with force_refresh
        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            force_refresh=True,  # Bypass cache!
        )
        
        print(f"  ✓ With force_refresh=True: {result.total_resources} EC2 instances")
        print(f"    Compliance score: {result.compliance_score:.1%}")
        print(f"    Violations: {len(result.violations)}")
        
        if cache:
            await cache.close()
        
    except Exception as e:
        print(f"  ✗ force_refresh test error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Debug complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
