# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Unit tests for MultiRegionScanner service.

Tests the multi-region scanning orchestration including:
- Parallel execution with concurrency control
- Retry logic with exponential backoff
- Result aggregation
- Global resource handling
- Error handling and partial failures

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.clients.regional_client_factory import RegionalClientFactory
from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.enums import Severity
from mcp_server.models.multi_region import (
    GLOBAL_RESOURCE_TYPES,
    MultiRegionComplianceResult,
    RegionalScanResult,
    RegionScanMetadata,
)
from mcp_server.models.violations import Violation
from mcp_server.services.multi_region_scanner import (
    MultiRegionScanner,
    MultiRegionScanError,
    InvalidRegionFilterError,
)
from mcp_server.services.region_discovery_service import RegionDiscoveryService


@pytest.fixture
def mock_region_discovery():
    """Create a mock RegionDiscoveryService."""
    mock = AsyncMock(spec=RegionDiscoveryService)
    mock.get_enabled_regions.return_value = ["us-east-1", "us-west-2", "eu-west-1"]
    return mock


@pytest.fixture
def mock_client_factory():
    """Create a mock RegionalClientFactory."""
    mock = MagicMock(spec=RegionalClientFactory)
    mock.get_client.return_value = MagicMock()
    return mock


@pytest.fixture
def mock_compliance_service():
    """Create a mock ComplianceService."""
    mock = AsyncMock()
    mock.check_compliance.return_value = ComplianceResult(
        compliance_score=0.8,
        total_resources=10,
        compliant_resources=8,
        violations=[],
        cost_attribution_gap=100.0,
    )
    return mock


@pytest.fixture
def compliance_service_factory(mock_compliance_service):
    """Create a factory that returns the mock compliance service."""
    def factory(client):
        return mock_compliance_service
    return factory


@pytest.fixture
def scanner(mock_region_discovery, mock_client_factory, compliance_service_factory):
    """Create a MultiRegionScanner with mocked dependencies."""
    return MultiRegionScanner(
        region_discovery=mock_region_discovery,
        client_factory=mock_client_factory,
        compliance_service_factory=compliance_service_factory,
        max_concurrent_regions=5,
        region_timeout_seconds=60,
        max_retries=2,
    )


class TestMultiRegionScannerInit:
    """Tests for MultiRegionScanner initialization."""

    def test_init_with_defaults(
        self, mock_region_discovery, mock_client_factory, compliance_service_factory
    ):
        """Test scanner initializes with default values."""
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
        )
        
        assert scanner.max_concurrent_regions == 5
        assert scanner.region_timeout_seconds == 60
        assert scanner.max_retries == 3

    def test_init_with_custom_values(
        self, mock_region_discovery, mock_client_factory, compliance_service_factory
    ):
        """Test scanner initializes with custom values."""
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=10,
            region_timeout_seconds=120,
            max_retries=5,
        )
        
        assert scanner.max_concurrent_regions == 10
        assert scanner.region_timeout_seconds == 120
        assert scanner.max_retries == 5


class TestIsGlobalResourceType:
    """Tests for _is_global_resource_type method."""

    def test_s3_bucket_is_global(self, scanner):
        """Test S3 bucket is identified as global."""
        assert scanner._is_global_resource_type("s3:bucket") is True

    def test_iam_role_is_global(self, scanner):
        """Test IAM role is identified as global."""
        assert scanner._is_global_resource_type("iam:role") is True

    def test_ec2_instance_is_regional(self, scanner):
        """Test EC2 instance is identified as regional."""
        assert scanner._is_global_resource_type("ec2:instance") is False

    def test_rds_db_is_regional(self, scanner):
        """Test RDS database is identified as regional."""
        assert scanner._is_global_resource_type("rds:db") is False

    def test_case_insensitive(self, scanner):
        """Test global resource type check is case insensitive."""
        assert scanner._is_global_resource_type("S3:BUCKET") is True
        assert scanner._is_global_resource_type("IAM:Role") is True

    def test_all_global_types(self, scanner):
        """Test all defined global resource types are recognized."""
        for resource_type in GLOBAL_RESOURCE_TYPES:
            assert scanner._is_global_resource_type(resource_type) is True


