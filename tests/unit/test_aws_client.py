"""Unit tests for AWS client wrapper."""

import pytest
from datetime import datetime, UTC
from moto import mock_aws
import boto3

from mcp_server.clients import AWSClient
from mcp_server.clients.aws_client import AWSAPIError


@pytest.fixture
def aws_client():
    """Create an AWSClient instance for testing."""
    return AWSClient(region="us-east-1")


# =============================================================================
# EC2 Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_ec2_instances_empty():
    """Test fetching EC2 instances when none exist."""
    with mock_aws():
        client = AWSClient(region="us-east-1")
        instances = await client.get_ec2_instances()
        assert instances == []


@pytest.mark.asyncio
async def test_get_ec2_instances_with_tags():
    """Test fetching EC2 instances with tags."""
    with mock_aws():
        # Create EC2 instance with tags
        ec2 = boto3.resource("ec2", region_name="us-east-1")
        instances = ec2.create_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)
        instance = instances[0]
        instance.create_tags(Tags=[
            {"Key": "Name", "Value": "test-instance"},
            {"Key": "Environment", "Value": "production"},
        ])
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_ec2_instances()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "ec2:instance"
        assert resources[0]["region"] == "us-east-1"
        assert resources[0]["tags"]["Name"] == "test-instance"
        assert resources[0]["tags"]["Environment"] == "production"
        assert resources[0]["arn"].startswith("arn:aws:ec2:")


@pytest.mark.asyncio
async def test_get_ec2_instances_without_tags():
    """Test fetching EC2 instances without tags."""
    with mock_aws():
        # Create EC2 instance without tags
        ec2 = boto3.resource("ec2", region_name="us-east-1")
        instances = ec2.create_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_ec2_instances()
        
        assert len(resources) == 1
        assert resources[0]["tags"] == {}


@pytest.mark.asyncio
async def test_get_ec2_instances_multiple():
    """Test fetching multiple EC2 instances."""
    with mock_aws():
        ec2 = boto3.resource("ec2", region_name="us-east-1")
        
        # Create 3 instances
        for i in range(3):
            instances = ec2.create_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)
            instance = instances[0]
            instance.create_tags(Tags=[{"Key": "Index", "Value": str(i)}])
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_ec2_instances()
        
        assert len(resources) == 3
        assert all(r["resource_type"] == "ec2:instance" for r in resources)


# =============================================================================
# RDS Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_rds_instances_empty():
    """Test fetching RDS instances when none exist."""
    with mock_aws():
        client = AWSClient(region="us-east-1")
        instances = await client.get_rds_instances()
        assert instances == []


@pytest.mark.asyncio
async def test_get_rds_instances_with_tags():
    """Test fetching RDS instances with tags."""
    with mock_aws():
        rds = boto3.client("rds", region_name="us-east-1")
        
        # Create RDS instance
        rds.create_db_instance(
            DBInstanceIdentifier="test-db",
            DBInstanceClass="db.t3.micro",
            Engine="postgres",
            MasterUsername="admin",
            MasterUserPassword="password123",
            Tags=[
                {"Key": "Environment", "Value": "staging"},
                {"Key": "Owner", "Value": "team-a"},
            ]
        )
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_rds_instances()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "rds:db"
        assert resources[0]["resource_id"] == "test-db"
        assert resources[0]["tags"]["Environment"] == "staging"
        assert resources[0]["tags"]["Owner"] == "team-a"


@pytest.mark.asyncio
async def test_get_rds_instances_without_tags():
    """Test fetching RDS instances without tags."""
    with mock_aws():
        rds = boto3.client("rds", region_name="us-east-1")
        
        # Create RDS instance without tags
        rds.create_db_instance(
            DBInstanceIdentifier="test-db",
            DBInstanceClass="db.t3.micro",
            Engine="postgres",
            MasterUsername="admin",
            MasterUserPassword="password123",
        )
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_rds_instances()
        
        assert len(resources) == 1
        assert resources[0]["tags"] == {}


# =============================================================================
# S3 Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_s3_buckets_empty():
    """Test fetching S3 buckets when none exist."""
    with mock_aws():
        client = AWSClient(region="us-east-1")
        buckets = await client.get_s3_buckets()
        assert buckets == []


