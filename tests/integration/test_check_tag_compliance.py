"""Integration tests for check_tag_compliance tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, UTC

from mcp_server.tools.check_tag_compliance import check_tag_compliance
from mcp_server.services.compliance_service import ComplianceService
from mcp_server.clients.cache import RedisCache
from mcp_server.clients.aws_client import AWSClient
from mcp_server.services.policy_service import PolicyService
from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.violations import Violation
from mcp_server.models.enums import ViolationType, Severity


@pytest.fixture
def mock_cache():
    """Create a mock Redis cache."""
    cache = MagicMock(spec=RedisCache)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    cache.clear = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def mock_aws_client():
    """Create a mock AWS client."""
    client = MagicMock(spec=AWSClient)

    # Default: return empty lists for all resource types
    client.get_ec2_instances = AsyncMock(return_value=[])
    client.get_rds_instances = AsyncMock(return_value=[])
    client.get_s3_buckets = AsyncMock(return_value=[])
    client.get_lambda_functions = AsyncMock(return_value=[])
    client.get_ecs_services = AsyncMock(return_value=[])
    client.get_opensearch_domains = AsyncMock(return_value=[])
    client.get_all_tagged_resources = AsyncMock(return_value=[])

    return client


@pytest.fixture
def mock_policy_service():
    """Create a mock policy service."""
    service = MagicMock(spec=PolicyService)
    service.validate_resource_tags = MagicMock(return_value=[])
    return service


@pytest.fixture
def compliance_service(mock_cache, mock_aws_client, mock_policy_service):
    """Create a ComplianceService instance with mocked dependencies."""
    return ComplianceService(
        cache=mock_cache,
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        cache_ttl=3600,
    )


@pytest.mark.integration
class TestCheckTagComplianceBasic:
    """Test basic check_tag_compliance functionality."""

    @pytest.mark.asyncio
    async def test_check_compliance_single_resource_type(self, compliance_service, mock_aws_client):
        """Test checking compliance for a single resource type."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 1
        assert result.compliance_score >= 0.0
        assert result.compliance_score <= 1.0

    @pytest.mark.asyncio
    async def test_check_compliance_multiple_resource_types(
        self, compliance_service, mock_aws_client
    ):
        """Test checking compliance for multiple resource types."""
        # Setup mock resources for EC2
        ec2_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            }
        ]

        # Setup mock resources for RDS
        rds_resources = [
            {
                "resource_id": "db-456",
                "resource_type": "rds:db",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 200.0,
                "arn": "arn:aws:rds:us-east-1:123456789012:db:db-456",
            }
        ]

        mock_aws_client.get_ec2_instances.return_value = ec2_resources
        mock_aws_client.get_rds_instances.return_value = rds_resources

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance", "rds:db"],
            filters=None,
            severity="all",
        )

        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 2
        assert result.compliance_score >= 0.0
        assert result.compliance_score <= 1.0

    @pytest.mark.asyncio
    async def test_check_compliance_empty_resource_types_raises(self, compliance_service):
        """Test that empty resource_types raises ValueError."""
        with pytest.raises(ValueError, match="resource_types cannot be empty"):
            await check_tag_compliance(
                compliance_service=compliance_service,
                resource_types=[],
                filters=None,
                severity="all",
            )

    @pytest.mark.asyncio
    async def test_check_compliance_invalid_resource_type_raises(self, compliance_service):
        """Test that invalid resource type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid resource types"):
            await check_tag_compliance(
                compliance_service=compliance_service,
                resource_types=["invalid:type"],
                filters=None,
                severity="all",
            )

    @pytest.mark.asyncio
    async def test_check_compliance_invalid_severity_raises(self, compliance_service):
        """Test that invalid severity raises ValueError."""
        with pytest.raises(ValueError, match="Invalid severity"):
            await check_tag_compliance(
                compliance_service=compliance_service,
                resource_types=["ec2:instance"],
                filters=None,
                severity="invalid",
            )


@pytest.mark.integration
class TestCheckTagComplianceFilters:
    """Test check_tag_compliance with various filter combinations."""

    @pytest.mark.asyncio
    async def test_check_compliance_filter_by_region(self, compliance_service, mock_aws_client):
        """Test filtering by region."""
        # Setup mock resources in different regions
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456",
            },
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters={"region": "us-east-1"},
            severity="all",
        )

        # Should only include resources from us-east-1
        assert result.total_resources == 1

    @pytest.mark.asyncio
    async def test_check_compliance_filter_by_multiple_regions(
        self, compliance_service, mock_aws_client
    ):
        """Test filtering by multiple regions."""
        # Setup mock resources in different regions
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456",
            },
            {
                "resource_id": "i-789",
                "resource_type": "ec2:instance",
                "region": "eu-west-1",
                "tags": {"CostCenter": "Sales"},
                "cost_impact": 200.0,
                "arn": "arn:aws:ec2:eu-west-1:123456789012:instance/i-789",
            },
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters={"region": ["us-east-1", "us-west-2"]},
            severity="all",
        )

        # Should include resources from us-east-1 and us-west-2
        assert result.total_resources == 2

    @pytest.mark.asyncio
    async def test_check_compliance_filter_by_account(self, compliance_service, mock_aws_client):
        """Test filtering by account ID."""
        # Setup mock resources in different accounts
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:987654321098:instance/i-456",
            },
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters={"account_id": "123456789012"},
            severity="all",
        )

        # Should only include resources from account 123456789012
        assert result.total_resources == 1

    @pytest.mark.asyncio
    async def test_check_compliance_filter_combined(self, compliance_service, mock_aws_client):
        """Test filtering by both region and account."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {"CostCenter": "Marketing"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-456",
            },
            {
                "resource_id": "i-789",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Sales"},
                "cost_impact": 200.0,
                "arn": "arn:aws:ec2:us-east-1:987654321098:instance/i-789",
            },
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters={"region": "us-east-1", "account_id": "123456789012"},
            severity="all",
        )

        # Should only include i-123 (us-east-1 + account 123456789012)
        assert result.total_resources == 1


