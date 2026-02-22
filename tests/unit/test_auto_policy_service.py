"""Unit tests for AutoPolicyService (Phase 2.4).

Tests the auto-policy detection and loading service that determines
the tagging policy source on server startup:
1. Existing policy file -> use as-is
2. AWS Organizations tag policy -> import and convert
3. Fallback -> create a sensible default policy
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.services.auto_policy_service import (
    DEFAULT_POLICY,
    SERVICE_RESOURCE_MAPPINGS,
    AutoPolicyResult,
    AutoPolicyService,
    _convert_aws_policy,
    _extract_tag_values,
    _parse_enforced_for,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tmp_policy_path(tmp_path):
    """Return a path to a temporary policy file location (does not create the file)."""
    return str(tmp_path / "policies" / "tagging_policy.json")


@pytest.fixture
def existing_policy_path(tmp_path):
    """Create a temporary policy file that already exists."""
    policy_dir = tmp_path / "policies"
    policy_dir.mkdir(parents=True)
    policy_file = policy_dir / "tagging_policy.json"
    policy_file.write_text(
        json.dumps(
            {
                "version": "1.0",
                "required_tags": [{"name": "Team", "applies_to": []}],
                "optional_tags": [],
            }
        ),
        encoding="utf-8",
    )
    return str(policy_file)


@pytest.fixture
def mock_aws_session():
    """Create a mock boto3 session with Organizations client."""
    session = MagicMock()
    org_client = MagicMock()
    session.client.return_value = org_client
    return session, org_client


@pytest.fixture
def sample_aws_tag_policy():
    """A sample AWS Organizations tag policy in AWS native format."""
    return {
        "tags": {
            "Environment": {
                "tag_key": {"@@assign": "Environment"},
                "tag_value": {"@@assign": ["production", "staging", "development"]},
                "enforced_for": {"@@assign": ["ec2:instance", "rds:db"]},
            },
            "Owner": {
                "tag_key": {"@@assign": "Owner"},
                "tag_value": None,
                "enforced_for": {"@@assign": ["ec2:instance"]},
            },
            "Project": {
                "tag_key": {"@@assign": "Project"},
            },
        }
    }


# =============================================================================
# AutoPolicyResult Tests
# =============================================================================


class TestAutoPolicyResult:
    """Tests for the AutoPolicyResult data class."""

    def test_result_attributes(self):
        result = AutoPolicyResult(
            source="existing_file",
            policy_path="/path/to/policy.json",
            success=True,
            message="Found existing file",
            aws_policy_id="p-123",
        )
        assert result.source == "existing_file"
        assert result.policy_path == "/path/to/policy.json"
        assert result.success is True
        assert result.message == "Found existing file"
        assert result.aws_policy_id == "p-123"

    def test_result_optional_aws_policy_id(self):
        result = AutoPolicyResult(
            source="default",
            policy_path="/path/to/policy.json",
            success=True,
            message="Default created",
        )
        assert result.aws_policy_id is None


# =============================================================================
# Step 1: Existing Policy File
# =============================================================================


class TestExistingPolicyFile:
    """Tests for when a policy file already exists on disk."""

    async def test_existing_file_returns_immediately(self, existing_policy_path):
        """When a policy file exists, detect_and_load returns source='existing_file'."""
        service = AutoPolicyService(policy_path=existing_policy_path)
        result = await service.detect_and_load()

        assert result.source == "existing_file"
        assert result.success is True
        assert result.policy_path == existing_policy_path
        assert "existing" in result.message.lower() or "Using" in result.message

    async def test_existing_file_skips_aws_import(
        self, existing_policy_path, mock_aws_session
    ):
        """Even with auto_import=True and a session, existing file wins."""
        session, org_client = mock_aws_session
        service = AutoPolicyService(
            policy_path=existing_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "existing_file"
        # Should never call Organizations API
        session.client.assert_not_called()

    async def test_existing_file_with_fallback_disabled(self, existing_policy_path):
        """Existing file takes precedence even when fallback is disabled."""
        service = AutoPolicyService(
            policy_path=existing_policy_path,
            fallback_to_default=False,
        )
        result = await service.detect_and_load()

        assert result.source == "existing_file"
        assert result.success is True


# =============================================================================
# Step 2: AWS Organizations Import
# =============================================================================


class TestAWSOrganizationsImport:
    """Tests for importing tag policies from AWS Organizations."""

    async def test_aws_import_success(
        self, tmp_policy_path, mock_aws_session, sample_aws_tag_policy
    ):
        """Successful AWS Organizations import saves policy and returns source='aws_organizations'."""
        session, org_client = mock_aws_session
        org_client.list_policies.return_value = {
            "Policies": [
                {"Id": "p-abc123", "Name": "TagPolicy", "Description": "Test"}
            ]
        }
        org_client.describe_policy.return_value = {
            "Policy": {"Content": json.dumps(sample_aws_tag_policy)}
        }

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "aws_organizations"
        assert result.success is True
        assert result.aws_policy_id == "p-abc123"
        assert "p-abc123" in result.message

        # Verify file was written
        saved = json.loads(Path(tmp_policy_path).read_text(encoding="utf-8"))
        assert saved["version"] == "1.0"
        assert saved["metadata"]["source"] == "aws_organizations"
        # Environment tag had enforced_for, so should be required
        required_names = [t["name"] for t in saved["required_tags"]]
        assert "Environment" in required_names
        assert "Owner" in required_names

    async def test_aws_import_with_specific_policy_id(
        self, tmp_policy_path, mock_aws_session, sample_aws_tag_policy
    ):
        """When aws_policy_id is provided, it uses that ID directly without listing."""
        session, org_client = mock_aws_session
        org_client.describe_policy.return_value = {
            "Policy": {"Content": json.dumps(sample_aws_tag_policy)}
        }

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
            aws_policy_id="p-specific456",
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "aws_organizations"
        assert result.success is True
        assert result.aws_policy_id == "p-specific456"
        # Should NOT call list_policies when ID is specified
        org_client.list_policies.assert_not_called()
        org_client.describe_policy.assert_called_once()

    async def test_aws_import_no_policies_found(
        self, tmp_policy_path, mock_aws_session
    ):
        """When AWS Organizations has no tag policies, falls through to default."""
        session, org_client = mock_aws_session
        org_client.list_policies.return_value = {"Policies": []}

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        # Should fall through to default
        assert result.source == "default"
        assert result.success is True

    async def test_aws_import_access_denied(self, tmp_policy_path, mock_aws_session):
        """AccessDenied from AWS Organizations falls through gracefully."""
        session, org_client = mock_aws_session
        org_client.list_policies.side_effect = Exception(
            "An error occurred (AccessDenied) when calling the ListPolicies operation"
        )

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "default"
        assert result.success is True

    async def test_aws_import_organizations_not_in_use(
        self, tmp_policy_path, mock_aws_session
    ):
        """AWSOrganizationsNotInUse falls through gracefully."""
        session, org_client = mock_aws_session
        org_client.list_policies.side_effect = Exception(
            "AWSOrganizationsNotInUseException: Your account is not part of an organization"
        )

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "default"
        assert result.success is True

    async def test_aws_import_generic_exception(
        self, tmp_policy_path, mock_aws_session
    ):
        """Generic AWS exception falls through to default."""
        session, org_client = mock_aws_session
        org_client.list_policies.side_effect = Exception("Network timeout")

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "default"
        assert result.success is True

    async def test_aws_import_client_creation_failure(
        self, tmp_policy_path
    ):
        """If creating the Organizations client itself throws, falls through."""
        session = MagicMock()
        session.client.side_effect = Exception("Cannot create client")

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "default"
        assert result.success is True


# =============================================================================
# Step 2b: AWS Import Disabled / No Session
# =============================================================================


class TestAWSImportDisabled:
    """Tests for scenarios where AWS import is skipped."""

    async def test_auto_import_disabled(self, tmp_policy_path):
        """When auto_import=False, skips AWS and goes straight to default."""
        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=False,
        )
        result = await service.detect_and_load(aws_session=MagicMock())

        assert result.source == "default"
        assert result.success is True

    async def test_no_aws_session(self, tmp_policy_path):
        """When aws_session is None, skips AWS import."""
        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=None)

        assert result.source == "default"
        assert result.success is True

    async def test_no_aws_session_and_auto_import_false(self, tmp_policy_path):
        """Both disabled: goes straight to default."""
        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=False,
        )
        result = await service.detect_and_load(aws_session=None)

        assert result.source == "default"
        assert result.success is True


# =============================================================================
# Step 3: Default Policy Creation
# =============================================================================


class TestDefaultPolicyCreation:
    """Tests for default policy fallback."""

    async def test_default_policy_has_required_tags(self, tmp_policy_path):
        """Default policy includes Owner, Environment, Application as required."""
        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=False,
        )
        result = await service.detect_and_load()

        assert result.source == "default"
        assert result.success is True

        saved = json.loads(Path(tmp_policy_path).read_text(encoding="utf-8"))
        required_names = [t["name"] for t in saved["required_tags"]]
        assert "Owner" in required_names
        assert "Environment" in required_names
        assert "Application" in required_names

    async def test_default_policy_has_optional_tags(self, tmp_policy_path):
        """Default policy includes Project and CostCenter as optional."""
        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=False,
        )
        await service.detect_and_load()

        saved = json.loads(Path(tmp_policy_path).read_text(encoding="utf-8"))
        optional_names = [t["name"] for t in saved["optional_tags"]]
        assert "Project" in optional_names
        assert "CostCenter" in optional_names

    async def test_default_policy_metadata(self, tmp_policy_path):
        """Default policy has correct metadata source and created_at."""
        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=False,
        )
        await service.detect_and_load()

        saved = json.loads(Path(tmp_policy_path).read_text(encoding="utf-8"))
        assert saved["metadata"]["source"] == "default"
        assert saved["metadata"]["created_at"] is not None

    async def test_default_policy_environment_allowed_values(self, tmp_policy_path):
        """Environment tag in default policy has specific allowed values."""
        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=False,
        )
        await service.detect_and_load()

        saved = json.loads(Path(tmp_policy_path).read_text(encoding="utf-8"))
        env_tag = next(
            t for t in saved["required_tags"] if t["name"] == "Environment"
        )
        assert "production" in env_tag["allowed_values"]
        assert "staging" in env_tag["allowed_values"]
        assert "development" in env_tag["allowed_values"]
        assert "test" in env_tag["allowed_values"]

    async def test_default_policy_creates_parent_directory(self, tmp_path):
        """Default policy creation creates parent directories that don't exist."""
        deep_path = str(tmp_path / "a" / "b" / "c" / "policy.json")
        service = AutoPolicyService(
            policy_path=deep_path,
            auto_import=False,
        )
        result = await service.detect_and_load()

        assert result.success is True
        assert Path(deep_path).exists()

    async def test_default_policy_write_failure(self, tmp_path):
        """When file write fails, returns success=False with error."""
        # Use a path that can't be written (read-only directory trick)
        service = AutoPolicyService(
            policy_path=str(tmp_path / "policies" / "policy.json"),
            auto_import=False,
        )

        with patch.object(
            AutoPolicyService,
            "_save_policy",
            side_effect=PermissionError("Permission denied"),
        ):
            result = await service.detect_and_load()

        assert result.source == "default"
        assert result.success is False
        assert "Failed" in result.message or "Permission" in result.message

    async def test_default_policy_does_not_mutate_module_constant(self, tmp_policy_path):
        """Creating default policy does not alter the DEFAULT_POLICY module constant."""
        original_metadata_created_at = DEFAULT_POLICY["metadata"]["created_at"]

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=False,
        )
        await service.detect_and_load()

        # Module constant should be unchanged
        assert DEFAULT_POLICY["metadata"]["created_at"] == original_metadata_created_at


