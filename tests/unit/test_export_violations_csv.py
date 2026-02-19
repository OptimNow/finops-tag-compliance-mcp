"""Unit tests for export_violations_csv tool."""

import csv
import io
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.enums import Severity, ViolationType
from mcp_server.models.violations import Violation
from mcp_server.services.compliance_service import ComplianceService
from mcp_server.tools.export_violations_csv import (
    AVAILABLE_COLUMNS,
    DEFAULT_COLUMNS,
    ExportViolationsCsvResult,
    export_violations_csv,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_violations():
    """Create a list of sample violations for testing."""
    return [
        Violation(
            resource_id="i-0001234567890abcd",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="Environment",
            severity=Severity.ERROR,
            current_value=None,
            allowed_values=["production", "staging", "development"],
            cost_impact_monthly=150.50,
        ),
        Violation(
            resource_id="i-0009876543210fedc",
            resource_type="ec2:instance",
            region="us-west-2",
            violation_type=ViolationType.INVALID_VALUE,
            tag_name="CostCenter",
            severity=Severity.WARNING,
            current_value="InvalidDept",
            allowed_values=["Engineering", "Marketing", "Sales"],
            cost_impact_monthly=75.25,
        ),
        Violation(
            resource_id="my-bucket",
            resource_type="s3:bucket",
            region="global",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="Owner",
            severity=Severity.ERROR,
            current_value=None,
            allowed_values=None,
            cost_impact_monthly=0.0,
        ),
    ]


@pytest.fixture
def compliance_result_with_violations(sample_violations):
    """Create a ComplianceResult populated with sample violations."""
    return ComplianceResult(
        compliance_score=0.60,
        total_resources=10,
        compliant_resources=6,
        violations=sample_violations,
        cost_attribution_gap=225.75,
        scan_timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def empty_compliance_result():
    """Create a ComplianceResult with zero violations."""
    return ComplianceResult(
        compliance_score=1.0,
        total_resources=5,
        compliant_resources=5,
        violations=[],
        cost_attribution_gap=0.0,
        scan_timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_compliance_service(compliance_result_with_violations):
    """Create a mock ComplianceService that returns sample violations."""
    service = MagicMock(spec=ComplianceService)
    service.check_compliance = AsyncMock(
        return_value=compliance_result_with_violations
    )
    return service


@pytest.fixture
def mock_compliance_service_empty(empty_compliance_result):
    """Create a mock ComplianceService that returns no violations."""
    service = MagicMock(spec=ComplianceService)
    service.check_compliance = AsyncMock(return_value=empty_compliance_result)
    return service


# =============================================================================
# ExportViolationsCsvResult Model Tests
# =============================================================================


class TestExportViolationsCsvResult:
    """Test ExportViolationsCsvResult Pydantic model."""

    def test_model_fields_present(self):
        """Test that all expected fields exist on the model."""
        result = ExportViolationsCsvResult(
            csv_data="header\nrow1\n",
            row_count=1,
            column_count=1,
            columns=["resource_arn"],
            format="csv",
            filters_applied={"severity": "all"},
        )
        assert result.csv_data == "header\nrow1\n"
        assert result.row_count == 1
        assert result.column_count == 1
        assert result.columns == ["resource_arn"]
        assert result.format == "csv"
        assert result.filters_applied == {"severity": "all"}
        assert isinstance(result.export_timestamp, datetime)

    def test_default_values(self):
        """Test that default values are applied correctly."""
        result = ExportViolationsCsvResult(csv_data="")
        assert result.row_count == 0
        assert result.column_count == 0
        assert result.columns == []
        assert result.format == "csv"
        assert result.filters_applied == {}
        assert result.export_timestamp is not None

    def test_export_timestamp_is_utc(self):
        """Test that the default export_timestamp is in UTC."""
        result = ExportViolationsCsvResult(csv_data="")
        assert result.export_timestamp.tzinfo is not None

    def test_model_serialization(self):
        """Test that the model can be serialized to dict/JSON."""
        result = ExportViolationsCsvResult(
            csv_data="a,b\n1,2\n",
            row_count=1,
            column_count=2,
            columns=["a", "b"],
        )
        result_dict = result.model_dump(mode="json")
        assert "csv_data" in result_dict
        assert "row_count" in result_dict
        assert "export_timestamp" in result_dict


# =============================================================================
# Default and Custom Column Selection Tests
# =============================================================================


class TestColumnSelection:
    """Test column selection logic."""

    @pytest.mark.asyncio
    async def test_default_columns_when_none(self, mock_compliance_service):
        """Test that DEFAULT_COLUMNS are used when columns param is None."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=None,
        )
        assert result.columns == DEFAULT_COLUMNS
        assert result.column_count == len(DEFAULT_COLUMNS)

    @pytest.mark.asyncio
    async def test_custom_columns_selection(self, mock_compliance_service):
        """Test that custom columns are used when specified."""
        custom_cols = ["resource_arn", "tag_name", "severity"]
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=custom_cols,
        )
        assert result.columns == custom_cols
        assert result.column_count == len(custom_cols)

    @pytest.mark.asyncio
    async def test_all_available_columns(self, mock_compliance_service):
        """Test that all available columns can be selected."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=AVAILABLE_COLUMNS,
        )
        assert result.columns == AVAILABLE_COLUMNS
        assert result.column_count == len(AVAILABLE_COLUMNS)

    @pytest.mark.asyncio
    async def test_invalid_column_raises_error(self, mock_compliance_service):
        """Test that specifying an invalid column raises ValueError."""
        with pytest.raises(ValueError, match="Invalid columns"):
            await export_violations_csv(
                compliance_service=mock_compliance_service,
                columns=["resource_arn", "nonexistent_column"],
            )

    @pytest.mark.asyncio
    async def test_single_column(self, mock_compliance_service):
        """Test exporting with a single column."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=["tag_name"],
        )
        assert result.columns == ["tag_name"]
        assert result.column_count == 1

        # Parse CSV and verify only one column
        reader = csv.reader(io.StringIO(result.csv_data))
        header = next(reader)
        assert header == ["tag_name"]


# =============================================================================
# CSV Content and Structure Tests
# =============================================================================


class TestCsvContent:
    """Test CSV data structure and content."""

    @pytest.mark.asyncio
    async def test_csv_has_header_row(self, mock_compliance_service):
        """Test that CSV data contains a header row."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        header = next(reader)
        assert header == DEFAULT_COLUMNS

    @pytest.mark.asyncio
    async def test_csv_has_data_rows(self, mock_compliance_service):
        """Test that CSV data contains correct number of data rows."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        rows = list(reader)
        # First row is header, rest are data
        data_rows = rows[1:]
        assert len(data_rows) == 3  # 3 sample violations

    @pytest.mark.asyncio
    async def test_row_count_matches_csv_data(self, mock_compliance_service):
        """Test that row_count matches the actual number of data rows in csv_data."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        rows = list(reader)
        data_rows = rows[1:]  # Exclude header
        assert result.row_count == len(data_rows)

    @pytest.mark.asyncio
    async def test_violation_type_values_in_csv(self, mock_compliance_service):
        """Test that violation_type is serialized as its string value."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=["violation_type"],
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        next(reader)  # Skip header
        violation_types = [row[0] for row in reader]
        assert "missing_required_tag" in violation_types
        assert "invalid_value" in violation_types

    @pytest.mark.asyncio
    async def test_severity_values_in_csv(self, mock_compliance_service):
        """Test that severity is serialized as its string value."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=["severity"],
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        next(reader)  # Skip header
        severities = [row[0] for row in reader]
        assert "error" in severities
        assert "warning" in severities

    @pytest.mark.asyncio
    async def test_allowed_values_joined_by_semicolon(self, mock_compliance_service):
        """Test that allowed_values are joined with semicolons in CSV."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=["allowed_values"],
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        next(reader)  # Skip header
        rows = list(reader)
        # First violation has allowed_values ["production", "staging", "development"]
        assert rows[0][0] == "production; staging; development"

    @pytest.mark.asyncio
    async def test_cost_impact_formatted_two_decimals(self, mock_compliance_service):
        """Test that cost_impact_monthly is formatted with two decimal places."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=["cost_impact_monthly"],
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        next(reader)  # Skip header
        rows = list(reader)
        assert rows[0][0] == "150.50"
        assert rows[1][0] == "75.25"
        assert rows[2][0] == "0.00"

    @pytest.mark.asyncio
    async def test_null_current_value_becomes_empty_string(
        self, mock_compliance_service
    ):
        """Test that None current_value becomes empty string in CSV."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=["current_value"],
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        next(reader)  # Skip header
        rows = list(reader)
        # First violation has current_value=None
        assert rows[0][0] == ""
        # Second violation has current_value="InvalidDept"
        assert rows[1][0] == "InvalidDept"

    @pytest.mark.asyncio
    async def test_null_allowed_values_becomes_empty_string(
        self, mock_compliance_service
    ):
        """Test that None allowed_values becomes empty string in CSV."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=["allowed_values"],
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        next(reader)  # Skip header
        rows = list(reader)
        # Third violation (Owner on s3:bucket) has allowed_values=None
        assert rows[2][0] == ""

    @pytest.mark.asyncio
    async def test_region_values_in_csv(self, mock_compliance_service):
        """Test that region is correctly populated in CSV."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=["region"],
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        next(reader)  # Skip header
        regions = [row[0] for row in reader]
        assert "us-east-1" in regions
        assert "us-west-2" in regions
        assert "global" in regions


# =============================================================================
# Severity Filtering Tests
# =============================================================================


class TestSeverityFiltering:
    """Test severity filter parameter."""

    @pytest.mark.asyncio
    async def test_severity_all(self, mock_compliance_service):
        """Test that severity='all' passes through to compliance service."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            severity="all",
        )
        mock_compliance_service.check_compliance.assert_called_once()
        call_kwargs = mock_compliance_service.check_compliance.call_args[1]
        assert call_kwargs["severity"] == "all"
        assert result.filters_applied["severity"] == "all"

    @pytest.mark.asyncio
    async def test_severity_errors_only(self, mock_compliance_service):
        """Test that severity='errors_only' passes through to compliance service."""
        await export_violations_csv(
            compliance_service=mock_compliance_service,
            severity="errors_only",
        )
        call_kwargs = mock_compliance_service.check_compliance.call_args[1]
        assert call_kwargs["severity"] == "errors_only"

    @pytest.mark.asyncio
    async def test_severity_warnings_only(self, mock_compliance_service):
        """Test that severity='warnings_only' passes through to compliance service."""
        await export_violations_csv(
            compliance_service=mock_compliance_service,
            severity="warnings_only",
        )
        call_kwargs = mock_compliance_service.check_compliance.call_args[1]
        assert call_kwargs["severity"] == "warnings_only"

    @pytest.mark.asyncio
    async def test_invalid_severity_raises_error(self, mock_compliance_service):
        """Test that an invalid severity value raises ValueError."""
        with pytest.raises(ValueError, match="Invalid severity"):
            await export_violations_csv(
                compliance_service=mock_compliance_service,
                severity="critical",
            )

    @pytest.mark.asyncio
    async def test_filters_applied_contains_severity(self, mock_compliance_service):
        """Test that filters_applied dict reflects the severity used."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            severity="errors_only",
        )
        assert result.filters_applied["severity"] == "errors_only"


# =============================================================================
# Empty Scan Tests
# =============================================================================


class TestEmptyScan:
    """Test behavior when compliance scan returns no violations."""

    @pytest.mark.asyncio
    async def test_empty_scan_returns_header_only(self, mock_compliance_service_empty):
        """Test that empty scan produces CSV with header only."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service_empty,
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        rows = list(reader)
        assert len(rows) == 1  # Header only
        assert rows[0] == DEFAULT_COLUMNS

    @pytest.mark.asyncio
    async def test_empty_scan_row_count_zero(self, mock_compliance_service_empty):
        """Test that empty scan has row_count=0."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service_empty,
        )
        assert result.row_count == 0

    @pytest.mark.asyncio
    async def test_empty_scan_still_has_columns(self, mock_compliance_service_empty):
        """Test that empty scan still reports correct columns."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service_empty,
        )
        assert result.columns == DEFAULT_COLUMNS
        assert result.column_count == len(DEFAULT_COLUMNS)