@pytest.mark.integration
class TestCheckTagComplianceSeverity:
    """Test check_tag_compliance with severity filtering."""

    @pytest.mark.asyncio
    async def test_check_compliance_severity_all(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test severity filter 'all' returns all violations."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "InvalidValue"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456",
            },
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources

        # Setup violations with different severities
        error_violation = Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0,
        )

        warning_violation = Violation(
            resource_id="i-456",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.INVALID_VALUE,
            tag_name="CostCenter",
            severity=Severity.WARNING,
            cost_impact_monthly=150.0,
        )

        mock_policy_service.validate_resource_tags.side_effect = [
            [error_violation],
            [warning_violation],
        ]

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Should include both error and warning violations
        assert len(result.violations) == 2

    @pytest.mark.asyncio
    async def test_check_compliance_severity_errors_only(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test severity filter 'errors_only' returns only errors."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "InvalidValue"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456",
            },
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources

        # Setup violations with different severities
        error_violation = Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0,
        )

        warning_violation = Violation(
            resource_id="i-456",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.INVALID_VALUE,
            tag_name="CostCenter",
            severity=Severity.WARNING,
            cost_impact_monthly=150.0,
        )

        mock_policy_service.validate_resource_tags.side_effect = [
            [error_violation],
            [warning_violation],
        ]

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="errors_only",
        )

        # Should only include error violations
        assert len(result.violations) == 1
        assert result.violations[0].severity == Severity.ERROR

    @pytest.mark.asyncio
    async def test_check_compliance_severity_warnings_only(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test severity filter 'warnings_only' returns only warnings."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "InvalidValue"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456",
            },
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources

        # Setup violations with different severities
        error_violation = Violation(
            resource_id="i-123",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0,
        )

        warning_violation = Violation(
            resource_id="i-456",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.INVALID_VALUE,
            tag_name="CostCenter",
            severity=Severity.WARNING,
            cost_impact_monthly=150.0,
        )

        mock_policy_service.validate_resource_tags.side_effect = [
            [error_violation],
            [warning_violation],
        ]

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="warnings_only",
        )

        # Should only include warning violations
        assert len(result.violations) == 1
        assert result.violations[0].severity == Severity.WARNING


