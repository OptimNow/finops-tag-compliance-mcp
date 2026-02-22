"""Unit tests for generate_openops_workflow tool."""

import json

import pytest
import yaml

from mcp_server.services.policy_service import PolicyService
from mcp_server.tools.generate_openops_workflow import (
    GenerateOpenOpsWorkflowResult,
    WorkflowStep,
    generate_openops_workflow,
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
# Tests for WorkflowStep model
# =============================================================================


class TestWorkflowStep:
    """Test WorkflowStep Pydantic model."""

    def test_model_fields(self):
        """Test that WorkflowStep has all required fields."""
        step = WorkflowStep(
            name="Identify Non-Compliant Resources",
            action="compliance_check",
            description="Scan resources and identify tagging violations.",
        )
        assert step.name == "Identify Non-Compliant Resources"
        assert step.action == "compliance_check"
        assert step.description == "Scan resources and identify tagging violations."

    def test_description_default(self):
        """Test that description defaults to empty string."""
        step = WorkflowStep(name="test", action="test_action")
        assert step.description == ""


# =============================================================================
# Tests for GenerateOpenOpsWorkflowResult model
# =============================================================================


class TestGenerateOpenOpsWorkflowResult:
    """Test GenerateOpenOpsWorkflowResult Pydantic model."""

    def test_model_fields(self):
        """Test that result model has all required fields."""
        result = GenerateOpenOpsWorkflowResult(
            workflow_name="Fix ec2:instance Tagging Violations",
            yaml_content="name: test\n",
            description="test workflow",
            steps=[],
            resource_types=["ec2:instance"],
            remediation_strategy="notify",
        )
        assert result.workflow_name == "Fix ec2:instance Tagging Violations"
        assert result.yaml_content == "name: test\n"
        assert result.description == "test workflow"
        assert result.steps == []
        assert result.resource_types == ["ec2:instance"]
        assert result.remediation_strategy == "notify"

    def test_step_count_computed_from_steps_list(self):
        """Test that step_count is computed from the steps list length."""
        steps = [
            WorkflowStep(name=f"step-{i}", action="test") for i in range(4)
        ]
        result = GenerateOpenOpsWorkflowResult(
            workflow_name="test",
            yaml_content="test",
            description="test",
            steps=steps,
            resource_types=["ec2:instance"],
            remediation_strategy="notify",
        )
        assert result.step_count == 4

    def test_step_count_overrides_explicit_value(self):
        """Test that model_post_init overrides explicit step_count."""
        result = GenerateOpenOpsWorkflowResult(
            workflow_name="test",
            yaml_content="test",
            description="test",
            steps=[WorkflowStep(name="s1", action="a1")],
            step_count=999,
            resource_types=[],
            remediation_strategy="notify",
        )
        assert result.step_count == 1

    def test_model_serialization(self):
        """Test that result serializes to dict correctly."""
        result = GenerateOpenOpsWorkflowResult(
            workflow_name="test",
            yaml_content="yaml: content\n",
            description="desc",
            steps=[],
            resource_types=["ec2:instance"],
            remediation_strategy="report",
        )
        data = result.model_dump(mode="json")
        assert data["workflow_name"] == "test"
        assert data["remediation_strategy"] == "report"
        assert data["step_count"] == 0
        assert data["resource_types"] == ["ec2:instance"]


# =============================================================================
# Tests for generate_openops_workflow() function
# =============================================================================


class TestGenerateOpenOpsWorkflowTool:
    """Test generate_openops_workflow tool function."""

    @pytest.mark.asyncio
    async def test_returns_correct_result_type(self, policy_service):
        """Test that the function returns GenerateOpenOpsWorkflowResult."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        assert isinstance(result, GenerateOpenOpsWorkflowResult)

    @pytest.mark.asyncio
    async def test_empty_resource_types_raises_value_error(self, policy_service):
        """Test that empty resource_types raises ValueError."""
        with pytest.raises(ValueError, match="resource_types cannot be empty"):
            await generate_openops_workflow(
                policy_service=policy_service,
                resource_types=[],
            )

    @pytest.mark.asyncio
    async def test_invalid_strategy_raises_value_error(self, policy_service):
        """Test that invalid remediation_strategy raises ValueError."""
        with pytest.raises(ValueError, match="Invalid remediation_strategy"):
            await generate_openops_workflow(
                policy_service=policy_service,
                resource_types=["ec2:instance"],
                remediation_strategy="invalid_strategy",
            )

    @pytest.mark.asyncio
    async def test_threshold_below_zero_raises_value_error(self, policy_service):
        """Test that threshold < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="threshold must be between 0.0 and 1.0"):
            await generate_openops_workflow(
                policy_service=policy_service,
                resource_types=["ec2:instance"],
                threshold=-0.1,
            )

    @pytest.mark.asyncio
    async def test_threshold_above_one_raises_value_error(self, policy_service):
        """Test that threshold > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="threshold must be between 0.0 and 1.0"):
            await generate_openops_workflow(
                policy_service=policy_service,
                resource_types=["ec2:instance"],
                threshold=1.5,
            )

    @pytest.mark.asyncio
    async def test_threshold_boundary_zero(self, policy_service):
        """Test that threshold=0.0 is accepted."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            threshold=0.0,
        )
        assert isinstance(result, GenerateOpenOpsWorkflowResult)

    @pytest.mark.asyncio
    async def test_threshold_boundary_one(self, policy_service):
        """Test that threshold=1.0 is accepted."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            threshold=1.0,
        )
        assert isinstance(result, GenerateOpenOpsWorkflowResult)

    # -------------------------------------------------------------------------
    # Remediation strategies
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_notify_strategy(self, policy_service):
        """Test workflow generation with 'notify' strategy."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="notify",
        )
        assert result.remediation_strategy == "notify"
        assert result.step_count >= 1
        # Notify strategy should have compliance_check, notification, and ticket steps
        action_types = [s.action for s in result.steps]
        assert "compliance_check" in action_types
        assert "notification" in action_types
        assert "ticket" in action_types

    @pytest.mark.asyncio
    async def test_auto_tag_strategy(self, policy_service):
        """Test workflow generation with 'auto_tag' strategy."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="auto_tag",
        )
        assert result.remediation_strategy == "auto_tag"
        assert result.step_count >= 1
        # Auto-tag strategy should have compliance_check and aws_cli steps
        action_types = [s.action for s in result.steps]
        assert "compliance_check" in action_types
        assert "aws_cli" in action_types

    @pytest.mark.asyncio
    async def test_report_strategy(self, policy_service):
        """Test workflow generation with 'report' strategy."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="report",
        )
        assert result.remediation_strategy == "report"
        assert result.step_count >= 1
        # Report strategy should have compliance_report, export, and notification steps
        action_types = [s.action for s in result.steps]
        assert "compliance_report" in action_types
        assert "export" in action_types
        assert "notification" in action_types

    @pytest.mark.asyncio
    async def test_default_strategy_is_notify(self, policy_service):
        """Test that default remediation_strategy is 'notify'."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        assert result.remediation_strategy == "notify"

    # -------------------------------------------------------------------------
    # YAML content validation
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_yaml_content_is_valid_yaml(self, policy_service):
        """Test that yaml_content is valid YAML."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        parsed = yaml.safe_load(result.yaml_content)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_yaml_contains_workflow_name(self, policy_service):
        """Test that YAML contains the workflow name."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        parsed = yaml.safe_load(result.yaml_content)
        assert "name" in parsed
        assert parsed["name"] == result.workflow_name

    @pytest.mark.asyncio
    async def test_yaml_contains_version(self, policy_service):
        """Test that YAML contains a version field."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        parsed = yaml.safe_load(result.yaml_content)
        assert "version" in parsed
        assert parsed["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_yaml_contains_triggers(self, policy_service):
        """Test that YAML contains triggers."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            threshold=0.75,
        )
        parsed = yaml.safe_load(result.yaml_content)
        assert "triggers" in parsed
        triggers = parsed["triggers"]
        assert any(t.get("compliance_score_below") == 0.75 for t in triggers)

    @pytest.mark.asyncio
    async def test_yaml_contains_filters(self, policy_service):
        """Test that YAML contains resource filters."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance", "rds:db"],
        )
        parsed = yaml.safe_load(result.yaml_content)
        assert "filters" in parsed
        assert "resource_types" in parsed["filters"]
        assert "ec2:instance" in parsed["filters"]["resource_types"]
        assert "rds:db" in parsed["filters"]["resource_types"]

    @pytest.mark.asyncio
    async def test_yaml_contains_steps(self, policy_service):
        """Test that YAML contains steps."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        parsed = yaml.safe_load(result.yaml_content)
        assert "steps" in parsed
        assert isinstance(parsed["steps"], list)
        assert len(parsed["steps"]) > 0

    @pytest.mark.asyncio
    async def test_yaml_contains_metadata(self, policy_service):
        """Test that YAML contains metadata."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        parsed = yaml.safe_load(result.yaml_content)
        assert "metadata" in parsed
        assert parsed["metadata"]["generated_by"] == "finops-tag-compliance-mcp"
        assert "generated_at" in parsed["metadata"]
        assert "target_tags" in parsed["metadata"]
        assert "threshold" in parsed["metadata"]

    # -------------------------------------------------------------------------
    # Schedule parameter
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_schedule_included_in_triggers(self, policy_service):
        """Test that schedule is added to triggers when provided."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            schedule="0 9 * * MON",
        )
        parsed = yaml.safe_load(result.yaml_content)
        triggers = parsed["triggers"]
        assert any(t.get("schedule") == "0 9 * * MON" for t in triggers)

    @pytest.mark.asyncio
    async def test_no_schedule_trigger_when_none(self, policy_service):
        """Test that no schedule trigger is added when schedule is None."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            schedule=None,
        )
        parsed = yaml.safe_load(result.yaml_content)
        triggers = parsed["triggers"]
        assert not any("schedule" in t for t in triggers)

    @pytest.mark.asyncio
    async def test_daily_schedule(self, policy_service):
        """Test daily cron schedule."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            schedule="0 9 * * *",
        )
        parsed = yaml.safe_load(result.yaml_content)
        triggers = parsed["triggers"]
        assert any(t.get("schedule") == "0 9 * * *" for t in triggers)

    @pytest.mark.asyncio
    async def test_weekly_schedule(self, policy_service):
        """Test weekly cron schedule."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            schedule="0 9 * * MON",
        )
        parsed = yaml.safe_load(result.yaml_content)
        triggers = parsed["triggers"]
        assert any(t.get("schedule") == "0 9 * * MON" for t in triggers)

    @pytest.mark.asyncio
    async def test_monthly_schedule(self, policy_service):
        """Test monthly cron schedule."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            schedule="0 9 1 * *",
        )
        parsed = yaml.safe_load(result.yaml_content)
        triggers = parsed["triggers"]
        assert any(t.get("schedule") == "0 9 1 * *" for t in triggers)

    # -------------------------------------------------------------------------
    # Target tags
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_target_tags_filters_to_specific_tags(self, policy_service):
        """Test that target_tags filters the workflow to specific tags only."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            target_tags=["Environment"],
        )
        parsed = yaml.safe_load(result.yaml_content)
        assert parsed["filters"]["tag_keys"] == ["Environment"]
        assert parsed["metadata"]["target_tags"] == ["Environment"]

    @pytest.mark.asyncio
    async def test_target_tags_none_uses_all_required(self, policy_service):
        """Test that target_tags=None uses all required tags."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            target_tags=None,
        )
        parsed = yaml.safe_load(result.yaml_content)
        tag_keys = parsed["filters"]["tag_keys"]
        assert "Environment" in tag_keys
        assert "Owner" in tag_keys

    # -------------------------------------------------------------------------
    # Workflow description
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_description_contains_strategy(self, policy_service):
        """Test that description mentions the remediation strategy."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="auto_tag",
        )
        assert "auto_tag" in result.description

    @pytest.mark.asyncio
    async def test_description_contains_resource_types(self, policy_service):
        """Test that description mentions the resource types."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        assert "ec2:instance" in result.description

    @pytest.mark.asyncio
    async def test_description_contains_threshold(self, policy_service):
        """Test that description mentions the threshold."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            threshold=0.75,
        )
        assert "75%" in result.description

    # -------------------------------------------------------------------------
    # Workflow name
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_workflow_name_contains_resource_types(self, policy_service):
        """Test that workflow name contains the resource types."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )
        assert "ec2:instance" in result.workflow_name

    @pytest.mark.asyncio
    async def test_workflow_name_multiple_resource_types(self, policy_service):
        """Test workflow name with multiple resource types."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance", "rds:db"],
        )
        assert "ec2:instance" in result.workflow_name
        assert "rds:db" in result.workflow_name

    # -------------------------------------------------------------------------
    # Auto-tag strategy specifics
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_auto_tag_creates_step_per_tag(self, policy_service):
        """Test that auto_tag strategy creates a tagging step per required tag."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="auto_tag",
        )
        # Should have: identify + tag per tag + verify
        # ec2:instance has Environment and Owner in fixture
        aws_cli_steps = [s for s in result.steps if s.action == "aws_cli"]
        assert len(aws_cli_steps) == 2  # One for Environment, one for Owner

    @pytest.mark.asyncio
    async def test_auto_tag_has_verify_step(self, policy_service):
        """Test that auto_tag strategy includes a verification step."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="auto_tag",
        )
        step_names = [s.name for s in result.steps]
        assert "Verify Remediation" in step_names

    @pytest.mark.asyncio
    async def test_auto_tag_uses_first_allowed_value(self, policy_service):
        """Test that auto_tag uses the first allowed_value as default."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="auto_tag",
            target_tags=["Environment"],
        )
        # Find the aws_cli step for Environment
        aws_cli_steps = [s for s in result.steps if s.action == "aws_cli"]
        assert len(aws_cli_steps) >= 1
        # Description should mention the default value "production"
        env_step = next(s for s in aws_cli_steps if "Environment" in s.name)
        assert "production" in env_step.description

    @pytest.mark.asyncio
    async def test_auto_tag_uses_unassigned_when_no_allowed_values(self, policy_service):
        """Test that auto_tag uses 'unassigned' when tag has no allowed_values."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="auto_tag",
            target_tags=["Owner"],
        )
        aws_cli_steps = [s for s in result.steps if s.action == "aws_cli"]
        assert len(aws_cli_steps) >= 1
        owner_step = next(s for s in aws_cli_steps if "Owner" in s.name)
        assert "unassigned" in owner_step.description

    # -------------------------------------------------------------------------
    # Edge cases
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_compliance_service_none_accepted(self, policy_service):
        """Test that compliance_service=None is accepted without error."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            compliance_service=None,
        )
        assert isinstance(result, GenerateOpenOpsWorkflowResult)

    @pytest.mark.asyncio
    async def test_empty_policy_generates_workflow_with_no_tag_steps(self, empty_policy_service):
        """Test that empty policy still generates a workflow structure."""
        result = await generate_openops_workflow(
            policy_service=empty_policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="notify",
        )
        # Notify has 3 steps even with no tags, since it relies on compliance_check
        assert isinstance(result, GenerateOpenOpsWorkflowResult)
        assert result.step_count >= 1

    @pytest.mark.asyncio
    async def test_resource_types_passed_through_to_result(self, policy_service):
        """Test that resource_types are passed through to the result."""
        types = ["ec2:instance", "rds:db", "s3:bucket"]
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=types,
        )
        assert result.resource_types == types

    @pytest.mark.asyncio
    async def test_steps_have_name_and_action(self, policy_service):
        """Test that all steps have non-empty name and action."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="notify",
        )
        for step in result.steps:
            assert isinstance(step, WorkflowStep)
            assert len(step.name) > 0
            assert len(step.action) > 0

    @pytest.mark.asyncio
    async def test_yaml_round_trip(self, policy_service):
        """Test that YAML content can be round-tripped (load then dump)."""
        result = await generate_openops_workflow(
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            remediation_strategy="auto_tag",
        )
        parsed = yaml.safe_load(result.yaml_content)
        re_dumped = yaml.dump(parsed, default_flow_style=False, sort_keys=False)
        re_parsed = yaml.safe_load(re_dumped)
        assert parsed == re_parsed