# =============================================================================
# Fallback Disabled
# =============================================================================


class TestFallbackDisabled:
    """Tests for when fallback_to_default=False."""

    async def test_no_fallback_and_aws_fails(self, tmp_policy_path, mock_aws_session):
        """When fallback is disabled and AWS fails, returns success=False."""
        session, org_client = mock_aws_session
        org_client.list_policies.return_value = {"Policies": []}

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
            fallback_to_default=False,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "none"
        assert result.success is False
        assert "manually" in result.message.lower() or "Create" in result.message

    async def test_no_fallback_no_aws_session(self, tmp_policy_path):
        """When fallback is disabled and no AWS session, returns success=False."""
        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
            fallback_to_default=False,
        )
        result = await service.detect_and_load(aws_session=None)

        assert result.source == "none"
        assert result.success is False

    async def test_no_fallback_auto_import_disabled(self, tmp_policy_path):
        """When both fallback and auto_import are disabled, returns failure."""
        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=False,
            fallback_to_default=False,
        )
        result = await service.detect_and_load()

        assert result.source == "none"
        assert result.success is False


# =============================================================================
# AWS Policy Conversion (_convert_aws_policy)
# =============================================================================


class TestConvertAWSPolicy:
    """Tests for the _convert_aws_policy function."""

    def test_basic_conversion(self, sample_aws_tag_policy):
        """Converts a standard AWS policy to MCP format."""
        result = _convert_aws_policy(sample_aws_tag_policy)

        assert result["version"] == "1.0"
        assert "required_tags" in result
        assert "optional_tags" in result
        assert result["metadata"]["source"] == "aws_organizations"

    def test_enforced_tags_become_required(self, sample_aws_tag_policy):
        """Tags with enforced_for end up in required_tags."""
        result = _convert_aws_policy(sample_aws_tag_policy)

        required_names = [t["name"] for t in result["required_tags"]]
        assert "Environment" in required_names
        assert "Owner" in required_names

    def test_unenforced_tags_become_optional(self, sample_aws_tag_policy):
        """Tags without enforced_for end up in optional_tags."""
        result = _convert_aws_policy(sample_aws_tag_policy)

        optional_names = [t["name"] for t in result["optional_tags"]]
        assert "Project" in optional_names

    def test_allowed_values_propagated(self, sample_aws_tag_policy):
        """Allowed values from AWS tag_value are preserved."""
        result = _convert_aws_policy(sample_aws_tag_policy)

        env_tag = next(
            t for t in result["required_tags"] if t["name"] == "Environment"
        )
        assert env_tag["allowed_values"] == ["production", "staging", "development"]

    def test_no_allowed_values_for_freeform_tags(self, sample_aws_tag_policy):
        """Tags with no tag_value have allowed_values=None."""
        result = _convert_aws_policy(sample_aws_tag_policy)

        owner_tag = next(
            t for t in result["required_tags"] if t["name"] == "Owner"
        )
        assert owner_tag["allowed_values"] is None

    def test_applies_to_from_enforced_for(self, sample_aws_tag_policy):
        """Resource types come from enforced_for."""
        result = _convert_aws_policy(sample_aws_tag_policy)

        env_tag = next(
            t for t in result["required_tags"] if t["name"] == "Environment"
        )
        assert "ec2:instance" in env_tag["applies_to"]
        assert "rds:db" in env_tag["applies_to"]

    def test_empty_tags_section(self):
        """Empty tags section produces empty required and optional lists."""
        result = _convert_aws_policy({"tags": {}})
        assert result["required_tags"] == []
        assert result["optional_tags"] == []

    def test_missing_tags_section(self):
        """Missing tags section produces empty lists."""
        result = _convert_aws_policy({})
        assert result["required_tags"] == []
        assert result["optional_tags"] == []

    def test_non_dict_tag_config_skipped(self):
        """Non-dict entries in tags section are ignored."""
        result = _convert_aws_policy({"tags": {"BadTag": "not_a_dict"}})
        assert result["required_tags"] == []
        assert result["optional_tags"] == []

    def test_tag_key_fallback_to_section_key(self):
        """When tag_key is not a dict, falls back to the section key name."""
        policy = {
            "tags": {
                "FallbackTag": {
                    "tag_key": "plain_string",  # Not a dict
                    "enforced_for": {"@@assign": ["s3:bucket"]},
                }
            }
        }
        result = _convert_aws_policy(policy)
        assert result["required_tags"][0]["name"] == "FallbackTag"

    def test_tag_key_assign_overrides_section_key(self):
        """@@assign in tag_key overrides the section key name."""
        policy = {
            "tags": {
                "SectionKey": {
                    "tag_key": {"@@assign": "ActualName"},
                    "enforced_for": {"@@assign": ["ec2:instance"]},
                }
            }
        }
        result = _convert_aws_policy(policy)
        assert result["required_tags"][0]["name"] == "ActualName"

    def test_validation_regex_always_none(self, sample_aws_tag_policy):
        """AWS policy conversion sets validation_regex to None (AWS doesn't have regex)."""
        result = _convert_aws_policy(sample_aws_tag_policy)

        for tag in result["required_tags"] + result["optional_tags"]:
            assert tag["validation_regex"] is None

    def test_tag_naming_rules_defaults(self, sample_aws_tag_policy):
        """Converted policy includes standard tag_naming_rules."""
        result = _convert_aws_policy(sample_aws_tag_policy)

        assert result["tag_naming_rules"]["case_sensitivity"] is False
        assert result["tag_naming_rules"]["max_key_length"] == 128
        assert result["tag_naming_rules"]["max_value_length"] == 256


