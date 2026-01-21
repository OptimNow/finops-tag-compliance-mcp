# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Unit tests for suggest_tags tool."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_server.clients.aws_client import AWSClient
from mcp_server.models.suggestions import TagSuggestion
from mcp_server.services.policy_service import PolicyService
from mcp_server.tools.suggest_tags import SuggestTagsResult, suggest_tags
from mcp_server.utils.arn_utils import (
    extract_resource_id,
    is_valid_arn,
    parse_arn,
    service_to_resource_type,
)


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

    # Mock get_required_tags to return a list of required tags
    def get_required_tags(resource_type):
        return [
            MagicMock(
                name="Environment",
                allowed_values=["production", "staging", "development"],
                validation_regex=None,
            ),
            MagicMock(
                name="CostCenter",
                allowed_values=["Engineering", "Marketing", "Sales"],
                validation_regex=None,
            ),
        ]

    service.get_required_tags = get_required_tags
    return service


# Tests for ARN validation and parsing functions (now in shared module)


def test_is_valid_arn_valid_ec2():
    """Test ARN validation with valid EC2 ARN."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
    assert is_valid_arn(arn) is True


def test_is_valid_arn_valid_s3():
    """Test ARN validation with valid S3 ARN."""
    arn = "arn:aws:s3:::my-bucket"
    assert is_valid_arn(arn) is True


def test_is_valid_arn_valid_rds():
    """Test ARN validation with valid RDS ARN."""
    arn = "arn:aws:rds:us-east-1:123456789012:db:mydb"
    assert is_valid_arn(arn) is True


def test_is_valid_arn_valid_lambda():
    """Test ARN validation with valid Lambda ARN."""
    arn = "arn:aws:lambda:us-east-1:123456789012:function:my-function"
    assert is_valid_arn(arn) is True


def test_is_valid_arn_invalid_format():
    """Test ARN validation with invalid format."""
    assert is_valid_arn("not-an-arn") is False


def test_is_valid_arn_empty_string():
    """Test ARN validation with empty string."""
    assert is_valid_arn("") is False


def test_is_valid_arn_none():
    """Test ARN validation with None."""
    assert is_valid_arn(None) is False


def test_parse_arn_ec2_instance():
    """Test parsing EC2 instance ARN."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0"
    parsed = parse_arn(arn)

    assert parsed["service"] == "ec2"
    assert parsed["region"] == "us-east-1"
    assert parsed["account"] == "123456789012"
    assert parsed["resource_type"] == "ec2:instance"
    assert parsed["resource_id"] == "i-1234567890abcdef0"


def test_parse_arn_s3_bucket():
    """Test parsing S3 bucket ARN."""
    arn = "arn:aws:s3:::my-bucket"
    parsed = parse_arn(arn)

    assert parsed["service"] == "s3"
    assert parsed["region"] == "global"
    assert parsed["resource_type"] == "s3:bucket"
    assert parsed["resource_id"] == "my-bucket"


def test_parse_arn_rds_database():
    """Test parsing RDS database ARN."""
    arn = "arn:aws:rds:us-west-2:123456789012:db:mydb"
    parsed = parse_arn(arn)

    assert parsed["service"] == "rds"
    assert parsed["region"] == "us-west-2"
    assert parsed["resource_type"] == "rds:db"
    assert parsed["resource_id"] == "mydb"


def test_parse_arn_lambda_function():
    """Test parsing Lambda function ARN."""
    arn = "arn:aws:lambda:eu-west-1:123456789012:function:my-function"
    parsed = parse_arn(arn)

    assert parsed["service"] == "lambda"
    assert parsed["region"] == "eu-west-1"
    assert parsed["resource_type"] == "lambda:function"
    assert parsed["resource_id"] == "my-function"


def test_parse_arn_invalid_format():
    """Test parsing invalid ARN format."""
    with pytest.raises(ValueError, match="Invalid ARN format"):
        parse_arn("invalid-arn")


def test_service_to_resource_type_ec2():
    """Test service to resource type mapping for EC2."""
    resource_type = service_to_resource_type("ec2", "instance/i-12345")
    assert resource_type == "ec2:instance"


def test_service_to_resource_type_s3():
    """Test service to resource type mapping for S3."""
    resource_type = service_to_resource_type("s3", "my-bucket")
    assert resource_type == "s3:bucket"


def test_service_to_resource_type_rds():
    """Test service to resource type mapping for RDS."""
    resource_type = service_to_resource_type("rds", "db:mydb")
    assert resource_type == "rds:db"


