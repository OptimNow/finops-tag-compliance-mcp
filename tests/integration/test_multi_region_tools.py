# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Integration tests for multi-region tool flows.

These tests verify end-to-end flows for multi-region scanning with mocked AWS APIs.
Tests cover:
- check_tag_compliance with multi-region scanning
- find_untagged_resources with multi-region scanning
- Partial failure handling when some regions fail

Requirements: 3.1, 3.5
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_server.clients.aws_client import AWSClient
from mcp_server.clients.cache import RedisCache
from mcp_server.clients.regional_client_factory import RegionalClientFactory
from mcp_server.models.compliance import ComplianceResult
from mcp_server.models.enums import Severity, ViolationType
from mcp_server.models.multi_region import (
    MultiRegionComplianceResult,
    RegionalScanResult,
    RegionalSummary,
    RegionScanMetadata,
)
from mcp_server.models.violations import Violation
from mcp_server.services.compliance_service import ComplianceService
from mcp_server.services.multi_region_scanner import MultiRegionScanner
from mcp_server.services.policy_service import PolicyService
from mcp_server.services.region_discovery_service import RegionDiscoveryService
from mcp_server.tools.check_tag_compliance import check_tag_compliance
from mcp_server.tools.find_untagged_resources import find_untagged_resources


# =============================================================================
# Test Fixtures
# =============================================================================


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
def mock_policy_service():
    """Create a mock policy service."""
    from datetime import timezone
    
    from mcp_server.models.policy import OptionalTag, RequiredTag, TagNamingRules, TagPolicy

    service = MagicMock(spec=PolicyService)
    service.validate_resource_tags = MagicMock(return_value=[])

    # Mock get_policy to return a valid policy object
    mock_policy = TagPolicy(
        version="1.0",
        last_updated=datetime.now(timezone.utc),
        required_tags=[
            RequiredTag(
                name="CostCenter",
                description="Cost center for billing",
                allowed_values=["Engineering", "Marketing", "Sales"],
                applies_to=["ec2:instance", "rds:db"],
            ),
            RequiredTag(
                name="Environment",
                description="Deployment environment",
                allowed_values=["production", "staging", "development"],
                applies_to=["ec2:instance", "rds:db", "lambda:function"],
            ),
        ],
        optional_tags=[
            OptionalTag(name="Project", description="Project name"),
        ],
        tag_naming_rules=TagNamingRules(
            case_sensitivity=False,
            allow_special_characters=False,
            max_key_length=128,
            max_value_length=256,
        ),
    )
    service.get_policy = MagicMock(return_value=mock_policy)

    return service


def create_mock_aws_client(region: str) -> MagicMock:
    """Create a mock AWS client for a specific region."""
    client = MagicMock(spec=AWSClient)
    client.region = region
    client.get_ec2_instances = AsyncMock(return_value=[])
    client.get_rds_instances = AsyncMock(return_value=[])
    client.get_s3_buckets = AsyncMock(return_value=[])
    client.get_lambda_functions = AsyncMock(return_value=[])
    client.get_ecs_services = AsyncMock(return_value=[])
    client.get_opensearch_domains = AsyncMock(return_value=[])
    client.get_all_tagged_resources = AsyncMock(return_value=[])
    client.get_tags_for_arns = AsyncMock(return_value={})
    client.get_cost_data_by_resource = AsyncMock(return_value=({}, {}, {}, "estimated"))
    client.get_service_name_for_resource_type = MagicMock(return_value="Amazon EC2")
    return client


@pytest.fixture
def mock_region_discovery():
    """Create a mock region discovery service."""
    service = MagicMock(spec=RegionDiscoveryService)
    service.get_enabled_regions = AsyncMock(
        return_value=["us-east-1", "us-west-2", "eu-west-1"]
    )
    return service


@pytest.fixture
def mock_client_factory():
    """Create a mock regional client factory that returns region-specific clients."""
    factory = MagicMock(spec=RegionalClientFactory)
    
    # Store clients by region for consistent returns
    clients: dict[str, MagicMock] = {}
    
    def get_client(region: str) -> MagicMock:
        if region not in clients:
            clients[region] = create_mock_aws_client(region)
        return clients[region]
    
    factory.get_client = MagicMock(side_effect=get_client)
    factory._clients = clients  # Expose for test access
    return factory


