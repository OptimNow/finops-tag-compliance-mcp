"""Unit tests for validate_resource_tags tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_server.tools.validate_resource_tags import validate_resource_tags
from mcp_server.utils.arn_utils import (
    is_valid_arn,
    parse_arn,
    service_to_resource_type,
    extract_resource_id,
)
from mcp_server.clients.aws_client import AWSClient
from mcp_server.services.policy_service import PolicyService
from mcp_server.models.violations import Violation
from mcp_server.models.enums import ViolationType, Severity


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    client = MagicMock(spec=AWSClient)
    client.region = "us-east-1"
    return client


@pytest.fixture
def mock_policy_service():
    """Create a mock policy service."""
    service = MagicMock(spec=PolicyService)

    # Mock validate_resource_tags to return violations
    def validate_tags(resource_id, resource_type, region, tags, cost_impact):
        violations = []

        # Simulate missing CostCenter tag
        if "CostCenter" not in tags:
            violations.append(
                Violation(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=Severity.ERROR,
                    current_value=None,
                    allowed_values=["Engineering", "Marketing", "Sales"],
                    cost_impact_monthly=cost_impact,
                )
            )

        # Simulate invalid Environment value
        if "Environment" in tags and tags["Environment"] not in ["production", "staging", "dev"]:
            violations.append(
                Violation(
                    resource_id=resource_id,
                    resource_type=resource_type,
                    region=region,
                    violation_type=ViolationType.INVALID_VALUE,
                    tag_name="Environment",
                    severity=Severity.ERROR,
                    current_value=tags["Environment"],
                    allowed_values=["production", "staging", "dev"],
                    cost_impact_monthly=cost_impact,
                )
            )

        return violations

    service.validate_resource_tags = validate_tags
    return service


# Tests for ARN validation and parsing functions


def testis_valid_arn_valid_ec2():
    """Test ARN validation with valid EC2 ARN."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
    assert is_valid_arn(arn) is True


def testis_valid_arn_valid_s3():
    """Test ARN validation with valid S3 ARN."""
    arn = "arn:aws:s3:::my-bucket"
    assert is_valid_arn(arn) is True


def testis_valid_arn_valid_rds():
    """Test ARN validation with valid RDS ARN."""
    arn = "arn:aws:rds:us-east-1:123456789012:db:mydb"
    assert is_valid_arn(arn) is True


def testis_valid_arn_valid_lambda():
    """Test ARN validation with valid Lambda ARN."""
    arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"
    assert is_valid_arn(arn) is True


def testis_valid_arn_invalid_format():
    """Test ARN validation with invalid format."""
    assert is_valid_arn("not-an-arn") is False


def testis_valid_arn_empty_string():
    """Test ARN validation with empty string."""
    assert is_valid_arn("") is False


def testis_valid_arn_none():
    """Test ARN validation with None."""
    assert is_valid_arn(None) is False


