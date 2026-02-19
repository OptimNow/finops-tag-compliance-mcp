"""Unit tests for import_aws_tag_policy tool."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.tools.import_aws_tag_policy import (
    AvailablePolicy,
    ImportAwsTagPolicyResult,
    PolicySummary,
    SERVICE_RESOURCE_MAPPINGS,
    _convert_aws_policy,
    _extract_tag_values,
    _parse_enforced_for,
    import_aws_tag_policy,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client with a mock organizations client.

    Note: We do NOT use spec=AWSClient because the tool accesses
    aws_client.session.client("organizations"), and AWSClient does not
    have a 'session' attribute. MagicMock without spec allows this
    attribute chain to be auto-created.
    """
    client = MagicMock()
    client.region = "us-east-1"
    return client


@pytest.fixture
def mock_organizations_client():
    """Create a mock boto3 organizations client."""
    org_client = MagicMock()
    return org_client


@pytest.fixture
def sample_aws_tag_policy():
    """Create a sample AWS Organizations tag policy document."""
    return {
        "tags": {
            "Environment": {
                "tag_key": {"@@assign": "Environment"},
                "tag_value": {
                    "@@assign": ["production", "staging", "development"]
                },
                "enforced_for": {
                    "@@assign": ["ec2:instance", "s3:bucket"]
                },
            },
            "Owner": {
                "tag_key": {"@@assign": "Owner"},
                "enforced_for": {
                    "@@assign": ["ec2:instance"]
                },
            },
            "Project": {
                "tag_key": {"@@assign": "Project"},
                "tag_value": {
                    "@@assign": ["alpha", "beta", "gamma"]
                },
                # No enforced_for -- should become optional
            },
        }
    }


@pytest.fixture
def sample_list_policies_response():
    """Create a sample response from list_policies."""
    return {
        "Policies": [
            {
                "Id": "p-abc12345",
                "Name": "Standard Tags",
                "Description": "Organization tag policy",
                "Type": "TAG_POLICY",
            },
            {
                "Id": "p-def67890",
                "Name": "Cost Allocation Tags",
                "Description": "Tags for cost allocation",
                "Type": "TAG_POLICY",
            },
        ]
    }


@pytest.fixture
def sample_describe_policy_response(sample_aws_tag_policy):
    """Create a sample response from describe_policy."""
    import json

    return {
        "Policy": {
            "PolicySummary": {
                "Id": "p-abc12345",
                "Name": "Standard Tags",
            },
            "Content": json.dumps(sample_aws_tag_policy),
        }
    }


# =============================================================================
# ImportAwsTagPolicyResult Model Tests
# =============================================================================


class TestImportAwsTagPolicyResult:
    """Test ImportAwsTagPolicyResult Pydantic model."""

    def test_model_fields_present(self):
        """Test that all expected fields exist on the model."""
        result = ImportAwsTagPolicyResult(
            status="success",
            policy={"required_tags": [], "optional_tags": []},
            saved_to="/path/to/file.json",
            summary=PolicySummary(
                required_tags_count=2,
                optional_tags_count=1,
                enforced_services=["ec2", "s3"],
            ),
            available_policies=None,
            message="Success",
        )
        assert result.status == "success"
        assert result.policy is not None
        assert result.saved_to == "/path/to/file.json"
        assert result.summary.required_tags_count == 2
        assert result.summary.optional_tags_count == 1
        assert result.available_policies is None
        assert result.message == "Success"
        assert isinstance(result.conversion_timestamp, datetime)

    def test_default_values(self):
        """Test that optional fields have correct defaults."""
        result = ImportAwsTagPolicyResult(status="error")
        assert result.policy is None
        assert result.saved_to is None
        assert result.summary is None
        assert result.available_policies is None
        assert result.message == ""
        assert result.conversion_timestamp is not None

    def test_listed_status_with_available_policies(self):
        """Test model with listed status and available_policies populated."""
        result = ImportAwsTagPolicyResult(
            status="listed",
            available_policies=[
                AvailablePolicy(
                    policy_id="p-abc",
                    policy_name="Test Policy",
                    description="A test policy",
                ),
            ],
            message="Found 1 policy",
        )
        assert result.status == "listed"
        assert len(result.available_policies) == 1
        assert result.available_policies[0].policy_id == "p-abc"

    def test_error_status(self):
        """Test model with error status."""
        result = ImportAwsTagPolicyResult(
            status="error",
            message="Insufficient permissions",
        )
        assert result.status == "error"
        assert "permissions" in result.message

    def test_saved_status(self):
        """Test model with saved status."""
        result = ImportAwsTagPolicyResult(
            status="saved",
            policy={"required_tags": []},
            saved_to="policies/tagging_policy.json",
            message="Saved successfully",
        )
        assert result.status == "saved"
        assert result.saved_to is not None

    def test_model_serialization(self):
        """Test that the model can be serialized to dict."""
        result = ImportAwsTagPolicyResult(
            status="success",
            message="OK",
        )
        result_dict = result.model_dump(mode="json")
        assert "status" in result_dict
        assert "message" in result_dict
        assert "conversion_timestamp" in result_dict


