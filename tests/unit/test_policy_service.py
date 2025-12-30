"""
Unit tests for PolicyService.

Tests the policy loading, validation, and retrieval functionality.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import mock_open, patch, MagicMock

from mcp_server.services import PolicyService
from mcp_server.services.policy_service import PolicyValidationError, PolicyNotFoundError
from mcp_server.models import TagPolicy, RequiredTag, OptionalTag


class TestPolicyServiceLoading:
    """Test policy loading functionality."""

    def test_load_policy_from_valid_file(self, tmp_path):
        """Test loading a valid policy file."""
        # Create a valid policy file
        policy_data = {
            "version": "1.0",
            "required_tags": [
                {
                    "name": "CostCenter",
                    "description": "Cost center",
                    "applies_to": ["ec2:instance"],
                }
            ],
            "optional_tags": [],
        }
        
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy_data))
        
        # Load the policy
        service = PolicyService(policy_path=policy_file)
        policy = service.load_policy()
        
        # Verify
        assert isinstance(policy, TagPolicy)
        assert policy.version == "1.0"
        assert len(policy.required_tags) == 1
        assert policy.required_tags[0].name == "CostCenter"

    def test_load_policy_file_not_found(self):
        """Test loading when policy file doesn't exist."""
        service = PolicyService(policy_path="nonexistent.json")
        
        with pytest.raises(PolicyNotFoundError) as exc_info:
            service.load_policy()
        
        assert "not found" in str(exc_info.value).lower()

    def test_load_policy_invalid_json(self, tmp_path):
        """Test loading a file with invalid JSON."""
        policy_file = tmp_path / "invalid.json"
        policy_file.write_text("{ invalid json }")
        
        service = PolicyService(policy_path=policy_file)
        
        with pytest.raises(PolicyValidationError) as exc_info:
            service.load_policy()
        
        assert "invalid json" in str(exc_info.value).lower()

    def test_load_policy_invalid_structure(self, tmp_path):
        """Test loading a file with invalid policy structure."""
        policy_data = {
            "version": "1.0",
            "required_tags": [
                {
                    "name": "CostCenter",
                    "description": "Cost center",
                    # Missing required 'applies_to' field
                }
            ],
        }
        
        policy_file = tmp_path / "invalid_structure.json"
        policy_file.write_text(json.dumps(policy_data))
        
        service = PolicyService(policy_path=policy_file)
        
        with pytest.raises(PolicyValidationError) as exc_info:
            service.load_policy()
        
        assert "invalid policy structure" in str(exc_info.value).lower()

    def test_load_policy_caches_result(self, tmp_path):
        """Test that loaded policy is cached."""
        policy_data = {
            "version": "1.0",
            "required_tags": [],
            "optional_tags": [],
        }
        
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy_data))
        
        service = PolicyService(policy_path=policy_file)
        policy1 = service.load_policy()
        policy2 = service.get_policy()
        
        # Should be the same object (cached)
        assert policy1 is policy2


