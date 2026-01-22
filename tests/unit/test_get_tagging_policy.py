"""Unit tests for get_tagging_policy tool."""

import json

import pytest

from mcp_server.models.policy import TagNamingRules, TagPolicy
from mcp_server.services.policy_service import PolicyService
from mcp_server.tools.get_tagging_policy import (
    GetTaggingPolicyResult,
    get_tagging_policy,
)


@pytest.fixture
def mock_policy_service(tmp_path):
    """Create a mock policy service with a loaded policy."""
    policy_data = {
        "version": "1.0",
        "last_updated": "2025-12-30T00:00:00Z",
        "required_tags": [
            {
                "name": "CostCenter",
                "description": "Department for cost allocation",
                "allowed_values": ["Engineering", "Marketing", "Sales"],
                "validation_regex": None,
                "applies_to": ["ec2:instance", "rds:db", "s3:bucket"],
            },
            {
                "name": "Owner",
                "description": "Email address of the resource owner",
                "allowed_values": None,
                "validation_regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
                "applies_to": ["ec2:instance", "rds:db", "s3:bucket"],
            },
            {
                "name": "Environment",
                "description": "Deployment environment",
                "allowed_values": ["production", "staging", "development"],
                "validation_regex": None,
                "applies_to": ["ec2:instance", "rds:db"],
            },
        ],
        "optional_tags": [
            {
                "name": "Project",
                "description": "Project identifier",
                "allowed_values": None,
            },
            {
                "name": "Compliance",
                "description": "Compliance framework",
                "allowed_values": ["HIPAA", "PCI-DSS", "SOC2"],
            },
        ],
        "tag_naming_rules": {
            "case_sensitivity": False,
            "allow_special_characters": False,
            "max_key_length": 128,
            "max_value_length": 256,
        },
    }

    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps(policy_data))

    service = PolicyService(policy_path=policy_file)
    service.load_policy()
    return service


