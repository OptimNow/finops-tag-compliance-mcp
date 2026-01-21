# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Unit tests for check_tag_compliance tool."""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_server.tools.check_tag_compliance import check_tag_compliance
from mcp_server.services.compliance_service import ComplianceService
from mcp_server.services.history_service import HistoryService
from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.violations import Violation
from mcp_server.models.enums import ViolationType, Severity


@pytest.fixture
def sample_compliance_result():
    """Create a sample compliance result for testing."""
    return ComplianceResult(
        compliance_score=0.75,
        total_resources=100,
        compliant_resources=75,
        violations=[
            Violation(
                resource_id="i-1234567890abcdef0",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR,
                current_value=None,
                allowed_values=["Engineering", "Marketing", "Sales"],
                cost_impact_monthly=150.0,
            ),
            Violation(
                resource_id="i-0987654321fedcba0",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.INVALID_VALUE,
                tag_name="Environment",
                severity=Severity.WARNING,
                current_value="prod",
                allowed_values=["production", "staging", "development"],
                cost_impact_monthly=75.0,
            ),
        ],
        cost_attribution_gap=5000.0,
        scan_timestamp=datetime.now(UTC),
    )


@pytest.fixture
def mock_compliance_service(sample_compliance_result):
    """Create a mock compliance service."""
    service = MagicMock(spec=ComplianceService)
    service.check_compliance = AsyncMock(return_value=sample_compliance_result)
    return service


@pytest.fixture
def mock_history_service():
    """Create a mock history service."""
    service = MagicMock(spec=HistoryService)
    service.store_scan_result = AsyncMock(return_value=None)
    return service


class TestCheckTagComplianceValidation:
    """Test input validation for check_tag_compliance tool."""

    @pytest.mark.asyncio
    async def test_empty_resource_types_raises_error(self, mock_compliance_service):
        """Test that empty resource_types raises ValueError."""
        with pytest.raises(ValueError, match="resource_types cannot be empty"):
            await check_tag_compliance(
                compliance_service=mock_compliance_service,
                resource_types=[],
            )

    @pytest.mark.asyncio
    async def test_invalid_resource_type_raises_error(self, mock_compliance_service):
        """Test that invalid resource type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid resource types"):
            await check_tag_compliance(
                compliance_service=mock_compliance_service,
                resource_types=["invalid:type"],
            )

    @pytest.mark.asyncio
    async def test_invalid_severity_raises_error(self, mock_compliance_service):
        """Test that invalid severity raises ValueError."""
        with pytest.raises(ValueError, match="Invalid severity"):
            await check_tag_compliance(
                compliance_service=mock_compliance_service,
                resource_types=["ec2:instance"],
                severity="invalid_severity",
            )

    @pytest.mark.asyncio
    async def test_all_resource_type_is_valid(self, mock_compliance_service):
        """Test that 'all' is a valid resource type."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["all"],
        )
        assert result is not None
        mock_compliance_service.check_compliance.assert_called_once()


class TestCheckTagComplianceBasicFunctionality:
    """Test basic functionality of check_tag_compliance tool."""

    @pytest.mark.asyncio
    async def test_single_resource_type(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test compliance check with single resource type."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
        )

        assert result == sample_compliance_result
        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            force_refresh=False,
        )

    @pytest.mark.asyncio
    async def test_multiple_resource_types(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test compliance check with multiple resource types."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance", "rds:db", "s3:bucket"],
        )

        assert result == sample_compliance_result
        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance", "rds:db", "s3:bucket"],
            filters=None,
            severity="all",
            force_refresh=False,
        )

    @pytest.mark.asyncio
    async def test_with_region_filter(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test compliance check with region filter."""
        filters = {"region": "us-west-2"}

        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            filters=filters,
        )

        assert result == sample_compliance_result
        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance"],
            filters=filters,
            severity="all",
            force_refresh=False,
        )

    @pytest.mark.asyncio
    async def test_with_account_filter(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test compliance check with account ID filter."""
        filters = {"account_id": "123456789012"}

        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            filters=filters,
        )

        assert result == sample_compliance_result
        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance"],
            filters=filters,
            severity="all",
            force_refresh=False,
        )