# =============================================================================
# Tag Value Extraction (_extract_tag_values)
# =============================================================================


class TestExtractTagValues:
    """Tests for the _extract_tag_values helper function."""

    def test_none_input(self):
        assert _extract_tag_values(None) is None

    def test_dict_with_assign(self):
        result = _extract_tag_values({"@@assign": ["prod", "staging"]})
        assert result == ["prod", "staging"]

    def test_dict_with_empty_assign(self):
        result = _extract_tag_values({"@@assign": []})
        assert result is None

    def test_direct_list(self):
        result = _extract_tag_values(["alpha", "beta"])
        assert result == ["alpha", "beta"]

    def test_empty_list(self):
        result = _extract_tag_values([])
        assert result is None

    def test_non_string_values_filtered(self):
        """Non-string items in the values list are skipped."""
        result = _extract_tag_values({"@@assign": ["valid", 123, None, "also_valid"]})
        assert result == ["valid", "also_valid"]

    def test_wildcard_stripped(self):
        """Trailing asterisks are stripped from values."""
        result = _extract_tag_values({"@@assign": ["prod*", "staging*"]})
        assert result == ["prod", "staging"]

    def test_pure_wildcard_removed(self):
        """A value that is just '*' becomes empty string and is removed."""
        result = _extract_tag_values({"@@assign": ["*"]})
        assert result is None

    def test_mixed_wildcards(self):
        """Mix of wildcards and regular values."""
        result = _extract_tag_values({"@@assign": ["*", "production", "staging*"]})
        assert result == ["production", "staging"]

    def test_unsupported_type_returns_none(self):
        """Non-dict, non-list, non-None returns None."""
        assert _extract_tag_values(42) is None
        assert _extract_tag_values("string_value") is None
        assert _extract_tag_values(True) is None