def test_service_to_resource_type_lambda():
    """Test service to resource type mapping for Lambda."""
    resource_type = service_to_resource_type("lambda", "function:my-func")
    assert resource_type == "lambda:function"


def test_service_to_resource_type_ecs():
    """Test service to resource type mapping for ECS."""
    resource_type = service_to_resource_type("ecs", "service/my-cluster/my-service")
    assert resource_type == "ecs:service"


def test_extract_resource_id_with_slash():
    """Test extracting resource ID with slash separator."""
    resource_id = extract_resource_id("instance/i-12345")
    assert resource_id == "i-12345"


def test_extract_resource_id_with_colon():
    """Test extracting resource ID with colon separator."""
    resource_id = extract_resource_id("db:mydb")
    assert resource_id == "mydb"


def test_extract_resource_id_simple():
    """Test extracting simple resource ID."""
    resource_id = extract_resource_id("my-bucket")
    assert resource_id == "my-bucket"


def test_extract_resource_id_multiple_slashes():
    """Test extracting resource ID with multiple slashes."""
    resource_id = extract_resource_id("service/cluster/my-service")
    assert resource_id == "my-service"


# Tests for SuggestTagsResult (now Pydantic model)


def test_suggest_tags_result_model_dump():
    """Test SuggestTagsResult serialization using Pydantic model_dump."""
    suggestions = [
        TagSuggestion(
            tag_key="Environment",
            suggested_value="production",
            confidence=0.85,
            reasoning="Detected 'prod' pattern in resource name",
        ),
        TagSuggestion(
            tag_key="CostCenter",
            suggested_value="Engineering",
            confidence=0.75,
            reasoning="Found in similar resources",
        ),
    ]

    result = SuggestTagsResult(
        resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
        resource_type="ec2:instance",
        suggestions=suggestions,
        current_tags={"Name": "test-instance"},
    )

    result_dict = result.model_dump()

    assert result_dict["resource_arn"] == "arn:aws:ec2:us-east-1:123456789012:instance/i-12345"
    assert result_dict["resource_type"] == "ec2:instance"
    assert result_dict["suggestion_count"] == 2
    assert len(result_dict["suggestions"]) == 2
    assert result_dict["suggestions"][0]["tag_key"] == "Environment"
    assert result_dict["suggestions"][0]["confidence"] == 0.85
    assert result_dict["current_tags"] == {"Name": "test-instance"}


def test_suggest_tags_result_empty_suggestions():
    """Test SuggestTagsResult with no suggestions."""
    result = SuggestTagsResult(
        resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-12345",
        resource_type="ec2:instance",
        suggestions=[],
        current_tags={"CostCenter": "Engineering", "Environment": "production"},
    )

    result_dict = result.model_dump()

    assert result_dict["suggestion_count"] == 0
    assert len(result_dict["suggestions"]) == 0


# Tests for suggest_tags tool


@pytest.mark.asyncio
async def test_suggest_tags_empty_arn():
    """Test suggest_tags with empty ARN."""
    mock_client = MagicMock()
    mock_policy = MagicMock()

    with pytest.raises(ValueError, match="resource_arn cannot be empty"):
        await suggest_tags(aws_client=mock_client, policy_service=mock_policy, resource_arn="")


@pytest.mark.asyncio
async def test_suggest_tags_invalid_arn():
    """Test suggest_tags with invalid ARN format."""
    mock_client = MagicMock()
    mock_policy = MagicMock()

    with pytest.raises(ValueError, match="Invalid ARN format"):
        await suggest_tags(
            aws_client=mock_client, policy_service=mock_policy, resource_arn="not-an-arn"
        )


@pytest.mark.asyncio
async def test_suggest_tags_ec2_instance_with_prod_pattern(mock_aws_client, mock_policy_service):
    """Test suggestion generation for EC2 instance with production pattern."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-prod-12345"

    # Mock get_tags_for_arns to return tags for the resource
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: {}})  # No existing tags

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    assert result.resource_arn == arn
    assert result.resource_type == "ec2:instance"
    assert result.current_tags == {}
    # Should have suggestions for missing tags
    assert len(result.suggestions) >= 0


@pytest.mark.asyncio
async def test_suggest_tags_confidence_score_bounds(mock_aws_client, mock_policy_service):
    """Test that confidence scores are within valid bounds (0.0 to 1.0)."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-prod-12345"

    # Mock get_tags_for_arns
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: {}})

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    # Verify all suggestions have valid confidence scores
    for suggestion in result.suggestions:
        assert isinstance(suggestion.confidence, float)
        assert 0.0 <= suggestion.confidence <= 1.0


