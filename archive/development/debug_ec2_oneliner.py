# Debug script to test EC2 fetching inside Docker container
# Run with: sudo docker exec tagging-mcp-server python -c "exec(__import__('base64').b64decode('BASE64_HERE').decode())"

import asyncio
import boto3
import os

async def debug_ec2():
    print("=== EC2 Debug ===")
    
    # Check environment
    region = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'not-set'))
    print(f"AWS_REGION env: {region}")
    
    # Direct boto3 call
    print("\n--- Direct boto3 EC2 call ---")
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    try:
        response = ec2.describe_instances()
        reservations = response.get('Reservations', [])
        print(f"Reservations count: {len(reservations)}")
        
        instance_count = 0
        for res in reservations:
            instances = res.get('Instances', [])
            instance_count += len(instances)
            for inst in instances:
                print(f"  Instance: {inst.get('InstanceId')} - State: {inst.get('State', {}).get('Name')}")
        
        print(f"Total instances: {instance_count}")
        
    except Exception as e:
        print(f"ERROR: {e}")
    
    # Test via AWSClient
    print("\n--- Via AWSClient ---")
    try:
        from mcp_server.clients.aws_client import AWSClient
        from mcp_server.config import get_settings
        
        settings = get_settings()
        print(f"Settings region: {settings.aws_region}")
        
        client = AWSClient(region=settings.aws_region)
        print(f"AWSClient region: {client.region}")
        
        instances = await client.get_ec2_instances()
        print(f"AWSClient returned {len(instances)} instances")
        for inst in instances:
            print(f"  {inst.get('resource_id')} - {inst.get('instance_state')}")
            
    except Exception as e:
        print(f"AWSClient ERROR: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(debug_ec2())
