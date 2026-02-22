"""Unit tests for EC2 instance state enrichment in the Tagging API path.

The Resource Groups Tagging API returns EC2 instances without state information,
so terminated instances can slip past the compliance service safety net filter.
The _enrich_ec2_instance_states method calls describe_instances to fetch actual
state and enrich the resource entries before they reach the filter.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.clients.aws_client import AWSClient


@pytest.fixture
def mock_aws_client():
    """Create a minimally-mocked AWSClient for enrichment tests."""
    with patch.object(AWSClient, "__init__", lambda self, **kwargs: None):
        client = AWSClient()
        client.region = "us-east-1"
        client.ec2 = MagicMock()
        client._last_call_time = {}
        client._min_call_interval = 0.0
        return client


def _make_ec2_resource(instance_id, region="us-east-1", instance_state=None):
    """Helper to create an EC2 resource dict as returned by get_all_tagged_resources."""
    resource = {
        "resource_id": instance_id,
        "resource_type": "ec2:instance",
        "region": region,
        "tags": {"Name": "test"},
        "arn": f"arn:aws:ec2:{region}:123456789012:instance/{instance_id}",
        "created_at": None,
    }
    if instance_state:
        resource["instance_state"] = instance_state
    return resource


def _make_s3_resource(bucket_name):
    """Helper to create an S3 resource dict."""
    return {
        "resource_id": bucket_name,
        "resource_type": "s3:bucket",
        "region": "global",
        "tags": {},
        "arn": f"arn:aws:s3:::{bucket_name}",
        "created_at": None,
    }


def _describe_instances_response(instances):
    """Build a describe_instances response from a list of (id, state, type) tuples."""
    return {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": iid,
                        "State": {"Name": state},
                        "InstanceType": itype,
                    }
                    for iid, state, itype in instances
                ]
            }
        ]
    }


class TestEnrichEC2InstanceStates:
    """Tests for AWSClient._enrich_ec2_instance_states."""

    @pytest.mark.asyncio
    async def test_enriches_terminated_instances(self, mock_aws_client):
        """Terminated instances get their state populated so the safety net can filter them."""
        resources = [
            _make_ec2_resource("i-terminated1"),
            _make_ec2_resource("i-running1"),
        ]

        mock_aws_client.ec2.describe_instances.return_value = _describe_instances_response([
            ("i-terminated1", "terminated", "t3.micro"),
            ("i-running1", "running", "t3.medium"),
        ])

        result = await mock_aws_client._enrich_ec2_instance_states(resources)

        assert result[0]["instance_state"] == "terminated"
        assert result[0]["instance_type"] == "t3.micro"
        assert result[1]["instance_state"] == "running"
        assert result[1]["instance_type"] == "t3.medium"

    @pytest.mark.asyncio
    async def test_skips_non_ec2_resources(self, mock_aws_client):
        """S3 buckets and other non-EC2 resources are not touched."""
        resources = [
            _make_s3_resource("my-bucket"),
            _make_ec2_resource("i-abc123"),
        ]

        mock_aws_client.ec2.describe_instances.return_value = _describe_instances_response([
            ("i-abc123", "running", "t3.small"),
        ])

        result = await mock_aws_client._enrich_ec2_instance_states(resources)

        # S3 resource unchanged
        assert "instance_state" not in result[0]
        # EC2 enriched
        assert result[1]["instance_state"] == "running"

    @pytest.mark.asyncio
    async def test_skips_already_enriched_instances(self, mock_aws_client):
        """Instances that already have instance_state are not re-fetched."""
        resources = [
            _make_ec2_resource("i-already", instance_state="running"),
        ]

        result = await mock_aws_client._enrich_ec2_instance_states(resources)

        # No describe_instances call should have been made
        mock_aws_client.ec2.describe_instances.assert_not_called()
        assert result[0]["instance_state"] == "running"

    @pytest.mark.asyncio
    async def test_no_ec2_instances_skips_api_call(self, mock_aws_client):
        """When there are no EC2 instances, no API call is made."""
        resources = [
            _make_s3_resource("bucket-1"),
            _make_s3_resource("bucket-2"),
        ]

        result = await mock_aws_client._enrich_ec2_instance_states(resources)

        mock_aws_client.ec2.describe_instances.assert_not_called()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self, mock_aws_client):
        """Empty resource list returns empty."""
        result = await mock_aws_client._enrich_ec2_instance_states([])

        mock_aws_client.ec2.describe_instances.assert_not_called()
        assert result == []

    @pytest.mark.asyncio
    async def test_graceful_failure_on_api_error(self, mock_aws_client):
        """If describe_instances fails, resources are returned unenriched."""
        resources = [
            _make_ec2_resource("i-fail1"),
        ]

        mock_aws_client.ec2.describe_instances.side_effect = Exception("AccessDenied")

        result = await mock_aws_client._enrich_ec2_instance_states(resources)

        # Resource returned without state — safety net will have to handle it
        assert len(result) == 1
        assert "instance_state" not in result[0]

    @pytest.mark.asyncio
    async def test_batches_large_instance_lists(self, mock_aws_client):
        """More than 100 instances are batched into multiple API calls."""
        # Create 150 instances
        resources = [_make_ec2_resource(f"i-{i:04d}") for i in range(150)]

        # Mock two batched responses
        batch1_instances = [(f"i-{i:04d}", "running", "t3.micro") for i in range(100)]
        batch2_instances = [(f"i-{i:04d}", "terminated", "t3.micro") for i in range(100, 150)]

        mock_aws_client.ec2.describe_instances.side_effect = [
            _describe_instances_response(batch1_instances),
            _describe_instances_response(batch2_instances),
        ]

        result = await mock_aws_client._enrich_ec2_instance_states(resources)

        # Two API calls made (100 + 50)
        assert mock_aws_client.ec2.describe_instances.call_count == 2

        # First 100 running, last 50 terminated
        assert result[0]["instance_state"] == "running"
        assert result[149]["instance_state"] == "terminated"

    @pytest.mark.asyncio
    async def test_partial_enrichment_on_missing_instance(self, mock_aws_client):
        """If an instance ID is not returned by describe_instances, it stays unenriched."""
        resources = [
            _make_ec2_resource("i-exists"),
            _make_ec2_resource("i-gone"),  # Deleted between Tagging API call and describe
        ]

        # Only i-exists is returned
        mock_aws_client.ec2.describe_instances.return_value = _describe_instances_response([
            ("i-exists", "running", "t3.medium"),
        ])

        result = await mock_aws_client._enrich_ec2_instance_states(resources)

        assert result[0]["instance_state"] == "running"
        assert "instance_state" not in result[1]  # Not enriched
