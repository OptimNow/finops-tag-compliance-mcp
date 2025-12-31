"""Tests for shared resource utilities."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_server.utils.resource_utils import fetch_resources_by_type, extract_account_from_arn


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
    async def test_fetch_resources_by_type_unknown_type(self):
        """Test handling of unknown resource type."""
        aws_client = MagicMock()
        
        result = await fetch_resources_by_type(aws_client, "unknown:type")
        
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_resources_by_type_api_error(self):
        """Test handling of API errors."""
        aws_client = MagicMock()
        aws_client.get_s3_buckets = AsyncMock(side_effect=Exception("API Error"))
        
        with pytest.raises(Exception, match="API Error"):
            await fetch_resources_by_type(aws_client, "s3:bucket")


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