class TestApplyRegionFilter:
    """Tests for _apply_region_filter method."""

    def test_no_filter_returns_all_regions(self, scanner):
        """Test that no filter returns all enabled regions.
        
        Validates: Requirement 6.4
        """
        enabled = ["us-east-1", "us-west-2", "eu-west-1"]
        result = scanner._apply_region_filter(enabled, None)
        assert result == enabled

    def test_empty_filter_returns_all_regions(self, scanner):
        """Test that empty filter returns all enabled regions.
        
        Validates: Requirement 6.4
        """
        enabled = ["us-east-1", "us-west-2", "eu-west-1"]
        result = scanner._apply_region_filter(enabled, {})
        assert result == enabled

    def test_single_region_filter(self, scanner):
        """Test filtering to a single region.
        
        Validates: Requirement 6.1
        """
        enabled = ["us-east-1", "us-west-2", "eu-west-1"]
        result = scanner._apply_region_filter(enabled, {"regions": "us-east-1"})
        assert result == ["us-east-1"]

    def test_multiple_region_filter(self, scanner):
        """Test filtering to multiple regions.
        
        Validates: Requirements 6.1, 6.2
        """
        enabled = ["us-east-1", "us-west-2", "eu-west-1"]
        result = scanner._apply_region_filter(
            enabled, {"regions": ["us-east-1", "eu-west-1"]}
        )
        assert result == ["us-east-1", "eu-west-1"]

    def test_filter_raises_error_for_invalid_region(self, scanner):
        """Test that filter raises error for invalid/disabled regions.
        
        Validates: Requirement 6.3
        """
        enabled = ["us-east-1", "us-west-2"]
        with pytest.raises(InvalidRegionFilterError) as exc_info:
            scanner._apply_region_filter(
                enabled, {"regions": ["us-east-1", "invalid-region"]}
            )
        
        error = exc_info.value
        assert "invalid-region" in error.invalid_regions
        assert error.enabled_regions == enabled
        assert "invalid-region" in str(error)

    def test_filter_raises_error_for_disabled_region(self, scanner):
        """Test that filter raises error for disabled regions.
        
        Validates: Requirement 6.3
        """
        enabled = ["us-east-1", "us-west-2"]
        # ap-southeast-1 is a valid AWS region but not in enabled list
        with pytest.raises(InvalidRegionFilterError) as exc_info:
            scanner._apply_region_filter(
                enabled, {"regions": ["ap-southeast-1"]}
            )
        
        error = exc_info.value
        assert "ap-southeast-1" in error.invalid_regions
        assert len(error.invalid_regions) == 1

    def test_filter_raises_error_for_multiple_invalid_regions(self, scanner):
        """Test that filter raises error listing all invalid regions.
        
        Validates: Requirement 6.3
        """
        enabled = ["us-east-1", "us-west-2"]
        with pytest.raises(InvalidRegionFilterError) as exc_info:
            scanner._apply_region_filter(
                enabled, {"regions": ["invalid-1", "invalid-2", "us-east-1"]}
            )
        
        error = exc_info.value
        assert "invalid-1" in error.invalid_regions
        assert "invalid-2" in error.invalid_regions
        assert len(error.invalid_regions) == 2
        # us-east-1 should NOT be in invalid_regions
        assert "us-east-1" not in error.invalid_regions

    def test_region_key_alias(self, scanner):
        """Test that 'region' key works as alias for 'regions'.
        
        Validates: Requirement 6.1
        """
        enabled = ["us-east-1", "us-west-2", "eu-west-1"]
        result = scanner._apply_region_filter(enabled, {"region": "us-west-2"})
        assert result == ["us-west-2"]

    def test_region_key_alias_raises_error_for_invalid(self, scanner):
        """Test that 'region' key alias also validates regions.
        
        Validates: Requirement 6.3
        """
        enabled = ["us-east-1", "us-west-2"]
        with pytest.raises(InvalidRegionFilterError):
            scanner._apply_region_filter(enabled, {"region": "invalid-region"})

    def test_filter_preserves_order(self, scanner):
        """Test that filter preserves the order of regions in the filter."""
        enabled = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        result = scanner._apply_region_filter(
            enabled, {"regions": ["eu-west-1", "us-east-1", "ap-southeast-1"]}
        )
        # Order should match the filter, not the enabled list
        assert result == ["eu-west-1", "us-east-1", "ap-southeast-1"]

    def test_filter_with_empty_regions_list(self, scanner):
        """Test that empty regions list in filter returns all enabled regions.
        
        Validates: Requirement 6.4
        """
        enabled = ["us-east-1", "us-west-2", "eu-west-1"]
        result = scanner._apply_region_filter(enabled, {"regions": []})
        assert result == enabled

    def test_filter_with_none_regions_value(self, scanner):
        """Test that None regions value returns all enabled regions.
        
        Validates: Requirement 6.4
        """
        enabled = ["us-east-1", "us-west-2", "eu-west-1"]
        result = scanner._apply_region_filter(enabled, {"regions": None})
        assert result == enabled