# =============================================================================
# Enforced_for Parsing (_parse_enforced_for)
# =============================================================================


class TestParseEnforcedFor:
    """Tests for the _parse_enforced_for helper function."""

    def test_none_input(self):
        assert _parse_enforced_for(None) == []

    def test_dict_with_assign(self):
        result = _parse_enforced_for({"@@assign": ["ec2:instance", "rds:db"]})
        assert result == ["ec2:instance", "rds:db"]

    def test_direct_list(self):
        result = _parse_enforced_for(["s3:bucket", "lambda:function"])
        assert result == ["s3:bucket", "lambda:function"]

    def test_empty_list(self):
        assert _parse_enforced_for([]) == []

    def test_empty_assign(self):
        assert _parse_enforced_for({"@@assign": []}) == []

    def test_all_supported_expansion(self):
        """ec2:ALL_SUPPORTED expands to ec2:instance and ec2:volume."""
        result = _parse_enforced_for({"@@assign": ["ec2:ALL_SUPPORTED"]})
        assert "ec2:instance" in result
        assert "ec2:volume" in result

    def test_wildcard_expansion(self):
        """ec2:* expands the same as ALL_SUPPORTED."""
        result = _parse_enforced_for({"@@assign": ["ec2:*"]})
        assert "ec2:instance" in result
        assert "ec2:volume" in result

    def test_s3_all_supported(self):
        result = _parse_enforced_for({"@@assign": ["s3:ALL_SUPPORTED"]})
        assert result == ["s3:bucket"]

    def test_unknown_service_all_supported(self):
        """Unknown service with ALL_SUPPORTED gets a generic resource type."""
        result = _parse_enforced_for({"@@assign": ["unknownservice:ALL_SUPPORTED"]})
        assert result == ["unknownservice:resource"]

    def test_unknown_service_wildcard(self):
        result = _parse_enforced_for({"@@assign": ["custom:*"]})
        assert result == ["custom:resource"]

    def test_mixed_specific_and_wildcard(self):
        """Mix of specific types and wildcards."""
        result = _parse_enforced_for(
            {"@@assign": ["s3:bucket", "ec2:ALL_SUPPORTED", "lambda:function"]}
        )
        assert "s3:bucket" in result
        assert "ec2:instance" in result
        assert "ec2:volume" in result
        assert "lambda:function" in result

    def test_non_string_entries_skipped(self):
        """Non-string entries in the list are ignored."""
        result = _parse_enforced_for({"@@assign": ["ec2:instance", 42, None]})
        assert result == ["ec2:instance"]

    def test_unsupported_type_returns_empty(self):
        """Non-dict, non-list, non-None input returns empty list."""
        assert _parse_enforced_for(42) == []
        assert _parse_enforced_for("string") == []


