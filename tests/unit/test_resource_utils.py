"""Tests for shared resource utilities."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_server.utils.resource_utils import (
    fetch_resources_by_type,
    extract_account_from_arn,
    fetch_all_resources_via_tagging_api,
    fetch_resources_via_tagging_api,
    get_supported_resource_types,
    get_tagging_api_resource_types,
    SUPPORTED_RESOURCE_TYPES,
    TAGGING_API_RESOURCE_TYPES,
)


class TestFetchResourcesByType:
    """Test the fetch_resources_by_type utility function."""

    @pytest.mark.asyncio
    async def test_fetch_resources_by_type_success(self):
        """Test successful resource fetching."""
        # Mock AWS client
        aws_client = MagicMock()
        aws_client.get_ec2_instances = AsyncMock(return_value=[
            {"resource_id": "i-123", "tags": {"Name": "test"}}
        ])
        
        result = await fetch_resources_by_type(aws_client, "ec2:instance")
        
        assert len(result) == 1
        assert result[0]["resource_id"] == "i-123"
        aws_client.get_ec2_instances.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_fetch_resources_by_type_with_filters(self):
        """Test resource fetching with filters."""
        # Mock AWS client
        aws_client = MagicMock()
        aws_client.get_rds_instances = AsyncMock(return_value=[
            {"resource_id": "db-123", "tags": {"Environment": "prod"}}
        ])
        
        filters = {"region": "us-east-1"}
        result = await fetch_resources_by_type(aws_client, "rds:db", filters)
        
        assert len(result) == 1
        assert result[0]["resource_id"] == "db-123"
        aws_client.get_rds_instances.assert_called_once_with(filters)

    @pytest.mark.asyncio
    async def test_fetch_resources_by_type_unknown_type_uses_tagging_api(self):
        """Test that unknown resource types fall back to Tagging API."""
        aws_client = MagicMock()
        aws_client.get_all_tagged_resources = AsyncMock(return_value=[
            {"resource_id": "table-123", "resource_type": "dynamodb:table", "tags": {}}
        ])
        
        result = await fetch_resources_by_type(aws_client, "dynamodb:table")
        
        assert len(result) == 1
        assert result[0]["resource_type"] == "dynamodb:table"
        aws_client.get_all_tagged_resources.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_resources_by_type_api_error(self):
        """Test handling of API errors."""
        aws_client = MagicMock()
        aws_client.get_s3_buckets = AsyncMock(side_effect=Exception("API Error"))
        
        with pytest.raises(Exception, match="API Error"):
            await fetch_resources_by_type(aws_client, "s3:bucket")

    @pytest.mark.asyncio
    async def test_fetch_resources_by_type_all(self):
        """Test fetching all resources via Tagging API."""
        aws_client = MagicMock()
        aws_client.get_all_tagged_resources = AsyncMock(return_value=[
            {"resource_id": "i-123", "resource_type": "ec2:instance", "tags": {}},
            {"resource_id": "bucket-1", "resource_type": "s3:bucket", "tags": {}},
            {"resource_id": "table-1", "resource_type": "dynamodb:table", "tags": {}},
        ])
        
        result = await fetch_resources_by_type(aws_client, "all")
        
        assert len(result) == 3
        resource_types = {r["resource_type"] for r in result}
        assert "ec2:instance" in resource_types
        assert "s3:bucket" in resource_types
        assert "dynamodb:table" in resource_types
        aws_client.get_all_tagged_resources.assert_called_once()


class TestFetchAllResourcesViaTaggingApi:
    """Test the fetch_all_resources_via_tagging_api function."""

    @pytest.mark.asyncio
    async def test_fetch_all_resources_success(self):
        """Test successful fetching of all resources."""
        aws_client = MagicMock()
        aws_client.get_all_tagged_resources = AsyncMock(return_value=[
            {"resource_id": "i-123", "resource_type": "ec2:instance", "tags": {"Env": "prod"}},
            {"resource_id": "bucket-1", "resource_type": "s3:bucket", "tags": {}},
        ])
        
        result = await fetch_all_resources_via_tagging_api(aws_client)
        
        assert len(result) == 2
        aws_client.get_all_tagged_resources.assert_called_once_with(
            resource_type_filters=None,
            tag_filters=None
        )

    @pytest.mark.asyncio
    async def test_fetch_all_resources_with_tag_filters(self):
        """Test fetching resources with tag filters."""
        aws_client = MagicMock()
        aws_client.get_all_tagged_resources = AsyncMock(return_value=[
            {"resource_id": "i-123", "resource_type": "ec2:instance", "tags": {"Env": "prod"}},
        ])
        
        filters = {"tag_filters": [{"Key": "Env", "Values": ["prod"]}]}
        result = await fetch_all_resources_via_tagging_api(aws_client, filters)
        
        assert len(result) == 1
        aws_client.get_all_tagged_resources.assert_called_once_with(
            resource_type_filters=None,
            tag_filters=[{"Key": "Env", "Values": ["prod"]}]
        )

    @pytest.mark.asyncio
    async def test_fetch_all_resources_api_error(self):
        """Test handling of API errors."""
        aws_client = MagicMock()
        aws_client.get_all_tagged_resources = AsyncMock(side_effect=Exception("API Error"))
        
        with pytest.raises(Exception, match="API Error"):
            await fetch_all_resources_via_tagging_api(aws_client)


class TestFetchResourcesViaTaggingApi:
    """Test the fetch_resources_via_tagging_api function."""

    @pytest.mark.asyncio
    async def test_fetch_specific_types(self):
        """Test fetching specific resource types via Tagging API."""
        aws_client = MagicMock()
        aws_client.get_all_tagged_resources = AsyncMock(return_value=[
            {"resource_id": "table-1", "resource_type": "dynamodb:table", "tags": {}},
            {"resource_id": "table-2", "resource_type": "dynamodb:table", "tags": {}},
        ])
        
        result = await fetch_resources_via_tagging_api(aws_client, ["dynamodb:table"])
        
        assert len(result) == 2
        aws_client.get_all_tagged_resources.assert_called_once_with(
            resource_type_filters=["dynamodb:table"],
            tag_filters=None
        )

    @pytest.mark.asyncio
    async def test_fetch_multiple_types(self):
        """Test fetching multiple resource types via Tagging API."""
        aws_client = MagicMock()
        aws_client.get_all_tagged_resources = AsyncMock(return_value=[
            {"resource_id": "table-1", "resource_type": "dynamodb:table", "tags": {}},
            {"resource_id": "topic-1", "resource_type": "sns:topic", "tags": {}},
        ])
        
        result = await fetch_resources_via_tagging_api(
            aws_client, 
            ["dynamodb:table", "sns:topic"]
        )
        
        assert len(result) == 2
        aws_client.get_all_tagged_resources.assert_called_once_with(
            resource_type_filters=["dynamodb:table", "sns:topic"],
            tag_filters=None
        )


class TestExtractAccountFromArn:
    """Test the extract_account_from_arn utility function."""

    def test_extract_account_from_arn_valid(self):
        """Test extracting account ID from valid ARN."""
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-123"
        account = extract_account_from_arn(arn)
        assert account == "123456789012"

    def test_extract_account_from_arn_empty(self):
        """Test extracting account from empty ARN."""
        account = extract_account_from_arn("")
        assert account == "unknown"

    def test_extract_account_from_arn_none(self):
        """Test extracting account from None ARN."""
        account = extract_account_from_arn(None)
        assert account == "unknown"

    def test_extract_account_from_arn_invalid_format(self):
        """Test extracting account from invalid ARN format."""
        account = extract_account_from_arn("not-an-arn")
        assert account == "unknown"

    def test_extract_account_from_arn_short_arn(self):
        """Test extracting account from ARN with insufficient parts."""
        arn = "arn:aws:s3"
        account = extract_account_from_arn(arn)
        assert account == "unknown"

    def test_extract_account_from_arn_empty_account_field(self):
        """Test extracting account from ARN with empty account field."""
        arn = "arn:aws:s3:::bucket-name"
        account = extract_account_from_arn(arn)
        assert account == "unknown"

    def test_extract_account_from_arn_lambda(self):
        """Test extracting account from Lambda ARN."""
        arn = "arn:aws:lambda:us-west-2:987654321098:function:my-function"
        account = extract_account_from_arn(arn)
        assert account == "987654321098"


class TestResourceTypeConstants:
    """Test resource type constants and helper functions."""

    def test_supported_resource_types_not_empty(self):
        """Test that SUPPORTED_RESOURCE_TYPES is not empty."""
        assert len(SUPPORTED_RESOURCE_TYPES) > 0
        assert "ec2:instance" in SUPPORTED_RESOURCE_TYPES
        assert "s3:bucket" in SUPPORTED_RESOURCE_TYPES

    def test_tagging_api_resource_types_not_empty(self):
        """Test that TAGGING_API_RESOURCE_TYPES is not empty."""
        assert len(TAGGING_API_RESOURCE_TYPES) > 0
        assert "dynamodb:table" in TAGGING_API_RESOURCE_TYPES
        assert "sns:topic" in TAGGING_API_RESOURCE_TYPES

    def test_tagging_api_includes_supported_types(self):
        """Test that Tagging API types include all supported types."""
        for rt in SUPPORTED_RESOURCE_TYPES:
            assert rt in TAGGING_API_RESOURCE_TYPES

    def test_get_supported_resource_types_returns_copy(self):
        """Test that get_supported_resource_types returns a copy."""
        types1 = get_supported_resource_types()
        types2 = get_supported_resource_types()
        
        # Should be equal but not the same object
        assert types1 == types2
        assert types1 is not types2
        
        # Modifying one shouldn't affect the other
        types1.append("test:type")
        assert "test:type" not in types2

    def test_get_tagging_api_resource_types_returns_copy(self):
        """Test that get_tagging_api_resource_types returns a copy."""
        types1 = get_tagging_api_resource_types()
        types2 = get_tagging_api_resource_types()
        
        # Should be equal but not the same object
        assert types1 == types2
        assert types1 is not types2