class TestInvalidRegionFilterError:
    """Tests for InvalidRegionFilterError exception."""

    def test_error_contains_invalid_regions(self):
        """Test error contains list of invalid regions."""
        error = InvalidRegionFilterError(
            message="Invalid regions",
            invalid_regions=["invalid-1", "invalid-2"],
            enabled_regions=["us-east-1", "us-west-2"],
        )
        
        assert error.invalid_regions == ["invalid-1", "invalid-2"]
        assert error.enabled_regions == ["us-east-1", "us-west-2"]
        assert str(error) == "Invalid regions"

    def test_error_message_includes_details(self):
        """Test error message includes helpful details."""
        error = InvalidRegionFilterError(
            message="Invalid or disabled regions in filter: ['bad-region']. "
                    "Available regions: ['us-east-1', 'us-west-2']",
            invalid_regions=["bad-region"],
            enabled_regions=["us-east-1", "us-west-2"],
        )
        
        assert "bad-region" in str(error)
        assert "us-east-1" in str(error)


class TestIsTransientError:
    """Tests for _is_transient_error method."""

    def test_throttling_is_transient(self, scanner):
        """Test throttling errors are identified as transient."""
        error = Exception("ThrottlingException: Rate exceeded")
        assert scanner._is_transient_error(error) is True

    def test_service_unavailable_is_transient(self, scanner):
        """Test service unavailable errors are transient."""
        error = Exception("ServiceUnavailable: Try again later")
        assert scanner._is_transient_error(error) is True

    def test_internal_error_is_transient(self, scanner):
        """Test internal errors are transient."""
        error = Exception("InternalError: Something went wrong")
        assert scanner._is_transient_error(error) is True

    def test_access_denied_is_not_transient(self, scanner):
        """Test access denied errors are not transient."""
        error = Exception("AccessDenied: You don't have permission")
        assert scanner._is_transient_error(error) is False

    def test_invalid_parameter_is_not_transient(self, scanner):
        """Test invalid parameter errors are not transient."""
        error = Exception("InvalidParameterValue: Bad input")
        assert scanner._is_transient_error(error) is False