# =============================================================================
# Directory Creation
# =============================================================================


class TestDirectoryCreation:
    """Tests for parent directory creation during policy save."""

    async def test_creates_nested_directories(self, tmp_path):
        """_save_policy creates all missing parent directories."""
        deep_path = str(tmp_path / "deep" / "nested" / "dir" / "policy.json")
        service = AutoPolicyService(
            policy_path=deep_path,
            auto_import=False,
        )
        result = await service.detect_and_load()

        assert result.success is True
        assert Path(deep_path).exists()
        assert Path(deep_path).parent.is_dir()

    async def test_existing_directory_no_error(self, tmp_path):
        """If the parent directory already exists, no error on mkdir."""
        policy_dir = tmp_path / "existing_dir"
        policy_dir.mkdir()
        policy_path = str(policy_dir / "policy.json")

        service = AutoPolicyService(
            policy_path=policy_path,
            auto_import=False,
        )
        result = await service.detect_and_load()

        assert result.success is True
        assert Path(policy_path).exists()


# =============================================================================
# Service Resource Mappings Constant
# =============================================================================


class TestServiceResourceMappings:
    """Verify SERVICE_RESOURCE_MAPPINGS has expected entries."""

    def test_ec2_mapping(self):
        assert "ec2:instance" in SERVICE_RESOURCE_MAPPINGS["ec2"]
        assert "ec2:volume" in SERVICE_RESOURCE_MAPPINGS["ec2"]

    def test_s3_mapping(self):
        assert SERVICE_RESOURCE_MAPPINGS["s3"] == ["s3:bucket"]

    def test_rds_mapping(self):
        assert SERVICE_RESOURCE_MAPPINGS["rds"] == ["rds:db"]

    def test_lambda_mapping(self):
        assert SERVICE_RESOURCE_MAPPINGS["lambda"] == ["lambda:function"]

    def test_all_services_have_list_values(self):
        for service, types in SERVICE_RESOURCE_MAPPINGS.items():
            assert isinstance(types, list), f"{service} value should be a list"
            assert len(types) > 0, f"{service} should have at least one type"