# =============================================================================
# Resource Types and Filters Tests
# =============================================================================


class TestResourceTypesAndFilters:
    """Test resource_types parameter and filter tracking."""

    @pytest.mark.asyncio
    async def test_default_resource_types_is_all(self, mock_compliance_service):
        """Test that default resource_types is ['all']."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
        )
        assert result.filters_applied["resource_types"] == ["all"]

    @pytest.mark.asyncio
    async def test_specific_resource_types(self, mock_compliance_service):
        """Test that specific resource_types are passed to compliance service."""
        await export_violations_csv(
            compliance_service=mock_compliance_service,
            resource_types=["ec2:instance", "s3:bucket"],
        )
        call_kwargs = mock_compliance_service.check_compliance.call_args[1]
        assert call_kwargs["resource_types"] == ["ec2:instance", "s3:bucket"]

    @pytest.mark.asyncio
    async def test_filters_applied_includes_resource_types(
        self, mock_compliance_service
    ):
        """Test that filters_applied tracks the resource_types used."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            resource_types=["rds:db"],
        )
        assert result.filters_applied["resource_types"] == ["rds:db"]


# =============================================================================
# Multi-Region Scanner Tests
# =============================================================================


class TestMultiRegionScanner:
    """Test multi-region scanner integration."""

    @pytest.mark.asyncio
    async def test_uses_multi_region_scanner_when_provided(
        self, sample_violations
    ):
        """Test that multi_region_scanner is used when provided and enabled."""
        from mcp_server.models.multi_region import (
            MultiRegionComplianceResult,
            RegionScanMetadata,
        )

        mock_scanner = MagicMock()
        mock_scanner.multi_region_enabled = True
        mock_scanner.scan_all_regions = AsyncMock(
            return_value=MultiRegionComplianceResult(
                compliance_score=0.6,
                total_resources=10,
                compliant_resources=6,
                violations=sample_violations,
                region_metadata=RegionScanMetadata(
                    total_regions=2,
                    successful_regions=["us-east-1", "us-west-2"],
                ),
            )
        )

        mock_service = MagicMock(spec=ComplianceService)

        result = await export_violations_csv(
            compliance_service=mock_service,
            multi_region_scanner=mock_scanner,
        )

        mock_scanner.scan_all_regions.assert_called_once()
        mock_service.check_compliance.assert_not_called()
        assert result.row_count == 3

    @pytest.mark.asyncio
    async def test_falls_back_to_compliance_service_when_scanner_disabled(
        self, mock_compliance_service
    ):
        """Test fallback to ComplianceService when scanner is disabled."""
        mock_scanner = MagicMock()
        mock_scanner.multi_region_enabled = False

        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            multi_region_scanner=mock_scanner,
        )

        mock_compliance_service.check_compliance.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_compliance_service_when_scanner_none(
        self, mock_compliance_service
    ):
        """Test fallback to ComplianceService when scanner is None."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            multi_region_scanner=None,
        )

        mock_compliance_service.check_compliance.assert_called_once()


# =============================================================================
# Result Consistency Tests
# =============================================================================


class TestResultConsistency:
    """Test consistency between result fields."""

    @pytest.mark.asyncio
    async def test_format_is_always_csv(self, mock_compliance_service):
        """Test that the format field is always 'csv'."""
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
        )
        assert result.format == "csv"

    @pytest.mark.asyncio
    async def test_column_count_matches_columns_list(self, mock_compliance_service):
        """Test that column_count equals length of columns list."""
        custom_cols = ["resource_arn", "tag_name", "severity", "region"]
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=custom_cols,
        )
        assert result.column_count == len(result.columns)

    @pytest.mark.asyncio
    async def test_csv_columns_match_reported_columns(self, mock_compliance_service):
        """Test that CSV header matches the reported columns list."""
        custom_cols = ["resource_type", "tag_name", "severity"]
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
            columns=custom_cols,
        )
        reader = csv.reader(io.StringIO(result.csv_data))
        header = next(reader)
        assert header == result.columns

    @pytest.mark.asyncio
    async def test_export_timestamp_is_recent(self, mock_compliance_service):
        """Test that export_timestamp is close to current time."""
        before = datetime.now(timezone.utc)
        result = await export_violations_csv(
            compliance_service=mock_compliance_service,
        )
        after = datetime.now(timezone.utc)
        assert before <= result.export_timestamp <= after
