# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Unit tests for check_tag_compliance tool with multi-region scanner support.

Tests the check_tag_compliance tool's integration with MultiRegionScanner,
including backward compatibility for single-region mode.

Requirements: 3.1, 7.4
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.enums import Severity, ViolationType
from mcp_server.models.multi_region import (
    MultiRegionComplianceResult,
    RegionalSummary,
    RegionScanMetadata,
)
from mcp_server.models.violations import Violation
from mcp_server.services.compliance_service import ComplianceService
from mcp_server.services.history_service import HistoryService
from mcp_server.services.multi_region_scanner import MultiRegionScanner
from mcp_server.tools.check_tag_compliance import check_tag_compliance


@pytest.fixture
def mock_compliance_service():
    """Create a mock ComplianceService."""
    service = MagicMock(spec=ComplianceService)
    service.check_compliance = AsyncMock(
        return_value=ComplianceResult(
            compliance_score=0.8,
            total_resources=10,
            compliant_resources=8,
            violations=[],
            cost_attribution_gap=100.0,
            scan_timestamp=datetime.utcnow(),
        )
    )
    return service


@pytest.fixture
def mock_multi_region_scanner():
    """Create a mock MultiRegionScanner with multi-region enabled."""
    scanner = MagicMock(spec=MultiRegionScanner)
    scanner.multi_region_enabled = True
    scanner.scan_all_regions = AsyncMock(
        return_value=MultiRegionComplianceResult(
            compliance_score=0.75,
            total_resources=50,
            compliant_resources=37,
            violations=[],
            cost_attribution_gap=500.0,
            scan_timestamp=datetime.utcnow(),
            region_metadata=RegionScanMetadata(
                total_regions=5,
                successful_regions=["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"],
                failed_regions=["ap-northeast-1"],
                skipped_regions=[],
            ),
            regional_breakdown={
                "us-east-1": RegionalSummary(
                    region="us-east-1",
                    total_resources=15,
                    compliant_resources=12,
                    compliance_score=0.8,
                    violation_count=3,
                    cost_attribution_gap=100.0,
                ),
                "us-west-2": RegionalSummary(
                    region="us-west-2",
                    total_resources=10,
                    compliant_resources=8,
                    compliance_score=0.8,
                    violation_count=2,
                    cost_attribution_gap=80.0,
                ),
            },
        )
    )
    return scanner


@pytest.fixture
def mock_multi_region_scanner_disabled():
    """Create a mock MultiRegionScanner with multi-region disabled."""
    scanner = MagicMock(spec=MultiRegionScanner)
    scanner.multi_region_enabled = False
    scanner.scan_all_regions = AsyncMock()
    return scanner


@pytest.fixture
def mock_history_service():
    """Create a mock HistoryService."""
    service = MagicMock(spec=HistoryService)
    service.store_scan_result = AsyncMock()
    return service


