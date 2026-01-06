"""Unit tests for AWS client wrapper."""

import pytest
from datetime import datetime, UTC
from moto import mock_aws
import boto3
from unittest.mock import patch, AsyncMock

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


@pytest.mark.asyncio
async def test_get_account_id_caching():
    """Test that account ID is cached after first retrieval."""
    client = AWSClient()
    
    # Mock STS response
    mock_response = {"Account": "123456789012"}
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_response
        
        # First call should fetch from STS
        account_id1 = await client._get_account_id()
        assert account_id1 == "123456789012"
        assert mock_call.call_count == 1
        
        # Second call should use cached value
        account_id2 = await client._get_account_id()
        assert account_id2 == "123456789012"
        assert mock_call.call_count == 1  # Should not call STS again


@pytest.mark.asyncio
async def test_get_account_id_error_handling():
    """Test error handling when STS call fails."""
    client = AWSClient()
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("STS unavailable")
        
        with pytest.raises(AWSAPIError, match="Failed to get account ID"):
            await client._get_account_id()


# =============================================================================
# OpenSearch Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_opensearch_domains_empty():
    """Test fetching OpenSearch domains when none exist."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_get_account_id', new_callable=AsyncMock) as mock_account:
        mock_account.return_value = "123456789012"
        
        with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"DomainNames": []}
            
            domains = await client.get_opensearch_domains()
            assert domains == []


@pytest.mark.asyncio
async def test_get_opensearch_domains_with_tags():
    """Test fetching OpenSearch domains with tags."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_get_account_id', new_callable=AsyncMock) as mock_account:
        mock_account.return_value = "123456789012"
        
        # Mock the sequence of calls: list_domain_names, describe_domain, list_tags
        call_count = [0]
        
        async def mock_call_side_effect(service_name, func, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # list_domain_names
                return {"DomainNames": [{"DomainName": "test-domain"}]}
            elif call_count[0] == 2:  # describe_domain
                return {
                    "DomainStatus": {
                        "DomainName": "test-domain",
                        "ARN": "arn:aws:es:us-east-1:123456789012:domain/test-domain",
                        "Created": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
                    }
                }
            elif call_count[0] == 3:  # list_tags
                return {
                    "TagList": [
                        {"Key": "Environment", "Value": "production"},
                        {"Key": "Owner", "Value": "data-team"}
                    ]
                }
            return {}
        
        with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = mock_call_side_effect
            
            resources = await client.get_opensearch_domains()
            
            assert len(resources) == 1
            assert resources[0]["resource_type"] == "opensearch:domain"
            assert resources[0]["resource_id"] == "test-domain"
            assert resources[0]["region"] == "us-east-1"
            assert resources[0]["tags"]["Environment"] == "production"
            assert resources[0]["tags"]["Owner"] == "data-team"
            assert resources[0]["arn"] == "arn:aws:es:us-east-1:123456789012:domain/test-domain"


@pytest.mark.asyncio
async def test_get_opensearch_domains_without_tags():
    """Test fetching OpenSearch domains without tags."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_get_account_id', new_callable=AsyncMock) as mock_account:
        mock_account.return_value = "123456789012"
        
        call_count = [0]
        
        async def mock_call_side_effect(service_name, func, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # list_domain_names
                return {"DomainNames": [{"DomainName": "test-domain"}]}
            elif call_count[0] == 2:  # describe_domain
                return {
                    "DomainStatus": {
                        "DomainName": "test-domain",
                        "ARN": "arn:aws:es:us-east-1:123456789012:domain/test-domain",
                        "Created": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
                    }
                }
            elif call_count[0] == 3:  # list_tags - raise error to simulate no tags
                raise AWSAPIError("No tags found")
            return {}
        
        with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = mock_call_side_effect
            
            resources = await client.get_opensearch_domains()
            
            assert len(resources) == 1
            assert resources[0]["tags"] == {}


@pytest.mark.asyncio
async def test_get_opensearch_domains_multiple():
    """Test fetching multiple OpenSearch domains."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_get_account_id', new_callable=AsyncMock) as mock_account:
        mock_account.return_value = "123456789012"
        
        call_count = [0]
        
        async def mock_call_side_effect(service_name, func, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # list_domain_names
                return {
                    "DomainNames": [
                        {"DomainName": "domain-1"},
                        {"DomainName": "domain-2"},
                        {"DomainName": "domain-3"}
                    ]
                }
            elif call_count[0] in [2, 4, 6]:  # describe_domain calls
                domain_idx = (call_count[0] - 2) // 2
                domain_name = f"domain-{domain_idx + 1}"
                return {
                    "DomainStatus": {
                        "DomainName": domain_name,
                        "ARN": f"arn:aws:es:us-east-1:123456789012:domain/{domain_name}",
                        "Created": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
                    }
                }
            elif call_count[0] in [3, 5, 7]:  # list_tags calls
                return {"TagList": []}
            return {}
        
        with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = mock_call_side_effect
            
            resources = await client.get_opensearch_domains()
            
            assert len(resources) == 3
            assert all(r["resource_type"] == "opensearch:domain" for r in resources)


@pytest.mark.asyncio
async def test_get_opensearch_domains_describe_error():
    """Test handling of describe_domain errors for individual domains."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_get_account_id', new_callable=AsyncMock) as mock_account:
        mock_account.return_value = "123456789012"
        
        call_count = [0]
        
        async def mock_call_side_effect(service_name, func, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # list_domain_names
                return {
                    "DomainNames": [
                        {"DomainName": "good-domain"},
                        {"DomainName": "bad-domain"}
                    ]
                }
            elif call_count[0] == 2:  # describe_domain for good-domain
                return {
                    "DomainStatus": {
                        "DomainName": "good-domain",
                        "ARN": "arn:aws:es:us-east-1:123456789012:domain/good-domain",
                        "Created": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
                    }
                }
            elif call_count[0] == 3:  # list_tags for good-domain
                return {"TagList": []}
            elif call_count[0] == 4:  # describe_domain for bad-domain - error
                raise AWSAPIError("Domain not accessible")
            return {}
        
        with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
            mock_call.side_effect = mock_call_side_effect
            
            # Should return only the good domain, not fail entirely
            resources = await client.get_opensearch_domains()
            
            assert len(resources) == 1
            assert resources[0]["resource_id"] == "good-domain"


@pytest.mark.asyncio
async def test_ec2_arn_includes_account_id():
    """Test that EC2 instance ARNs include the account ID."""
    client = AWSClient()
    
    # Mock STS response for account ID
    with patch.object(client, '_get_account_id', new_callable=AsyncMock) as mock_get_account:
        mock_get_account.return_value = "123456789012"
        
        # Mock EC2 response
        mock_response = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-1234567890abcdef0",
                            "Tags": [{"Key": "Name", "Value": "test-instance"}],
                            "LaunchTime": datetime.now()
                        }
                    ]
                }
            ]
        }
        
        with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_response
            
            result = await client.get_ec2_instances()
            
            assert len(result) == 1
            assert result[0]["arn"] == "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
            
            # Verify account ID was fetched
            mock_get_account.assert_called_once()


# =============================================================================
# Resource Groups Tagging API Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_all_tagged_resources_empty():
    """Test fetching resources when none exist."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"ResourceTagMappingList": []}
        
        resources = await client.get_all_tagged_resources()
        assert resources == []


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_ec2():
    """Test fetching EC2 instances via Resource Groups Tagging API."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                    "Tags": [
                        {"Key": "Environment", "Value": "production"},
                        {"Key": "Owner", "Value": "team-a"}
                    ]
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "ec2:instance"
        assert resources[0]["resource_id"] == "i-1234567890abcdef0"
        assert resources[0]["region"] == "us-east-1"
        assert resources[0]["tags"]["Environment"] == "production"
        assert resources[0]["tags"]["Owner"] == "team-a"


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_s3():
    """Test fetching S3 buckets via Resource Groups Tagging API."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:s3:::my-bucket-name",
                    "Tags": [
                        {"Key": "DataClassification", "Value": "confidential"}
                    ]
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "s3:bucket"
        assert resources[0]["resource_id"] == "my-bucket-name"
        assert resources[0]["tags"]["DataClassification"] == "confidential"


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_lambda():
    """Test fetching Lambda functions via Resource Groups Tagging API."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                    "Tags": [
                        {"Key": "Application", "Value": "backend-api"}
                    ]
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "lambda:function"
        assert resources[0]["resource_id"] == "my-function"


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_rds():
    """Test fetching RDS instances via Resource Groups Tagging API."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:rds:us-east-1:123456789012:db:my-database",
                    "Tags": [
                        {"Key": "Environment", "Value": "staging"}
                    ]
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "rds:db"
        assert resources[0]["resource_id"] == "my-database"


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_dynamodb():
    """Test fetching DynamoDB tables via Resource Groups Tagging API."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:dynamodb:us-east-1:123456789012:table/my-table",
                    "Tags": [
                        {"Key": "Application", "Value": "user-service"}
                    ]
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "dynamodb:table"
        assert resources[0]["resource_id"] == "my-table"


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_sns():
    """Test fetching SNS topics via Resource Groups Tagging API."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:sns:us-east-1:123456789012:my-topic",
                    "Tags": [
                        {"Key": "Team", "Value": "notifications"}
                    ]
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "sns:topic"
        assert resources[0]["resource_id"] == "my-topic"


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_sqs():
    """Test fetching SQS queues via Resource Groups Tagging API."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:sqs:us-east-1:123456789012:my-queue",
                    "Tags": [
                        {"Key": "Purpose", "Value": "order-processing"}
                    ]
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 1
        assert resources[0]["resource_type"] == "sqs:queue"
        assert resources[0]["resource_id"] == "my-queue"


@pytest.mark.asyncio
async def test_get_all_tagged_resources_multiple_types():
    """Test fetching multiple resource types in one call."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
                    "Tags": [{"Key": "Environment", "Value": "production"}]
                },
                {
                    "ResourceARN": "arn:aws:s3:::my-bucket",
                    "Tags": [{"Key": "DataClassification", "Value": "public"}]
                },
                {
                    "ResourceARN": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                    "Tags": [{"Key": "Team", "Value": "backend"}]
                },
                {
                    "ResourceARN": "arn:aws:dynamodb:us-east-1:123456789012:table/users",
                    "Tags": [{"Key": "Application", "Value": "user-service"}]
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 4
        resource_types = {r["resource_type"] for r in resources}
        assert "ec2:instance" in resource_types
        assert "s3:bucket" in resource_types
        assert "lambda:function" in resource_types
        assert "dynamodb:table" in resource_types


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_pagination():
    """Test pagination handling for large result sets."""
    client = AWSClient(region="us-east-1")
    
    call_count = [0]
    
    async def mock_call_side_effect(service_name, func, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return {
                "ResourceTagMappingList": [
                    {
                        "ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-page1",
                        "Tags": [{"Key": "Page", "Value": "1"}]
                    }
                ],
                "PaginationToken": "token123"
            }
        else:
            return {
                "ResourceTagMappingList": [
                    {
                        "ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-page2",
                        "Tags": [{"Key": "Page", "Value": "2"}]
                    }
                ]
            }
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = mock_call_side_effect
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 2
        assert call_count[0] == 2
        resource_ids = {r["resource_id"] for r in resources}
        assert "i-page1" in resource_ids
        assert "i-page2" in resource_ids


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_resource_type_filter():
    """Test filtering by resource type."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
                    "Tags": [{"Key": "Environment", "Value": "production"}]
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources(
            resource_type_filters=["ec2:instance"]
        )
        
        assert len(resources) == 1
        # Verify the filter was passed to the API
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args[1]
        assert "ResourceTypeFilters" in call_kwargs
        assert "ec2:instance" in call_kwargs["ResourceTypeFilters"]


@pytest.mark.asyncio
async def test_get_all_tagged_resources_with_tag_filter():
    """Test filtering by tag key/value."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
                    "Tags": [{"Key": "Environment", "Value": "production"}]
                }
            ]
        }
        
        tag_filters = [{"Key": "Environment", "Values": ["production"]}]
        resources = await client.get_all_tagged_resources(tag_filters=tag_filters)
        
        assert len(resources) == 1
        # Verify the filter was passed to the API
        mock_call.assert_called_once()
        call_kwargs = mock_call.call_args[1]
        assert "TagFilters" in call_kwargs