class TestGetTaggingPolicyResult:
    """Test GetTaggingPolicyResult class."""

    def test_result_to_dict_complete_structure(self, mock_policy_service):
        """Test that result.to_dict() returns complete policy structure."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        # Verify all required fields are present
        assert "version" in result_dict
        assert "last_updated" in result_dict
        assert "required_tags" in result_dict
        assert "optional_tags" in result_dict
        assert "tag_naming_rules" in result_dict
        assert "required_tag_count" in result_dict
        assert "optional_tag_count" in result_dict

    def test_result_to_dict_version(self, mock_policy_service):
        """Test that version is correctly serialized."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        assert result_dict["version"] == "1.0"

    def test_result_to_dict_last_updated_format(self, mock_policy_service):
        """Test that last_updated is in ISO format."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        # Should be ISO format string
        assert isinstance(result_dict["last_updated"], str)
        assert "T" in result_dict["last_updated"]
        # ISO format can end with Z or +00:00
        assert "Z" in result_dict["last_updated"] or "+00:00" in result_dict["last_updated"]

    def test_result_to_dict_required_tags_count(self, mock_policy_service):
        """Test that required tag count is correct."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        assert result_dict["required_tag_count"] == 3
        assert len(result_dict["required_tags"]) == 3

    def test_result_to_dict_optional_tags_count(self, mock_policy_service):
        """Test that optional tag count is correct."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        assert result_dict["optional_tag_count"] == 2
        assert len(result_dict["optional_tags"]) == 2

    def test_result_to_dict_required_tag_structure(self, mock_policy_service):
        """Test that required tags have complete structure."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        # Check first required tag
        cost_center_tag = result_dict["required_tags"][0]
        assert cost_center_tag["name"] == "CostCenter"
        assert cost_center_tag["description"] == "Department for cost allocation"
        assert cost_center_tag["allowed_values"] == ["Engineering", "Marketing", "Sales"]
        assert cost_center_tag["validation_regex"] is None
        assert cost_center_tag["applies_to"] == ["ec2:instance", "rds:db", "s3:bucket"]

    def test_result_to_dict_required_tag_with_regex(self, mock_policy_service):
        """Test that required tags with regex are correctly serialized."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        # Check Owner tag which has regex
        owner_tag = result_dict["required_tags"][1]
        assert owner_tag["name"] == "Owner"
        assert owner_tag["validation_regex"] is not None
        assert "^[a-zA-Z0-9" in owner_tag["validation_regex"]

    def test_result_to_dict_optional_tag_structure(self, mock_policy_service):
        """Test that optional tags have complete structure."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        # Check first optional tag
        project_tag = result_dict["optional_tags"][0]
        assert project_tag["name"] == "Project"
        assert project_tag["description"] == "Project identifier"
        assert project_tag["allowed_values"] is None

    def test_result_to_dict_optional_tag_with_values(self, mock_policy_service):
        """Test that optional tags with allowed values are correctly serialized."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        # Check Compliance tag which has allowed values
        compliance_tag = result_dict["optional_tags"][1]
        assert compliance_tag["name"] == "Compliance"
        assert compliance_tag["allowed_values"] == ["HIPAA", "PCI-DSS", "SOC2"]

    def test_result_to_dict_tag_naming_rules(self, mock_policy_service):
        """Test that tag naming rules are correctly serialized."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        rules = result_dict["tag_naming_rules"]
        assert rules["case_sensitivity"] is False
        assert rules["allow_special_characters"] is False
        assert rules["max_key_length"] == 128
        assert rules["max_value_length"] == 256

    def test_result_to_dict_all_required_tags_present(self, mock_policy_service):
        """Test that all required tags are present in serialized output."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        tag_names = {tag["name"] for tag in result_dict["required_tags"]}
        assert tag_names == {"CostCenter", "Owner", "Environment"}

    def test_result_to_dict_all_optional_tags_present(self, mock_policy_service):
        """Test that all optional tags are present in serialized output."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        tag_names = {tag["name"] for tag in result_dict["optional_tags"]}
        assert tag_names == {"Project", "Compliance"}

    def test_result_to_dict_required_tags_have_applies_to(self, mock_policy_service):
        """Test that all required tags include applies_to field."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        for tag in result_dict["required_tags"]:
            assert "applies_to" in tag
            assert isinstance(tag["applies_to"], list)
            assert len(tag["applies_to"]) > 0

    def test_result_to_dict_optional_tags_no_applies_to(self, mock_policy_service):
        """Test that optional tags don't include applies_to field."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        for tag in result_dict["optional_tags"]:
            assert "applies_to" not in tag

    def test_result_to_dict_json_serializable(self, mock_policy_service):
        """Test that result.to_dict() output is JSON serializable."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()

        # Should not raise an exception
        json_str = json.dumps(result_dict)
        assert isinstance(json_str, str)
        assert len(json_str) > 0

    def test_result_to_dict_roundtrip(self, mock_policy_service):
        """Test that result.to_dict() can be serialized and deserialized."""
        policy = mock_policy_service.get_policy()
        result = GetTaggingPolicyResult(policy=policy)

        result_dict = result.to_dict()
        json_str = json.dumps(result_dict)
        deserialized = json.loads(json_str)

        # Verify key fields are preserved
        assert deserialized["version"] == result_dict["version"]
        assert deserialized["required_tag_count"] == result_dict["required_tag_count"]
        assert deserialized["optional_tag_count"] == result_dict["optional_tag_count"]


class TestGetTaggingPolicyTool:
    """Test get_tagging_policy tool."""

    @pytest.mark.asyncio
    async def test_get_tagging_policy_returns_result(self, mock_policy_service):
        """Test that get_tagging_policy returns GetTaggingPolicyResult."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        assert isinstance(result, GetTaggingPolicyResult)

    @pytest.mark.asyncio
    async def test_get_tagging_policy_result_has_policy(self, mock_policy_service):
        """Test that result contains the policy."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        assert result.policy is not None
        assert isinstance(result.policy, TagPolicy)

    @pytest.mark.asyncio
    async def test_get_tagging_policy_policy_version(self, mock_policy_service):
        """Test that returned policy has correct version."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        assert result.policy.version == "1.0"

    @pytest.mark.asyncio
    async def test_get_tagging_policy_required_tags_count(self, mock_policy_service):
        """Test that returned policy has correct number of required tags."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        assert len(result.policy.required_tags) == 3

    @pytest.mark.asyncio
    async def test_get_tagging_policy_optional_tags_count(self, mock_policy_service):
        """Test that returned policy has correct number of optional tags."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        assert len(result.policy.optional_tags) == 2

    @pytest.mark.asyncio
    async def test_get_tagging_policy_required_tags_have_names(self, mock_policy_service):
        """Test that all required tags have names."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        for tag in result.policy.required_tags:
            assert tag.name is not None
            assert len(tag.name) > 0

    @pytest.mark.asyncio
    async def test_get_tagging_policy_required_tags_have_descriptions(self, mock_policy_service):
        """Test that all required tags have descriptions."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        for tag in result.policy.required_tags:
            assert tag.description is not None
            assert len(tag.description) > 0

    @pytest.mark.asyncio
    async def test_get_tagging_policy_required_tags_have_applies_to(self, mock_policy_service):
        """Test that all required tags have applies_to field."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        for tag in result.policy.required_tags:
            assert tag.applies_to is not None
            assert isinstance(tag.applies_to, list)
            assert len(tag.applies_to) > 0

    @pytest.mark.asyncio
    async def test_get_tagging_policy_optional_tags_have_names(self, mock_policy_service):
        """Test that all optional tags have names."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        for tag in result.policy.optional_tags:
            assert tag.name is not None
            assert len(tag.name) > 0

    @pytest.mark.asyncio
    async def test_get_tagging_policy_optional_tags_have_descriptions(self, mock_policy_service):
        """Test that all optional tags have descriptions."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        for tag in result.policy.optional_tags:
            assert tag.description is not None
            assert len(tag.description) > 0

    @pytest.mark.asyncio
    async def test_get_tagging_policy_tag_naming_rules_present(self, mock_policy_service):
        """Test that tag naming rules are present."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        assert result.policy.tag_naming_rules is not None
        assert isinstance(result.policy.tag_naming_rules, TagNamingRules)

    @pytest.mark.asyncio
    async def test_get_tagging_policy_tag_naming_rules_valid(self, mock_policy_service):
        """Test that tag naming rules have valid values."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        rules = result.policy.tag_naming_rules
        assert isinstance(rules.case_sensitivity, bool)
        assert isinstance(rules.allow_special_characters, bool)
        assert isinstance(rules.max_key_length, int)
        assert isinstance(rules.max_value_length, int)
        assert rules.max_key_length > 0
        assert rules.max_value_length > 0

    @pytest.mark.asyncio
    async def test_get_tagging_policy_to_dict_works(self, mock_policy_service):
        """Test that result.to_dict() works correctly."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "version" in result_dict
        assert "required_tags" in result_dict
        assert "optional_tags" in result_dict

    @pytest.mark.asyncio
    async def test_get_tagging_policy_specific_required_tag_costcenter(self, mock_policy_service):
        """Test that CostCenter required tag is present with correct structure."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        cost_center = next(
            (tag for tag in result.policy.required_tags if tag.name == "CostCenter"), None
        )

        assert cost_center is not None
        assert cost_center.description == "Department for cost allocation"
        assert cost_center.allowed_values == ["Engineering", "Marketing", "Sales"]
        assert cost_center.applies_to == ["ec2:instance", "rds:db", "s3:bucket"]

    @pytest.mark.asyncio
    async def test_get_tagging_policy_specific_required_tag_owner(self, mock_policy_service):
        """Test that Owner required tag is present with correct structure."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        owner = next((tag for tag in result.policy.required_tags if tag.name == "Owner"), None)

        assert owner is not None
        assert owner.description == "Email address of the resource owner"
        assert owner.validation_regex is not None
        assert "^[a-zA-Z0-9" in owner.validation_regex

    @pytest.mark.asyncio
    async def test_get_tagging_policy_specific_required_tag_environment(self, mock_policy_service):
        """Test that Environment required tag is present with correct structure."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        environment = next(
            (tag for tag in result.policy.required_tags if tag.name == "Environment"), None
        )

        assert environment is not None
        assert environment.description == "Deployment environment"
        assert environment.allowed_values == ["production", "staging", "development"]

    @pytest.mark.asyncio
    async def test_get_tagging_policy_specific_optional_tag_project(self, mock_policy_service):
        """Test that Project optional tag is present."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        project = next((tag for tag in result.policy.optional_tags if tag.name == "Project"), None)

        assert project is not None
        assert project.description == "Project identifier"

    @pytest.mark.asyncio
    async def test_get_tagging_policy_specific_optional_tag_compliance(self, mock_policy_service):
        """Test that Compliance optional tag is present with allowed values."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        compliance = next(
            (tag for tag in result.policy.optional_tags if tag.name == "Compliance"), None
        )

        assert compliance is not None
        assert compliance.description == "Compliance framework"
        assert compliance.allowed_values == ["HIPAA", "PCI-DSS", "SOC2"]

    @pytest.mark.asyncio
    async def test_get_tagging_policy_last_updated_present(self, mock_policy_service):
        """Test that last_updated timestamp is present."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        assert result.policy.last_updated is not None

    @pytest.mark.asyncio
    async def test_get_tagging_policy_requirements_6_1(self, mock_policy_service):
        """Test Requirement 6.1: Return complete policy configuration."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        # Should return complete policy with all sections
        assert result.policy.version is not None
        assert result.policy.required_tags is not None
        assert result.policy.optional_tags is not None
        assert result.policy.tag_naming_rules is not None

    @pytest.mark.asyncio
    async def test_get_tagging_policy_requirements_6_2(self, mock_policy_service):
        """Test Requirement 6.2: Return required tags with descriptions, allowed values, and validation rules."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        for tag in result.policy.required_tags:
            assert tag.name is not None
            assert tag.description is not None
            # Either allowed_values or validation_regex should be present (or both)
            # But at minimum, the fields should exist
            assert hasattr(tag, "allowed_values")
            assert hasattr(tag, "validation_regex")

    @pytest.mark.asyncio
    async def test_get_tagging_policy_requirements_6_3(self, mock_policy_service):
        """Test Requirement 6.3: Return optional tags with their descriptions."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        for tag in result.policy.optional_tags:
            assert tag.name is not None
            assert tag.description is not None

    @pytest.mark.asyncio
    async def test_get_tagging_policy_requirements_6_4(self, mock_policy_service):
        """Test Requirement 6.4: Indicate which resource types each tag applies to."""
        result = await get_tagging_policy(policy_service=mock_policy_service)

        for tag in result.policy.required_tags:
            assert tag.applies_to is not None
            assert isinstance(tag.applies_to, list)
            assert len(tag.applies_to) > 0
            # Each applies_to should be a resource type string
            for resource_type in tag.applies_to:
                assert isinstance(resource_type, str)
                assert ":" in resource_type  # Format: service:resource_type