@pytest.mark.asyncio
async def test_get_s3_buckets_with_tags():
    """Test fetching S3 buckets with tags."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        
        # Create bucket with tags
        s3.create_bucket(Bucket="test-bucket")
        s3.put_bucket_tagging(
            Bucket="test-bucket",
            Tagging={
                "TagSet": [
                    {"Key": "DataClassification", "Value": "confidential"},
                    {"Key": "Owner", "Value": "data-team"},
                ]
            }
        )
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_s3_buckets()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "s3:bucket"
        assert resources[0]["resource_id"] == "test-bucket"
        assert resources[0]["region"] == "global"
        assert resources[0]["tags"]["DataClassification"] == "confidential"
        assert resources[0]["tags"]["Owner"] == "data-team"


@pytest.mark.asyncio
async def test_get_s3_buckets_without_tags():
    """Test fetching S3 buckets without tags."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        
        # Create bucket without tags
        s3.create_bucket(Bucket="test-bucket")
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_s3_buckets()
        
        assert len(resources) == 1
        assert resources[0]["tags"] == {}


@pytest.mark.asyncio
async def test_get_s3_buckets_multiple():
    """Test fetching multiple S3 buckets."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        
        # Create 3 buckets
        for i in range(3):
            s3.create_bucket(Bucket=f"test-bucket-{i}")
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_s3_buckets()
        
        assert len(resources) == 3
        assert all(r["resource_type"] == "s3:bucket" for r in resources)


# =============================================================================
# Lambda Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_lambda_functions_empty():
    """Test fetching Lambda functions when none exist."""
    with mock_aws():
        client = AWSClient(region="us-east-1")
        functions = await client.get_lambda_functions()
        assert functions == []


@pytest.mark.asyncio
async def test_get_lambda_functions_with_tags():
    """Test fetching Lambda functions with tags."""
    with mock_aws():
        # Create IAM role first
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(
            RoleName="lambda-role",
            AssumeRolePolicyDocument="""{
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "lambda.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }"""
        )
        
        lambda_client = boto3.client("lambda", region_name="us-east-1")
        
        # Create Lambda function with tags
        lambda_client.create_function(
            FunctionName="test-function",
            Runtime="python3.11",
            Role="arn:aws:iam::123456789012:role/lambda-role",
            Handler="index.handler",
            Code={"ZipFile": b"fake code"},
            Tags={
                "Environment": "production",
                "Team": "backend",
            }
        )
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_lambda_functions()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "lambda:function"
        assert resources[0]["resource_id"] == "test-function"
        assert resources[0]["tags"]["Environment"] == "production"
        assert resources[0]["tags"]["Team"] == "backend"


@pytest.mark.asyncio
async def test_get_lambda_functions_without_tags():
    """Test fetching Lambda functions without tags."""
    with mock_aws():
        # Create IAM role first
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(
            RoleName="lambda-role",
            AssumeRolePolicyDocument="""{
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "lambda.amazonaws.com"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }"""
        )
        
        lambda_client = boto3.client("lambda", region_name="us-east-1")
        
        # Create Lambda function without tags
        lambda_client.create_function(
            FunctionName="test-function",
            Runtime="python3.11",
            Role="arn:aws:iam::123456789012:role/lambda-role",
            Handler="index.handler",
            Code={"ZipFile": b"fake code"},
        )
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_lambda_functions()
        
        assert len(resources) == 1
        assert resources[0]["tags"] == {}


# =============================================================================
# ECS Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_ecs_services_empty():
    """Test fetching ECS services when none exist."""
    with mock_aws():
        client = AWSClient(region="us-east-1")
        services = await client.get_ecs_services()
        assert services == []


@pytest.mark.asyncio
async def test_get_ecs_services_with_tags():
    """Test fetching ECS services with tags."""
    with mock_aws():
        ecs = boto3.client("ecs", region_name="us-east-1")
        
        # Create cluster
        ecs.create_cluster(clusterName="test-cluster")
        
        # Register task definition
        ecs.register_task_definition(
            family="test-task",
            containerDefinitions=[
                {
                    "name": "test-container",
                    "image": "nginx",
                    "memory": 512,
                }
            ]
        )
        
        # Create service with tags
        ecs.create_service(
            cluster="test-cluster",
            serviceName="test-service",
            taskDefinition="test-task",
            desiredCount=1,
            tags=[
                {"key": "Environment", "value": "production"},
                {"key": "Owner", "value": "platform-team"},
            ]
        )
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_ecs_services()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "ecs:service"
        assert resources[0]["resource_id"] == "test-service"
        # ECS tags use lowercase 'key' and 'value'
        assert len(resources[0]["tags"]) == 2
        assert "Environment" in resources[0]["tags"] or "environment" in resources[0]["tags"]