class TestCalculateBackoffDelay:
    """Tests for _calculate_backoff_delay method."""

    def test_first_attempt_delay(self, scanner):
        """Test delay for first retry attempt."""
        delay = scanner._calculate_backoff_delay(0)
        # Base delay is 1.0, so delay should be between 1.0 and 1.25 (with jitter)
        assert 1.0 <= delay <= 1.25

    def test_second_attempt_delay(self, scanner):
        """Test delay increases for second attempt."""
        delay = scanner._calculate_backoff_delay(1)
        # Base delay * 2^1 = 2.0, so delay should be between 2.0 and 2.5
        assert 2.0 <= delay <= 2.5

    def test_delay_capped_at_max(self, scanner):
        """Test delay is capped at max_delay_seconds."""
        scanner.max_delay_seconds = 10.0
        delay = scanner._calculate_backoff_delay(10)  # Would be 1024 without cap
        # Should be capped at 10.0 + jitter (up to 2.5)
        assert delay <= 12.5


class TestScanAllRegions:
    """Tests for scan_all_regions method."""

    @pytest.mark.asyncio
    async def test_scans_all_enabled_regions(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that all enabled regions are scanned."""
        mock_region_discovery.get_enabled_regions.return_value = [
            "us-east-1", "us-west-2", "eu-west-1"
        ]
        
        def factory(client):
            return mock_compliance_service
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Should have scanned all 3 regions
        assert result.region_metadata.total_regions == 3
        assert len(result.region_metadata.successful_regions) == 3

    @pytest.mark.asyncio
    async def test_empty_results_are_successful(
        self, mock_region_discovery, mock_client_factory
    ):
        """Test that regions with zero resources are marked as successful."""
        mock_region_discovery.get_enabled_regions.return_value = ["us-east-1"]
        
        # Return empty compliance result
        mock_compliance = AsyncMock()
        mock_compliance.check_compliance.return_value = ComplianceResult(
            compliance_score=1.0,
            total_resources=0,
            compliant_resources=0,
            violations=[],
            cost_attribution_gap=0.0,
        )
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance,
        )
        
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
        )
        
        # Empty result should be successful
        assert "us-east-1" in result.region_metadata.successful_regions
        assert result.compliance_score == 1.0

    @pytest.mark.asyncio
    async def test_partial_failures_continue_scanning(
        self, mock_region_discovery, mock_client_factory
    ):
        """Test that scanning continues when some regions fail."""
        mock_region_discovery.get_enabled_regions.return_value = [
            "us-east-1", "us-west-2", "eu-west-1"
        ]
        
        call_count = 0
        
        async def mock_check_compliance(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Fail on second region
                raise Exception("AccessDenied: Region not accessible")
            return ComplianceResult(
                compliance_score=0.8,
                total_resources=10,
                compliant_resources=8,
                violations=[],
                cost_attribution_gap=100.0,
            )
        
        mock_compliance = AsyncMock()
        mock_compliance.check_compliance = mock_check_compliance
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance,
            max_retries=0,  # No retries for this test
        )
        
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
        )
        
        # Should have 2 successful and 1 failed
        assert len(result.region_metadata.successful_regions) == 2
        assert len(result.region_metadata.failed_regions) == 1

    @pytest.mark.asyncio
    async def test_region_filter_applied(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that region filter limits which regions are scanned."""
        mock_region_discovery.get_enabled_regions.return_value = [
            "us-east-1", "us-west-2", "eu-west-1"
        ]
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
        )
        
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": ["us-east-1"]},
        )
        
        # Should only scan the filtered region
        assert result.region_metadata.total_regions == 1
        assert "us-east-1" in result.region_metadata.successful_regions

    @pytest.mark.asyncio
    async def test_region_filter_with_invalid_region_raises_error(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that invalid region in filter raises InvalidRegionFilterError.
        
        Validates: Requirement 6.3
        """
        mock_region_discovery.get_enabled_regions.return_value = [
            "us-east-1", "us-west-2", "eu-west-1"
        ]
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
        )
        
        with pytest.raises(InvalidRegionFilterError) as exc_info:
            await scanner.scan_all_regions(
                resource_types=["ec2:instance"],
                filters={"regions": ["us-east-1", "invalid-region"]},
            )
        
        error = exc_info.value
        assert "invalid-region" in error.invalid_regions
        assert "us-east-1" not in error.invalid_regions

    @pytest.mark.asyncio
    async def test_region_filter_with_disabled_region_raises_error(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that disabled region in filter raises InvalidRegionFilterError.
        
        Validates: Requirement 6.3
        """
        mock_region_discovery.get_enabled_regions.return_value = [
            "us-east-1", "us-west-2"
        ]
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
        )
        
        # eu-west-1 is a valid AWS region but not enabled in this account
        with pytest.raises(InvalidRegionFilterError) as exc_info:
            await scanner.scan_all_regions(
                resource_types=["ec2:instance"],
                filters={"regions": ["eu-west-1"]},
            )
        
        error = exc_info.value
        assert "eu-west-1" in error.invalid_regions
        assert error.enabled_regions == ["us-east-1", "us-west-2"]

    @pytest.mark.asyncio
    async def test_region_filter_tracks_skipped_regions(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that skipped regions are tracked in metadata.
        
        Validates: Requirements 6.1, 6.2
        """
        mock_region_discovery.get_enabled_regions.return_value = [
            "us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"
        ]
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
        )
        
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": ["us-east-1", "eu-west-1"]},
        )
        
        # Should scan only filtered regions
        assert set(result.region_metadata.successful_regions) == {"us-east-1", "eu-west-1"}
        # Should track skipped regions
        assert set(result.region_metadata.skipped_regions) == {"us-west-2", "ap-southeast-1"}

    @pytest.mark.asyncio
    async def test_no_filter_scans_all_enabled_regions(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that no filter scans all enabled regions.
        
        Validates: Requirement 6.4
        """
        mock_region_discovery.get_enabled_regions.return_value = [
            "us-east-1", "us-west-2", "eu-west-1"
        ]
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
        )
        
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
        )
        
        # Should scan all enabled regions
        assert result.region_metadata.total_regions == 3
        assert set(result.region_metadata.successful_regions) == {
            "us-east-1", "us-west-2", "eu-west-1"
        }
        # No skipped regions when no filter
        assert result.region_metadata.skipped_regions == []


