"""Unit tests for generate_custodian_policy tool."""

import json

import pytest
import yaml

from mcp_server.services.policy_service import PolicyService
from mcp_server.tools.generate_custodian_policy import (
    CUSTODIAN_RESOURCE_MAP,
    CustodianPolicyOutput,
    GenerateCustodianPolicyResult,
    generate_custodian_policy,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def policy_data():
    """Return a tagging policy dict with required tags for testing."""
    return {
        "version": "1.0",
        "last_updated": "2026-01-09T00:00:00Z",
        "required_tags": [
            {
                "name": "Environment",
                "description": "Deployment environment",
                "allowed_values": ["production", "staging", "development"],
                "validation_regex": None,
                "applies_to": ["ec2:instance", "rds:db", "s3:bucket", "lambda:function"],
            },
            {
                "name": "Owner",
                "description": "Email of the resource owner",
                "allowed_values": None,
                "validation_regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$",
                "applies_to": ["ec2:instance", "rds:db"],
            },
        ],
        "optional_tags": [
            {
                "name": "Project",
                "description": "Project identifier",
                "allowed_values": None,
            },
        ],
    }


@pytest.fixture
def policy_service(tmp_path, policy_data):
    """Create a real PolicyService from a temp policy JSON file."""
    policy_file = tmp_path / "tagging_policy.json"
    policy_file.write_text(json.dumps(policy_data), encoding="utf-8")
    service = PolicyService(policy_path=str(policy_file))
    service.load_policy()
    return service


@pytest.fixture
def empty_policy_service(tmp_path):
    """Create a PolicyService with no required tags."""
    empty_policy = {
        "version": "1.0",
        "last_updated": "2026-01-09T00:00:00Z",
        "required_tags": [],
        "optional_tags": [],
    }
    policy_file = tmp_path / "empty_policy.json"
    policy_file.write_text(json.dumps(empty_policy), encoding="utf-8")
    service = PolicyService(policy_path=str(policy_file))
    service.load_policy()
    return service


# =============================================================================
# Tests for CustodianPolicyOutput model
# =============================================================================


class TestCustodianPolicyOutput:
    """Test CustodianPolicyOutput Pydantic model."""

    def test_model_fields(self):
        """Test that CustodianPolicyOutput has all required fields."""
        output = CustodianPolicyOutput(
            name="enforce-required-tags-ec2-instance",
            resource_type="ec2",
            yaml_content="policies:\n- name: test\n",
            description="Enforce required tags on ec2:instance resources.",
            filter_count=2,
            action_type="notify",
        )
        assert output.name == "enforce-required-tags-ec2-instance"
        assert output.resource_type == "ec2"
        assert output.yaml_content == "policies:\n- name: test\n"
        assert output.description == "Enforce required tags on ec2:instance resources."
        assert output.filter_count == 2
        assert output.action_type == "notify"

    def test_filter_count_default(self):
        """Test that filter_count defaults to 0."""
        output = CustodianPolicyOutput(
            name="test",
            resource_type="ec2",
            yaml_content="test",
            description="test",
            action_type="tag",
        )
        assert output.filter_count == 0


# =============================================================================
# Tests for GenerateCustodianPolicyResult model
# =============================================================================


class TestGenerateCustodianPolicyResult:
    """Test GenerateCustodianPolicyResult Pydantic model."""

    def test_model_fields_defaults(self):
        """Test that all fields have proper defaults."""
        result = GenerateCustodianPolicyResult()
        assert result.policies == []
        assert result.combined_yaml == ""
        assert result.total_policies == 0
        assert result.resource_types_covered == []
        assert result.dry_run is False
        assert result.target_tags == []

    def test_total_policies_computed_from_policies_list(self):
        """Test that total_policies is computed from the policies list length."""
        policies = [
            CustodianPolicyOutput(
                name=f"policy-{i}",
                resource_type="ec2",
                yaml_content="test",
                description="test",
                action_type="notify",
            )
            for i in range(3)
        ]
        result = GenerateCustodianPolicyResult(policies=policies)
        assert result.total_policies == 3

    def test_total_policies_computed_on_init(self):
        """Test that model_post_init correctly computes total_policies."""
        result = GenerateCustodianPolicyResult(
            policies=[
                CustodianPolicyOutput(
                    name="p1",
                    resource_type="ec2",
                    yaml_content="y",
                    description="d",
                    action_type="notify",
                ),
            ],
            total_policies=999,  # Explicit value should be overridden
        )
        # model_post_init sets total_policies = len(policies)
        assert result.total_policies == 1

    def test_model_serialization(self):
        """Test that the result model serializes to dict correctly."""
        result = GenerateCustodianPolicyResult(
            policies=[],
            combined_yaml="",
            resource_types_covered=["ec2:instance"],
            dry_run=True,
            target_tags=["Environment"],
        )
        data = result.model_dump(mode="json")
        assert data["dry_run"] is True
        assert data["resource_types_covered"] == ["ec2:instance"]
        assert data["target_tags"] == ["Environment"]
        assert data["total_policies"] == 0


# =============================================================================
# Tests for CUSTODIAN_RESOURCE_MAP
# =============================================================================


class TestCustodianResourceMap:
    """Test CUSTODIAN_RESOURCE_MAP mappings."""

    def test_ec2_instance_mapping(self):
        """Test ec2:instance maps to 'ec2'."""
        assert CUSTODIAN_RESOURCE_MAP["ec2:instance"] == "ec2"

    def test_rds_db_mapping(self):
        """Test rds:db maps to 'rds'."""
        assert CUSTODIAN_RESOURCE_MAP["rds:db"] == "rds"

    def test_s3_bucket_mapping(self):
        """Test s3:bucket maps to 's3'."""
        assert CUSTODIAN_RESOURCE_MAP["s3:bucket"] == "s3"

    def test_lambda_function_mapping(self):
        """Test lambda:function maps to 'lambda'."""
        assert CUSTODIAN_RESOURCE_MAP["lambda:function"] == "lambda"

    def test_ecs_service_mapping(self):
        """Test ecs:service maps to 'ecs-service'."""
        assert CUSTODIAN_RESOURCE_MAP["ecs:service"] == "ecs-service"

    def test_dynamodb_table_mapping(self):
        """Test dynamodb:table maps to 'dynamodb-table'."""
        assert CUSTODIAN_RESOURCE_MAP["dynamodb:table"] == "dynamodb-table"

    def test_opensearch_domain_mapping(self):
        """Test opensearch:domain maps to 'opensearch'."""
        assert CUSTODIAN_RESOURCE_MAP["opensearch:domain"] == "opensearch"

    def test_all_known_resource_types_have_mappings(self):
        """Test that the map contains a reasonable number of resource types."""
        # The map should have entries for all major resource types
        assert len(CUSTODIAN_RESOURCE_MAP) >= 30

    def test_unknown_resource_type_returns_none(self):
        """Test that an unknown resource type returns None from .get()."""
        assert CUSTODIAN_RESOURCE_MAP.get("unknown:type") is None


# =============================================================================
# Tests for generate_custodian_policy() function
# =============================================================================


class TestGenerateCustodianPolicyTool:
    """Test generate_custodian_policy tool function."""

    @pytest.mark.asyncio
    async def test_returns_correct_result_type(self, policy_service):
        """Test that the function returns GenerateCustodianPolicyResult."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        assert isinstance(result, GenerateCustodianPolicyResult)

    @pytest.mark.asyncio
    async def test_empty_resource_types_raises_value_error(self, policy_service):
        """Test that empty resource_types raises ValueError."""
        with pytest.raises(ValueError, match="resource_types cannot be empty"):
            await generate_custodian_policy(
                policy_service=policy_service,
                resource_types=[],
            )

    @pytest.mark.asyncio
    async def test_invalid_violation_type_raises_value_error(self, policy_service):
        """Test that invalid violation_types raises ValueError."""
        with pytest.raises(ValueError, match="Invalid violation_type"):
            await generate_custodian_policy(
                policy_service=policy_service,
                resource_types=["ec2:instance"],
                violation_types=["nonexistent_type"],
            )

    @pytest.mark.asyncio
    async def test_invalid_target_tags_raises_value_error(self, policy_service):
        """Test that target_tags not matching any required tags raises ValueError."""
        with pytest.raises(ValueError, match="None of the target_tags"):
            await generate_custodian_policy(
                policy_service=policy_service,
                resource_types=["ec2:instance"],
                target_tags=["NonExistentTag"],
            )

    # -------------------------------------------------------------------------
    # dry_run behavior
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_dry_run_true_generates_notify_actions(self, policy_service):
        """Test that dry_run=True generates policies with 'notify' actions."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            dry_run=True,
        )
        assert result.dry_run is True
        for policy in result.policies:
            assert policy.action_type == "notify"
            # Parse YAML and verify notify action
            parsed = yaml.safe_load(policy.yaml_content)
            actions = parsed["policies"][0]["actions"]
            assert any(a.get("type") == "notify" for a in actions)

    @pytest.mark.asyncio
    async def test_dry_run_false_generates_tag_actions(self, policy_service):
        """Test that dry_run=False generates policies with 'tag' actions."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            dry_run=False,
        )
        assert result.dry_run is False
        for policy in result.policies:
            assert policy.action_type == "tag"
            # Parse YAML and verify tag action
            parsed = yaml.safe_load(policy.yaml_content)
            actions = parsed["policies"][0]["actions"]
            assert any(a.get("type") == "tag" for a in actions)

    @pytest.mark.asyncio
    async def test_dry_run_default_is_true(self, policy_service):
        """Test that dry_run defaults to True."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        assert result.dry_run is True

    @pytest.mark.asyncio
    async def test_enforce_mode_tag_action_uses_first_allowed_value(self, policy_service):
        """Test that enforce mode uses the first allowed_value as default tag value."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            target_tags=["Environment"],
            dry_run=False,
        )
        assert len(result.policies) > 0
        parsed = yaml.safe_load(result.policies[0].yaml_content)
        actions = parsed["policies"][0]["actions"]
        tag_action = next(a for a in actions if a.get("type") == "tag")
        # Environment's first allowed_value is "production"
        assert tag_action["tags"]["Environment"] == "production"

    @pytest.mark.asyncio
    async def test_enforce_mode_tag_uses_unassigned_when_no_allowed_values(self, policy_service):
        """Test that enforce mode uses 'unassigned' when tag has no allowed_values."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            target_tags=["Owner"],
            dry_run=False,
        )
        assert len(result.policies) > 0
        parsed = yaml.safe_load(result.policies[0].yaml_content)
        actions = parsed["policies"][0]["actions"]
        tag_action = next(a for a in actions if a.get("type") == "tag")
        assert tag_action["tags"]["Owner"] == "unassigned"

    # -------------------------------------------------------------------------
    # Filtering by resource_types
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_single_resource_type(self, policy_service):
        """Test generating policy for a single resource type."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        assert len(result.policies) == 1
        assert result.resource_types_covered == ["ec2:instance"]
        assert result.policies[0].resource_type == "ec2"

    @pytest.mark.asyncio
    async def test_multiple_resource_types(self, policy_service):
        """Test generating policies for multiple resource types."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance", "rds:db"],
        )
        assert len(result.policies) == 2
        assert "ec2:instance" in result.resource_types_covered
        assert "rds:db" in result.resource_types_covered

    @pytest.mark.asyncio
    async def test_unsupported_resource_type_skipped(self, policy_service):
        """Test that unsupported resource types are silently skipped."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance", "unsupported:type"],
        )
        # Only ec2:instance should produce a policy
        assert len(result.policies) == 1
        assert result.resource_types_covered == ["ec2:instance"]

    @pytest.mark.asyncio
    async def test_all_unsupported_resource_types_produces_empty(self, policy_service):
        """Test that all unsupported types results in empty policies."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["unsupported:type"],
        )
        assert len(result.policies) == 0
        assert result.combined_yaml == ""

    # -------------------------------------------------------------------------
    # Filtering by violation_types
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_violation_type_missing_tag_only(self, policy_service):
        """Test generating policy for missing_tag violations only."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            violation_types=["missing_tag"],
        )
        assert len(result.policies) > 0
        parsed = yaml.safe_load(result.policies[0].yaml_content)
        filters = parsed["policies"][0]["filters"]
        # Should have absent filters but no value filters
        for f in filters:
            if isinstance(f, dict):
                assert "type" not in f or f.get("type") != "value"

    @pytest.mark.asyncio
    async def test_violation_type_invalid_value_only(self, policy_service):
        """Test generating policy for invalid_value violations only."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            violation_types=["invalid_value"],
            target_tags=["Environment"],
        )
        assert len(result.policies) > 0
        parsed = yaml.safe_load(result.policies[0].yaml_content)
        filters = parsed["policies"][0]["filters"]
        # Should have value filter for Environment (it has allowed_values)
        has_value_filter = False
        for f in filters:
            if isinstance(f, dict) and f.get("type") == "value":
                has_value_filter = True
        assert has_value_filter

    @pytest.mark.asyncio
    async def test_violation_types_both(self, policy_service):
        """Test generating policy addressing both violation types."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            violation_types=["missing_tag", "invalid_value"],
        )
        assert len(result.policies) > 0

    @pytest.mark.asyncio
    async def test_violation_types_none_defaults_to_all(self, policy_service):
        """Test that violation_types=None addresses all violation types."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            violation_types=None,
        )
        assert len(result.policies) > 0

    # -------------------------------------------------------------------------
    # Filtering by target_tags
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_target_tags_filters_to_specific_tags(self, policy_service):
        """Test that target_tags filters policies to specific tags only."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            target_tags=["Environment"],
        )
        assert result.target_tags == ["Environment"]
        # Verify the generated YAML only references Environment
        parsed = yaml.safe_load(result.combined_yaml)
        policy_desc = parsed["policies"][0]["description"]
        assert "Environment" in policy_desc

    @pytest.mark.asyncio
    async def test_target_tags_none_uses_all_required(self, policy_service):
        """Test that target_tags=None uses all required tags from policy."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            target_tags=None,
        )
        # Policy has Environment and Owner for ec2:instance
        assert "Environment" in result.target_tags
        assert "Owner" in result.target_tags

    # -------------------------------------------------------------------------
    # combined_yaml validation
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_combined_yaml_is_valid_yaml(self, policy_service):
        """Test that combined_yaml is valid YAML."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance", "rds:db"],
        )
        parsed = yaml.safe_load(result.combined_yaml)
        assert "policies" in parsed
        assert isinstance(parsed["policies"], list)

    @pytest.mark.asyncio
    async def test_combined_yaml_contains_all_policies(self, policy_service):
        """Test that combined_yaml contains all individual policies."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance", "rds:db"],
        )
        parsed = yaml.safe_load(result.combined_yaml)
        assert len(parsed["policies"]) == len(result.policies)

    @pytest.mark.asyncio
    async def test_individual_yaml_content_is_valid(self, policy_service):
        """Test that each policy's yaml_content is independently valid YAML."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        for policy in result.policies:
            parsed = yaml.safe_load(policy.yaml_content)
            assert "policies" in parsed
            assert len(parsed["policies"]) == 1

    # -------------------------------------------------------------------------
    # Policy structure
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_policy_name_contains_resource_type(self, policy_service):
        """Test that generated policy names contain the resource type."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        assert "ec2-instance" in result.policies[0].name

    @pytest.mark.asyncio
    async def test_policy_has_description(self, policy_service):
        """Test that generated policies include a description."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            dry_run=True,
        )
        for policy in result.policies:
            assert len(policy.description) > 0
            # Dry run description should mention DRY RUN
            assert "DRY RUN" in policy.description

    @pytest.mark.asyncio
    async def test_enforce_description_does_not_say_dry_run(self, policy_service):
        """Test that enforce mode description does not say DRY RUN."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            dry_run=False,
        )
        for policy in result.policies:
            assert "DRY RUN" not in policy.description

    @pytest.mark.asyncio
    async def test_filter_count_is_positive(self, policy_service):
        """Test that filter_count is positive when policies are generated."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        for policy in result.policies:
            assert policy.filter_count > 0

    # -------------------------------------------------------------------------
    # Edge cases
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_resource_type_with_no_applicable_tags(self, policy_service):
        """Test resource type where no tags from policy apply."""
        # lambda:function has Environment but not Owner in the test policy
        # If we target only Owner, lambda:function should be skipped
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["lambda:function"],
            target_tags=["Owner"],
        )
        # Owner doesn't apply_to lambda:function in our fixture
        assert len(result.policies) == 0

    @pytest.mark.asyncio
    async def test_empty_policy_no_required_tags(self, empty_policy_service):
        """Test with a policy that has no required tags."""
        with pytest.raises(ValueError, match="None of the target_tags"):
            await generate_custodian_policy(
                policy_service=empty_policy_service,
                resource_types=["ec2:instance"],
                target_tags=["Environment"],
            )

    @pytest.mark.asyncio
    async def test_empty_policy_no_target_tags(self, empty_policy_service):
        """Test with empty policy and no target_tags produces no policies."""
        result = await generate_custodian_policy(
            policy_service=empty_policy_service,
            resource_types=["ec2:instance"],
        )
        assert len(result.policies) == 0
        assert result.total_policies == 0

    @pytest.mark.asyncio
    async def test_compliance_service_none_accepted(self, policy_service):
        """Test that compliance_service=None is accepted without error."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            compliance_service=None,
        )
        assert isinstance(result, GenerateCustodianPolicyResult)

    @pytest.mark.asyncio
    async def test_notify_action_structure(self, policy_service):
        """Test that notify action has the expected structure."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            dry_run=True,
        )
        parsed = yaml.safe_load(result.policies[0].yaml_content)
        actions = parsed["policies"][0]["actions"]
        notify_action = next(a for a in actions if a.get("type") == "notify")
        assert "template" in notify_action
        assert "subject" in notify_action
        assert "to" in notify_action
        assert "transport" in notify_action

    @pytest.mark.asyncio
    async def test_tag_action_structure(self, policy_service):
        """Test that tag action has the expected structure."""
        result = await generate_custodian_policy(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            dry_run=False,
        )
        parsed = yaml.safe_load(result.policies[0].yaml_content)
        actions = parsed["policies"][0]["actions"]
        tag_action = next(a for a in actions if a.get("type") == "tag")
        assert "tags" in tag_action
        assert isinstance(tag_action["tags"], dict)