def testparse_arn_ec2_instance():
    """Test parsing EC2 instance ARN."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
    parsed = parse_arn(arn)

    assert parsed["service"] == "ec2"
    assert parsed["region"] == "us-east-1"
    assert parsed["account"] == "123456789012"
    assert parsed["resource_type"] == "ec2:instance"
    assert parsed["resource_id"] == "i-1234567890abcdef0"


def testparse_arn_s3_bucket():
    """Test parsing S3 bucket ARN."""
    arn = "arn:aws:s3:::my-bucket"
    parsed = parse_arn(arn)

    assert parsed["service"] == "s3"
    assert parsed["region"] == "global"  # S3 buckets have no region
    assert parsed["resource_type"] == "s3:bucket"
    assert parsed["resource_id"] == "my-bucket"


def testparse_arn_rds_database():
    """Test parsing RDS database ARN."""
    arn = "arn:aws:rds:us-west-2:123456789012:db:mydb"
    parsed = parse_arn(arn)

    assert parsed["service"] == "rds"
    assert parsed["region"] == "us-west-2"
    assert parsed["resource_type"] == "rds:db"
    assert parsed["resource_id"] == "mydb"


def testparse_arn_lambda_function():
    """Test parsing Lambda function ARN."""
    arn = "arn:aws:lambda:eu-west-1:123456789012:function:my-function"
    parsed = parse_arn(arn)

    assert parsed["service"] == "lambda"
    assert parsed["region"] == "eu-west-1"
    assert parsed["resource_type"] == "lambda:function"
    assert parsed["resource_id"] == "my-function"


def testparse_arn_invalid_format():
    """Test parsing invalid ARN format."""
    with pytest.raises(ValueError, match="Invalid ARN format"):
        parse_arn("invalid-arn")


def testservice_to_resource_type_ec2():
    """Test service to resource type mapping for EC2."""
    resource_type = service_to_resource_type("ec2", "instance/i-12345")
    assert resource_type == "ec2:instance"


def testservice_to_resource_type_s3():
    """Test service to resource type mapping for S3."""
    resource_type = service_to_resource_type("s3", "my-bucket")
    assert resource_type == "s3:bucket"


def testservice_to_resource_type_rds():
    """Test service to resource type mapping for RDS."""
    resource_type = service_to_resource_type("rds", "db:mydb")
    assert resource_type == "rds:db"


def testservice_to_resource_type_lambda():
    """Test service to resource type mapping for Lambda."""
    resource_type = service_to_resource_type("lambda", "function:my-func")
    assert resource_type == "lambda:function"


def testservice_to_resource_type_ecs():
    """Test service to resource type mapping for ECS."""
    resource_type = service_to_resource_type("ecs", "service/my-cluster/my-service")
    assert resource_type == "ecs:service"


def testextract_resource_id_with_slash():
    """Test extracting resource ID with slash separator."""
    resource_id = extract_resource_id("instance/i-12345")
    assert resource_id == "i-12345"


def testextract_resource_id_with_colon():
    """Test extracting resource ID with colon separator."""
    resource_id = extract_resource_id("db:mydb")
    assert resource_id == "mydb"


def testextract_resource_id_simple():
    """Test extracting simple resource ID."""
    resource_id = extract_resource_id("my-bucket")
    assert resource_id == "my-bucket"


def testextract_resource_id_multiple_slashes():
    """Test extracting resource ID with multiple slashes."""
    resource_id = extract_resource_id("service/cluster/my-service")
    assert resource_id == "my-service"


# Tests for validate_resource_tags tool


@pytest.mark.asyncio
async def test_validate_resource_tags_empty_list():
    """Test validation with empty ARN list."""
    mock_client = MagicMock()
    mock_policy = MagicMock()

    with pytest.raises(ValueError, match="resource_arns cannot be empty"):
        await validate_resource_tags(
            aws_client=mock_client, policy_service=mock_policy, resource_arns=[]
        )


@pytest.mark.asyncio
async def test_validate_resource_tags_invalid_arn():
    """Test validation with invalid ARN format."""
    mock_client = MagicMock()
    mock_policy = MagicMock()

    with pytest.raises(ValueError, match="Invalid ARN format"):
        await validate_resource_tags(
            aws_client=mock_client, policy_service=mock_policy, resource_arns=["not-an-arn"]
        )


@pytest.mark.asyncio
async def test_validate_resource_tags_missing_tags(mock_aws_client, mock_policy_service):
    """Test validation detects missing required tags."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-12345"

    # Mock AWS client to return resource with missing tags
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},  # Missing CostCenter
                "created_at": None,
                "arn": arn,
            }
        ]
    )

    result = await validate_resource_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arns=[arn]
    )

    assert result.total_resources == 1
    assert result.compliant_resources == 0
    assert result.non_compliant_resources == 1

    resource_result = result.results[0]
    assert resource_result.resource_arn == arn
    assert resource_result.resource_id == "i-12345"
    assert resource_result.resource_type == "ec2:instance"
    assert resource_result.is_compliant is False
    assert len(resource_result.violations) == 1
    assert resource_result.violations[0].violation_type == ViolationType.MISSING_REQUIRED_TAG
    assert resource_result.violations[0].tag_name == "CostCenter"


@pytest.mark.asyncio
async def test_validate_resource_tags_invalid_value(mock_aws_client, mock_policy_service):
    """Test validation detects invalid tag values."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-12345"

    # Mock AWS client to return resource with invalid tag value
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {
                    "CostCenter": "Engineering",
                    "Environment": "invalid-env",  # Invalid value
                },
                "created_at": None,
                "arn": arn,
            }
        ]
    )

    result = await validate_resource_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arns=[arn]
    )

    assert result.total_resources == 1
    assert result.compliant_resources == 0
    assert result.non_compliant_resources == 1

    resource_result = result.results[0]
    assert resource_result.is_compliant is False
    assert len(resource_result.violations) == 1

    violation = resource_result.violations[0]
    assert violation.violation_type == ViolationType.INVALID_VALUE
    assert violation.tag_name == "Environment"
    assert violation.current_value == "invalid-env"
    assert violation.allowed_values == ["production", "staging", "dev"]


@pytest.mark.asyncio
async def test_validate_resource_tags_compliant_resource(mock_aws_client, mock_policy_service):
    """Test validation passes for compliant resources."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-12345"

    # Mock AWS client to return compliant resource
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "created_at": None,
                "arn": arn,
            }
        ]
    )

    result = await validate_resource_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arns=[arn]
    )

    assert result.total_resources == 1
    assert result.compliant_resources == 1
    assert result.non_compliant_resources == 0

    resource_result = result.results[0]
    assert resource_result.is_compliant is True
    assert len(resource_result.violations) == 0