class TestAggregateResults:
    """Tests for _aggregate_results method."""

    def test_aggregates_compliance_score(self, scanner):
        """Test compliance score is calculated correctly across regions."""
        results = [
            RegionalScanResult(
                region="us-east-1",
                success=True,
                resources=[],
                violations=[],
                compliant_count=8,
            ),
            RegionalScanResult(
                region="us-west-2",
                success=True,
                resources=[],
                violations=[],
                compliant_count=6,
            ),
        ]
        
        # Add violations to make total resources = compliant + violations
        results[0].violations = [
            Violation(
                resource_id="arn:aws:ec2:us-east-1:123:instance/i-1",
                resource_type="ec2:instance",
                region="us-east-1",
                tag_name="Environment",
                violation_type="missing_required_tag",
                severity=Severity.ERROR,
                cost_impact_monthly=50.0,
            ),
            Violation(
                resource_id="arn:aws:ec2:us-east-1:123:instance/i-2",
                resource_type="ec2:instance",
                region="us-east-1",
                tag_name="Environment",
                violation_type="missing_required_tag",
                severity=Severity.ERROR,
                cost_impact_monthly=50.0,
            ),
        ]
        results[1].violations = [
            Violation(
                resource_id="arn:aws:ec2:us-west-2:123:instance/i-3",
                resource_type="ec2:instance",
                region="us-west-2",
                tag_name="Environment",
                violation_type="missing_required_tag",
                severity=Severity.ERROR,
                cost_impact_monthly=100.0,
            ),
        ]
        
        aggregated = scanner._aggregate_results(results)
        
        # Total: 8 + 2 + 6 + 1 = 17 resources, 14 compliant
        # Score = 14/17 ≈ 0.824
        assert aggregated.total_resources == 17
        assert aggregated.compliant_resources == 14
        assert 0.82 <= aggregated.compliance_score <= 0.83

    def test_aggregates_cost_gap(self, scanner):
        """Test cost attribution gap is summed across regions."""
        results = [
            RegionalScanResult(
                region="us-east-1",
                success=True,
                resources=[],
                violations=[
                    Violation(
                        resource_id="arn:aws:ec2:us-east-1:123:instance/i-1",
                        resource_type="ec2:instance",
                        region="us-east-1",
                        tag_name="Environment",
                        violation_type="missing_required_tag",
                        severity=Severity.ERROR,
                        cost_impact_monthly=100.0,
                    ),
                ],
                compliant_count=5,
            ),
            RegionalScanResult(
                region="us-west-2",
                success=True,
                resources=[],
                violations=[
                    Violation(
                        resource_id="arn:aws:ec2:us-west-2:123:instance/i-2",
                        resource_type="ec2:instance",
                        region="us-west-2",
                        tag_name="Environment",
                        violation_type="missing_required_tag",
                        severity=Severity.ERROR,
                        cost_impact_monthly=200.0,
                    ),
                ],
                compliant_count=3,
            ),
        ]
        
        aggregated = scanner._aggregate_results(results)
        
        # Total cost gap = 100 + 200 = 300
        assert aggregated.cost_attribution_gap == 300.0

    def test_includes_failed_regions_in_metadata(self, scanner):
        """Test failed regions are tracked in metadata."""
        results = [
            RegionalScanResult(
                region="us-east-1",
                success=True,
                resources=[],
                violations=[],
                compliant_count=5,
            ),
            RegionalScanResult(
                region="us-west-2",
                success=False,
                error_message="Access denied",
            ),
        ]
        
        aggregated = scanner._aggregate_results(results)
        
        assert "us-east-1" in aggregated.region_metadata.successful_regions
        assert "us-west-2" in aggregated.region_metadata.failed_regions

    def test_empty_results_score_is_one(self, scanner):
        """Test compliance score is 1.0 when no resources found."""
        results = [
            RegionalScanResult(
                region="us-east-1",
                success=True,
                resources=[],
                violations=[],
                compliant_count=0,
            ),
        ]
        
        aggregated = scanner._aggregate_results(results)
        
        assert aggregated.compliance_score == 1.0
        assert aggregated.total_resources == 0

    def test_regional_breakdown_included(self, scanner):
        """Test per-region breakdown is included in results."""
        results = [
            RegionalScanResult(
                region="us-east-1",
                success=True,
                resources=[],
                violations=[],
                compliant_count=10,
            ),
            RegionalScanResult(
                region="us-west-2",
                success=True,
                resources=[],
                violations=[
                    Violation(
                        resource_id="arn:aws:ec2:us-west-2:123:instance/i-1",
                        resource_type="ec2:instance",
                        region="us-west-2",
                        tag_name="Environment",
                        violation_type="missing_required_tag",
                        severity=Severity.ERROR,
                        cost_impact_monthly=50.0,
                    ),
                ],
                compliant_count=5,
            ),
        ]
        
        aggregated = scanner._aggregate_results(results)
        
        assert "us-east-1" in aggregated.regional_breakdown
        assert "us-west-2" in aggregated.regional_breakdown
        
        us_east = aggregated.regional_breakdown["us-east-1"]
        assert us_east.total_resources == 10
        assert us_east.compliance_score == 1.0
        
        us_west = aggregated.regional_breakdown["us-west-2"]
        assert us_west.total_resources == 6
        assert us_west.violation_count == 1