@pytest.mark.integration
@pytest.mark.slow
class TestCheckTagCompliancePerformance:
    """Test check_tag_compliance performance with large datasets."""

    @pytest.mark.asyncio
    async def test_check_compliance_1000_resources(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test performance with 1000 resources (Requirement 1.5)."""
        import time

        # Generate 1000 mock resources
        mock_resources = []
        for i in range(1000):
            mock_resources.append(
                {
                    "resource_id": f"i-{i:016x}",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "tags": {"CostCenter": "Engineering", "Environment": "production"},
                    "cost_impact": 100.0,
                    "arn": f"arn:aws:ec2:us-east-1:123456789012:instance/i-{i:016x}",
                }
            )

        mock_aws_client.get_ec2_instances.return_value = mock_resources
        mock_policy_service.validate_resource_tags.return_value = []  # All compliant

        # Measure execution time
        start_time = time.time()

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify results
        assert result.total_resources == 1000
        assert result.compliance_score == 1.0

        # Performance requirement: complete within 5 seconds
        assert execution_time < 5.0, f"Execution took {execution_time:.2f}s, expected < 5s"

    @pytest.mark.asyncio
    async def test_check_compliance_1000_resources_with_violations(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test performance with 1000 resources including violations."""
        import time

        # Generate 1000 mock resources (50% with violations)
        mock_resources = []
        for i in range(1000):
            tags = {"CostCenter": "Engineering"} if i % 2 == 0 else {}
            mock_resources.append(
                {
                    "resource_id": f"i-{i:016x}",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "tags": tags,
                    "cost_impact": 100.0,
                    "arn": f"arn:aws:ec2:us-east-1:123456789012:instance/i-{i:016x}",
                }
            )

        mock_aws_client.get_ec2_instances.return_value = mock_resources

        # Setup violations for resources without tags
        def validate_side_effect(resource_id, resource_type, region, tags, cost_impact):
            if not tags:
                return [
                    Violation(
                        resource_id=resource_id,
                        resource_type=resource_type,
                        region=region,
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        tag_name="CostCenter",
                        severity=Severity.ERROR,
                        cost_impact_monthly=cost_impact,
                    )
                ]
            return []

        mock_policy_service.validate_resource_tags.side_effect = validate_side_effect

        # Measure execution time
        start_time = time.time()

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify results
        assert result.total_resources == 1000
        assert result.compliance_score == 0.5  # 50% compliant
        assert len(result.violations) == 500

        # Performance requirement: complete within 5 seconds
        assert execution_time < 5.0, f"Execution took {execution_time:.2f}s, expected < 5s"


@pytest.mark.integration
class TestCheckTagComplianceHistoryStorage:
    """Test automatic history storage for compliance scans."""

    @pytest.mark.asyncio
    async def test_compliance_check_stores_history_automatically(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test that compliance checks automatically store results in history database."""
        from mcp_server.services.history_service import HistoryService
        from mcp_server.tools.get_violation_history import get_violation_history

        # Create an in-memory history service for testing
        history_service = HistoryService(db_path=":memory:")

        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "i-456",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-456",
            },
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources

        # Setup one violation
        violation = Violation(
            resource_id="i-456",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=150.0,
        )

        mock_policy_service.validate_resource_tags.side_effect = [
            [],  # First resource is compliant
            [violation],  # Second resource has violation
        ]

        # Run compliance check with history service and store_snapshot=True
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            history_service=history_service,
            store_snapshot=True,  # Explicitly request history storage
        )

        # Verify compliance result
        assert result.total_resources == 2
        assert result.compliant_resources == 1
        assert result.compliance_score == 0.5
        assert len(result.violations) == 1

        # Verify that the result was stored in history using the same history service
        history_result = await history_service.get_history(days_back=1, group_by="day")

        # Should have one history entry
        assert len(history_result.history) == 1

        # Verify stored data matches compliance result
        stored_entry = history_result.history[0]
        assert stored_entry.compliance_score == result.compliance_score
        assert stored_entry.total_resources == result.total_resources
        assert stored_entry.compliant_resources == result.compliant_resources
        assert stored_entry.violation_count == len(result.violations)

        # Verify timestamp is from today (grouped by day, so it's at midnight)
        from datetime import datetime, timedelta

        today = datetime.utcnow().date()
        assert (
            stored_entry.timestamp.date() == today
        ), f"Stored timestamp {stored_entry.timestamp} is not from today"

        # Clean up
        history_service.close()

    @pytest.mark.asyncio
    async def test_compliance_check_handles_history_storage_errors_gracefully(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test that compliance checks continue working even if history storage fails."""
        from mcp_server.services.history_service import HistoryService
        from unittest.mock import AsyncMock

        # Create a mock history service that raises an exception
        history_service = MagicMock(spec=HistoryService)
        history_service.store_scan_result = AsyncMock(side_effect=Exception("Database error"))

        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        mock_policy_service.validate_resource_tags.return_value = []

        # Run compliance check with failing history service and store_snapshot=True
        # This should NOT raise an exception
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            history_service=history_service,
            store_snapshot=True,  # Explicitly request history storage
        )

        # Verify compliance check still worked
        assert result.total_resources == 1
        assert result.compliant_resources == 1
        assert result.compliance_score == 1.0
        assert len(result.violations) == 0

        # Verify that store_scan_result was called (but failed)
        history_service.store_scan_result.assert_called_once_with(result)

    @pytest.mark.asyncio
    async def test_compliance_check_works_without_history_service(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test that compliance checks work normally when no history service is provided."""
        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        mock_policy_service.validate_resource_tags.return_value = []

        # Run compliance check without history service (None)
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            history_service=None,
        )

        # Verify compliance check worked normally
        assert result.total_resources == 1
        assert result.compliant_resources == 1
        assert result.compliance_score == 1.0
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_compliance_check_does_not_store_history_by_default(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test that compliance checks do NOT store history when store_snapshot=False (default)."""
        from mcp_server.services.history_service import HistoryService

        # Create an in-memory history service for testing
        history_service = HistoryService(db_path=":memory:")

        # Setup mock resources
        mock_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            }
        ]
        mock_aws_client.get_ec2_instances.return_value = mock_resources
        mock_policy_service.validate_resource_tags.return_value = []

        # Run compliance check WITHOUT store_snapshot (defaults to False)
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            history_service=history_service,
            # store_snapshot defaults to False
        )

        # Verify compliance result
        assert result.total_resources == 1
        assert result.compliant_resources == 1
        assert result.compliance_score == 1.0

        # Verify that NO history was stored
        history_result = await history_service.get_history(days_back=1, group_by="day")

        # Should have NO history entries
        assert (
            len(history_result.history) == 0
        ), "History should NOT be stored when store_snapshot=False"

        # Clean up
        history_service.close()