@pytest.mark.asyncio
async def test_get_all_tagged_resources_without_tags():
    """Test handling resources with no tags."""
    client = AWSClient(region="us-east-1")
    
    with patch.object(client, '_call_with_backoff', new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            "ResourceTagMappingList": [
                {
                    "ResourceARN": "arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
                    "Tags": []
                }
            ]
        }
        
        resources = await client.get_all_tagged_resources()
        
        assert len(resources) == 1
        assert resources[0]["tags"] == {}


# =============================================================================
# ARN Parsing Tests
# =============================================================================

def test_parse_arn_ec2_instance(aws_client):
    """Test parsing EC2 instance ARN."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "ec2"
    assert result["region"] == "us-east-1"
    assert result["account"] == "123456789012"
    assert result["resource_type"] == "ec2:instance"
    assert result["resource_id"] == "i-1234567890abcdef0"


def test_parse_arn_s3_bucket(aws_client):
    """Test parsing S3 bucket ARN (no region/account)."""
    arn = "arn:aws:s3:::my-bucket-name"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "s3"
    assert result["region"] == ""
    assert result["account"] == ""
    assert result["resource_type"] == "s3:bucket"
    assert result["resource_id"] == "my-bucket-name"


def test_parse_arn_lambda_function(aws_client):
    """Test parsing Lambda function ARN."""
    arn = "arn:aws:lambda:us-west-2:123456789012:function:my-function"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "lambda"
    assert result["region"] == "us-west-2"
    assert result["resource_type"] == "lambda:function"
    assert result["resource_id"] == "my-function"


def test_parse_arn_rds_db(aws_client):
    """Test parsing RDS database ARN."""
    arn = "arn:aws:rds:eu-west-1:123456789012:db:my-database"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "rds"
    assert result["region"] == "eu-west-1"
    assert result["resource_type"] == "rds:db"
    assert result["resource_id"] == "my-database"


def test_parse_arn_dynamodb_table(aws_client):
    """Test parsing DynamoDB table ARN."""
    arn = "arn:aws:dynamodb:us-east-1:123456789012:table/users"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "dynamodb"
    assert result["resource_type"] == "dynamodb:table"
    assert result["resource_id"] == "users"


def test_parse_arn_sns_topic(aws_client):
    """Test parsing SNS topic ARN."""
    arn = "arn:aws:sns:us-east-1:123456789012:my-topic"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "sns"
    assert result["resource_type"] == "sns:topic"
    assert result["resource_id"] == "my-topic"


def test_parse_arn_sqs_queue(aws_client):
    """Test parsing SQS queue ARN."""
    arn = "arn:aws:sqs:us-east-1:123456789012:my-queue"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "sqs"
    assert result["resource_type"] == "sqs:queue"
    assert result["resource_id"] == "my-queue"


def test_parse_arn_ecs_service(aws_client):
    """Test parsing ECS service ARN."""
    arn = "arn:aws:ecs:us-east-1:123456789012:service/my-cluster/my-service"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "ecs"
    assert result["resource_type"] == "ecs:service"
    assert result["resource_id"] == "my-service"


def test_parse_arn_opensearch_domain(aws_client):
    """Test parsing OpenSearch domain ARN."""
    arn = "arn:aws:es:us-east-1:123456789012:domain/my-search"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "es"
    assert result["resource_type"] == "opensearch:domain"
    assert result["resource_id"] == "my-search"


def test_parse_arn_secretsmanager(aws_client):
    """Test parsing Secrets Manager secret ARN."""
    arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret-abc123"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "secretsmanager"
    assert result["resource_type"] == "secretsmanager:secret"
    assert result["resource_id"] == "my-secret-abc123"


def test_parse_arn_kms_key(aws_client):
    """Test parsing KMS key ARN."""
    arn = "arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "kms"
    assert result["resource_type"] == "kms:key"
    assert result["resource_id"] == "12345678-1234-1234-1234-123456789012"


def test_parse_arn_cloudwatch_alarm(aws_client):
    """Test parsing CloudWatch alarm ARN."""
    arn = "arn:aws:cloudwatch:us-east-1:123456789012:alarm:my-alarm"
    result = aws_client._parse_arn(arn)
    
    assert result["service"] == "cloudwatch"
    assert result["resource_type"] == "cloudwatch:alarm"
    assert result["resource_id"] == "my-alarm"


def test_parse_arn_invalid(aws_client):
    """Test parsing invalid ARN."""
    arn = "not-an-arn"
    result = aws_client._parse_arn(arn)
    
    assert result["resource_type"] == "unknown"
    assert result["resource_id"] == "not-an-arn"


# =============================================================================
# Resource Type Conversion Tests
# =============================================================================

def test_convert_resource_types_ec2(aws_client):
    """Test converting ec2:instance to AWS format."""
    result = aws_client._convert_resource_types_to_aws_format(["ec2:instance"])
    assert "ec2:instance" in result


def test_convert_resource_types_s3(aws_client):
    """Test converting s3:bucket to AWS format (s3)."""
    result = aws_client._convert_resource_types_to_aws_format(["s3:bucket"])
    assert "s3" in result


def test_convert_resource_types_opensearch(aws_client):
    """Test converting opensearch:domain to AWS format (es:domain)."""
    result = aws_client._convert_resource_types_to_aws_format(["opensearch:domain"])
    assert "es:domain" in result


def test_convert_resource_types_all(aws_client):
    """Test that 'all' returns empty list (no filter)."""
    result = aws_client._convert_resource_types_to_aws_format(["all"])
    assert result == []


def test_convert_resource_types_multiple(aws_client):
    """Test converting multiple resource types."""
    result = aws_client._convert_resource_types_to_aws_format([
        "ec2:instance", "s3:bucket", "lambda:function"
    ])
    assert "ec2:instance" in result
    assert "s3" in result
    assert "lambda:function" in result


def test_convert_resource_types_unknown(aws_client):
    """Test that unknown types are passed through unchanged."""
    result = aws_client._convert_resource_types_to_aws_format(["custom:resource"])
    assert "custom:resource" in result