class TestCheckTagComplianceSeverityFiltering:
    """Test severity filtering in check_tag_compliance tool."""

    @pytest.mark.asyncio
    async def test_errors_only_severity(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test severity filter 'errors_only'."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            severity="errors_only",
        )

        assert result is not None
        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance"],
            filters=None,
            severity="errors_only",
            force_refresh=False,
        )

    @pytest.mark.asyncio
    async def test_warnings_only_severity(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test severity filter 'warnings_only'."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            severity="warnings_only",
        )

        assert result is not None
        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance"],
            filters=None,
            severity="warnings_only",
            force_refresh=False,
        )


class TestCheckTagComplianceForceRefresh:
    """Test force_refresh functionality in check_tag_compliance tool."""

    @pytest.mark.asyncio
    async def test_force_refresh_true(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test compliance check with force_refresh=True."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            force_refresh=True,
        )

        assert result is not None
        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            force_refresh=True,
        )

    @pytest.mark.asyncio
    async def test_force_refresh_false_default(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test compliance check with default force_refresh (False)."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
        )

        assert result is not None
        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            force_refresh=False,
        )


class TestCheckTagComplianceHistoryStorage:
    """Test history storage functionality in check_tag_compliance tool."""

    @pytest.mark.asyncio
    async def test_store_snapshot_true_with_history_service(
        self, mock_compliance_service, mock_history_service, sample_compliance_result
    ):
        """Test that results are stored when store_snapshot=True and history_service provided."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            history_service=mock_history_service,
            store_snapshot=True,
        )

        assert result == sample_compliance_result
        mock_history_service.store_scan_result.assert_called_once_with(
            sample_compliance_result
        )

    @pytest.mark.asyncio
    async def test_store_snapshot_false_no_storage(
        self, mock_compliance_service, mock_history_service, sample_compliance_result
    ):
        """Test that results are not stored when store_snapshot=False."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            history_service=mock_history_service,
            store_snapshot=False,
        )

        assert result == sample_compliance_result
        mock_history_service.store_scan_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_snapshot_true_no_history_service(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test that store_snapshot=True without history_service doesn't raise error."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            history_service=None,
            store_snapshot=True,
        )

        # Should still return result, just without storing
        assert result == sample_compliance_result

    @pytest.mark.asyncio
    async def test_history_storage_failure_doesnt_fail_compliance_check(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test that history storage failure doesn't fail the compliance check."""
        mock_history_service = MagicMock(spec=HistoryService)
        mock_history_service.store_scan_result = AsyncMock(
            side_effect=Exception("Database error")
        )

        # Should still return result despite storage failure
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            history_service=mock_history_service,
            store_snapshot=True,
        )

        assert result == sample_compliance_result


class TestCheckTagComplianceReturnValues:
    """Test return values from check_tag_compliance tool."""

    @pytest.mark.asyncio
    async def test_returns_compliance_result(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test that function returns ComplianceResult."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
        )

        assert isinstance(result, ComplianceResult)

    @pytest.mark.asyncio
    async def test_result_contains_expected_fields(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test that result contains all expected fields."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
        )

        assert hasattr(result, "compliance_score")
        assert hasattr(result, "total_resources")
        assert hasattr(result, "compliant_resources")
        assert hasattr(result, "violations")
        assert hasattr(result, "cost_attribution_gap")
        assert hasattr(result, "scan_timestamp")

    @pytest.mark.asyncio
    async def test_compliance_score_in_valid_range(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test that compliance score is between 0 and 1."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
        )

        assert 0.0 <= result.compliance_score <= 1.0

    @pytest.mark.asyncio
    async def test_violations_is_list(
        self, mock_compliance_service, sample_compliance_result
    ):
        """Test that violations is a list."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
        )

        assert isinstance(result.violations, list)


class TestCheckTagComplianceSupportedResourceTypes:
    """Test that all supported resource types are accepted."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "resource_type",
        [
            "ec2:instance",
            "ec2:volume",
            "rds:db",
            "s3:bucket",
            "lambda:function",
            "ecs:service",
            "ecs:cluster",
            "dynamodb:table",
            "elasticache:cluster",
            "opensearch:domain",
        ],
    )
    async def test_supported_resource_type(
        self, mock_compliance_service, sample_compliance_result, resource_type
    ):
        """Test that supported resource types don't raise errors."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=[resource_type],
        )

        assert result is not None
        mock_compliance_service.check_compliance.assert_called()