# =============================================================================
# PolicySummary Model Tests
# =============================================================================


class TestPolicySummary:
    """Test PolicySummary Pydantic model."""

    def test_default_values(self):
        """Test PolicySummary defaults."""
        summary = PolicySummary()
        assert summary.required_tags_count == 0
        assert summary.optional_tags_count == 0
        assert summary.enforced_services == []

    def test_with_values(self):
        """Test PolicySummary with populated values."""
        summary = PolicySummary(
            required_tags_count=3,
            optional_tags_count=2,
            enforced_services=["ec2", "rds", "s3"],
        )
        assert summary.required_tags_count == 3
        assert summary.optional_tags_count == 2
        assert len(summary.enforced_services) == 3


# =============================================================================
# AvailablePolicy Model Tests
# =============================================================================


class TestAvailablePolicy:
    """Test AvailablePolicy Pydantic model."""

    def test_required_fields(self):
        """Test that policy_id and policy_name are required."""
        policy = AvailablePolicy(
            policy_id="p-abc12345",
            policy_name="Test Policy",
        )
        assert policy.policy_id == "p-abc12345"
        assert policy.policy_name == "Test Policy"
        assert policy.description == ""

    def test_with_description(self):
        """Test AvailablePolicy with a description."""
        policy = AvailablePolicy(
            policy_id="p-abc12345",
            policy_name="Test Policy",
            description="A test tag policy",
        )
        assert policy.description == "A test tag policy"


# =============================================================================
# _convert_aws_policy Tests
# =============================================================================