class TestScanRegion:
    """Tests for _scan_region method."""

    @pytest.mark.asyncio
    async def test_successful_scan(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test successful region scan returns proper result."""
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
        )
        
        result = await scanner._scan_region(
            region="us-east-1",
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        assert result.success is True
        assert result.region == "us-east-1"
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_timeout_returns_failed_result(
        self, mock_region_discovery, mock_client_factory
    ):
        """Test that timeout returns a failed result."""
        async def slow_check(*args, **kwargs):
            await asyncio.sleep(10)  # Longer than timeout
            return ComplianceResult(
                compliance_score=1.0,
                total_resources=0,
                compliant_resources=0,
                violations=[],
                cost_attribution_gap=0.0,
            )
        
        mock_compliance = AsyncMock()
        mock_compliance.check_compliance = slow_check
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance,
            region_timeout_seconds=1,  # Short timeout
            max_retries=0,
        )
        
        result = await scanner._scan_region(
            region="us-east-1",
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        assert result.success is False
        assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(
        self, mock_region_discovery, mock_client_factory
    ):
        """Test that transient errors trigger retries."""
        call_count = 0
        
        async def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("ThrottlingException: Rate exceeded")
            return ComplianceResult(
                compliance_score=1.0,
                total_resources=5,
                compliant_resources=5,
                violations=[],
                cost_attribution_gap=0.0,
            )
        
        mock_compliance = AsyncMock()
        mock_compliance.check_compliance = failing_then_success
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance,
            max_retries=3,
            base_delay_seconds=0.01,  # Fast retries for testing
        )
        
        result = await scanner._scan_region(
            region="us-east-1",
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        assert result.success is True
        assert call_count == 3  # Failed twice, succeeded on third


class TestMultiRegionScanError:
    """Tests for MultiRegionScanError exception."""

    def test_error_contains_failed_regions(self):
        """Test error contains list of failed regions."""
        error = MultiRegionScanError(
            message="All regions failed",
            failed_regions=["us-east-1", "us-west-2"],
        )
        
        assert error.failed_regions == ["us-east-1", "us-west-2"]
        assert str(error) == "All regions failed"

    def test_error_contains_partial_results(self):
        """Test error can contain partial results."""
        partial = MultiRegionComplianceResult(
            compliance_score=0.5,
            total_resources=10,
            compliant_resources=5,
            violations=[],
            region_metadata=RegionScanMetadata(
                total_regions=3,
                successful_regions=["us-east-1"],
                failed_regions=["us-west-2", "eu-west-1"],
            ),
        )
        
        error = MultiRegionScanError(
            message="Partial failure",
            failed_regions=["us-west-2", "eu-west-1"],
            partial_results=partial,
        )
        
        assert error.partial_results is not None
        assert error.partial_results.compliance_score == 0.5


class TestDisabledMode:
    """Tests for multi-region disabled mode.
    
    When MULTI_REGION_ENABLED=False, the scanner should only scan the default
    region and skip region discovery entirely.
    
    Validates: Requirements 7.1, 7.4
    """

    @pytest.mark.asyncio
    async def test_disabled_mode_scans_only_default_region(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that disabled mode scans only the default region.
        
        Validates: Requirements 7.1, 7.4
        """
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
            multi_region_enabled=False,
            default_region="us-east-1",
        )
        
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
        )
        
        # Should only scan the default region
        assert result.region_metadata.total_regions == 1
        assert result.region_metadata.successful_regions == ["us-east-1"]
        assert result.region_metadata.failed_regions == []
        assert result.region_metadata.skipped_regions == []

    @pytest.mark.asyncio
    async def test_disabled_mode_skips_region_discovery(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that disabled mode does not call region discovery.
        
        Validates: Requirements 7.1, 7.4
        """
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
            multi_region_enabled=False,
            default_region="us-west-2",
        )
        
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
        )
        
        # Region discovery should NOT be called when disabled
        mock_region_discovery.get_enabled_regions.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_mode_uses_custom_default_region(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that disabled mode uses the configured default region.
        
        Validates: Requirement 7.4
        """
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
            multi_region_enabled=False,
            default_region="eu-west-1",
        )
        
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
        )
        
        # Should scan the custom default region
        assert result.region_metadata.successful_regions == ["eu-west-1"]
        assert "eu-west-1" in result.regional_breakdown

    @pytest.mark.asyncio
    async def test_disabled_mode_ignores_region_filter(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that disabled mode ignores region filters.
        
        When multi-region is disabled, region filters should be ignored
        and only the default region should be scanned.
        
        Validates: Requirements 7.1, 7.4
        """
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
            multi_region_enabled=False,
            default_region="us-east-1",
        )
        
        # Even with a region filter, disabled mode should only scan default region
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": ["us-west-2", "eu-west-1"]},
        )
        
        # Should still only scan the default region
        assert result.region_metadata.total_regions == 1
        assert result.region_metadata.successful_regions == ["us-east-1"]

    @pytest.mark.asyncio
    async def test_enabled_mode_scans_all_regions(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that enabled mode scans all discovered regions.
        
        Validates: Requirement 7.1 (contrast with disabled mode)
        """
        mock_region_discovery.get_enabled_regions.return_value = [
            "us-east-1", "us-west-2", "eu-west-1"
        ]
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
            multi_region_enabled=True,  # Explicitly enabled
            default_region="us-east-1",
        )
        
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
        )
        
        # Should scan all discovered regions
        assert result.region_metadata.total_regions == 3
        assert set(result.region_metadata.successful_regions) == {
            "us-east-1", "us-west-2", "eu-west-1"
        }

    @pytest.mark.asyncio
    async def test_enabled_mode_calls_region_discovery(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that enabled mode calls region discovery.
        
        Validates: Requirement 7.1 (contrast with disabled mode)
        """
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
            multi_region_enabled=True,
            default_region="us-east-1",
        )
        
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
        )
        
        # Region discovery SHOULD be called when enabled
        mock_region_discovery.get_enabled_regions.assert_called_once()

    def test_init_with_disabled_mode(
        self, mock_region_discovery, mock_client_factory, compliance_service_factory
    ):
        """Test scanner initializes correctly with disabled mode."""
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            multi_region_enabled=False,
            default_region="ap-southeast-1",
        )
        
        assert scanner.multi_region_enabled is False
        assert scanner.default_region == "ap-southeast-1"

    def test_init_defaults_to_enabled(
        self, mock_region_discovery, mock_client_factory, compliance_service_factory
    ):
        """Test scanner defaults to multi-region enabled."""
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
        )
        
        assert scanner.multi_region_enabled is True
        assert scanner.default_region == "us-east-1"

    @pytest.mark.asyncio
    async def test_disabled_mode_handles_global_resources(
        self, mock_region_discovery, mock_client_factory, mock_compliance_service
    ):
        """Test that disabled mode correctly handles global resources.
        
        Global resources should still be scanned from the default region.
        
        Validates: Requirements 7.1, 7.4
        """
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance_service,
            multi_region_enabled=False,
            default_region="us-east-1",
        )
        
        # Scan both global and regional resource types
        result = await scanner.scan_all_regions(
            resource_types=["s3:bucket", "ec2:instance"],
        )
        
        # Should still only scan from default region
        assert result.region_metadata.total_regions == 1
        assert result.region_metadata.successful_regions == ["us-east-1"]

    @pytest.mark.asyncio
    async def test_disabled_mode_with_scan_failure(
        self, mock_region_discovery, mock_client_factory
    ):
        """Test that disabled mode handles scan failures correctly.
        
        Validates: Requirements 7.1, 7.4
        """
        async def failing_check(*args, **kwargs):
            raise Exception("AccessDenied: Region not accessible")
        
        mock_compliance = AsyncMock()
        mock_compliance.check_compliance = failing_check
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda c: mock_compliance,
            multi_region_enabled=False,
            default_region="us-east-1",
            max_retries=0,
        )
        
        # When the only region fails, should raise MultiRegionScanError
        with pytest.raises(MultiRegionScanError) as exc_info:
            await scanner.scan_all_regions(
                resource_types=["ec2:instance"],
            )
        
        error = exc_info.value
        assert "us-east-1" in error.failed_regions
        assert error.partial_results is not None
        assert error.partial_results.region_metadata.total_regions == 1
