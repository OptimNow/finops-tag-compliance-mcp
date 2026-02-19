"""Unit tests for detect_tag_drift tool."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_server.clients.aws_client import AWSClient
from mcp_server.services.policy_service import PolicyService
from mcp_server.tools.detect_tag_drift import (
    DetectTagDriftResult,
    TagDriftEntry,
    detect_tag_drift,
    _infer_resource_type,
    _extract_region_from_arn,
    _classify_severity,
    _find_tag_definition,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    client = MagicMock(spec=AWSClient)
    client.region = "us-east-1"
    client.get_all_tagged_resources = AsyncMock(return_value=[])
    return client


@pytest.fixture
def policy_file(tmp_path):
    """Create a temporary tagging policy JSON file and return its path."""
    policy_data = {
        "version": "1.0",
        "required_tags": [
            {
                "name": "Environment",
                "description": "Deployment environment",
                "allowed_values": ["production", "staging", "development"],
                "applies_to": ["ec2:instance", "rds:db", "s3:bucket"],
            },
            {
                "name": "Owner",
                "description": "Resource owner",
                "allowed_values": None,
                "applies_to": [],
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
    policy_path = tmp_path / "test_policy.json"
    policy_path.write_text(json.dumps(policy_data), encoding="utf-8")
    return policy_path


@pytest.fixture
def policy_service(policy_file):
    """Create a real PolicyService loaded from the test policy file."""
    service = PolicyService(policy_path=str(policy_file))
    service.load_policy()
    return service


@pytest.fixture
def sample_ec2_resources():
    """Sample EC2 resources returned by AWS client."""
    return [
        {
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
            "tags": {
                "Environment": "production",
                "Owner": "team-alpha",
                "Name": "web-server-1",
            },
        },
        {
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-def456",
            "tags": {
                "Environment": "invalid-env",
                "Name": "web-server-2",
            },
        },
        {
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-ghi789",
            "tags": {
                "Name": "web-server-3",
            },
        },
    ]


# =============================================================================
# Tests for TagDriftEntry model
# =============================================================================


class TestTagDriftEntry:
    """Test TagDriftEntry Pydantic model."""

    def test_model_fields(self):
        """Test that TagDriftEntry has all expected fields."""
        entry = TagDriftEntry(
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
            resource_id="i-abc123",
            resource_type="ec2:instance",
            region="us-east-1",
            tag_key="Environment",
            drift_type="removed",
            old_value="production",
            new_value=None,
            severity="critical",
        )
        assert entry.resource_arn == "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123"
        assert entry.resource_id == "i-abc123"
        assert entry.resource_type == "ec2:instance"
        assert entry.region == "us-east-1"
        assert entry.tag_key == "Environment"
        assert entry.drift_type == "removed"
        assert entry.old_value == "production"
        assert entry.new_value is None
        assert entry.severity == "critical"

    def test_model_defaults(self):
        """Test default values for optional fields."""
        entry = TagDriftEntry(
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
            resource_id="i-abc123",
            resource_type="ec2:instance",
            tag_key="Environment",
            drift_type="removed",
            severity="critical",
        )
        assert entry.region == ""
        assert entry.old_value is None
        assert entry.new_value is None

    def test_model_changed_drift(self):
        """Test TagDriftEntry for a 'changed' drift type."""
        entry = TagDriftEntry(
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
            resource_id="i-abc123",
            resource_type="ec2:instance",
            region="us-east-1",
            tag_key="Environment",
            drift_type="changed",
            old_value=None,
            new_value="invalid-env",
            severity="warning",
        )
        assert entry.drift_type == "changed"
        assert entry.new_value == "invalid-env"
        assert entry.severity == "warning"

    def test_model_serialization(self):
        """Test that TagDriftEntry serializes correctly."""
        entry = TagDriftEntry(
            resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
            resource_id="i-abc123",
            resource_type="ec2:instance",
            region="us-east-1",
            tag_key="Owner",
            drift_type="removed",
            severity="critical",
        )
        entry_dict = entry.model_dump()
        assert "resource_arn" in entry_dict
        assert "drift_type" in entry_dict
        assert "severity" in entry_dict
        assert entry_dict["old_value"] is None
        assert entry_dict["new_value"] is None


# =============================================================================
# Tests for DetectTagDriftResult model
# =============================================================================


class TestDetectTagDriftResult:
    """Test DetectTagDriftResult Pydantic model."""

    def test_empty_result(self):
        """Test result with no drifts."""
        result = DetectTagDriftResult(
            drift_detected=[],
            resources_analyzed=10,
            lookback_days=7,
            summary={"added": 0, "removed": 0, "changed": 0},
        )
        assert result.total_drifts == 0
        assert result.resources_analyzed == 10
        assert result.lookback_days == 7
        assert result.drift_detected == []

    def test_total_drifts_computed_from_drift_detected(self):
        """Test that total_drifts equals len(drift_detected)."""
        entries = [
            TagDriftEntry(
                resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
                resource_id="i-abc123",
                resource_type="ec2:instance",
                tag_key="Environment",
                drift_type="removed",
                severity="critical",
            ),
            TagDriftEntry(
                resource_arn="arn:aws:ec2:us-east-1:123456789012:instance/i-def456",
                resource_id="i-def456",
                resource_type="ec2:instance",
                tag_key="Owner",
                drift_type="removed",
                severity="critical",
            ),
        ]
        result = DetectTagDriftResult(
            drift_detected=entries,
            resources_analyzed=5,
            lookback_days=7,
            summary={"added": 0, "removed": 2, "changed": 0},
        )
        assert result.total_drifts == 2
        assert result.total_drifts == len(result.drift_detected)

    def test_default_values(self):
        """Test DetectTagDriftResult default values."""
        result = DetectTagDriftResult()
        assert result.drift_detected == []
        assert result.total_drifts == 0
        assert result.resources_analyzed == 0
        assert result.lookback_days == 7
        assert result.baseline_timestamp is None
        assert result.summary == {}

    def test_scan_timestamp_is_utc(self):
        """Test that scan_timestamp is timezone-aware UTC."""
        result = DetectTagDriftResult()
        assert result.scan_timestamp.tzinfo is not None

    def test_model_serialization(self):
        """Test that the result model serializes correctly."""
        result = DetectTagDriftResult(
            drift_detected=[],
            resources_analyzed=5,
            lookback_days=14,
            summary={"added": 0, "removed": 0, "changed": 0},
        )
        result_dict = result.model_dump()
        assert "drift_detected" in result_dict
        assert "total_drifts" in result_dict
        assert "resources_analyzed" in result_dict
        assert "lookback_days" in result_dict
        assert "summary" in result_dict


# =============================================================================
# Tests for _infer_resource_type helper
# =============================================================================


class TestInferResourceType:
    """Test _infer_resource_type helper function."""

    def test_ec2_instance(self):
        """Test inferring ec2:instance from EC2 instance ARN."""
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123"
        assert _infer_resource_type(arn) == "ec2:instance"

    def test_rds_db(self):
        """Test inferring rds:db from RDS ARN."""
        arn = "arn:aws:rds:us-east-1:123456789012:db:mydb"
        assert _infer_resource_type(arn) == "rds:db"

    def test_s3_bucket(self):
        """Test inferring s3 type from S3 bucket ARN."""
        arn = "arn:aws:s3:::my-bucket"
        # S3 ARN structure: arn:aws:s3:::bucket-name (parts[5] = bucket-name)
        result = _infer_resource_type(arn)
        assert result.startswith("s3:")

    def test_lambda_function(self):
        """Test inferring lambda:function from Lambda ARN."""
        arn = "arn:aws:lambda:us-east-1:123456789012:function:my-func"
        assert _infer_resource_type(arn) == "lambda:function"

    def test_invalid_arn(self):
        """Test that invalid ARN returns 'unknown'."""
        assert _infer_resource_type("not-an-arn") == "unknown"

    def test_empty_string(self):
        """Test that empty string returns 'unknown'."""
        assert _infer_resource_type("") == "unknown"

    def test_short_arn(self):
        """Test ARN with fewer than 6 parts."""
        assert _infer_resource_type("arn:aws:ec2") == "unknown"


# =============================================================================
# Tests for _extract_region_from_arn helper
# =============================================================================


class TestExtractRegionFromArn:
    """Test _extract_region_from_arn helper function."""

    def test_us_east_1(self):
        """Test extracting us-east-1 region."""
        arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123"
        assert _extract_region_from_arn(arn) == "us-east-1"

    def test_eu_west_1(self):
        """Test extracting eu-west-1 region."""
        arn = "arn:aws:rds:eu-west-1:123456789012:db:mydb"
        assert _extract_region_from_arn(arn) == "eu-west-1"

    def test_global_resource(self):
        """Test that S3 bucket ARN (no region) returns 'global'."""
        arn = "arn:aws:s3:::my-bucket"
        assert _extract_region_from_arn(arn) == "global"

    def test_invalid_arn(self):
        """Test that invalid ARN returns 'unknown'."""
        assert _extract_region_from_arn("not-an-arn") == "unknown"

    def test_empty_string(self):
        """Test that empty string returns 'unknown'."""
        assert _extract_region_from_arn("") == "unknown"


# =============================================================================
# Tests for _classify_severity helper
# =============================================================================


class TestClassifySeverity:
    """Test _classify_severity helper function."""

    def test_required_tag_removed_is_critical(self, policy_service):
        """Test that removing a required tag is classified as critical."""
        policy = policy_service.get_policy()
        severity = _classify_severity("Environment", policy, "removed")
        assert severity == "critical"

    def test_required_tag_changed_is_warning(self, policy_service):
        """Test that changing a required tag value is classified as warning."""
        policy = policy_service.get_policy()
        severity = _classify_severity("Environment", policy, "changed")
        assert severity == "warning"

    def test_optional_tag_removed_is_info(self, policy_service):
        """Test that removing an optional tag is classified as info."""
        policy = policy_service.get_policy()
        severity = _classify_severity("Project", policy, "removed")
        assert severity == "info"

    def test_optional_tag_changed_is_info(self, policy_service):
        """Test that changing an optional tag is classified as info."""
        policy = policy_service.get_policy()
        severity = _classify_severity("Project", policy, "changed")
        assert severity == "info"

    def test_unknown_tag_is_info(self, policy_service):
        """Test that an unknown tag drift is classified as info."""
        policy = policy_service.get_policy()
        severity = _classify_severity("UnknownTag", policy, "removed")
        assert severity == "info"

    def test_required_tag_added_is_info(self, policy_service):
        """Test that adding a required tag is classified as info."""
        policy = policy_service.get_policy()
        severity = _classify_severity("Environment", policy, "added")
        assert severity == "info"


# =============================================================================
# Tests for _find_tag_definition helper
# =============================================================================


class TestFindTagDefinition:
    """Test _find_tag_definition helper function."""

    def test_find_required_tag(self, policy_service):
        """Test finding a required tag in the policy."""
        policy = policy_service.get_policy()
        tag_def = _find_tag_definition(policy, "Environment")
        assert tag_def is not None
        assert tag_def.name == "Environment"

    def test_find_optional_tag(self, policy_service):
        """Test finding an optional tag in the policy."""
        policy = policy_service.get_policy()
        tag_def = _find_tag_definition(policy, "Project")
        assert tag_def is not None
        assert tag_def.name == "Project"

    def test_find_nonexistent_tag(self, policy_service):
        """Test finding a tag that does not exist in policy."""
        policy = policy_service.get_policy()
        tag_def = _find_tag_definition(policy, "NonExistent")
        assert tag_def is None

    def test_find_tag_with_allowed_values(self, policy_service):
        """Test that found tag has allowed_values when defined."""
        policy = policy_service.get_policy()
        tag_def = _find_tag_definition(policy, "Environment")
        assert tag_def is not None
        assert tag_def.allowed_values is not None
        assert "production" in tag_def.allowed_values


# =============================================================================
# Tests for detect_tag_drift tool function
# =============================================================================


class TestDetectTagDriftTool:
    """Test the detect_tag_drift async tool function."""

    @pytest.mark.asyncio
    async def test_default_parameters(self, mock_aws_client, policy_service):
        """Test detect_tag_drift with default parameters."""
        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
        )

        assert isinstance(result, DetectTagDriftResult)
        assert result.lookback_days == 7
        assert result.resources_analyzed == 0
        assert result.total_drifts == 0

    @pytest.mark.asyncio
    async def test_default_resource_types(self, mock_aws_client, policy_service):
        """Test that default resource_types is ec2, s3, rds."""
        await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
        )

        # Should have been called 3 times: ec2:instance, s3:bucket, rds:db
        assert mock_aws_client.get_all_tagged_resources.call_count == 3
        call_args_list = mock_aws_client.get_all_tagged_resources.call_args_list
        resource_types_queried = [
            call.kwargs.get("resource_type_filters", call.args[0] if call.args else None)
            for call in call_args_list
        ]
        # Flatten for inspection
        flat_types = []
        for rt in resource_types_queried:
            if isinstance(rt, list):
                flat_types.extend(rt)
            else:
                flat_types.append(rt)
        assert "ec2:instance" in flat_types
        assert "s3:bucket" in flat_types
        assert "rds:db" in flat_types

    @pytest.mark.asyncio
    async def test_custom_resource_types(self, mock_aws_client, policy_service):
        """Test detect_tag_drift with custom resource_types."""
        await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["lambda:function"],
        )

        assert mock_aws_client.get_all_tagged_resources.call_count == 1

    @pytest.mark.asyncio
    async def test_lookback_days_validation_too_low(self, mock_aws_client, policy_service):
        """Test that lookback_days < 1 raises ValueError."""
        with pytest.raises(ValueError, match="lookback_days must be between 1 and 90"):
            await detect_tag_drift(
                aws_client=mock_aws_client,
                policy_service=policy_service,
                lookback_days=0,
            )

    @pytest.mark.asyncio
    async def test_lookback_days_validation_too_high(self, mock_aws_client, policy_service):
        """Test that lookback_days > 90 raises ValueError."""
        with pytest.raises(ValueError, match="lookback_days must be between 1 and 90"):
            await detect_tag_drift(
                aws_client=mock_aws_client,
                policy_service=policy_service,
                lookback_days=91,
            )

    @pytest.mark.asyncio
    async def test_lookback_days_boundary_min(self, mock_aws_client, policy_service):
        """Test lookback_days=1 is valid."""
        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            lookback_days=1,
        )
        assert result.lookback_days == 1

    @pytest.mark.asyncio
    async def test_lookback_days_boundary_max(self, mock_aws_client, policy_service):
        """Test lookback_days=90 is valid."""
        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            lookback_days=90,
        )
        assert result.lookback_days == 90

    @pytest.mark.asyncio
    async def test_missing_required_tag_detected_as_removed(
        self, mock_aws_client, policy_service, sample_ec2_resources
    ):
        """Test that a missing required tag is detected as 'removed' drift."""
        # i-ghi789 is missing both Environment and Owner
        mock_aws_client.get_all_tagged_resources = AsyncMock(
            return_value=[sample_ec2_resources[2]]  # Only the resource missing tags
        )

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        assert result.total_drifts >= 1
        removed_drifts = [d for d in result.drift_detected if d.drift_type == "removed"]
        assert len(removed_drifts) >= 1

        # Should detect missing Environment tag
        env_drifts = [d for d in removed_drifts if d.tag_key == "Environment"]
        assert len(env_drifts) == 1
        assert env_drifts[0].severity == "critical"

    @pytest.mark.asyncio
    async def test_invalid_tag_value_detected_as_changed(
        self, mock_aws_client, policy_service, sample_ec2_resources
    ):
        """Test that an invalid tag value is detected as 'changed' drift."""
        # i-def456 has Environment="invalid-env" which is not in allowed_values
        mock_aws_client.get_all_tagged_resources = AsyncMock(
            return_value=[sample_ec2_resources[1]]
        )

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        changed_drifts = [d for d in result.drift_detected if d.drift_type == "changed"]
        assert len(changed_drifts) >= 1

        env_changed = [d for d in changed_drifts if d.tag_key == "Environment"]
        assert len(env_changed) == 1
        assert env_changed[0].new_value == "invalid-env"
        assert env_changed[0].severity == "warning"

    @pytest.mark.asyncio
    async def test_compliant_resource_no_drift(
        self, mock_aws_client, policy_service, sample_ec2_resources
    ):
        """Test that a fully compliant resource produces no drift entries."""
        # i-abc123 has valid Environment and Owner
        mock_aws_client.get_all_tagged_resources = AsyncMock(
            return_value=[sample_ec2_resources[0]]
        )

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        assert result.total_drifts == 0
        assert result.drift_detected == []

    @pytest.mark.asyncio
    async def test_resources_analyzed_count(
        self, mock_aws_client, policy_service, sample_ec2_resources
    ):
        """Test that resources_analyzed correctly counts all resources."""
        mock_aws_client.get_all_tagged_resources = AsyncMock(
            return_value=sample_ec2_resources
        )

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        assert result.resources_analyzed == 3

    @pytest.mark.asyncio
    async def test_summary_counts_match_drift_entries(
        self, mock_aws_client, policy_service, sample_ec2_resources
    ):
        """Test that summary counts match the actual drift entries."""
        mock_aws_client.get_all_tagged_resources = AsyncMock(
            return_value=sample_ec2_resources
        )

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        # Count drifts by type manually
        removed_count = sum(1 for d in result.drift_detected if d.drift_type == "removed")
        changed_count = sum(1 for d in result.drift_detected if d.drift_type == "changed")
        added_count = sum(1 for d in result.drift_detected if d.drift_type == "added")

        assert result.summary.get("removed", 0) == removed_count
        assert result.summary.get("changed", 0) == changed_count
        assert result.summary.get("added", 0) == added_count

    @pytest.mark.asyncio
    async def test_total_drifts_equals_len_drift_detected(
        self, mock_aws_client, policy_service, sample_ec2_resources
    ):
        """Test that total_drifts always equals len(drift_detected)."""
        mock_aws_client.get_all_tagged_resources = AsyncMock(
            return_value=sample_ec2_resources
        )

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        assert result.total_drifts == len(result.drift_detected)

    @pytest.mark.asyncio
    async def test_custom_tag_keys_filter(self, mock_aws_client, policy_service):
        """Test that tag_keys parameter limits which tags are monitored."""
        resource = {
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
            "tags": {},  # Missing all tags
        }
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[resource])

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
            tag_keys=["Owner"],  # Only monitor Owner
        )

        # Should only detect drift for Owner, not Environment
        drift_tags = {d.tag_key for d in result.drift_detected}
        assert "Owner" in drift_tags
        assert "Environment" not in drift_tags

    @pytest.mark.asyncio
    async def test_drift_entry_has_correct_region(
        self, mock_aws_client, policy_service
    ):
        """Test that drift entries have the correct region extracted from ARN."""
        resource = {
            "arn": "arn:aws:ec2:eu-west-1:123456789012:instance/i-abc123",
            "tags": {},
        }
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[resource])

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        for drift in result.drift_detected:
            assert drift.region == "eu-west-1"

    @pytest.mark.asyncio
    async def test_drift_entry_has_correct_resource_id(
        self, mock_aws_client, policy_service
    ):
        """Test that drift entries extract the correct resource ID from ARN."""
        resource = {
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-xyz999",
            "tags": {},
        }
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[resource])

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        for drift in result.drift_detected:
            assert drift.resource_id == "i-xyz999"

    @pytest.mark.asyncio
    async def test_drift_entry_has_correct_resource_type(
        self, mock_aws_client, policy_service
    ):
        """Test that drift entries infer the correct resource type from ARN."""
        resource = {
            "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
            "tags": {},
        }
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[resource])

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        for drift in result.drift_detected:
            assert drift.resource_type == "ec2:instance"

    @pytest.mark.asyncio
    async def test_aws_error_handled_gracefully(self, mock_aws_client, policy_service):
        """Test that AWS API errors are handled gracefully."""
        mock_aws_client.get_all_tagged_resources = AsyncMock(
            side_effect=Exception("AWS API Error")
        )

        # Should not raise, just log warning and return empty results
        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        assert result.resources_analyzed == 0
        assert result.total_drifts == 0

    @pytest.mark.asyncio
    async def test_resource_without_arn_skipped(self, mock_aws_client, policy_service):
        """Test that resources without ARN are skipped."""
        resources = [
            {"arn": "", "tags": {}},
            {"tags": {"Environment": "production"}},
        ]
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=resources)

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance"],
        )

        # Resources without ARN should not be counted
        assert result.resources_analyzed == 0

    @pytest.mark.asyncio
    async def test_applies_to_filtering(self, mock_aws_client, policy_service):
        """Test that tag applies_to filtering works correctly."""
        # Environment applies_to: ["ec2:instance", "rds:db", "s3:bucket"]
        # A lambda function should still be checked for Owner (applies_to: [])
        # but should also be checked for Environment since ec2 ARN maps to ec2:instance
        resource = {
            "arn": "arn:aws:lambda:us-east-1:123456789012:function/my-func",
            "tags": {"Owner": "team-alpha"},
        }
        mock_aws_client.get_all_tagged_resources = AsyncMock(return_value=[resource])

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["lambda:function"],
        )

        # Environment applies_to ec2:instance, rds:db, s3:bucket — NOT lambda:function
        # So Environment drift should NOT be reported for lambda
        env_drifts = [d for d in result.drift_detected if d.tag_key == "Environment"]
        assert len(env_drifts) == 0

        # Owner applies_to [] (all types) and is missing from tags... wait, Owner IS present
        # So no drift for Owner either
        assert result.total_drifts == 0

    @pytest.mark.asyncio
    async def test_multiple_resource_types_scanned(self, mock_aws_client, policy_service):
        """Test scanning multiple resource types in a single call."""
        ec2_resources = [
            {
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123",
                "tags": {"Environment": "production", "Owner": "team-a"},
            }
        ]
        rds_resources = [
            {
                "arn": "arn:aws:rds:us-east-1:123456789012:db:mydb",
                "tags": {},  # Missing all required tags
            }
        ]

        # Return different resources for each resource type call
        mock_aws_client.get_all_tagged_resources = AsyncMock(
            side_effect=[ec2_resources, rds_resources]
        )

        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            resource_types=["ec2:instance", "rds:db"],
        )

        assert result.resources_analyzed == 2
        # EC2 instance is compliant, RDS should have drifts
        assert result.total_drifts >= 1

    @pytest.mark.asyncio
    async def test_lookback_days_passed_through(self, mock_aws_client, policy_service):
        """Test that lookback_days is correctly reflected in result."""
        result = await detect_tag_drift(
            aws_client=mock_aws_client,
            policy_service=policy_service,
            lookback_days=30,
        )

        assert result.lookback_days == 30