@pytest.fixture
def compliance_service_factory(mock_cache, mock_policy_service):
    """Create a factory function for compliance services."""
    def factory(aws_client: AWSClient) -> ComplianceService:
        return ComplianceService(
            cache=mock_cache,
            aws_client=aws_client,
            policy_service=mock_policy_service,
            cache_ttl=3600,
        )
    return factory


@pytest.fixture
def multi_region_scanner(
    mock_region_discovery,
    mock_client_factory,
    compliance_service_factory,
):
    """Create a MultiRegionScanner with mocked dependencies."""
    return MultiRegionScanner(
        region_discovery=mock_region_discovery,
        client_factory=mock_client_factory,
        compliance_service_factory=compliance_service_factory,
        max_concurrent_regions=5,
        region_timeout_seconds=60,
        multi_region_enabled=True,
        default_region="us-east-1",
    )


@pytest.fixture
def compliance_service(mock_cache, mock_policy_service):
    """Create a ComplianceService with a default mock AWS client."""
    mock_aws_client = create_mock_aws_client("us-east-1")
    return ComplianceService(
        cache=mock_cache,
        aws_client=mock_aws_client,
        policy_service=mock_policy_service,
        cache_ttl=3600,
    )


# =============================================================================
# Test check_tag_compliance with Multi-Region
# =============================================================================