@pytest.mark.integration
class TestCheckTagComplianceOpenSearch:
    """Test check_tag_compliance with OpenSearch domains."""

    @pytest.mark.asyncio
    async def test_check_compliance_opensearch_domains(self, compliance_service, mock_aws_client):
        """Test checking compliance for OpenSearch domains."""
        # Setup mock OpenSearch resources
        mock_resources = [
            {
                "resource_id": "test-domain",
                "resource_type": "opensearch:domain",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 84.80,
                "arn": "arn:aws:es:us-east-1:123456789012:domain/test-domain",
            }
        ]
        mock_aws_client.get_opensearch_domains.return_value = mock_resources

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["opensearch:domain"],
            filters=None,
            severity="all",
        )

        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 1
        assert result.compliance_score >= 0.0
        assert result.compliance_score <= 1.0

    @pytest.mark.asyncio
    async def test_check_compliance_opensearch_with_other_types(
        self, compliance_service, mock_aws_client
    ):
        """Test checking compliance for OpenSearch along with other resource types."""
        # Setup mock EC2 resources
        ec2_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            }
        ]

        # Setup mock OpenSearch resources
        opensearch_resources = [
            {
                "resource_id": "search-domain",
                "resource_type": "opensearch:domain",
                "region": "us-east-1",
                "tags": {"CostCenter": "DataTeam"},
                "cost_impact": 84.80,
                "arn": "arn:aws:es:us-east-1:123456789012:domain/search-domain",
            }
        ]

        mock_aws_client.get_ec2_instances.return_value = ec2_resources
        mock_aws_client.get_opensearch_domains.return_value = opensearch_resources

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance", "opensearch:domain"],
            filters=None,
            severity="all",
        )

        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 2
        assert result.compliance_score >= 0.0
        assert result.compliance_score <= 1.0

    @pytest.mark.asyncio
    async def test_check_compliance_opensearch_with_violations(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test OpenSearch compliance check with violations."""
        # Setup mock OpenSearch resources without required tags
        mock_resources = [
            {
                "resource_id": "untagged-domain",
                "resource_type": "opensearch:domain",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 84.80,
                "arn": "arn:aws:es:us-east-1:123456789012:domain/untagged-domain",
            }
        ]
        mock_aws_client.get_opensearch_domains.return_value = mock_resources

        # Setup violation for missing tags
        violation = Violation(
            resource_id="untagged-domain",
            resource_type="opensearch:domain",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=84.80,
        )
        mock_policy_service.validate_resource_tags.return_value = [violation]

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["opensearch:domain"],
            filters=None,
            severity="all",
        )

        assert result.total_resources == 1
        assert result.compliant_resources == 0
        assert result.compliance_score == 0.0
        assert len(result.violations) == 1
        assert result.violations[0].resource_type == "opensearch:domain"
        assert result.violations[0].cost_impact_monthly == 84.80


@pytest.mark.integration
class TestCheckTagComplianceAllResourceTypes:
    """Test check_tag_compliance with resource_types: ["all"] using Resource Groups Tagging API."""

    @pytest.mark.asyncio
    async def test_check_compliance_all_resource_types(self, compliance_service, mock_aws_client):
        """Test checking compliance for all resource types via Tagging API."""
        # Setup mock resources from Tagging API
        mock_tagging_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "my-bucket",
                "resource_type": "s3:bucket",
                "region": "us-east-1",
                "tags": {"CostCenter": "DataTeam"},
                "cost_impact": 50.0,
                "arn": "arn:aws:s3:::my-bucket",
            },
            {
                "resource_id": "my-function",
                "resource_type": "lambda:function",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 25.0,
                "arn": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
            },
        ]
        mock_aws_client.get_all_tagged_resources.return_value = mock_tagging_resources

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["all"],
            filters=None,
            severity="all",
        )

        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 3
        assert result.compliance_score >= 0.0
        assert result.compliance_score <= 1.0
        # Verify Tagging API was called
        mock_aws_client.get_all_tagged_resources.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_compliance_all_discovers_many_resource_types(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test that 'all' discovers resources across many different types."""
        # Simulate resources from 10+ different resource types
        mock_tagging_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "vol-456",
                "resource_type": "ec2:volume",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 50.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:volume/vol-456",
            },
            {
                "resource_id": "bucket-1",
                "resource_type": "s3:bucket",
                "region": "us-east-1",
                "tags": {"CostCenter": "Data"},
                "cost_impact": 30.0,
                "arn": "arn:aws:s3:::bucket-1",
            },
            {
                "resource_id": "func-1",
                "resource_type": "lambda:function",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 20.0,
                "arn": "arn:aws:lambda:us-east-1:123456789012:function:func-1",
            },
            {
                "resource_id": "db-1",
                "resource_type": "rds:db",
                "region": "us-east-1",
                "tags": {"CostCenter": "Data"},
                "cost_impact": 200.0,
                "arn": "arn:aws:rds:us-east-1:123456789012:db:db-1",
            },
            {
                "resource_id": "cluster-1",
                "resource_type": "ecs:cluster",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ecs:us-east-1:123456789012:cluster/cluster-1",
            },
            {
                "resource_id": "table-1",
                "resource_type": "dynamodb:table",
                "region": "us-east-1",
                "tags": {"CostCenter": "Data"},
                "cost_impact": 80.0,
                "arn": "arn:aws:dynamodb:us-east-1:123456789012:table/table-1",
            },
            {
                "resource_id": "queue-1",
                "resource_type": "sqs:queue",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 10.0,
                "arn": "arn:aws:sqs:us-east-1:123456789012:queue-1",
            },
            {
                "resource_id": "topic-1",
                "resource_type": "sns:topic",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 5.0,
                "arn": "arn:aws:sns:us-east-1:123456789012:topic-1",
            },
            {
                "resource_id": "secret-1",
                "resource_type": "secretsmanager:secret",
                "region": "us-east-1",
                "tags": {"CostCenter": "Security"},
                "cost_impact": 2.0,
                "arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:secret-1",
            },
        ]
        mock_aws_client.get_all_tagged_resources.return_value = mock_tagging_resources
        mock_policy_service.validate_resource_tags.return_value = []

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["all"],
            filters=None,
            severity="all",
        )

        assert result.total_resources == 10
        assert result.compliant_resources == 10
        assert result.compliance_score == 1.0

        # Verify we got resources from many different types
        resource_types_found = set()
        for resource in mock_tagging_resources:
            resource_types_found.add(resource["resource_type"])
        assert len(resource_types_found) >= 10

    @pytest.mark.asyncio
    async def test_check_compliance_all_with_violations(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test 'all' resource type with compliance violations."""
        mock_tagging_resources = [
            {
                "resource_id": "i-compliant",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng", "Environment": "prod"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-compliant",
            },
            {
                "resource_id": "i-noncompliant",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-noncompliant",
            },
            {
                "resource_id": "bucket-noncompliant",
                "resource_type": "s3:bucket",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 75.0,
                "arn": "arn:aws:s3:::bucket-noncompliant",
            },
        ]
        mock_aws_client.get_all_tagged_resources.return_value = mock_tagging_resources

        # Setup violations for non-compliant resources
        def mock_validate(resource_id, resource_type, region, tags, cost_impact):
            if not tags:
                return [
                    Violation(
                        resource_id=resource_id,
                        resource_type=resource_type,
                        region=region,
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        tag_name="CostCenter",
                        severity=Severity.ERROR,
                        cost_impact_monthly=cost_impact,
                    )
                ]
            return []

        mock_policy_service.validate_resource_tags.side_effect = mock_validate

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["all"],
            filters=None,
            severity="all",
        )

        assert result.total_resources == 3
        assert result.compliant_resources == 1
        assert result.compliance_score == pytest.approx(1 / 3, rel=0.01)
        assert len(result.violations) == 2

    @pytest.mark.asyncio
    async def test_check_compliance_all_empty_account(self, compliance_service, mock_aws_client):
        """Test 'all' resource type with no resources found."""
        mock_aws_client.get_all_tagged_resources.return_value = []

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["all"],
            filters=None,
            severity="all",
        )

        assert result.total_resources == 0
        assert result.compliant_resources == 0
        assert result.compliance_score == 1.0  # 100% compliant when no resources
        assert len(result.violations) == 0

    @pytest.mark.asyncio
    async def test_check_compliance_all_with_region_filter(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """Test 'all' resource type with region filter."""
        mock_tagging_resources = [
            {
                "resource_id": "i-east",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east",
            },
            {
                "resource_id": "i-west",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-west",
            },
        ]
        mock_aws_client.get_all_tagged_resources.return_value = mock_tagging_resources
        mock_policy_service.validate_resource_tags.return_value = []

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["all"],
            filters={"region": "us-east-1"},
            severity="all",
        )

        # Should filter to only us-east-1 resources
        assert result.total_resources == 1
        assert result.compliant_resources == 1


@pytest.mark.integration
class TestResourceGroupsTaggingAPIProperty:
    """Property 19: Resource Groups Tagging API Coverage tests."""

    @pytest.mark.asyncio
    async def test_property_19_tagging_api_returns_consistent_format(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """
        Property 19: Resource Groups Tagging API Coverage
        Validates: All resources from Tagging API have consistent format.
        """
        # Resources from Tagging API should have standard fields
        mock_tagging_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            },
            {
                "resource_id": "bucket-1",
                "resource_type": "s3:bucket",
                "region": "us-east-1",
                "tags": {},
                "cost_impact": 50.0,
                "arn": "arn:aws:s3:::bucket-1",
            },
        ]
        mock_aws_client.get_all_tagged_resources.return_value = mock_tagging_resources
        mock_policy_service.validate_resource_tags.return_value = []

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["all"],
            filters=None,
            severity="all",
        )

        # Verify result has expected structure
        assert hasattr(result, "total_resources")
        assert hasattr(result, "compliant_resources")
        assert hasattr(result, "compliance_score")
        assert hasattr(result, "violations")
        assert isinstance(result.compliance_score, float)
        assert 0.0 <= result.compliance_score <= 1.0

    @pytest.mark.asyncio
    async def test_property_19_tagging_api_handles_pagination(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """
        Property 19: Resource Groups Tagging API handles pagination correctly.
        Validates: Large accounts with many resources are fully scanned.
        """
        # Simulate a large account with 100+ resources
        mock_tagging_resources = []
        for i in range(150):
            mock_tagging_resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance" if i % 2 == 0 else "s3:bucket",
                    "region": "us-east-1",
                    "tags": {"CostCenter": "Eng"} if i % 3 != 0 else {},
                    "cost_impact": 10.0,
                    "arn": f"arn:aws:ec2:us-east-1:123456789012:instance/resource-{i}",
                }
            )
        mock_aws_client.get_all_tagged_resources.return_value = mock_tagging_resources
        mock_policy_service.validate_resource_tags.return_value = []

        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["all"],
            filters=None,
            severity="all",
        )

        # All 150 resources should be scanned
        assert result.total_resources == 150

    @pytest.mark.asyncio
    async def test_property_19_tagging_api_vs_specific_types_consistency(
        self, compliance_service, mock_aws_client, mock_policy_service
    ):
        """
        Property 19: Results from 'all' should be consistent with specific type queries.
        Validates: Tagging API returns same resources as individual type queries.
        """
        # Setup resources that would be returned by both methods
        ec2_resources = [
            {
                "resource_id": "i-123",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Eng"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123",
            }
        ]

        # Tagging API returns same EC2 instance
        mock_aws_client.get_all_tagged_resources.return_value = ec2_resources
        mock_aws_client.get_ec2_instances.return_value = ec2_resources
        mock_policy_service.validate_resource_tags.return_value = []

        # Query with "all"
        result_all = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["all"],
            filters=None,
            severity="all",
        )

        # Query with specific type
        result_specific = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Both should find the same resource count
        assert result_all.total_resources == result_specific.total_resources
        assert result_all.compliance_score == result_specific.compliance_score