class TestPolicyServiceRetrieval:
    """Test policy retrieval methods."""

    @pytest.fixture
    def service_with_policy(self, tmp_path):
        """Create a service with a loaded policy."""
        policy_data = {
            "version": "1.0",
            "required_tags": [
                {
                    "name": "CostCenter",
                    "description": "Cost center",
                    "allowed_values": ["Eng", "Sales"],
                    "applies_to": ["ec2:instance", "rds:db"],
                },
                {
                    "name": "Environment",
                    "description": "Environment",
                    "validation_regex": "^(prod|dev)$",
                    "applies_to": ["ec2:instance"],
                },
                {
                    "name": "DataClass",
                    "description": "Data classification",
                    "applies_to": ["s3:bucket"],
                },
            ],
            "optional_tags": [
                {
                    "name": "Project",
                    "description": "Project name",
                },
                {
                    "name": "Owner",
                    "description": "Owner email",
                    "allowed_values": ["alice@example.com", "bob@example.com"],
                },
            ],
        }
        
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy_data))
        
        service = PolicyService(policy_path=policy_file)
        service.load_policy()
        return service

    def test_get_policy_loads_if_not_cached(self, tmp_path):
        """Test that get_policy loads policy if not already loaded."""
        policy_data = {
            "version": "1.0",
            "required_tags": [],
            "optional_tags": [],
        }
        
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy_data))
        
        service = PolicyService(policy_path=policy_file)
        policy = service.get_policy()
        
        assert isinstance(policy, TagPolicy)

    def test_get_required_tags_all(self, service_with_policy):
        """Test getting all required tags."""
        tags = service_with_policy.get_required_tags()
        
        assert len(tags) == 3
        assert all(isinstance(tag, RequiredTag) for tag in tags)
        assert {tag.name for tag in tags} == {"CostCenter", "Environment", "DataClass"}

    def test_get_required_tags_filtered_by_resource_type(self, service_with_policy):
        """Test getting required tags filtered by resource type."""
        # EC2 instances should have CostCenter and Environment
        ec2_tags = service_with_policy.get_required_tags("ec2:instance")
        assert len(ec2_tags) == 2
        assert {tag.name for tag in ec2_tags} == {"CostCenter", "Environment"}
        
        # RDS should have only CostCenter
        rds_tags = service_with_policy.get_required_tags("rds:db")
        assert len(rds_tags) == 1
        assert rds_tags[0].name == "CostCenter"
        
        # S3 should have only DataClass
        s3_tags = service_with_policy.get_required_tags("s3:bucket")
        assert len(s3_tags) == 1
        assert s3_tags[0].name == "DataClass"
        
        # Lambda should have no required tags
        lambda_tags = service_with_policy.get_required_tags("lambda:function")
        assert len(lambda_tags) == 0

    def test_get_optional_tags(self, service_with_policy):
        """Test getting optional tags."""
        tags = service_with_policy.get_optional_tags()
        
        assert len(tags) == 2
        assert all(isinstance(tag, OptionalTag) for tag in tags)
        assert {tag.name for tag in tags} == {"Project", "Owner"}

    def test_get_tag_by_name_required(self, service_with_policy):
        """Test getting a required tag by name."""
        tag = service_with_policy.get_tag_by_name("CostCenter")
        
        assert tag is not None
        assert isinstance(tag, RequiredTag)
        assert tag.name == "CostCenter"
        assert tag.allowed_values == ["Eng", "Sales"]

    def test_get_tag_by_name_optional(self, service_with_policy):
        """Test getting an optional tag by name."""
        tag = service_with_policy.get_tag_by_name("Project")
        
        assert tag is not None
        assert isinstance(tag, OptionalTag)
        assert tag.name == "Project"

    def test_get_tag_by_name_not_found(self, service_with_policy):
        """Test getting a non-existent tag."""
        tag = service_with_policy.get_tag_by_name("NonExistent")
        
        assert tag is None

    def test_is_tag_required_true(self, service_with_policy):
        """Test checking if a tag is required for a resource type."""
        assert service_with_policy.is_tag_required("CostCenter", "ec2:instance") is True
        assert service_with_policy.is_tag_required("Environment", "ec2:instance") is True

    def test_is_tag_required_false(self, service_with_policy):
        """Test checking if a tag is not required for a resource type."""
        assert service_with_policy.is_tag_required("DataClass", "ec2:instance") is False
        assert service_with_policy.is_tag_required("Project", "ec2:instance") is False

    def test_get_allowed_values_with_values(self, service_with_policy):
        """Test getting allowed values for a tag that has them."""
        values = service_with_policy.get_allowed_values("CostCenter")
        
        assert values == ["Eng", "Sales"]

    def test_get_allowed_values_without_values(self, service_with_policy):
        """Test getting allowed values for a tag without restrictions."""
        values = service_with_policy.get_allowed_values("Environment")
        
        assert values is None

    def test_get_allowed_values_nonexistent_tag(self, service_with_policy):
        """Test getting allowed values for a non-existent tag."""
        values = service_with_policy.get_allowed_values("NonExistent")
        
        assert values is None

    def test_get_validation_regex_with_regex(self, service_with_policy):
        """Test getting validation regex for a tag that has one."""
        regex = service_with_policy.get_validation_regex("Environment")
        
        assert regex == "^(prod|dev)$"

    def test_get_validation_regex_without_regex(self, service_with_policy):
        """Test getting validation regex for a tag without one."""
        regex = service_with_policy.get_validation_regex("CostCenter")
        
        assert regex is None

    def test_get_validation_regex_optional_tag(self, service_with_policy):
        """Test getting validation regex for an optional tag (should be None)."""
        regex = service_with_policy.get_validation_regex("Project")
        
        assert regex is None


class TestPolicyServiceValidation:
    """Test policy validation methods."""

    def test_validate_policy_structure_valid(self):
        """Test validating a valid policy structure."""
        policy_data = {
            "version": "1.0",
            "required_tags": [
                {
                    "name": "CostCenter",
                    "description": "Cost center",
                    "applies_to": ["ec2:instance"],
                }
            ],
            "optional_tags": [],
        }
        
        service = PolicyService()
        is_valid, error = service.validate_policy_structure(policy_data)
        
        assert is_valid is True
        assert error is None

    def test_validate_policy_structure_invalid(self):
        """Test validating an invalid policy structure."""
        policy_data = {
            "version": "1.0",
            "required_tags": [
                {
                    "name": "CostCenter",
                    "description": "Cost center",
                    # Missing required 'applies_to' field
                }
            ],
        }
        
        service = PolicyService()
        is_valid, error = service.validate_policy_structure(policy_data)
        
        assert is_valid is False
        assert error is not None
        assert "applies_to" in error.lower()


class TestPolicyServiceReload:
    """Test policy reload functionality."""

    def test_reload_policy(self, tmp_path):
        """Test reloading policy from disk."""
        # Create initial policy
        policy_data_v1 = {
            "version": "1.0",
            "required_tags": [],
            "optional_tags": [],
        }
        
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy_data_v1))
        
        service = PolicyService(policy_path=policy_file)
        policy_v1 = service.load_policy()
        assert policy_v1.version == "1.0"
        
        # Update policy file
        policy_data_v2 = {
            "version": "2.0",
            "required_tags": [],
            "optional_tags": [],
        }
        policy_file.write_text(json.dumps(policy_data_v2))
        
        # Reload
        policy_v2 = service.reload_policy()
        assert policy_v2.version == "2.0"
        
        # Verify get_policy returns new version
        assert service.get_policy().version == "2.0"