@pytest.mark.integration
class TestCheckTagComplianceMultiRegion:
    """Integration tests for check_tag_compliance with multi-region scanning.
    
    Requirements: 3.1 - Scan resources across all enabled regions
    """

    @pytest.mark.asyncio
    async def test_check_compliance_scans_all_regions(
        self,
        compliance_service,
        multi_region_scanner,
        mock_client_factory,
    ):
        """Test that check_tag_compliance scans resources across all enabled regions.
        
        Validates: Requirements 3.1
        """
        # Setup mock resources in different regions
        us_east_1_resources = [
            {
                "resource_id": "i-east-1",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-1",
            }
        ]
        us_west_2_resources = [
            {
                "resource_id": "i-west-2",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {"CostCenter": "Marketing", "Environment": "staging"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-west-2",
            }
        ]
        eu_west_1_resources = [
            {
                "resource_id": "i-eu-1",
                "resource_type": "ec2:instance",
                "region": "eu-west-1",
                "tags": {"CostCenter": "Sales", "Environment": "development"},
                "cost_impact": 200.0,
                "arn": "arn:aws:ec2:eu-west-1:123456789012:instance/i-eu-1",
            }
        ]

        # Configure mock clients to return region-specific resources
        def setup_client_resources(region: str):
            client = mock_client_factory.get_client(region)
            if region == "us-east-1":
                client.get_ec2_instances.return_value = us_east_1_resources
            elif region == "us-west-2":
                client.get_ec2_instances.return_value = us_west_2_resources
            elif region == "eu-west-1":
                client.get_ec2_instances.return_value = eu_west_1_resources

        # Setup all regions
        for region in ["us-east-1", "us-west-2", "eu-west-1"]:
            setup_client_resources(region)

        # Call check_tag_compliance with multi-region scanner
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            multi_region_scanner=multi_region_scanner,
        )

        # Verify result is MultiRegionComplianceResult
        assert isinstance(result, MultiRegionComplianceResult)
        
        # Verify all regions were scanned
        assert len(result.region_metadata.successful_regions) == 3
        assert "us-east-1" in result.region_metadata.successful_regions
        assert "us-west-2" in result.region_metadata.successful_regions
        assert "eu-west-1" in result.region_metadata.successful_regions
        
        # Verify total resources from all regions
        assert result.total_resources == 3


    @pytest.mark.asyncio
    async def test_check_compliance_regional_breakdown(
        self,
        compliance_service,
        multi_region_scanner,
        mock_client_factory,
        mock_policy_service,
    ):
        """Test that regional_breakdown contains per-region summaries.
        
        Validates: Requirements 3.1, 4.5
        """
        # Setup resources with violations in different regions
        us_east_1_resources = [
            {
                "resource_id": "i-east-1",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},  # Missing Environment
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-1",
            },
            {
                "resource_id": "i-east-2",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-2",
            },
        ]
        us_west_2_resources = [
            {
                "resource_id": "i-west-1",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {},  # Missing all tags
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-west-1",
            }
        ]

        # Configure mock clients
        mock_client_factory.get_client("us-east-1").get_ec2_instances.return_value = (
            us_east_1_resources
        )
        mock_client_factory.get_client("us-west-2").get_ec2_instances.return_value = (
            us_west_2_resources
        )
        mock_client_factory.get_client("eu-west-1").get_ec2_instances.return_value = []

        # Setup violations
        violation_east = Violation(
            resource_id="i-east-1",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="Environment",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0,
        )
        violation_west = Violation(
            resource_id="i-west-1",
            resource_type="ec2:instance",
            region="us-west-2",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=150.0,
        )

        # Configure policy service to return violations based on resource
        def validate_side_effect(resource_id, resource_type, region, tags, cost_impact):
            if resource_id == "i-east-1":
                return [violation_east]
            elif resource_id == "i-west-1":
                return [violation_west]
            return []

        mock_policy_service.validate_resource_tags.side_effect = validate_side_effect

        # Call check_tag_compliance
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            multi_region_scanner=multi_region_scanner,
        )

        # Verify regional breakdown exists
        assert isinstance(result, MultiRegionComplianceResult)
        assert len(result.regional_breakdown) > 0
        
        # Verify per-region summaries
        for region, summary in result.regional_breakdown.items():
            assert isinstance(summary, RegionalSummary)
            assert summary.region == region
            assert summary.compliance_score >= 0.0
            assert summary.compliance_score <= 1.0


    @pytest.mark.asyncio
    async def test_check_compliance_with_region_filter(
        self,
        compliance_service,
        multi_region_scanner,
        mock_client_factory,
    ):
        """Test check_tag_compliance with region filter scans only specified regions.
        
        Validates: Requirements 6.1, 6.2
        """
        # Setup resources in all regions
        for region in ["us-east-1", "us-west-2", "eu-west-1"]:
            client = mock_client_factory.get_client(region)
            client.get_ec2_instances.return_value = [
                {
                    "resource_id": f"i-{region}",
                    "resource_type": "ec2:instance",
                    "region": region,
                    "tags": {"CostCenter": "Engineering", "Environment": "production"},
                    "cost_impact": 100.0,
                    "arn": f"arn:aws:ec2:{region}:123456789012:instance/i-{region}",
                }
            ]

        # Call with region filter for only us-east-1 and us-west-2
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters={"regions": ["us-east-1", "us-west-2"]},
            severity="all",
            multi_region_scanner=multi_region_scanner,
        )

        # Verify only filtered regions were scanned
        assert isinstance(result, MultiRegionComplianceResult)
        assert len(result.region_metadata.successful_regions) == 2
        assert "us-east-1" in result.region_metadata.successful_regions
        assert "us-west-2" in result.region_metadata.successful_regions
        assert "eu-west-1" not in result.region_metadata.successful_regions

    @pytest.mark.asyncio
    async def test_check_compliance_disabled_multi_region(
        self,
        compliance_service,
        mock_region_discovery,
        mock_client_factory,
        compliance_service_factory,
        mock_cache,
        mock_policy_service,
    ):
        """Test that when multi-region is disabled, falls back to single-region mode.
        
        When multi_region_enabled=False, the check_tag_compliance tool falls back
        to using the ComplianceService directly (single-region mode) and returns
        a ComplianceResult instead of MultiRegionComplianceResult.
        
        Validates: Requirements 7.1, 7.4
        """
        # Create scanner with multi-region disabled
        disabled_scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # Disabled
            default_region="us-east-1",
        )

        # Create a compliance service with resources in default region
        mock_aws_client = create_mock_aws_client("us-east-1")
        mock_aws_client.get_ec2_instances.return_value = [
            {
                "resource_id": "i-default",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-default",
            }
        ]
        
        single_region_service = ComplianceService(
            cache=mock_cache,
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
            cache_ttl=3600,
        )

        # Call check_tag_compliance with disabled scanner
        # When multi-region is disabled, it falls back to single-region mode
        result = await check_tag_compliance(
            compliance_service=single_region_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            multi_region_scanner=disabled_scanner,
        )

        # When multi-region is disabled, the tool falls back to single-region mode
        # and returns a ComplianceResult (not MultiRegionComplianceResult)
        assert isinstance(result, ComplianceResult)
        assert result.total_resources == 1


