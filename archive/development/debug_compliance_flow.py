# Debug script to test full compliance flow inside Docker container
import asyncio

async def debug_compliance():
    print("=== Compliance Flow Debug ===")
    
    # Test the full compliance service
    print("\n--- Testing ComplianceService ---")
    try:
        from mcp_server.config import get_settings
        from mcp_server.clients.aws_client import AWSClient
        from mcp_server.clients.cache import RedisCache
        from mcp_server.services.policy_service import PolicyService
        from mcp_server.services.compliance_service import ComplianceService
        
        settings = get_settings()
        print(f"Settings region: {settings.aws_region}")
        print(f"Redis URL: {settings.redis_url}")
        
        # Create dependencies
        aws_client = AWSClient(region=settings.aws_region)
        print(f"AWSClient created with region: {aws_client.region}")
        
        cache = RedisCache(settings.redis_url)
        await cache.connect()
        print(f"Redis connected: {cache._connected}")
        
        policy_service = PolicyService()
        print("PolicyService created")
        
        compliance_service = ComplianceService(
            cache=cache,
            aws_client=aws_client,
            policy_service=policy_service
        )
        print("ComplianceService created")
        
        # Test with force_refresh to bypass cache
        print("\n--- Calling check_compliance with force_refresh=True ---")
        result = await compliance_service.check_compliance(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            force_refresh=True
        )
        
        print(f"Result:")
        print(f"  compliance_score: {result.compliance_score}")
        print(f"  total_resources: {result.total_resources}")
        print(f"  compliant_resources: {result.compliant_resources}")
        print(f"  violations count: {len(result.violations)}")
        print(f"  cost_attribution_gap: {result.cost_attribution_gap}")
        
        if result.violations:
            print("\nViolations:")
            for v in result.violations[:3]:
                print(f"  - {v.resource_id}: {v.violation_type}")
        
        await cache.disconnect()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(debug_compliance())