class TestConvertAwsPolicy:
    """Test the _convert_aws_policy conversion function."""

    def test_basic_conversion(self, sample_aws_tag_policy):
        """Test basic conversion from AWS format to MCP format."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        assert "required_tags" in result
        assert "optional_tags" in result
        assert "version" in result
        assert "metadata" in result

    def test_assign_tag_key_extracted(self, sample_aws_tag_policy):
        """Test that @@assign tag_key names are extracted correctly."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        required_names = [t["name"] for t in result["required_tags"]]
        assert "Environment" in required_names
        assert "Owner" in required_names

    def test_tag_values_extracted(self, sample_aws_tag_policy):
        """Test that @@assign tag_value allowed_values are extracted."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        env_tag = next(
            t for t in result["required_tags"] if t["name"] == "Environment"
        )
        assert env_tag["allowed_values"] == [
            "production",
            "staging",
            "development",
        ]

    def test_enforced_for_becomes_applies_to(self, sample_aws_tag_policy):
        """Test that enforced_for is converted to applies_to."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        env_tag = next(
            t for t in result["required_tags"] if t["name"] == "Environment"
        )
        assert "ec2:instance" in env_tag["applies_to"]
        assert "s3:bucket" in env_tag["applies_to"]

    def test_tags_with_enforced_for_are_required(self, sample_aws_tag_policy):
        """Test that tags with enforced_for become required_tags."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        required_names = [t["name"] for t in result["required_tags"]]
        assert "Environment" in required_names
        assert "Owner" in required_names

    def test_tags_without_enforced_for_are_optional(self, sample_aws_tag_policy):
        """Test that tags without enforced_for become optional_tags."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        optional_names = [t["name"] for t in result["optional_tags"]]
        assert "Project" in optional_names

    def test_tag_entry_has_all_fields(self, sample_aws_tag_policy):
        """Test that each converted tag entry has all required MCP fields."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        for tag in result["required_tags"] + result["optional_tags"]:
            assert "name" in tag
            assert "description" in tag
            assert "allowed_values" in tag
            assert "validation_regex" in tag
            assert "applies_to" in tag

    def test_validation_regex_is_none(self, sample_aws_tag_policy):
        """Test that validation_regex is always None (AWS format does not have it)."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        for tag in result["required_tags"] + result["optional_tags"]:
            assert tag["validation_regex"] is None

    def test_description_mentions_aws_organizations(self, sample_aws_tag_policy):
        """Test that description references AWS Organizations."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        for tag in result["required_tags"] + result["optional_tags"]:
            assert "AWS Organizations" in tag["description"]

    def test_metadata_source_is_aws_organizations(self, sample_aws_tag_policy):
        """Test that metadata.source is 'aws_organizations'."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        assert result["metadata"]["source"] == "aws_organizations"

    def test_metadata_has_imported_at(self, sample_aws_tag_policy):
        """Test that metadata has an imported_at timestamp."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        assert "imported_at" in result["metadata"]

    def test_empty_tags_section(self):
        """Test conversion of empty tags section."""
        result = _convert_aws_policy({"tags": {}})
        assert result["required_tags"] == []
        assert result["optional_tags"] == []

    def test_no_tags_key(self):
        """Test conversion when 'tags' key is missing."""
        result = _convert_aws_policy({})
        assert result["required_tags"] == []
        assert result["optional_tags"] == []

    def test_tag_key_fallback_to_dict_key(self):
        """Test that when tag_key has no @@assign, the dict key is used as name."""
        aws_policy = {
            "tags": {
                "MyTag": {
                    "tag_key": {},
                    "enforced_for": {"@@assign": ["ec2:instance"]},
                }
            }
        }
        result = _convert_aws_policy(aws_policy)
        assert result["required_tags"][0]["name"] == "MyTag"

    def test_tag_key_not_dict(self):
        """Test that when tag_key is not a dict, the dict key is used."""
        aws_policy = {
            "tags": {
                "SimpleTag": {
                    "tag_key": "some_string",
                    "enforced_for": {"@@assign": ["s3:bucket"]},
                }
            }
        }
        result = _convert_aws_policy(aws_policy)
        assert result["required_tags"][0]["name"] == "SimpleTag"

    def test_owner_tag_no_allowed_values(self, sample_aws_tag_policy):
        """Test that Owner tag (no tag_value) has allowed_values=None."""
        result = _convert_aws_policy(sample_aws_tag_policy)
        owner_tag = next(
            t for t in result["required_tags"] if t["name"] == "Owner"
        )
        assert owner_tag["allowed_values"] is None


# =============================================================================
# _extract_tag_values Tests
# =============================================================================


class TestExtractTagValues:
    """Test the _extract_tag_values helper function."""

    def test_none_input(self):
        """Test that None input returns None."""
        assert _extract_tag_values(None) is None

    def test_empty_dict(self):
        """Test that empty dict returns None."""
        assert _extract_tag_values({}) is None

    def test_dict_with_assign(self):
        """Test extracting values from dict with @@assign."""
        result = _extract_tag_values({"@@assign": ["a", "b", "c"]})
        assert result == ["a", "b", "c"]

    def test_dict_with_assign_empty_list(self):
        """Test that empty @@assign list returns None."""
        result = _extract_tag_values({"@@assign": []})
        assert result is None

    def test_list_input(self):
        """Test extracting values from a plain list."""
        result = _extract_tag_values(["x", "y", "z"])
        assert result == ["x", "y", "z"]

    def test_wildcard_removal(self):
        """Test that trailing wildcards are removed from values."""
        result = _extract_tag_values({"@@assign": ["prod*", "staging*"]})
        assert result == ["prod", "staging"]

    def test_pure_wildcard_removed(self):
        """Test that a pure wildcard ('*') value is removed entirely."""
        result = _extract_tag_values({"@@assign": ["*"]})
        # "*" becomes "" after stripping, which is falsy, so it's filtered out
        assert result is None

    def test_mixed_values_and_wildcards(self):
        """Test mixed concrete values and wildcards."""
        result = _extract_tag_values(
            {"@@assign": ["production", "dev*", "*", "staging"]}
        )
        assert "production" in result
        assert "dev" in result
        assert "staging" in result
        assert "*" not in result
        assert "" not in result

    def test_non_string_values_skipped(self):
        """Test that non-string values in the list are skipped."""
        result = _extract_tag_values({"@@assign": [123, "valid"]})
        assert result == ["valid"]

    def test_non_dict_non_list_returns_none(self):
        """Test that a non-dict, non-list input returns None."""
        assert _extract_tag_values("some_string") is None
        assert _extract_tag_values(42) is None

    def test_dict_without_assign_key(self):
        """Test dict without @@assign returns None (empty list from .get)."""
        result = _extract_tag_values({"other_key": ["a"]})
        assert result is None


# =============================================================================
# _parse_enforced_for Tests
# =============================================================================


class TestParseEnforcedFor:
    """Test the _parse_enforced_for helper function."""

    def test_none_input(self):
        """Test that None input returns empty list."""
        assert _parse_enforced_for(None) == []

    def test_empty_dict(self):
        """Test that empty dict returns empty list."""
        assert _parse_enforced_for({}) == []

    def test_dict_with_assign_list(self):
        """Test extracting resources from dict with @@assign list."""
        result = _parse_enforced_for(
            {"@@assign": ["ec2:instance", "s3:bucket"]}
        )
        assert result == ["ec2:instance", "s3:bucket"]

    def test_plain_list_input(self):
        """Test extracting resources from a plain list."""
        result = _parse_enforced_for(["rds:db", "lambda:function"])
        assert result == ["rds:db", "lambda:function"]

    def test_all_supported_expansion(self):
        """Test that ec2:ALL_SUPPORTED is expanded to ec2 resource types."""
        result = _parse_enforced_for(
            {"@@assign": ["ec2:ALL_SUPPORTED"]}
        )
        assert "ec2:instance" in result
        assert "ec2:volume" in result

    def test_wildcard_expansion(self):
        """Test that s3:* is expanded like ALL_SUPPORTED."""
        result = _parse_enforced_for({"@@assign": ["s3:*"]})
        assert "s3:bucket" in result

    def test_unknown_service_all_supported(self):
        """Test ALL_SUPPORTED for an unmapped service uses fallback."""
        result = _parse_enforced_for(
            {"@@assign": ["unknownsvc:ALL_SUPPORTED"]}
        )
        assert result == ["unknownsvc:resource"]

    def test_unknown_service_wildcard(self):
        """Test wildcard for an unmapped service uses fallback."""
        result = _parse_enforced_for({"@@assign": ["unknownsvc:*"]})
        assert result == ["unknownsvc:resource"]

    def test_non_string_resources_skipped(self):
        """Test that non-string items in the resource list are skipped."""
        result = _parse_enforced_for({"@@assign": [123, "ec2:instance"]})
        assert result == ["ec2:instance"]

    def test_non_dict_non_list_returns_empty(self):
        """Test that a non-dict, non-list input returns empty list."""
        assert _parse_enforced_for("some_string") == []
        assert _parse_enforced_for(42) == []

    def test_mixed_explicit_and_wildcard(self):
        """Test a mix of explicit resources and wildcards."""
        result = _parse_enforced_for(
            {"@@assign": ["ec2:instance", "s3:*", "rds:db"]}
        )
        assert "ec2:instance" in result
        assert "s3:bucket" in result
        assert "rds:db" in result

    def test_lambda_all_supported(self):
        """Test ALL_SUPPORTED expansion for Lambda."""
        result = _parse_enforced_for(
            {"@@assign": ["lambda:ALL_SUPPORTED"]}
        )
        assert result == ["lambda:function"]

    def test_ecs_all_supported(self):
        """Test ALL_SUPPORTED expansion for ECS."""
        result = _parse_enforced_for(
            {"@@assign": ["ecs:ALL_SUPPORTED"]}
        )
        assert "ecs:service" in result
        assert "ecs:cluster" in result

    def test_glue_all_supported(self):
        """Test ALL_SUPPORTED expansion for Glue (multiple resource types)."""
        result = _parse_enforced_for(
            {"@@assign": ["glue:ALL_SUPPORTED"]}
        )
        assert "glue:job" in result
        assert "glue:crawler" in result
        assert "glue:database" in result


# =============================================================================
# SERVICE_RESOURCE_MAPPINGS Tests
# =============================================================================


class TestServiceResourceMappings:
    """Test the SERVICE_RESOURCE_MAPPINGS constant."""

    def test_has_expected_services(self):
        """Test that all expected AWS services are in the mapping."""
        expected_services = [
            "ec2",
            "s3",
            "rds",
            "lambda",
            "ecs",
            "eks",
            "dynamodb",
            "opensearch",
            "sns",
            "sqs",
            "kms",
        ]
        for service in expected_services:
            assert service in SERVICE_RESOURCE_MAPPINGS, (
                f"Missing service '{service}' in SERVICE_RESOURCE_MAPPINGS"
            )

    def test_ec2_has_instance_and_volume(self):
        """Test that EC2 maps to both instance and volume."""
        assert "ec2:instance" in SERVICE_RESOURCE_MAPPINGS["ec2"]
        assert "ec2:volume" in SERVICE_RESOURCE_MAPPINGS["ec2"]

    def test_s3_has_bucket(self):
        """Test that S3 maps to bucket."""
        assert SERVICE_RESOURCE_MAPPINGS["s3"] == ["s3:bucket"]

    def test_all_values_follow_format(self):
        """Test that all mapped values follow the 'service:type' format."""
        for service, types in SERVICE_RESOURCE_MAPPINGS.items():
            for resource_type in types:
                assert ":" in resource_type, (
                    f"Resource type '{resource_type}' for service '{service}' "
                    f"does not follow 'service:type' format"
                )


# =============================================================================
# import_aws_tag_policy - List Mode Tests
# =============================================================================


class TestListPoliciesMode:
    """Test import_aws_tag_policy in listing mode (policy_id=None)."""

    @pytest.mark.asyncio
    async def test_list_returns_available_policies(
        self, mock_aws_client, sample_list_policies_response
    ):
        """Test that listing mode returns available policies."""
        mock_org_client = MagicMock()
        mock_org_client.list_policies.return_value = (
            sample_list_policies_response
        )
        mock_aws_client.session.client.return_value = mock_org_client

        with patch("asyncio.to_thread") as mock_thread:
            # First call: session.client("organizations") -> mock_org_client
            # Second call: mock_org_client.list_policies(...) -> response
            mock_thread.side_effect = [
                mock_org_client,
                sample_list_policies_response,
            ]

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id=None,
            )

        assert result.status == "listed"
        assert result.available_policies is not None
        assert len(result.available_policies) == 2
        assert result.available_policies[0].policy_id == "p-abc12345"
        assert result.available_policies[0].policy_name == "Standard Tags"
        assert result.available_policies[1].policy_id == "p-def67890"

    @pytest.mark.asyncio
    async def test_list_no_policies_found(self, mock_aws_client):
        """Test listing when no tag policies exist."""
        mock_org_client = MagicMock()
        mock_org_client.list_policies.return_value = {"Policies": []}
        mock_aws_client.session.client.return_value = mock_org_client

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = [
                mock_org_client,
                {"Policies": []},
            ]

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id=None,
            )

        assert result.status == "listed"
        assert result.available_policies == []
        assert "No tag policies found" in result.message

    @pytest.mark.asyncio
    async def test_list_access_denied_returns_error(self, mock_aws_client):
        """Test that AccessDenied during listing returns error status."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = Exception(
                "AccessDenied: User is not authorized to perform organizations:ListPolicies"
            )

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id=None,
            )

        assert result.status == "error"
        assert "permissions" in result.message.lower()

    @pytest.mark.asyncio
    async def test_list_generic_error_returns_error(self, mock_aws_client):
        """Test that a generic error during listing returns error status."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = Exception("Connection timeout")

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id=None,
            )

        assert result.status == "error"
        assert "Connection timeout" in result.message


# =============================================================================
# import_aws_tag_policy - Import Mode Tests
# =============================================================================


class TestImportPolicyMode:
    """Test import_aws_tag_policy in import mode (with policy_id)."""

    @pytest.mark.asyncio
    async def test_import_success_without_save(
        self, mock_aws_client, sample_describe_policy_response
    ):
        """Test successful import without saving to file."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_org_client = MagicMock()
            mock_thread.side_effect = [
                mock_org_client,
                sample_describe_policy_response,
            ]

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id="p-abc12345",
                save_to_file=False,
            )

        assert result.status == "success"
        assert result.policy is not None
        assert result.saved_to is None
        assert result.summary is not None
        assert result.summary.required_tags_count == 2  # Environment, Owner
        assert result.summary.optional_tags_count == 1  # Project
        assert "p-abc12345" in result.message

    @pytest.mark.asyncio
    async def test_import_success_with_save(
        self, mock_aws_client, sample_describe_policy_response, tmp_path
    ):
        """Test successful import with saving to file."""
        output_file = str(tmp_path / "test_policy.json")

        with patch("asyncio.to_thread") as mock_thread:
            mock_org_client = MagicMock()
            mock_thread.side_effect = [
                mock_org_client,
                sample_describe_policy_response,
            ]

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id="p-abc12345",
                save_to_file=True,
                output_path=output_file,
            )

        assert result.status == "saved"
        assert result.saved_to == output_file
        assert "Saved to" in result.message

        # Verify the file was actually written
        import json

        with open(output_file, "r", encoding="utf-8") as f:
            saved_policy = json.load(f)
        assert "required_tags" in saved_policy
        assert "optional_tags" in saved_policy

    @pytest.mark.asyncio
    async def test_import_policy_has_correct_structure(
        self, mock_aws_client, sample_describe_policy_response
    ):
        """Test that imported policy has correct MCP format structure."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_org_client = MagicMock()
            mock_thread.side_effect = [
                mock_org_client,
                sample_describe_policy_response,
            ]

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id="p-abc12345",
                save_to_file=False,
            )

        policy = result.policy
        assert "version" in policy
        assert "required_tags" in policy
        assert "optional_tags" in policy
        assert "metadata" in policy

    @pytest.mark.asyncio
    async def test_import_summary_enforced_services(
        self, mock_aws_client, sample_describe_policy_response
    ):
        """Test that summary.enforced_services is correctly populated."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_org_client = MagicMock()
            mock_thread.side_effect = [
                mock_org_client,
                sample_describe_policy_response,
            ]

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id="p-abc12345",
                save_to_file=False,
            )

        assert result.summary is not None
        # Environment applies to ec2:instance and s3:bucket, Owner applies to ec2:instance
        assert "ec2" in result.summary.enforced_services
        assert "s3" in result.summary.enforced_services

    @pytest.mark.asyncio
    async def test_import_summary_enforced_services_sorted(
        self, mock_aws_client, sample_describe_policy_response
    ):
        """Test that summary.enforced_services is sorted."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_org_client = MagicMock()
            mock_thread.side_effect = [
                mock_org_client,
                sample_describe_policy_response,
            ]

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id="p-abc12345",
                save_to_file=False,
            )

        services = result.summary.enforced_services
        assert services == sorted(services)


# =============================================================================
# import_aws_tag_policy - Error Handling Tests
# =============================================================================


class TestImportErrorHandling:
    """Test error handling during import."""

    @pytest.mark.asyncio
    async def test_access_denied_returns_error_result(self, mock_aws_client):
        """Test that AccessDenied during fetch returns error result, not exception."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = Exception(
                "AccessDenied: User is not authorized to perform "
                "organizations:DescribePolicy"
            )

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id="p-abc12345",
                save_to_file=False,
            )

        assert result.status == "error"
        assert "permissions" in result.message.lower()
        assert "organizations:DescribePolicy" in result.message

    @pytest.mark.asyncio
    async def test_not_authorized_returns_error_result(self, mock_aws_client):
        """Test 'not authorized' phrasing in error is also caught."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = Exception(
                "User: arn:aws:iam::123:role/test is not authorized to perform this action"
            )

            result = await import_aws_tag_policy(
                aws_client=mock_aws_client,
                policy_id="p-abc12345",
                save_to_file=False,
            )

        assert result.status == "error"
        assert "permissions" in result.message.lower()

    @pytest.mark.asyncio
    async def test_generic_error_raises(self, mock_aws_client):
        """Test that a non-auth error during fetch is re-raised."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = RuntimeError("Network unreachable")

            with pytest.raises(RuntimeError, match="Network unreachable"):
                await import_aws_tag_policy(
                    aws_client=mock_aws_client,
                    policy_id="p-abc12345",
                    save_to_file=False,
                )

    @pytest.mark.asyncio
    async def test_save_failure_returns_error_with_policy(
        self, mock_aws_client, sample_describe_policy_response
    ):
        """Test that file save failure returns error but includes converted policy."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_org_client = MagicMock()
            mock_thread.side_effect = [
                mock_org_client,
                sample_describe_policy_response,
            ]

            # Patch Path.parent.mkdir to succeed, but open() to fail with
            # PermissionError, simulating a write failure cross-platform.
            with patch(
                "builtins.open",
                side_effect=PermissionError("Permission denied"),
            ):
                result = await import_aws_tag_policy(
                    aws_client=mock_aws_client,
                    policy_id="p-abc12345",
                    save_to_file=True,
                    output_path="policies/test_output.json",
                )

        assert result.status == "error"
        assert result.policy is not None  # Policy still available even on save failure
        assert result.summary is not None
        assert "failed to save" in result.message.lower()