# =============================================================================
# Test find_untagged_resources with Multi-Region
# =============================================================================


@pytest.mark.integration
class TestFindUntaggedResourcesMultiRegion:
    """Integration tests for find_untagged_resources with multi-region scanning.
    
    Requirements: 3.1 - Scan resources across all enabled regions
    """

    @pytest.mark.asyncio
    async def test_find_untagged_scans_all_regions(
        self,
        multi_region_scanner,
        mock_client_factory,
        mock_policy_service,
    ):
        """Test that find_untagged_resources scans all enabled regions.
        
        Validates: Requirements 3.1
        """
        # Setup untagged resources in different regions
        us_east_1_resources = [
            {
                "resource_id": "i-east-untagged",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},  # No tags
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-untagged",
            }
        ]
        us_west_2_resources = [
            {
                "resource_id": "i-west-untagged",
                "resource_type": "ec2:instance",
                "region": "us-west-2",
                "tags": {},  # No tags
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-west-untagged",
            }
        ]
        eu_west_1_resources = [
            {
                "resource_id": "i-eu-tagged",
                "resource_type": "ec2:instance",
                "region": "eu-west-1",
                "tags": {"CostCenter": "Sales", "Environment": "production"},
                "cost_impact": 200.0,
                "arn": "arn:aws:ec2:eu-west-1:123456789012:instance/i-eu-tagged",
            }
        ]

        # Configure mock clients
        mock_client_factory.get_client("us-east-1").get_ec2_instances.return_value = (
            us_east_1_resources
        )
        mock_client_factory.get_client("us-west-2").get_ec2_instances.return_value = (
            us_west_2_resources
        )
        mock_client_factory.get_client("eu-west-1").get_ec2_instances.return_value = (
            eu_west_1_resources
        )

        # Create a default AWS client for the tool
        default_client = create_mock_aws_client("us-east-1")

        # Call find_untagged_resources with multi-region scanner
        result = await find_untagged_resources(
            aws_client=default_client,
            policy_service=mock_policy_service,
            resource_types=["ec2:instance"],
            regions=None,  # Scan all regions
            multi_region_scanner=multi_region_scanner,
        )

        # Verify untagged resources from all regions are found
        assert result.total_untagged == 2  # Two untagged resources
        
        # Verify resources have correct region attributes
        regions_found = {r.region for r in result.resources}
        assert "us-east-1" in regions_found
        assert "us-west-2" in regions_found


    @pytest.mark.asyncio
    async def test_find_untagged_region_attribute_correct(
        self,
        multi_region_scanner,
        mock_client_factory,
        mock_policy_service,
    ):
        """Test that each resource has the correct region attribute.
        
        Validates: Requirements 4.2
        """
        # Setup resources in different regions
        regions_and_resources = {
            "us-east-1": [
                {
                    "resource_id": "i-east-1",
                    "resource_type": "ec2:instance",
                    "region": "us-east-1",
                    "tags": {},
                    "cost_impact": 100.0,
                    "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-1",
                }
            ],
            "us-west-2": [
                {
                    "resource_id": "i-west-1",
                    "resource_type": "ec2:instance",
                    "region": "us-west-2",
                    "tags": {},
                    "cost_impact": 150.0,
                    "arn": "arn:aws:ec2:us-west-2:123456789012:instance/i-west-1",
                }
            ],
            "eu-west-1": [
                {
                    "resource_id": "i-eu-1",
                    "resource_type": "ec2:instance",
                    "region": "eu-west-1",
                    "tags": {},
                    "cost_impact": 200.0,
                    "arn": "arn:aws:ec2:eu-west-1:123456789012:instance/i-eu-1",
                }
            ],
        }

        # Configure mock clients
        for region, resources in regions_and_resources.items():
            mock_client_factory.get_client(region).get_ec2_instances.return_value = resources

        # Create default client
        default_client = create_mock_aws_client("us-east-1")

        # Call find_untagged_resources
        result = await find_untagged_resources(
            aws_client=default_client,
            policy_service=mock_policy_service,
            resource_types=["ec2:instance"],
            regions=None,
            multi_region_scanner=multi_region_scanner,
        )

        # Verify each resource has correct region
        assert result.total_untagged == 3
        
        resource_regions = {r.resource_id: r.region for r in result.resources}
        assert resource_regions.get("i-east-1") == "us-east-1"
        assert resource_regions.get("i-west-1") == "us-west-2"
        assert resource_regions.get("i-eu-1") == "eu-west-1"

    @pytest.mark.asyncio
    async def test_find_untagged_with_region_filter(
        self,
        multi_region_scanner,
        mock_client_factory,
        mock_policy_service,
    ):
        """Test find_untagged_resources with region filter.
        
        Validates: Requirements 6.1
        """
        # Setup resources in all regions
        for region in ["us-east-1", "us-west-2", "eu-west-1"]:
            mock_client_factory.get_client(region).get_ec2_instances.return_value = [
                {
                    "resource_id": f"i-{region}",
                    "resource_type": "ec2:instance",
                    "region": region,
                    "tags": {},  # Untagged
                    "cost_impact": 100.0,
                    "arn": f"arn:aws:ec2:{region}:123456789012:instance/i-{region}",
                }
            ]

        # Create default client
        default_client = create_mock_aws_client("us-east-1")

        # Call with region filter
        result = await find_untagged_resources(
            aws_client=default_client,
            policy_service=mock_policy_service,
            resource_types=["ec2:instance"],
            regions=["us-east-1", "us-west-2"],  # Filter to 2 regions
            multi_region_scanner=multi_region_scanner,
        )

        # Verify only filtered regions are included
        assert result.total_untagged == 2
        regions_found = {r.region for r in result.resources}
        assert "us-east-1" in regions_found
        assert "us-west-2" in regions_found
        assert "eu-west-1" not in regions_found


