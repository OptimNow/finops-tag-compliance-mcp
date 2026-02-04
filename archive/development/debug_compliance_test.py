#!/usr/bin/env python3
"""Debug script to test ComplianceService directly."""
import asyncio
import sys
import logging
sys.path.insert(0, '/app')

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def main():
    print("=" * 60)
    print("DEBUG: Testing EC2 discovery at each layer")
    print("=" * 60)
    
    # Layer 1: Direct boto3
    print("\n[1] Testing direct boto3...")
    import boto3
    ec2 = boto3.client('ec2', region_name='us-east-1')
    resp = ec2.describe_instances()
    count = sum(len(r.get('Instances', list())) for r in resp.get('Reservations', list()))
    print(f"    boto3 found: {count} EC2 instances")
    
    # Layer 2: AWSClient
    print("\n[2] Testing AWSClient.get_ec2_instances()...")
    from mcp_server.clients.aws_client import AWSClient
    aws = AWSClient(region='us-east-1')
    print(f"    AWSClient region: {aws.region}")
    instances = await aws.get_ec2_instances()
    print(f"    AWSClient found: {len(instances)} instances")
    if instances:
        print(f"    First instance: {instances[0].get('resource_id', 'N/A')}")
        print(f"    First instance resource_type: {instances[0].get('resource_type', 'N/A')}")
    
    # Layer 3: fetch_resources_by_type
    print("\n[3] Testing fetch_resources_by_type()...")
    from mcp_server.utils.resource_utils import fetch_resources_by_type
    resources = await fetch_resources_by_type(aws, 'ec2:instance', None)
    print(f"    fetch_resources_by_type found: {len(resources)} resources")
    
    # Layer 4: Test resource type config
    print("\n[4] Testing resource type config...")
    from mcp_server.utils.resource_type_config import get_resource_type_config
    config = get_resource_type_config()
    print(f"    ec2:instance is_free_resource: {config.is_free_resource('ec2:instance')}")
    print(f"    ec2:instance is_cost_generating: {config.is_cost_generating('ec2:instance')}")
    cost_gen = config.get_cost_generating_resources()
    print(f"    ec2:instance in cost_generating: {'ec2:instance' in cost_gen}")
    
    # Layer 5: ComplianceService._scan_and_validate
    print("\n[5] Testing ComplianceService...")
    from mcp_server.clients.cache import RedisCache
    from mcp_server.services.policy_service import PolicyService
    from mcp_server.services.compliance_service import ComplianceService
    
    print("    Creating RedisCache...")
    try:
        cache = await RedisCache.create()
        print(f"    Redis connected: {await cache.is_connected()}")
    except Exception as e:
        print(f"    Redis failed: {e}")
        cache = None
    
    print("    Creating PolicyService...")
    policy = PolicyService()
    print(f"    Policy loaded: {len(policy.get_policy().required_tags)} required tags")
    
    print("    Creating ComplianceService...")
    svc = ComplianceService(cache=cache, aws_client=aws, policy_service=policy)
    print(f"    ComplianceService.aws_client is None: {svc.aws_client is None}")
    print(f"    ComplianceService.cache is None: {svc.cache is None}")
    print(f"    ComplianceService.aws_client.region: {svc.aws_client.region if svc.aws_client else 'N/A'}")
    
    print("\n    Calling _scan_and_validate directly...")
    result = await svc._scan_and_validate(
        resource_types=list(['ec2:instance']),
        filters=None,
        severity='all'
    )
    print(f"    _scan_and_validate result:")
    print(f"      total_resources: {result.total_resources}")
    print(f"      compliant_resources: {result.compliant_resources}")
    print(f"      violations: {len(result.violations)}")
    
    # Layer 6: Full check_compliance
    print("\n[6] Testing full check_compliance with force_refresh...")
    result2 = await svc.check_compliance(
        resource_types=list(['ec2:instance']),
        filters=None,
        severity='all',
        force_refresh=True
    )
    print(f"    check_compliance result:")
    print(f"      total_resources: {result2.total_resources}")
    print(f"      compliant_resources: {result2.compliant_resources}")
    print(f"      violations: {len(result2.violations)}")
    
    # Layer 7: Test via ServiceContainer (like main.py does)
    print("\n[7] Testing via ServiceContainer (like production)...")
    from mcp_server.container import ServiceContainer
    from mcp_server.config import settings
    
    container = ServiceContainer(settings=settings())
    await container.initialize()
    
    print(f"    Container initialized: {container.initialized}")
    print(f"    Container.aws_client is None: {container.aws_client is None}")
    print(f"    Container.compliance_service is None: {container.compliance_service is None}")
    
    if container.aws_client:
        print(f"    Container.aws_client.region: {container.aws_client.region}")
    
    if container.compliance_service:
        print(f"    Container.compliance_service.aws_client is None: {container.compliance_service.aws_client is None}")
        print(f"    Container.compliance_service.cache is None: {container.compliance_service.cache is None}")
        
        print("\n    Calling container.compliance_service.check_compliance...")
        result3 = await container.compliance_service.check_compliance(
            resource_types=list(['ec2:instance']),
            filters=None,
            severity='all',
            force_refresh=True
        )
        print(f"    Container compliance result:")
        print(f"      total_resources: {result3.total_resources}")
        print(f"      compliant_resources: {result3.compliant_resources}")
        print(f"      violations: {len(result3.violations)}")
    
    await container.shutdown()
    
    print("\n" + "=" * 60)
    print("DEBUG COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