@pytest.mark.asyncio
async def test_validate_resource_tags_multiple_resources(mock_aws_client, mock_policy_service):
    """Test validation of multiple resources."""
    arn1 = "arn:aws:ec2:us-east-1:123456789012:instance/i-11111"
    arn2 = "arn:aws:ec2:us-east-1:123456789012:instance/i-22222"

    # Mock AWS client to return multiple resources
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-11111",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "created_at": None,
                "arn": arn1,
            },
            {
                "resource_id": "i-22222",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},  # Missing tags
                "created_at": None,
                "arn": arn2,
            },
        ]
    )

    result = await validate_resource_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arns=[arn1, arn2]
    )

    assert result.total_resources == 2
    assert result.compliant_resources == 1
    assert result.non_compliant_resources == 1
    assert len(result.results) == 2


@pytest.mark.asyncio
async def test_validate_resource_tags_s3_bucket(mock_aws_client, mock_policy_service):
    """Test validation of S3 bucket."""
    arn = "arn:aws:s3:::my-bucket"

    # Mock AWS client to return S3 bucket
    mock_aws_client.get_s3_buckets = AsyncMock(
        return_value=[
            {
                "resource_id": "my-bucket",
                "resource_type": "s3:bucket",
                "region": "global",
                "tags": {"CostCenter": "Engineering"},
                "created_at": None,
                "arn": arn,
            }
        ]
    )

    result = await validate_resource_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arns=[arn]
    )

    assert result.total_resources == 1
    resource_result = result.results[0]
    assert resource_result.resource_type == "s3:bucket"
    assert resource_result.resource_id == "my-bucket"


@pytest.mark.asyncio
async def test_validate_resource_tags_rds_database(mock_aws_client, mock_policy_service):
    """Test validation of RDS database."""
    arn = "arn:aws:rds:us-east-1:123456789012:db:mydb"

    # Mock AWS client to return RDS instance
    mock_aws_client.get_rds_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "mydb",
                "resource_type": "rds:db",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "created_at": None,
                "arn": arn,
            }
        ]
    )

    result = await validate_resource_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arns=[arn]
    )

    assert result.total_resources == 1
    resource_result = result.results[0]
    assert resource_result.resource_type == "rds:db"
    assert resource_result.resource_id == "mydb"


@pytest.mark.asyncio
async def test_validate_resource_tags_lambda_function(mock_aws_client, mock_policy_service):
    """Test validation of Lambda function."""
    arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

    # Mock AWS client to return Lambda function
    mock_aws_client.get_lambda_functions = AsyncMock(
        return_value=[
            {
                "resource_id": "my-function",
                "resource_type": "lambda:function",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "created_at": None,
                "arn": arn,
            }
        ]
    )

    result = await validate_resource_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arns=[arn]
    )

    assert result.total_resources == 1
    resource_result = result.results[0]
    assert resource_result.resource_type == "lambda:function"
    assert resource_result.resource_id == "my-function"


@pytest.mark.asyncio
async def test_validate_resource_tags_current_tags_included(mock_aws_client, mock_policy_service):
    """Test that current tags are included in the result."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-12345"

    current_tags = {
        "CostCenter": "Engineering",
        "Environment": "production",
        "Owner": "john@example.com",
    }

    # Mock AWS client to return resource with tags
    mock_aws_client.get_ec2_instances = AsyncMock(
        return_value=[
            {
                "resource_id": "i-12345",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": current_tags,
                "created_at": None,
                "arn": arn,
            }
        ]
    )

    result = await validate_resource_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arns=[arn]
    )

    resource_result = result.results[0]
    assert resource_result.current_tags == current_tags


@pytest.mark.asyncio
@patch("mcp_server.tools.validate_resource_tags.logger")
async def test_validate_resource_tags_resource_not_found(
    mock_logger, mock_aws_client, mock_policy_service
):
    """Test handling when resource is not found."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-nonexistent"

    # Mock AWS client to return no resources
    mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])

    result = await validate_resource_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arns=[arn]
    )

    # Should still return a result with empty tags
    assert result.total_resources == 1
    resource_result = result.results[0]
    assert resource_result.current_tags == {}