class TestCheckTagComplianceBackwardCompatibility:
    """Test backward compatibility when multi_region_scanner is not provided."""

    @pytest.mark.asyncio
    async def test_single_region_mode_without_scanner(self, mock_compliance_service):
        """Test that tool works without multi_region_scanner (backward compatible)."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Should use compliance_service directly
        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            force_refresh=False,
        )

        # Should return ComplianceResult
        assert isinstance(result, ComplianceResult)
        assert result.compliance_score == 0.8
        assert result.total_resources == 10

    @pytest.mark.asyncio
    async def test_single_region_mode_with_filters(self, mock_compliance_service):
        """Test single-region mode with filters."""
        filters = {"region": "us-east-1", "account_id": "123456789012"}

        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance", "rds:db"],
            filters=filters,
            severity="errors_only",
        )

        mock_compliance_service.check_compliance.assert_called_once_with(
            resource_types=["ec2:instance", "rds:db"],
            filters=filters,
            severity="errors_only",
            force_refresh=False,
        )

        assert isinstance(result, ComplianceResult)

    @pytest.mark.asyncio
    async def test_force_refresh_passed_to_service(self, mock_compliance_service):
        """Test that force_refresh is passed to compliance service."""
        await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            force_refresh=True,
        )

        mock_compliance_service.check_compliance.assert_called_once()
        call_kwargs = mock_compliance_service.check_compliance.call_args.kwargs
        assert call_kwargs["force_refresh"] is True


class TestCheckTagComplianceMultiRegion:
    """Test multi-region scanning mode."""

    @pytest.mark.asyncio
    async def test_multi_region_mode_with_scanner(
        self, mock_compliance_service, mock_multi_region_scanner
    ):
        """Test that multi-region scanner is used when provided and enabled.
        
        Requirements: 3.1 - Route regional resource types through multi-region scanner
        """
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance", "rds:db"],
            filters=None,
            severity="all",
            multi_region_scanner=mock_multi_region_scanner,
        )

        # Should use multi_region_scanner, not compliance_service
        mock_multi_region_scanner.scan_all_regions.assert_called_once_with(
            resource_types=["ec2:instance", "rds:db"],
            filters=None,
            severity="all",
        )
        mock_compliance_service.check_compliance.assert_not_called()

        # Should return MultiRegionComplianceResult
        assert isinstance(result, MultiRegionComplianceResult)
        assert result.compliance_score == 0.75
        assert result.total_resources == 50
        assert len(result.region_metadata.successful_regions) == 4
        assert len(result.region_metadata.failed_regions) == 1

    @pytest.mark.asyncio
    async def test_multi_region_mode_with_region_filter(
        self, mock_compliance_service, mock_multi_region_scanner
    ):
        """Test multi-region mode passes region filters to scanner."""
        filters = {"regions": ["us-east-1", "us-west-2"]}

        await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            filters=filters,
            severity="all",
            multi_region_scanner=mock_multi_region_scanner,
        )

        mock_multi_region_scanner.scan_all_regions.assert_called_once_with(
            resource_types=["ec2:instance"],
            filters=filters,
            severity="all",
        )

    @pytest.mark.asyncio
    async def test_multi_region_disabled_falls_back_to_single_region(
        self, mock_compliance_service, mock_multi_region_scanner_disabled
    ):
        """Test fallback to single-region when multi-region is disabled.
        
        Requirements: 7.4 - Preserve backward compatibility for single-region mode
        """
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            multi_region_scanner=mock_multi_region_scanner_disabled,
        )

        # Should use compliance_service, not multi_region_scanner
        mock_compliance_service.check_compliance.assert_called_once()
        mock_multi_region_scanner_disabled.scan_all_regions.assert_not_called()

        # Should return ComplianceResult (single-region)
        assert isinstance(result, ComplianceResult)

    @pytest.mark.asyncio
    async def test_all_resource_type_uses_single_region(
        self, mock_compliance_service, mock_multi_region_scanner
    ):
        """Test that 'all' resource type uses single-region mode.
        
        The 'all' mode uses AWS Resource Groups Tagging API which handles
        regions differently, so we don't use multi-region scanner for it.
        """
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["all"],
            filters=None,
            severity="all",
            multi_region_scanner=mock_multi_region_scanner,
        )

        # Should use compliance_service for "all" mode
        mock_compliance_service.check_compliance.assert_called_once()
        mock_multi_region_scanner.scan_all_regions.assert_not_called()

        assert isinstance(result, ComplianceResult)


class TestCheckTagComplianceValidation:
    """Test input validation."""

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
                severity="invalid",
            )


class TestCheckTagComplianceHistoryStorage:
    """Test history storage functionality."""

    @pytest.mark.asyncio
    async def test_stores_single_region_result_in_history(
        self, mock_compliance_service, mock_history_service
    ):
        """Test that single-region results are stored in history when requested."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            history_service=mock_history_service,
            store_snapshot=True,
        )

        mock_history_service.store_scan_result.assert_called_once_with(result)

    @pytest.mark.asyncio
    async def test_stores_multi_region_result_in_history(
        self, mock_compliance_service, mock_multi_region_scanner, mock_history_service
    ):
        """Test that multi-region results are stored in history when requested."""
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            multi_region_scanner=mock_multi_region_scanner,
            history_service=mock_history_service,
            store_snapshot=True,
        )

        mock_history_service.store_scan_result.assert_called_once_with(result)
        assert isinstance(result, MultiRegionComplianceResult)

    @pytest.mark.asyncio
    async def test_does_not_store_when_store_snapshot_false(
        self, mock_compliance_service, mock_history_service
    ):
        """Test that results are not stored when store_snapshot is False."""
        await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            history_service=mock_history_service,
            store_snapshot=False,
        )

        mock_history_service.store_scan_result.assert_not_called()

    @pytest.mark.asyncio
    async def test_history_storage_error_does_not_fail_check(
        self, mock_compliance_service, mock_history_service
    ):
        """Test that history storage errors don't fail the compliance check."""
        mock_history_service.store_scan_result = AsyncMock(
            side_effect=Exception("Database error")
        )

        # Should not raise, just log warning
        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            history_service=mock_history_service,
            store_snapshot=True,
        )

        assert result is not None
        assert isinstance(result, ComplianceResult)


class TestCheckTagComplianceMultiRegionWithViolations:
    """Test multi-region scanning with violations."""

    @pytest.mark.asyncio
    async def test_multi_region_result_includes_violations(
        self, mock_compliance_service
    ):
        """Test that multi-region results include violations from all regions."""
        violations = [
            Violation(
                resource_id="i-123",
                resource_type="ec2:instance",
                region="us-east-1",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="CostCenter",
                severity=Severity.ERROR,
                cost_impact_monthly=100.0,
            ),
            Violation(
                resource_id="i-456",
                resource_type="ec2:instance",
                region="us-west-2",
                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                tag_name="Environment",
                severity=Severity.WARNING,
                cost_impact_monthly=50.0,
            ),
        ]

        scanner = MagicMock(spec=MultiRegionScanner)
        scanner.multi_region_enabled = True
        scanner.scan_all_regions = AsyncMock(
            return_value=MultiRegionComplianceResult(
                compliance_score=0.6,
                total_resources=5,
                compliant_resources=3,
                violations=violations,
                cost_attribution_gap=150.0,
                scan_timestamp=datetime.utcnow(),
                region_metadata=RegionScanMetadata(
                    total_regions=2,
                    successful_regions=["us-east-1", "us-west-2"],
                    failed_regions=[],
                    skipped_regions=[],
                ),
                regional_breakdown={},
            )
        )

        result = await check_tag_compliance(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance"],
            multi_region_scanner=scanner,
        )

        assert isinstance(result, MultiRegionComplianceResult)
        assert len(result.violations) == 2
        assert result.violations[0].region == "us-east-1"
        assert result.violations[1].region == "us-west-2"
        assert result.cost_attribution_gap == 150.0