# =============================================================================
# Test Partial Failure Handling
# =============================================================================


@pytest.mark.integration
class TestPartialFailureHandling:
    """Integration tests for partial failure handling in multi-region scanning.
    
    Requirements: 3.5 - Continue scanning other regions when one fails
    
    Note: The ComplianceService catches errors at the resource fetching level
    and returns empty results. To test true region-level failures, we need to
    make the compliance service itself fail for specific regions.
    """

    @pytest.mark.asyncio
    async def test_partial_failure_returns_results_from_successful_regions(
        self,
        compliance_service,
        mock_region_discovery,
        mock_client_factory,
        mock_cache,
        mock_policy_service,
    ):
        """Test that when one region fails at the compliance service level,
        other regions still return results.
        
        Validates: Requirements 3.5, 4.5
        """
        # Setup resources in successful regions
        mock_client_factory.get_client("us-east-1").get_ec2_instances.return_value = [
            {
                "resource_id": "i-east-1",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-1",
            }
        ]
        mock_client_factory.get_client("eu-west-1").get_ec2_instances.return_value = [
            {
                "resource_id": "i-eu-1",
                "resource_type": "ec2:instance",
                "region": "eu-west-1",
                "tags": {"CostCenter": "Sales", "Environment": "staging"},
                "cost_impact": 200.0,
                "arn": "arn:aws:ec2:eu-west-1:123456789012:instance/i-eu-1",
            }
        ]
        # us-west-2 returns empty (simulating no resources, not a failure)
        mock_client_factory.get_client("us-west-2").get_ec2_instances.return_value = []

        # Create a compliance service factory that fails for us-west-2
        def failing_compliance_factory(aws_client: AWSClient) -> ComplianceService:
            if aws_client.region == "us-west-2":
                # Create a mock that raises an exception
                mock_service = MagicMock(spec=ComplianceService)
                mock_service.check_compliance = AsyncMock(
                    side_effect=Exception("Simulated region failure for us-west-2")
                )
                return mock_service
            return ComplianceService(
                cache=mock_cache,
                aws_client=aws_client,
                policy_service=mock_policy_service,
                cache_ttl=3600,
            )

        # Create scanner with failing factory
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=failing_compliance_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=True,
            default_region="us-east-1",
            max_retries=0,  # No retries for faster test
        )

        # Call check_tag_compliance
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            multi_region_scanner=scanner,
        )

        # Verify partial results are returned
        assert isinstance(result, MultiRegionComplianceResult)
        
        # Verify successful regions returned results
        assert len(result.region_metadata.successful_regions) == 2
        assert "us-east-1" in result.region_metadata.successful_regions
        assert "eu-west-1" in result.region_metadata.successful_regions
        
        # Verify failed region is tracked
        assert len(result.region_metadata.failed_regions) == 1
        assert "us-west-2" in result.region_metadata.failed_regions
        
        # Verify resources from successful regions are included
        assert result.total_resources == 2


    @pytest.mark.asyncio
    async def test_failed_regions_metadata_populated(
        self,
        compliance_service,
        mock_region_discovery,
        mock_client_factory,
        mock_cache,
        mock_policy_service,
    ):
        """Test that failed_regions metadata is correctly populated.
        
        Validates: Requirements 3.5, 4.5
        """
        # Setup one successful region
        mock_client_factory.get_client("us-east-1").get_ec2_instances.return_value = [
            {
                "resource_id": "i-east-1",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-1",
            }
        ]
        # Other regions return empty
        mock_client_factory.get_client("us-west-2").get_ec2_instances.return_value = []
        mock_client_factory.get_client("eu-west-1").get_ec2_instances.return_value = []

        # Create a compliance service factory that fails for multiple regions
        def failing_compliance_factory(aws_client: AWSClient) -> ComplianceService:
            if aws_client.region == "us-west-2":
                mock_service = MagicMock(spec=ComplianceService)
                mock_service.check_compliance = AsyncMock(
                    side_effect=Exception("Throttling: Rate exceeded")
                )
                return mock_service
            elif aws_client.region == "eu-west-1":
                mock_service = MagicMock(spec=ComplianceService)
                mock_service.check_compliance = AsyncMock(
                    side_effect=Exception("Access Denied")
                )
                return mock_service
            return ComplianceService(
                cache=mock_cache,
                aws_client=aws_client,
                policy_service=mock_policy_service,
                cache_ttl=3600,
            )

        # Create scanner with no retries
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=failing_compliance_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=True,
            default_region="us-east-1",
            max_retries=0,
        )

        # Call check_tag_compliance
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            multi_region_scanner=scanner,
        )

        # Verify failed regions are tracked
        assert isinstance(result, MultiRegionComplianceResult)
        assert len(result.region_metadata.failed_regions) == 2
        assert "us-west-2" in result.region_metadata.failed_regions
        assert "eu-west-1" in result.region_metadata.failed_regions
        
        # Verify successful region is tracked
        assert len(result.region_metadata.successful_regions) == 1
        assert "us-east-1" in result.region_metadata.successful_regions
        
        # Verify total regions count
        assert result.region_metadata.total_regions == 3

    @pytest.mark.asyncio
    async def test_partial_results_returned_on_failure(
        self,
        compliance_service,
        mock_region_discovery,
        mock_client_factory,
        compliance_service_factory,
        mock_policy_service,
    ):
        """Test that partial results include resources and violations from successful regions.
        
        Validates: Requirements 3.5
        """
        # Setup resources with violations in successful region
        mock_client_factory.get_client("us-east-1").get_ec2_instances.return_value = [
            {
                "resource_id": "i-east-1",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {},  # Missing required tags
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-1",
            },
            {
                "resource_id": "i-east-2",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 150.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-2",
            },
        ]

        # Configure other regions to fail
        mock_client_factory.get_client("us-west-2").get_ec2_instances.side_effect = Exception(
            "API Error"
        )
        mock_client_factory.get_client("eu-west-1").get_ec2_instances.side_effect = Exception(
            "API Error"
        )

        # Setup violation for untagged resource
        violation = Violation(
            resource_id="i-east-1",
            resource_type="ec2:instance",
            region="us-east-1",
            violation_type=ViolationType.MISSING_REQUIRED_TAG,
            tag_name="CostCenter",
            severity=Severity.ERROR,
            cost_impact_monthly=100.0,
        )

        def validate_side_effect(resource_id, resource_type, region, tags, cost_impact):
            if resource_id == "i-east-1":
                return [violation]
            return []

        mock_policy_service.validate_resource_tags.side_effect = validate_side_effect

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=True,
            default_region="us-east-1",
            max_retries=0,
        )

        # Call check_tag_compliance
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            multi_region_scanner=scanner,
        )

        # Verify partial results contain data from successful region
        assert isinstance(result, MultiRegionComplianceResult)
        assert result.total_resources == 2  # Both resources from us-east-1
        assert len(result.violations) == 1  # One violation
        assert result.violations[0].resource_id == "i-east-1"
        assert result.compliance_score == 0.5  # 1 compliant out of 2


    @pytest.mark.asyncio
    async def test_empty_region_results_are_successful(
        self,
        compliance_service,
        multi_region_scanner,
        mock_client_factory,
    ):
        """Test that regions with zero resources are treated as successful.
        
        Validates: Requirements 3.3
        """
        # Setup one region with resources, others empty
        mock_client_factory.get_client("us-east-1").get_ec2_instances.return_value = [
            {
                "resource_id": "i-east-1",
                "resource_type": "ec2:instance",
                "region": "us-east-1",
                "tags": {"CostCenter": "Engineering", "Environment": "production"},
                "cost_impact": 100.0,
                "arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-east-1",
            }
        ]
        mock_client_factory.get_client("us-west-2").get_ec2_instances.return_value = []
        mock_client_factory.get_client("eu-west-1").get_ec2_instances.return_value = []

        # Call check_tag_compliance
        result = await check_tag_compliance(
            compliance_service=compliance_service,
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            multi_region_scanner=multi_region_scanner,
        )

        # Verify all regions are successful (including empty ones)
        assert isinstance(result, MultiRegionComplianceResult)
        assert len(result.region_metadata.successful_regions) == 3
        assert len(result.region_metadata.failed_regions) == 0
        
        # Verify total resources only from region with resources
        assert result.total_resources == 1