# =============================================================================
# End-to-End Flow Tests
# =============================================================================


class TestEndToEndFlow:
    """Integration-style tests validating the full detect_and_load flow."""

    async def test_full_aws_import_flow(self, tmp_policy_path, mock_aws_session):
        """Complete flow: no file -> AWS import -> saved file."""
        session, org_client = mock_aws_session
        aws_policy = {
            "tags": {
                "CostCenter": {
                    "tag_key": {"@@assign": "CostCenter"},
                    "tag_value": {"@@assign": ["CC-100", "CC-200"]},
                    "enforced_for": {"@@assign": ["ec2:ALL_SUPPORTED"]},
                }
            }
        }
        org_client.list_policies.return_value = {
            "Policies": [{"Id": "p-flow1", "Name": "FlowTest", "Description": ""}]
        }
        org_client.describe_policy.return_value = {
            "Policy": {"Content": json.dumps(aws_policy)}
        }

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "aws_organizations"
        assert result.success is True

        # Verify the saved file has the expanded resource types
        saved = json.loads(Path(tmp_policy_path).read_text(encoding="utf-8"))
        cc_tag = saved["required_tags"][0]
        assert cc_tag["name"] == "CostCenter"
        assert "ec2:instance" in cc_tag["applies_to"]
        assert "ec2:volume" in cc_tag["applies_to"]
        assert cc_tag["allowed_values"] == ["CC-100", "CC-200"]

    async def test_aws_fail_then_default_flow(self, tmp_policy_path, mock_aws_session):
        """Flow: no file -> AWS fails -> default created."""
        session, org_client = mock_aws_session
        org_client.list_policies.side_effect = Exception("AccessDenied")

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.source == "default"
        assert result.success is True
        assert Path(tmp_policy_path).exists()

    async def test_multiple_policies_uses_first(
        self, tmp_policy_path, mock_aws_session, sample_aws_tag_policy
    ):
        """When multiple tag policies exist, uses the first one."""
        session, org_client = mock_aws_session
        org_client.list_policies.return_value = {
            "Policies": [
                {"Id": "p-first", "Name": "FirstPolicy", "Description": ""},
                {"Id": "p-second", "Name": "SecondPolicy", "Description": ""},
                {"Id": "p-third", "Name": "ThirdPolicy", "Description": ""},
            ]
        }
        org_client.describe_policy.return_value = {
            "Policy": {"Content": json.dumps(sample_aws_tag_policy)}
        }

        service = AutoPolicyService(
            policy_path=tmp_policy_path,
            auto_import=True,
        )
        result = await service.detect_and_load(aws_session=session)

        assert result.aws_policy_id == "p-first"
        org_client.describe_policy.assert_called_once_with(PolicyId="p-first")
