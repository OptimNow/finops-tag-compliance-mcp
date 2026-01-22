"""
Property-based tests for ComplianceService.

Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
Validates: Requirements 1.1

Property 1 states:
*For any* set of resources scanned, the compliance score returned SHALL be
between 0.0 and 1.0 inclusive, and SHALL equal the ratio of compliant
resources to total resources. When total resources is zero, the score
SHALL be 1.0 (fully compliant by default).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mcp_server.clients.aws_client import AWSClient
from mcp_server.clients.cache import RedisCache
from mcp_server.models.enums import Severity, ViolationType
from mcp_server.models.violations import Violation
from mcp_server.services.compliance_service import ComplianceService
from mcp_server.services.policy_service import PolicyService

# =============================================================================
# Helper functions to create mocks
# =============================================================================


def create_mock_cache():
    """Create a mock Redis cache."""
    cache = MagicMock(spec=RedisCache)
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    cache.clear = AsyncMock(return_value=True)
    return cache


def create_mock_aws_client():
    """Create a mock AWS client."""
    return MagicMock(spec=AWSClient)


def create_mock_policy_service():
    """Create a mock policy service."""
    return MagicMock(spec=PolicyService)


def create_compliance_service():
    """Create a ComplianceService instance with mocked dependencies."""
    return ComplianceService(
        cache=create_mock_cache(),
        aws_client=create_mock_aws_client(),
        policy_service=create_mock_policy_service(),
        cache_ttl=3600,
    )


# =============================================================================
# Property 1: Compliance Score Bounds
# =============================================================================


class TestComplianceScoreBounds:
    """
    Property 1: Compliance Score Bounds

    For any set of resources scanned, the compliance score returned SHALL be
    between 0.0 and 1.0 inclusive, and SHALL equal the ratio of compliant
    resources to total resources. When total resources is zero, the score
    SHALL be 1.0 (fully compliant by default).

    Validates: Requirements 1.1
    """

    @given(
        total_resources=st.integers(min_value=0, max_value=10000),
        compliant_resources=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=100)
    def test_compliance_score_always_within_bounds(
        self,
        total_resources: int,
        compliant_resources: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        For any combination of total and compliant resources, the compliance
        score SHALL always be between 0.0 and 1.0 inclusive.
        """
        service = create_compliance_service()

        # Ensure compliant doesn't exceed total
        compliant = min(compliant_resources, total_resources)

        score = service._calculate_compliance_score(compliant, total_resources)

        # Score must be within bounds
        assert 0.0 <= score <= 1.0, (
            f"Score {score} out of bounds for " f"compliant={compliant}, total={total_resources}"
        )

    @given(
        total_resources=st.integers(min_value=1, max_value=10000),
        compliant_resources=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=100)
    def test_compliance_score_equals_ratio(
        self,
        total_resources: int,
        compliant_resources: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        For any non-zero total resources, the compliance score SHALL equal
        the ratio of compliant resources to total resources.
        """
        service = create_compliance_service()

        # Ensure compliant doesn't exceed total
        compliant = min(compliant_resources, total_resources)

        score = service._calculate_compliance_score(compliant, total_resources)
        expected_score = compliant / total_resources

        # Score must equal the ratio
        assert abs(score - expected_score) < 1e-10, (
            f"Score {score} != expected {expected_score} for "
            f"compliant={compliant}, total={total_resources}"
        )

    def test_compliance_score_zero_resources_returns_one(self):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        When total resources is zero, the score SHALL be 1.0 (fully compliant by default).
        """
        service = create_compliance_service()

        score = service._calculate_compliance_score(compliant_resources=0, total_resources=0)

        assert score == 1.0, f"Expected 1.0 for zero resources, got {score}"

    @given(total_resources=st.integers(min_value=1, max_value=10000))
    @settings(max_examples=100)
    def test_all_compliant_returns_one(
        self,
        total_resources: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        When all resources are compliant, the score SHALL be 1.0.
        """
        service = create_compliance_service()

        score = service._calculate_compliance_score(
            compliant_resources=total_resources, total_resources=total_resources
        )

        assert (
            score == 1.0
        ), f"Expected 1.0 when all {total_resources} resources compliant, got {score}"

    @given(total_resources=st.integers(min_value=1, max_value=10000))
    @settings(max_examples=100)
    def test_none_compliant_returns_zero(
        self,
        total_resources: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        When no resources are compliant, the score SHALL be 0.0.
        """
        service = create_compliance_service()

        score = service._calculate_compliance_score(
            compliant_resources=0, total_resources=total_resources
        )

        assert (
            score == 0.0
        ), f"Expected 0.0 when 0 of {total_resources} resources compliant, got {score}"

    @given(
        num_resources=st.integers(min_value=1, max_value=100),
        num_compliant=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_scan_and_validate_score_matches_ratio(
        self,
        num_resources: int,
        num_compliant: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        For any scan result, the compliance score in ComplianceResult SHALL
        equal the ratio of compliant_resources to total_resources.
        """
        # Ensure num_compliant doesn't exceed num_resources
        num_compliant = min(num_compliant, num_resources)

        # Generate mock resources
        resources = []
        for i in range(num_resources):
            resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "tags": {"CostCenter": "Engineering"} if i < num_compliant else {},
                    "cost_impact": 100.0,
                }
            )

        # Create fresh mocks for each test run
        mock_cache = create_mock_cache()
        mock_aws_client = create_mock_aws_client()
        mock_policy_service = create_mock_policy_service()

        # Configure mock AWS client to return our resources
        mock_aws_client.get_ec2_instances = AsyncMock(return_value=resources)

        # Configure mock policy service
        # Return no violations for compliant resources, one violation for non-compliant
        def mock_validate(resource_id, resource_type, region, tags, cost_impact=0.0):
            # Resources with tags are compliant, without tags are not
            if tags:
                return []
            else:
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

        mock_policy_service.validate_resource_tags = mock_validate

        # Create service and run scan
        service = ComplianceService(
            cache=mock_cache,
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
        )

        result = await service._scan_and_validate(
            resource_types=["ec2:instance"], filters=None, severity="all"
        )

        # Verify score bounds
        assert 0.0 <= result.compliance_score <= 1.0

        # Verify score equals ratio
        if result.total_resources > 0:
            expected_score = result.compliant_resources / result.total_resources
            assert (
                abs(result.compliance_score - expected_score) < 1e-10
            ), f"Score {result.compliance_score} != expected {expected_score}"

        # Verify counts
        assert result.total_resources == num_resources
        assert result.compliant_resources == num_compliant

    @pytest.mark.asyncio
    async def test_empty_scan_returns_score_one(self):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1

        When scanning returns zero resources, the compliance score SHALL be 1.0.
        """
        mock_cache = create_mock_cache()
        mock_aws_client = create_mock_aws_client()
        mock_policy_service = create_mock_policy_service()

        # Configure mock AWS client to return empty list
        mock_aws_client.get_ec2_instances = AsyncMock(return_value=[])

        service = ComplianceService(
            cache=mock_cache,
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
        )

        result = await service._scan_and_validate(
            resource_types=["ec2:instance"], filters=None, severity="all"
        )

        assert result.compliance_score == 1.0
        assert result.total_resources == 0
        assert result.compliant_resources == 0


# =============================================================================
# Property 3: Filter Consistency
# =============================================================================


class TestFilterConsistency:
    """
    Property 3: Filter Consistency

    For any compliance check or resource search with filters applied (region,
    account, severity, cost threshold), all returned results SHALL match the
    specified filter criteria. No results outside the filter scope SHALL be
    included.

    Validates: Requirements 1.3, 1.4, 2.3, 2.4
    """

    # -------------------------------------------------------------------------
    # Region Filtering Tests
    # -------------------------------------------------------------------------

    @given(
        num_resources=st.integers(min_value=1, max_value=50),
        target_region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]),
    )
    @settings(max_examples=100)
    def test_region_filter_returns_only_matching_resources(
        self,
        num_resources: int,
        target_region: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.3

        For any region filter applied, all returned resources SHALL be from
        the specified region. No resources from other regions SHALL be included.
        """
        service = create_compliance_service()

        # Generate resources across multiple regions
        all_regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        resources = []
        for i in range(num_resources):
            region = all_regions[i % len(all_regions)]
            resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance",
                    "region": region,
                    "tags": {},
                    "arn": f"arn:aws:ec2:{region}:123456789012:instance/i-{i:08d}",
                }
            )

        # Apply region filter
        filters = {"region": target_region}
        filtered = service._apply_resource_filters(resources, filters)

        # All returned resources must be from the target region
        for resource in filtered:
            assert resource["region"] == target_region, (
                f"Resource {resource['resource_id']} has region {resource['region']} "
                f"but filter was for {target_region}"
            )

    @given(
        num_resources=st.integers(min_value=1, max_value=50),
        target_regions=st.lists(
            st.sampled_from(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]),
            min_size=1,
            max_size=3,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_multi_region_filter_returns_only_matching_resources(
        self,
        num_resources: int,
        target_regions: list[str],
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.3, 2.4

        For any list of region filters applied, all returned resources SHALL be
        from one of the specified regions. No resources from other regions SHALL
        be included.
        """
        service = create_compliance_service()

        # Generate resources across multiple regions
        all_regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        resources = []
        for i in range(num_resources):
            region = all_regions[i % len(all_regions)]
            resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance",
                    "region": region,
                    "tags": {},
                    "arn": f"arn:aws:ec2:{region}:123456789012:instance/i-{i:08d}",
                }
            )

        # Apply multi-region filter
        filters = {"region": target_regions}
        filtered = service._apply_resource_filters(resources, filters)

        # All returned resources must be from one of the target regions
        for resource in filtered:
            assert resource["region"] in target_regions, (
                f"Resource {resource['resource_id']} has region {resource['region']} "
                f"but filter was for {target_regions}"
            )

    # -------------------------------------------------------------------------
    # Account ID Filtering Tests
    # -------------------------------------------------------------------------

    @given(
        num_resources=st.integers(min_value=1, max_value=50),
        target_account=st.sampled_from(["111111111111", "222222222222", "333333333333"]),
    )
    @settings(max_examples=100)
    def test_account_filter_returns_only_matching_resources(
        self,
        num_resources: int,
        target_account: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.3

        For any account_id filter applied, all returned resources SHALL be from
        the specified account. No resources from other accounts SHALL be included.
        """
        service = create_compliance_service()

        # Generate resources across multiple accounts
        all_accounts = ["111111111111", "222222222222", "333333333333"]
        resources = []
        for i in range(num_resources):
            account = all_accounts[i % len(all_accounts)]
            resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "tags": {},
                    "arn": f"arn:aws:ec2:us-east-1:{account}:instance/i-{i:08d}",
                }
            )

        # Apply account filter
        filters = {"account_id": target_account}
        filtered = service._apply_resource_filters(resources, filters)

        # All returned resources must be from the target account
        for resource in filtered:
            extracted_account = service._extract_account_from_arn(resource.get("arn", ""))
            assert extracted_account == target_account, (
                f"Resource {resource['resource_id']} has account {extracted_account} "
                f"but filter was for {target_account}"
            )

    @given(
        num_resources=st.integers(min_value=1, max_value=50),
        target_accounts=st.lists(
            st.sampled_from(["111111111111", "222222222222", "333333333333"]),
            min_size=1,
            max_size=2,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_multi_account_filter_returns_only_matching_resources(
        self,
        num_resources: int,
        target_accounts: list[str],
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.3

        For any list of account_id filters applied, all returned resources SHALL
        be from one of the specified accounts. No resources from other accounts
        SHALL be included.
        """
        service = create_compliance_service()

        # Generate resources across multiple accounts
        all_accounts = ["111111111111", "222222222222", "333333333333"]
        resources = []
        for i in range(num_resources):
            account = all_accounts[i % len(all_accounts)]
            resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "tags": {},
                    "arn": f"arn:aws:ec2:us-east-1:{account}:instance/i-{i:08d}",
                }
            )

        # Apply multi-account filter
        filters = {"account_id": target_accounts}
        filtered = service._apply_resource_filters(resources, filters)

        # All returned resources must be from one of the target accounts
        for resource in filtered:
            extracted_account = service._extract_account_from_arn(resource.get("arn", ""))
            assert extracted_account in target_accounts, (
                f"Resource {resource['resource_id']} has account {extracted_account} "
                f"but filter was for {target_accounts}"
            )

    # -------------------------------------------------------------------------
    # Severity Filtering Tests
    # -------------------------------------------------------------------------

    @given(
        num_violations=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_severity_filter_errors_only_returns_only_errors(
        self,
        num_violations: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.4

        For severity filter "errors_only", all returned violations SHALL have
        severity ERROR. No WARNING violations SHALL be included.
        """
        service = create_compliance_service()

        # Generate violations with mixed severities
        violations = []
        for i in range(num_violations):
            severity = Severity.ERROR if i % 2 == 0 else Severity.WARNING
            violations.append(
                Violation(
                    resource_id=f"resource-{i}",
                    resource_type="ec2:instance",
                    region="us-east-1",
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=severity,
                    cost_impact_monthly=100.0,
                )
            )

        # Apply errors_only filter
        filtered = service._filter_by_severity(violations, "errors_only")

        # All returned violations must be errors
        for violation in filtered:
            assert violation.severity == Severity.ERROR, (
                f"Violation {violation.resource_id} has severity {violation.severity} "
                f"but filter was for errors_only"
            )

    @given(
        num_violations=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_severity_filter_warnings_only_returns_only_warnings(
        self,
        num_violations: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.4

        For severity filter "warnings_only", all returned violations SHALL have
        severity WARNING. No ERROR violations SHALL be included.
        """
        service = create_compliance_service()

        # Generate violations with mixed severities
        violations = []
        for i in range(num_violations):
            severity = Severity.ERROR if i % 2 == 0 else Severity.WARNING
            violations.append(
                Violation(
                    resource_id=f"resource-{i}",
                    resource_type="ec2:instance",
                    region="us-east-1",
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=severity,
                    cost_impact_monthly=100.0,
                )
            )

        # Apply warnings_only filter
        filtered = service._filter_by_severity(violations, "warnings_only")

        # All returned violations must be warnings
        for violation in filtered:
            assert violation.severity == Severity.WARNING, (
                f"Violation {violation.resource_id} has severity {violation.severity} "
                f"but filter was for warnings_only"
            )

    @given(
        num_violations=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_severity_filter_all_returns_all_violations(
        self,
        num_violations: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.4

        For severity filter "all", all violations SHALL be returned regardless
        of their severity level.
        """
        service = create_compliance_service()

        # Generate violations with mixed severities
        violations = []
        for i in range(num_violations):
            severity = Severity.ERROR if i % 2 == 0 else Severity.WARNING
            violations.append(
                Violation(
                    resource_id=f"resource-{i}",
                    resource_type="ec2:instance",
                    region="us-east-1",
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=severity,
                    cost_impact_monthly=100.0,
                )
            )

        # Apply "all" filter
        filtered = service._filter_by_severity(violations, "all")

        # All violations should be returned
        assert len(filtered) == len(
            violations
        ), f"Expected {len(violations)} violations but got {len(filtered)}"

    # -------------------------------------------------------------------------
    # Combined Filters Tests
    # -------------------------------------------------------------------------

    @given(
        num_resources=st.integers(min_value=1, max_value=50),
        target_region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]),
        target_account=st.sampled_from(["111111111111", "222222222222", "333333333333"]),
    )
    @settings(max_examples=100)
    def test_combined_region_and_account_filter(
        self,
        num_resources: int,
        target_region: str,
        target_account: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.3

        For combined region and account_id filters, all returned resources SHALL
        match BOTH filter criteria. No resources outside either filter scope
        SHALL be included.
        """
        service = create_compliance_service()

        # Generate resources across multiple regions and accounts
        all_regions = ["us-east-1", "us-west-2", "eu-west-1"]
        all_accounts = ["111111111111", "222222222222", "333333333333"]
        resources = []
        for i in range(num_resources):
            region = all_regions[i % len(all_regions)]
            account = all_accounts[i % len(all_accounts)]
            resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance",
                    "region": region,
                    "tags": {},
                    "arn": f"arn:aws:ec2:{region}:{account}:instance/i-{i:08d}",
                }
            )

        # Apply combined filters
        filters = {"region": target_region, "account_id": target_account}
        filtered = service._apply_resource_filters(resources, filters)

        # All returned resources must match both filters
        for resource in filtered:
            assert resource["region"] == target_region, (
                f"Resource {resource['resource_id']} has region {resource['region']} "
                f"but filter was for {target_region}"
            )
            extracted_account = service._extract_account_from_arn(resource.get("arn", ""))
            assert extracted_account == target_account, (
                f"Resource {resource['resource_id']} has account {extracted_account} "
                f"but filter was for {target_account}"
            )

    # -------------------------------------------------------------------------
    # No Filter Tests (Baseline)
    # -------------------------------------------------------------------------

    @given(
        num_resources=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_no_filter_returns_all_resources(
        self,
        num_resources: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.3

        When no filters are applied, all resources SHALL be returned.
        """
        service = create_compliance_service()

        # Generate resources
        resources = []
        for i in range(num_resources):
            resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "tags": {},
                }
            )

        # Apply no filters
        filtered = service._apply_resource_filters(resources, None)

        # All resources should be returned
        assert len(filtered) == len(
            resources
        ), f"Expected {len(resources)} resources but got {len(filtered)}"

    @given(
        num_resources=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=100)
    def test_empty_filter_returns_all_resources(
        self,
        num_resources: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.3

        When an empty filter dict is applied, all resources SHALL be returned.
        """
        service = create_compliance_service()

        # Generate resources
        resources = []
        for i in range(num_resources):
            resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "tags": {},
                }
            )

        # Apply empty filters
        filtered = service._apply_resource_filters(resources, {})

        # All resources should be returned
        assert len(filtered) == len(
            resources
        ), f"Expected {len(resources)} resources but got {len(filtered)}"

    # -------------------------------------------------------------------------
    # Filter Completeness Tests (No False Negatives)
    # -------------------------------------------------------------------------

    @given(
        num_resources=st.integers(min_value=1, max_value=50),
        target_region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]),
    )
    @settings(max_examples=100)
    def test_region_filter_includes_all_matching_resources(
        self,
        num_resources: int,
        target_region: str,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.3

        For any region filter, all resources from the target region SHALL be
        included in the results. No matching resources SHALL be excluded.
        """
        service = create_compliance_service()

        # Generate resources across multiple regions
        all_regions = ["us-east-1", "us-west-2", "eu-west-1"]
        resources = []
        for i in range(num_resources):
            region = all_regions[i % len(all_regions)]
            resources.append(
                {
                    "resource_id": f"resource-{i}",
                    "resource_type": "ec2:instance",
                    "region": region,
                    "tags": {},
                }
            )

        # Count expected matches
        expected_count = sum(1 for r in resources if r["region"] == target_region)

        # Apply region filter
        filters = {"region": target_region}
        filtered = service._apply_resource_filters(resources, filters)

        # All matching resources should be included
        assert (
            len(filtered) == expected_count
        ), f"Expected {expected_count} resources in {target_region} but got {len(filtered)}"

    @given(
        num_violations=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=100)
    def test_severity_filter_includes_all_matching_violations(
        self,
        num_violations: int,
    ):
        """
        Feature: phase-1-aws-mvp, Property 3: Filter Consistency
        Validates: Requirements 1.4

        For any severity filter, all violations matching the severity SHALL be
        included in the results. No matching violations SHALL be excluded.
        """
        service = create_compliance_service()

        # Generate violations with mixed severities
        violations = []
        for i in range(num_violations):
            severity = Severity.ERROR if i % 2 == 0 else Severity.WARNING
            violations.append(
                Violation(
                    resource_id=f"resource-{i}",
                    resource_type="ec2:instance",
                    region="us-east-1",
                    violation_type=ViolationType.MISSING_REQUIRED_TAG,
                    tag_name="CostCenter",
                    severity=severity,
                    cost_impact_monthly=100.0,
                )
            )

        # Count expected errors
        expected_errors = sum(1 for v in violations if v.severity == Severity.ERROR)

        # Apply errors_only filter
        filtered = service._filter_by_severity(violations, "errors_only")

        # All error violations should be included
        assert (
            len(filtered) == expected_errors
        ), f"Expected {expected_errors} error violations but got {len(filtered)}"