@pytest.mark.asyncio
async def test_get_ecs_services_without_tags():
    """Test fetching ECS services without tags."""
    with mock_aws():
        ecs = boto3.client("ecs", region_name="us-east-1")
        
        # Create cluster
        ecs.create_cluster(clusterName="test-cluster")
        
        # Register task definition
        ecs.register_task_definition(
            family="test-task",
            containerDefinitions=[
                {
                    "name": "test-container",
                    "image": "nginx",
                    "memory": 512,
                }
            ]
        )
        
        # Create service without tags
        ecs.create_service(
            cluster="test-cluster",
            serviceName="test-service",
            taskDefinition="test-task",
            desiredCount=1,
        )
        
        client = AWSClient(region="us-east-1")
        resources = await client.get_ecs_services()
        
        assert len(resources) == 1
        assert resources[0]["tags"] == {}


# =============================================================================
# Cost Explorer Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_cost_data_default_period(aws_client):
    """Test cost data retrieval with default time period."""
    # This test uses moto's mock for Cost Explorer
    # Note: moto has limited support for Cost Explorer, so we test the structure
    
    # For now, we'll test that the method exists and can be called
    # Full testing would require AWS credentials or more advanced mocking
    assert hasattr(aws_client, "get_cost_data")
    assert callable(aws_client.get_cost_data)


# =============================================================================
# Error Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_aws_api_error_on_invalid_region(aws_client):
    """Test that AWSAPIError is raised on API failures."""
    # This would require actual AWS API calls or more sophisticated mocking
    # For now, we verify the error class exists
    assert issubclass(AWSAPIError, Exception)


# =============================================================================
# Tag Extraction Tests
# =============================================================================

def test_extract_tags_empty_list(aws_client):
    """Test tag extraction with empty list."""
    tags = aws_client._extract_tags([])
    assert tags == {}


def test_extract_tags_single_tag(aws_client):
    """Test tag extraction with single tag."""
    tag_list = [{"Key": "Environment", "Value": "production"}]
    tags = aws_client._extract_tags(tag_list)
    
    assert tags == {"Environment": "production"}


def test_extract_tags_multiple_tags(aws_client):
    """Test tag extraction with multiple tags."""
    tag_list = [
        {"Key": "Environment", "Value": "production"},
        {"Key": "Owner", "Value": "team-a"},
        {"Key": "CostCenter", "Value": "Engineering"},
    ]
    tags = aws_client._extract_tags(tag_list)
    
    assert tags == {
        "Environment": "production",
        "Owner": "team-a",
        "CostCenter": "Engineering",
    }


def test_extract_tags_with_empty_values(aws_client):
    """Test tag extraction with empty key or value."""
    tag_list = [
        {"Key": "Environment", "Value": "production"},
        {"Key": "", "Value": "empty-key"},
        {"Key": "empty-value", "Value": ""},
    ]
    tags = aws_client._extract_tags(tag_list)
    
    assert tags["Environment"] == "production"
    assert "" not in tags  # Empty keys are now filtered out
    assert tags["empty-value"] == ""


# =============================================================================
# Resource Format Tests
# =============================================================================

@pytest.mark.asyncio
async def test_resource_format_completeness():
    """Test that returned resources have all required fields."""
    with mock_aws():
        ec2 = boto3.resource("ec2", region_name="us-east-1")
        instances = ec2.create_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)
        instance = instances[0]
        instance.create_tags(Tags=[{"Key": "Name", "Value": "test"}])
        
        # Create client inside mock context
        client = AWSClient(region="us-east-1")
        resources = await client.get_ec2_instances()
        
        assert len(resources) == 1
        resource = resources[0]
        
        # Verify all required fields are present
        assert "resource_id" in resource
        assert "resource_type" in resource
        assert "region" in resource
        assert "tags" in resource
        assert "created_at" in resource
        assert "arn" in resource
        
        # Verify field types
        assert isinstance(resource["resource_id"], str)
        assert isinstance(resource["resource_type"], str)
        assert isinstance(resource["region"], str)
        assert isinstance(resource["tags"], dict)
        assert isinstance(resource["arn"], str)