# =============================================================================
# Test validate_resource_tags with Multi-Region
# =============================================================================


@pytest.mark.integration
class TestValidateResourceTagsMultiRegion:
    """Integration tests for validate_resource_tags with multi-region support.
    
    Requirements: 3.1 - Support ARNs from any region
    """

    @pytest.mark.asyncio
    async def test_validate_arns_from_multiple_regions(
        self,
        multi_region_scanner,
        mock_client_factory,
        mock_policy_service,
    ):
        """Test validating ARNs from different regions.
        
        Validates: Requirements 3.1
        """
        from mcp_server.tools.validate_resource_tags import validate_resource_tags

        # ARNs from different regions
        arns = [
            "arn:aws:ec2:us-east-1:123456789012:instance/i-east-1",
            "arn:aws:ec2:us-west-2:123456789012:instance/i-west-1",
            "arn:aws:ec2:eu-west-1:123456789012:instance/i-eu-1",
        ]

        # Configure mock clients to return tags for each region
        mock_client_factory.get_client("us-east-1").get_tags_for_arns.return_value = {
            arns[0]: {"CostCenter": "Engineering", "Environment": "production"}
        }
        mock_client_factory.get_client("us-west-2").get_tags_for_arns.return_value = {
            arns[1]: {"CostCenter": "Marketing"}  # Missing Environment
        }
        mock_client_factory.get_client("eu-west-1").get_tags_for_arns.return_value = {
            arns[2]: {}  # No tags
        }

        # Setup violations
        def validate_side_effect(resource_id, resource_type, region, tags, cost_impact):
            if not tags.get("Environment"):
                return [
                    Violation(
                        resource_id=resource_id,
                        resource_type=resource_type,
                        region=region,
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        tag_name="Environment",
                        severity=Severity.ERROR,
                        cost_impact_monthly=0.0,
                    )
                ]
            return []

        mock_policy_service.validate_resource_tags.side_effect = validate_side_effect

        # Create default client
        default_client = create_mock_aws_client("us-east-1")

        # Call validate_resource_tags with multi-region scanner
        result = await validate_resource_tags(
            aws_client=default_client,
            policy_service=mock_policy_service,
            resource_arns=arns,
            multi_region_scanner=multi_region_scanner,
        )

        # Verify all ARNs were validated
        assert result.total_resources == 3
        
        # Verify results include correct regions
        regions_validated = {r.region for r in result.results}
        assert "us-east-1" in regions_validated
        assert "us-west-2" in regions_validated
        assert "eu-west-1" in regions_validated
        
        # Verify compliance status
        assert result.compliant_resources == 1  # Only us-east-1 is compliant
        assert result.non_compliant_resources == 2