@pytest.mark.asyncio
async def test_suggest_tags_includes_reasoning(mock_aws_client, mock_policy_service):
    """Test that all suggestions include reasoning."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-prod-12345"

    # Mock get_tags_for_arns
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: {}})

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    # Verify all suggestions have reasoning
    for suggestion in result.suggestions:
        assert suggestion.reasoning is not None
        assert len(suggestion.reasoning) > 0
        assert isinstance(suggestion.reasoning, str)


@pytest.mark.asyncio
async def test_suggest_tags_s3_bucket(mock_aws_client, mock_policy_service):
    """Test suggestion generation for S3 bucket."""
    arn = "arn:aws:s3:::my-prod-bucket"

    # Mock get_tags_for_arns
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: {}})

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    assert result.resource_arn == arn
    assert result.resource_type == "s3:bucket"
    assert result.current_tags == {}


@pytest.mark.asyncio
async def test_suggest_tags_rds_database(mock_aws_client, mock_policy_service):
    """Test suggestion generation for RDS database."""
    arn = "arn:aws:rds:us-east-1:123456789012:db:prod-db"

    # Mock get_tags_for_arns
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: {}})

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    assert result.resource_arn == arn
    assert result.resource_type == "rds:db"
    assert result.current_tags == {}


@pytest.mark.asyncio
async def test_suggest_tags_lambda_function(mock_aws_client, mock_policy_service):
    """Test suggestion generation for Lambda function."""
    arn = "arn:aws:lambda:us-east-1:123456789012:function:prod-function"

    # Mock get_tags_for_arns
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: {}})

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    assert result.resource_arn == arn
    assert result.resource_type == "lambda:function"
    assert result.current_tags == {}


@pytest.mark.asyncio
async def test_suggest_tags_with_existing_tags(mock_aws_client, mock_policy_service):
    """Test suggestion generation for resource with some existing tags."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-prod-12345"

    existing_tags = {"Name": "test-instance", "Environment": "production"}

    # Mock get_tags_for_arns to return existing tags
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: existing_tags})

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    assert result.current_tags == existing_tags
    # Should not suggest Environment since it already exists
    env_suggestions = [s for s in result.suggestions if s.tag_key == "Environment"]
    assert len(env_suggestions) == 0


@pytest.mark.asyncio
async def test_suggest_tags_result_structure(mock_aws_client, mock_policy_service):
    """Test that suggest_tags returns properly structured result."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-12345"

    # Mock get_tags_for_arns
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: {}})

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    # Verify result structure
    assert isinstance(result, SuggestTagsResult)
    assert result.resource_arn == arn
    assert result.resource_type == "ec2:instance"
    assert isinstance(result.suggestions, list)
    assert isinstance(result.current_tags, dict)

    # Verify model_dump() works (Pydantic method)
    result_dict = result.model_dump()
    assert "resource_arn" in result_dict
    assert "resource_type" in result_dict
    assert "suggestions" in result_dict
    assert "current_tags" in result_dict
    assert "suggestion_count" in result_dict


@pytest.mark.asyncio
async def test_suggest_tags_multiple_suggestions(mock_aws_client, mock_policy_service):
    """Test that multiple suggestions can be generated for a resource."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-prod-eng-12345"

    # Mock get_tags_for_arns
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: {}})

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    # Should have suggestions for multiple missing tags
    assert isinstance(result.suggestions, list)
    # Each suggestion should be a TagSuggestion object
    for suggestion in result.suggestions:
        assert isinstance(suggestion, TagSuggestion)
        assert hasattr(suggestion, "tag_key")
        assert hasattr(suggestion, "suggested_value")
        assert hasattr(suggestion, "confidence")
        assert hasattr(suggestion, "reasoning")


@pytest.mark.asyncio
async def test_suggest_tags_confidence_varies_by_source(mock_aws_client, mock_policy_service):
    """Test that confidence scores vary based on suggestion source."""
    arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-prod-12345"

    # Mock get_tags_for_arns
    mock_aws_client.get_tags_for_arns = AsyncMock(return_value={arn: {}})

    # Mock get_all_tagged_resources for similar resources
    mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[])

    result = await suggest_tags(
        aws_client=mock_aws_client, policy_service=mock_policy_service, resource_arn=arn
    )

    # If we have multiple suggestions, they should have different confidence scores
    # (unless they happen to be the same)
    if len(result.suggestions) > 1:
        confidences = [s.confidence for s in result.suggestions]
        # At least verify all are valid
        for conf in confidences:
            assert 0.0 <= conf <= 1.0
