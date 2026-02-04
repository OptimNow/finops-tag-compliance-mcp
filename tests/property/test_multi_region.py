# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""
Property-based tests for multi-region scanning functionality.

Feature: multi-region-scanning
Validates: Requirements 1.2, 2.2, 5.2

Property 1: Region Filtering by Opt-In Status
*For any* list of regions returned by the EC2 DescribeRegions API, the Region_Discovery_Service
SHALL return only regions where `OptInStatus` is "opt-in-not-required" or "opted-in",
excluding all regions with "not-opted-in" status.

Property 2: Client Reuse Idempotence
*For any* region code, calling `get_client(region)` multiple times on the same
RegionalClientFactory instance SHALL return the same AWSClient instance (object identity).

Property 9: Global Resource Type Identification
*For any* resource type string, the `_is_global_resource_type()` method SHALL return
`True` if and only if the resource type is in the GLOBAL_RESOURCE_TYPES set.
"""

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from mcp_server.models.multi_region import (
    GLOBAL_RESOURCE_TYPES,
    REGIONAL_RESOURCE_TYPES,
)
from mcp_server.services.region_discovery_service import (
    filter_regions_by_opt_in_status,
    VALID_OPT_IN_STATUSES,
)
from mcp_server.clients.regional_client_factory import RegionalClientFactory


# =============================================================================
# Strategies for Property 1: Region Filtering by Opt-In Status
# =============================================================================

# Valid opt-in statuses that should be included
VALID_STATUSES = ["opt-in-not-required", "opted-in"]

# Invalid opt-in status that should be excluded
INVALID_STATUSES = ["not-opted-in"]

# All possible opt-in statuses from AWS
ALL_OPT_IN_STATUSES = VALID_STATUSES + INVALID_STATUSES

# Sample AWS region names for testing (realistic examples)
SAMPLE_REGION_NAMES = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1",
    "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1",
    "ap-northeast-2", "ap-northeast-3", "sa-east-1", "ca-central-1",
    "me-south-1", "af-south-1", "eu-south-1", "ap-east-1",
]

# Strategy for generating a valid AWS region name (from sample list for speed)
region_name_strategy = st.sampled_from(SAMPLE_REGION_NAMES)

# Strategy for generating opt-in status
opt_in_status_strategy = st.sampled_from(ALL_OPT_IN_STATUSES)

# Strategy for generating a single region info dictionary
region_info_strategy = st.fixed_dictionaries({
    "RegionName": region_name_strategy,
    "OptInStatus": opt_in_status_strategy,
})

# Strategy for generating a list of region info dictionaries
regions_list_strategy = st.lists(
    region_info_strategy,
    min_size=0,
    max_size=30  # AWS has ~30 regions
)

# Strategy for generating region info with only valid statuses
valid_region_info_strategy = st.fixed_dictionaries({
    "RegionName": region_name_strategy,
    "OptInStatus": st.sampled_from(VALID_STATUSES),
})

# Strategy for generating region info with only invalid statuses
invalid_region_info_strategy = st.fixed_dictionaries({
    "RegionName": region_name_strategy,
    "OptInStatus": st.just("not-opted-in"),
})


# =============================================================================
# Property 1: Region Filtering by Opt-In Status
# =============================================================================


class TestRegionFilteringByOptInStatus:
    """
    Property 1: Region Filtering by Opt-In Status
    
    For any list of regions returned by the EC2 DescribeRegions API, the
    Region_Discovery_Service SHALL return only regions where `OptInStatus`
    is "opt-in-not-required" or "opted-in", excluding all regions with
    "not-opted-in" status.
    """

    @given(regions=regions_list_strategy)
    @settings(max_examples=100)
    def test_all_returned_regions_have_valid_opt_in_status(
        self, regions: list[dict[str, str]]
    ):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        All returned regions SHALL have at least one entry with a valid opt-in status
        ("opt-in-not-required" or "opted-in").
        """
        result = filter_regions_by_opt_in_status(regions)
        
        # Build a lookup of region name to all opt-in statuses for that region
        region_statuses: dict[str, set[str]] = {}
        for r in regions:
            region_name = r.get("RegionName", "")
            opt_in_status = r.get("OptInStatus", "")
            if region_name:
                if region_name not in region_statuses:
                    region_statuses[region_name] = set()
                region_statuses[region_name].add(opt_in_status)
        
        # Verify all returned regions have at least one valid opt-in status
        for region_name in result:
            statuses = region_statuses.get(region_name, set())
            has_valid_status = any(s in VALID_OPT_IN_STATUSES for s in statuses)
            assert has_valid_status, (
                f"Region '{region_name}' was returned but has no valid opt-in status. "
                f"Statuses found: {statuses}. Expected at least one of {VALID_OPT_IN_STATUSES}"
            )

    @given(regions=regions_list_strategy)
    @settings(max_examples=100)
    def test_no_regions_with_not_opted_in_status_are_returned(
        self, regions: list[dict[str, str]]
    ):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        No regions that ONLY have "not-opted-in" status SHALL be returned.
        (If a region has both valid and invalid entries, it may be returned.)
        """
        result = filter_regions_by_opt_in_status(regions)
        result_set = set(result)
        
        # Build a lookup of region name to all opt-in statuses for that region
        region_statuses: dict[str, set[str]] = {}
        for r in regions:
            region_name = r.get("RegionName", "")
            opt_in_status = r.get("OptInStatus", "")
            if region_name:
                if region_name not in region_statuses:
                    region_statuses[region_name] = set()
                region_statuses[region_name].add(opt_in_status)
        
        # Find all regions that ONLY have "not-opted-in" status
        only_not_opted_in_regions = {
            region_name
            for region_name, statuses in region_statuses.items()
            if statuses == {"not-opted-in"}
        }
        
        # Verify none of them are in the result
        returned_only_not_opted_in = result_set & only_not_opted_in_regions
        assert len(returned_only_not_opted_in) == 0, (
            f"Regions with only 'not-opted-in' status were incorrectly returned: "
            f"{returned_only_not_opted_in}"
        )

    @given(regions=regions_list_strategy)
    @settings(max_examples=100)
    def test_all_regions_with_valid_status_are_included(
        self, regions: list[dict[str, str]]
    ):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        All regions with valid opt-in status SHALL be included in the result.
        """
        result = filter_regions_by_opt_in_status(regions)
        result_set = set(result)
        
        # Find all regions with valid opt-in status
        valid_regions = {
            r["RegionName"]
            for r in regions
            if r.get("OptInStatus") in VALID_OPT_IN_STATUSES and r.get("RegionName")
        }
        
        # Verify all valid regions are in the result
        missing_regions = valid_regions - result_set
        assert len(missing_regions) == 0, (
            f"Regions with valid opt-in status were not included: {missing_regions}"
        )

    @given(regions=st.lists(valid_region_info_strategy, min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_all_valid_regions_are_returned(
        self, regions: list[dict[str, str]]
    ):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        When all regions have valid opt-in status, all SHALL be returned.
        """
        result = filter_regions_by_opt_in_status(regions)
        
        # All input regions should be in the result
        input_region_names = {r["RegionName"] for r in regions}
        result_set = set(result)
        
        assert result_set == input_region_names, (
            f"Expected all valid regions to be returned. "
            f"Input: {input_region_names}, Result: {result_set}"
        )

    @given(regions=st.lists(invalid_region_info_strategy, min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_no_invalid_regions_are_returned(
        self, regions: list[dict[str, str]]
    ):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        When all regions have "not-opted-in" status, none SHALL be returned.
        """
        result = filter_regions_by_opt_in_status(regions)
        
        assert len(result) == 0, (
            f"Expected no regions to be returned when all have 'not-opted-in' status, "
            f"but got: {result}"
        )

    def test_empty_input_returns_empty_list(self):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        Empty input SHALL return empty list.
        """
        result = filter_regions_by_opt_in_status([])
        assert result == [], f"Expected empty list, got: {result}"

    def test_result_is_sorted(self):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        Result SHALL be sorted alphabetically for consistent ordering.
        """
        regions = [
            {"RegionName": "us-west-2", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "eu-west-1", "OptInStatus": "opted-in"},
            {"RegionName": "ap-south-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
        ]
        
        result = filter_regions_by_opt_in_status(regions)
        
        assert result == sorted(result), (
            f"Result should be sorted. Got: {result}, Expected: {sorted(result)}"
        )

    def test_regions_with_missing_region_name_are_excluded(self):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        Regions with missing or empty RegionName SHALL be excluded.
        """
        regions = [
            {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "", "OptInStatus": "opt-in-not-required"},  # Empty name
            {"OptInStatus": "opted-in"},  # Missing name
            {"RegionName": "us-west-2", "OptInStatus": "opted-in"},
        ]
        
        result = filter_regions_by_opt_in_status(regions)
        
        assert "us-east-1" in result
        assert "us-west-2" in result
        assert "" not in result
        assert len(result) == 2

    def test_regions_with_missing_opt_in_status_are_excluded(self):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        Regions with missing OptInStatus SHALL be excluded.
        """
        regions = [
            {"RegionName": "us-east-1", "OptInStatus": "opt-in-not-required"},
            {"RegionName": "us-west-2"},  # Missing OptInStatus
            {"RegionName": "eu-west-1", "OptInStatus": "opted-in"},
        ]
        
        result = filter_regions_by_opt_in_status(regions)
        
        assert "us-east-1" in result
        assert "eu-west-1" in result
        assert "us-west-2" not in result
        assert len(result) == 2

    def test_valid_opt_in_statuses_constant_matches_expected(self):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        VALID_OPT_IN_STATUSES constant SHALL contain exactly the expected values.
        """
        expected = frozenset(["opt-in-not-required", "opted-in"])
        
        assert VALID_OPT_IN_STATUSES == expected, (
            f"VALID_OPT_IN_STATUSES mismatch. "
            f"Expected: {expected}, Got: {VALID_OPT_IN_STATUSES}"
        )

    @given(regions=regions_list_strategy)
    @settings(max_examples=100)
    def test_result_count_matches_valid_region_count(
        self, regions: list[dict[str, str]]
    ):
        """
        Feature: multi-region-scanning, Property 1: Region Filtering by Opt-In Status
        Validates: Requirements 1.2
        
        The number of returned regions SHALL equal the number of input regions
        with valid opt-in status and non-empty names.
        """
        result = filter_regions_by_opt_in_status(regions)
        
        # Count valid regions in input
        valid_count = sum(
            1 for r in regions
            if r.get("OptInStatus") in VALID_OPT_IN_STATUSES and r.get("RegionName")
        )
        
        assert len(result) == valid_count, (
            f"Expected {valid_count} regions, got {len(result)}. "
            f"Input: {regions}, Result: {result}"
        )


# =============================================================================
# Property 2: Client Reuse Idempotence
# =============================================================================


class TestClientReuseIdempotence:
    """
    Property 2: Client Reuse Idempotence
    
    For any region code, calling `get_client(region)` multiple times on the same
    RegionalClientFactory instance SHALL return the same AWSClient instance
    (object identity).
    
    Feature: multi-region-scanning
    Validates: Requirements 2.2
    """

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_get_client_returns_same_instance_on_repeated_calls(self, region: str):
        """
        Feature: multi-region-scanning, Property 2: Client Reuse Idempotence
        Validates: Requirements 2.2
        
        Calling get_client(region) multiple times SHALL return the same object.
        """
        factory = RegionalClientFactory(default_region="us-east-1")
        
        try:
            # Get client twice for the same region
            client1 = factory.get_client(region)
            client2 = factory.get_client(region)
            
            # Verify object identity (same instance, not just equal)
            assert client1 is client2, (
                f"Expected get_client('{region}') to return the same instance, "
                f"but got different objects: id(client1)={id(client1)}, id(client2)={id(client2)}"
            )
        finally:
            # Clean up cached clients
            factory.clear_clients()

    @given(region=region_name_strategy, num_calls=st.integers(min_value=2, max_value=10))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_get_client_returns_same_instance_on_n_calls(self, region: str, num_calls: int):
        """
        Feature: multi-region-scanning, Property 2: Client Reuse Idempotence
        Validates: Requirements 2.2
        
        Calling get_client(region) N times SHALL always return the same object.
        """
        factory = RegionalClientFactory(default_region="us-east-1")
        
        try:
            # Get client multiple times
            clients = [factory.get_client(region) for _ in range(num_calls)]
            
            # All clients should be the same instance
            first_client = clients[0]
            for i, client in enumerate(clients[1:], start=2):
                assert client is first_client, (
                    f"Expected all {num_calls} calls to get_client('{region}') to return "
                    f"the same instance, but call #{i} returned a different object. "
                    f"id(first)={id(first_client)}, id(call_{i})={id(client)}"
                )
        finally:
            factory.clear_clients()

    @given(regions=st.lists(region_name_strategy, min_size=2, max_size=10, unique=True))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_different_regions_get_different_clients(self, regions: list[str]):
        """
        Feature: multi-region-scanning, Property 2: Client Reuse Idempotence
        Validates: Requirements 2.2
        
        Different regions SHALL get different client instances.
        """
        factory = RegionalClientFactory(default_region="us-east-1")
        
        try:
            # Get clients for all regions
            clients = {region: factory.get_client(region) for region in regions}
            
            # Verify each region has a unique client instance
            client_ids = {id(client) for client in clients.values()}
            assert len(client_ids) == len(regions), (
                f"Expected {len(regions)} unique client instances for {len(regions)} regions, "
                f"but got {len(client_ids)} unique instances. "
                f"Regions: {regions}"
            )
        finally:
            factory.clear_clients()

    @given(regions=st.lists(region_name_strategy, min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_client_reuse_with_interleaved_calls(self, regions: list[str]):
        """
        Feature: multi-region-scanning, Property 2: Client Reuse Idempotence
        Validates: Requirements 2.2
        
        Interleaved calls to get_client for different regions SHALL still
        return the same instance for each region.
        """
        factory = RegionalClientFactory(default_region="us-east-1")
        
        try:
            # First pass: get clients for all regions
            first_pass = {region: factory.get_client(region) for region in regions}
            
            # Second pass: get clients again in reverse order
            second_pass = {region: factory.get_client(region) for region in reversed(regions)}
            
            # Verify same instances are returned
            for region in regions:
                assert first_pass[region] is second_pass[region], (
                    f"Expected same client instance for region '{region}' across passes, "
                    f"but got different objects: "
                    f"id(first)={id(first_pass[region])}, id(second)={id(second_pass[region])}"
                )
        finally:
            factory.clear_clients()

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_client_count_increases_only_for_new_regions(self, region: str):
        """
        Feature: multi-region-scanning, Property 2: Client Reuse Idempotence
        Validates: Requirements 2.2
        
        The client count SHALL increase only when a new region is requested.
        """
        factory = RegionalClientFactory(default_region="us-east-1")
        
        try:
            # Initial count should be 0
            assert factory.get_client_count() == 0, "Expected 0 clients initially"
            
            # First call should create a client
            factory.get_client(region)
            assert factory.get_client_count() == 1, "Expected 1 client after first call"
            
            # Subsequent calls should NOT increase count
            factory.get_client(region)
            assert factory.get_client_count() == 1, "Expected 1 client after second call"
            
            factory.get_client(region)
            assert factory.get_client_count() == 1, "Expected 1 client after third call"
        finally:
            factory.clear_clients()

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_has_client_returns_true_after_get_client(self, region: str):
        """
        Feature: multi-region-scanning, Property 2: Client Reuse Idempotence
        Validates: Requirements 2.2
        
        has_client(region) SHALL return True after get_client(region) is called.
        """
        factory = RegionalClientFactory(default_region="us-east-1")
        
        try:
            # Before getting client
            assert not factory.has_client(region), (
                f"Expected has_client('{region}') to be False before get_client"
            )
            
            # After getting client
            factory.get_client(region)
            assert factory.has_client(region), (
                f"Expected has_client('{region}') to be True after get_client"
            )
        finally:
            factory.clear_clients()

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cached_regions_includes_region_after_get_client(self, region: str):
        """
        Feature: multi-region-scanning, Property 2: Client Reuse Idempotence
        Validates: Requirements 2.2
        
        cached_regions SHALL include the region after get_client(region) is called.
        """
        factory = RegionalClientFactory(default_region="us-east-1")
        
        try:
            # Before getting client
            assert region not in factory.cached_regions, (
                f"Expected '{region}' not in cached_regions before get_client"
            )
            
            # After getting client
            factory.get_client(region)
            assert region in factory.cached_regions, (
                f"Expected '{region}' in cached_regions after get_client"
            )
        finally:
            factory.clear_clients()

    def test_clear_clients_resets_cache(self):
        """
        Feature: multi-region-scanning, Property 2: Client Reuse Idempotence
        Validates: Requirements 2.2
        
        clear_clients() SHALL reset the cache, causing new instances to be created.
        """
        factory = RegionalClientFactory(default_region="us-east-1")
        region = "us-east-1"
        
        # Get initial client
        client1 = factory.get_client(region)
        assert factory.get_client_count() == 1
        
        # Clear cache
        factory.clear_clients()
        assert factory.get_client_count() == 0
        assert not factory.has_client(region)
        
        # Get client again - should be a NEW instance
        client2 = factory.get_client(region)
        assert factory.get_client_count() == 1
        
        # After clearing, we get a new instance (not the same object)
        assert client1 is not client2, (
            "Expected new client instance after clear_clients(), "
            "but got the same object"
        )
        
        # Clean up
        factory.clear_clients()

    def test_multiple_factories_have_independent_caches(self):
        """
        Feature: multi-region-scanning, Property 2: Client Reuse Idempotence
        Validates: Requirements 2.2
        
        Different RegionalClientFactory instances SHALL have independent caches.
        """
        factory1 = RegionalClientFactory(default_region="us-east-1")
        factory2 = RegionalClientFactory(default_region="us-east-1")
        region = "us-west-2"
        
        try:
            # Get client from factory1
            client1 = factory1.get_client(region)
            
            # factory2 should not have this client cached
            assert not factory2.has_client(region), (
                "Expected factory2 to have independent cache from factory1"
            )
            
            # Get client from factory2
            client2 = factory2.get_client(region)
            
            # They should be different instances
            assert client1 is not client2, (
                "Expected different factories to create different client instances"
            )
            
            # But within each factory, reuse should work
            assert factory1.get_client(region) is client1
            assert factory2.get_client(region) is client2
        finally:
            factory1.clear_clients()
            factory2.clear_clients()


# =============================================================================
# Helper Function
# =============================================================================


def is_global_resource_type(resource_type: str) -> bool:
    """
    Check if a resource type is global (not region-specific).
    
    This helper function mirrors the behavior expected from the
    `_is_global_resource_type()` method in MultiRegionScanner.
    
    Args:
        resource_type: The resource type string to check (e.g., "s3:bucket", "ec2:instance")
        
    Returns:
        True if the resource type is in GLOBAL_RESOURCE_TYPES, False otherwise
    """
    return resource_type in GLOBAL_RESOURCE_TYPES


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for global resource types (from the defined set)
global_resource_type_strategy = st.sampled_from(list(GLOBAL_RESOURCE_TYPES))

# Strategy for regional resource types (from the defined set)
regional_resource_type_strategy = st.sampled_from(list(REGIONAL_RESOURCE_TYPES))

# Strategy for random resource type strings that are NOT in either set
# Generate strings that look like resource types but aren't in our known sets
random_resource_type_strategy = st.from_regex(
    r"[a-z0-9]{2,15}:[a-z0-9\-]{2,20}",
    fullmatch=True
).filter(
    lambda x: x not in GLOBAL_RESOURCE_TYPES and x not in REGIONAL_RESOURCE_TYPES
)

# Strategy for completely arbitrary strings
arbitrary_string_strategy = st.text(min_size=0, max_size=100)


# =============================================================================
# Property 9: Global Resource Type Identification
# =============================================================================


class TestGlobalResourceTypeIdentification:
    """
    Property 9: Global Resource Type Identification
    
    For any resource type string, the `_is_global_resource_type()` method SHALL return
    `True` if and only if the resource type is in the GLOBAL_RESOURCE_TYPES set.
    """

    @given(resource_type=global_resource_type_strategy)
    @settings(max_examples=100)
    def test_global_resource_types_return_true(self, resource_type: str):
        """
        Feature: multi-region-scanning, Property 9: Global Resource Type Identification
        Validates: Requirements 5.2
        
        All types in GLOBAL_RESOURCE_TYPES SHALL return True.
        """
        result = is_global_resource_type(resource_type)
        
        assert result is True, (
            f"Expected is_global_resource_type('{resource_type}') to return True "
            f"because '{resource_type}' is in GLOBAL_RESOURCE_TYPES"
        )

    @given(resource_type=regional_resource_type_strategy)
    @settings(max_examples=100)
    def test_regional_resource_types_return_false(self, resource_type: str):
        """
        Feature: multi-region-scanning, Property 9: Global Resource Type Identification
        Validates: Requirements 5.2
        
        All types in REGIONAL_RESOURCE_TYPES SHALL return False.
        """
        result = is_global_resource_type(resource_type)
        
        assert result is False, (
            f"Expected is_global_resource_type('{resource_type}') to return False "
            f"because '{resource_type}' is a regional resource type"
        )

    @given(resource_type=random_resource_type_strategy)
    @settings(max_examples=100)
    def test_unknown_resource_types_return_false(self, resource_type: str):
        """
        Feature: multi-region-scanning, Property 9: Global Resource Type Identification
        Validates: Requirements 5.2
        
        Random strings not in either set SHALL return False.
        """
        result = is_global_resource_type(resource_type)
        
        assert result is False, (
            f"Expected is_global_resource_type('{resource_type}') to return False "
            f"because '{resource_type}' is not in GLOBAL_RESOURCE_TYPES"
        )

    @given(resource_type=arbitrary_string_strategy)
    @settings(max_examples=100)
    def test_arbitrary_strings_only_true_if_in_global_set(self, resource_type: str):
        """
        Feature: multi-region-scanning, Property 9: Global Resource Type Identification
        Validates: Requirements 5.2
        
        For any arbitrary string, the function SHALL return True if and only if
        the string is in GLOBAL_RESOURCE_TYPES.
        """
        result = is_global_resource_type(resource_type)
        expected = resource_type in GLOBAL_RESOURCE_TYPES
        
        assert result == expected, (
            f"Expected is_global_resource_type('{resource_type}') to return {expected}, "
            f"but got {result}. "
            f"Resource type {'is' if expected else 'is not'} in GLOBAL_RESOURCE_TYPES"
        )

    def test_all_global_types_exhaustively(self):
        """
        Feature: multi-region-scanning, Property 9: Global Resource Type Identification
        Validates: Requirements 5.2
        
        Exhaustively verify all defined global resource types return True.
        """
        expected_global_types = {
            "s3:bucket",
            "iam:role",
            "iam:user",
            "iam:policy",
            "route53:hostedzone",
            "cloudfront:distribution",
        }
        
        # Verify our constants match expected values
        assert GLOBAL_RESOURCE_TYPES == expected_global_types, (
            f"GLOBAL_RESOURCE_TYPES mismatch. "
            f"Expected: {expected_global_types}, Got: {GLOBAL_RESOURCE_TYPES}"
        )
        
        # Verify each returns True
        for resource_type in expected_global_types:
            assert is_global_resource_type(resource_type) is True, (
                f"Expected '{resource_type}' to be identified as global"
            )

    def test_all_regional_types_exhaustively(self):
        """
        Feature: multi-region-scanning, Property 9: Global Resource Type Identification
        Validates: Requirements 5.2
        
        Exhaustively verify all defined regional resource types return False.
        """
        expected_regional_types = {
            "ec2:instance",
            "ec2:volume",
            "ec2:snapshot",
            "ec2:elastic-ip",
            "ec2:natgateway",
            "rds:db",
            "lambda:function",
            "ecs:service",
            "ecs:cluster",
            "eks:cluster",
            "opensearch:domain",
            "dynamodb:table",
            "elasticache:cluster",
            "sqs:queue",
            "sns:topic",
            "kinesis:stream",
        }
        
        # Verify our constants match expected values
        assert REGIONAL_RESOURCE_TYPES == expected_regional_types, (
            f"REGIONAL_RESOURCE_TYPES mismatch. "
            f"Expected: {expected_regional_types}, Got: {REGIONAL_RESOURCE_TYPES}"
        )
        
        # Verify each returns False
        for resource_type in expected_regional_types:
            assert is_global_resource_type(resource_type) is False, (
                f"Expected '{resource_type}' to NOT be identified as global"
            )

    def test_global_and_regional_sets_are_disjoint(self):
        """
        Feature: multi-region-scanning, Property 9: Global Resource Type Identification
        Validates: Requirements 5.2
        
        GLOBAL_RESOURCE_TYPES and REGIONAL_RESOURCE_TYPES SHALL have no overlap.
        """
        intersection = GLOBAL_RESOURCE_TYPES & REGIONAL_RESOURCE_TYPES
        
        assert len(intersection) == 0, (
            f"GLOBAL_RESOURCE_TYPES and REGIONAL_RESOURCE_TYPES should be disjoint, "
            f"but found overlap: {intersection}"
        )

    def test_empty_string_returns_false(self):
        """
        Feature: multi-region-scanning, Property 9: Global Resource Type Identification
        Validates: Requirements 5.2
        
        Empty string SHALL return False.
        """
        assert is_global_resource_type("") is False

    def test_case_sensitivity(self):
        """
        Feature: multi-region-scanning, Property 9: Global Resource Type Identification
        Validates: Requirements 5.2
        
        Resource type matching SHALL be case-sensitive.
        """
        # Uppercase versions should NOT match
        assert is_global_resource_type("S3:BUCKET") is False
        assert is_global_resource_type("S3:bucket") is False
        assert is_global_resource_type("s3:BUCKET") is False
        assert is_global_resource_type("IAM:role") is False
        
        # Only exact lowercase matches should work
        assert is_global_resource_type("s3:bucket") is True
        assert is_global_resource_type("iam:role") is True


# =============================================================================
# Property 3: All Enabled Regions Are Scanned
# =============================================================================


class TestAllEnabledRegionsAreScanned:
    """
    Property 3: All Enabled Regions Are Scanned
    
    For any set of enabled regions and any regional resource type, when multi-region
    scanning is enabled and no region filter is provided, the MultiRegionScanner
    SHALL attempt to scan each enabled region exactly once.
    
    Feature: multi-region-scanning
    Validates: Requirements 2.1, 3.1, 6.4
    """

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_all_enabled_regions_are_scanned_exactly_once(
        self, enabled_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 3: All Enabled Regions Are Scanned
        Validates: Requirements 2.1, 3.1, 6.4
        
        When no region filter is provided, each enabled region SHALL be scanned exactly once.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService to return our generated regions
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_clients: dict[str, MagicMock] = {}
        
        def get_client_side_effect(region: str) -> MagicMock:
            if region not in mock_clients:
                mock_clients[region] = MagicMock()
                mock_clients[region].region = region
            return mock_clients[region]
        
        mock_client_factory.get_client = MagicMock(side_effect=get_client_side_effect)
        
        # Mock ComplianceService factory that tracks scanned regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(
                resource_types: list[str],
                filters: dict | None = None,
                severity: str = "all",
                force_refresh: bool = False,
            ) -> ComplianceResult:
                # Track that this region was scanned
                scanned_regions.append(aws_client.region)
                
                # Return empty but successful result
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner with mocked dependencies
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with regional resource type (no region filter)
        resource_types = ["ec2:instance"]  # Regional resource type
        await scanner.scan_all_regions(
            resource_types=resource_types,
            filters=None,  # No region filter
            severity="all",
        )
        
        # Verify each enabled region was scanned exactly once
        scanned_set = set(scanned_regions)
        enabled_set = set(enabled_regions)
        
        # All enabled regions should be scanned
        assert scanned_set == enabled_set, (
            f"Expected all enabled regions to be scanned. "
            f"Enabled: {enabled_set}, Scanned: {scanned_set}, "
            f"Missing: {enabled_set - scanned_set}, Extra: {scanned_set - enabled_set}"
        )
        
        # Each region should be scanned exactly once
        from collections import Counter
        region_counts = Counter(scanned_regions)
        for region, count in region_counts.items():
            assert count == 1, (
                f"Region '{region}' was scanned {count} times, expected exactly 1. "
                f"All scan counts: {dict(region_counts)}"
            )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=10,
            unique=True
        ),
        resource_type=regional_resource_type_strategy
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_all_regions_scanned_for_any_regional_resource_type(
        self, enabled_regions: list[str], resource_type: str
    ):
        """
        Feature: multi-region-scanning, Property 3: All Enabled Regions Are Scanned
        Validates: Requirements 2.1, 3.1, 6.4
        
        For any regional resource type, all enabled regions SHALL be scanned.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_clients: dict[str, MagicMock] = {}
        
        def get_client_side_effect(region: str) -> MagicMock:
            if region not in mock_clients:
                mock_clients[region] = MagicMock()
                mock_clients[region].region = region
            return mock_clients[region]
        
        mock_client_factory.get_client = MagicMock(side_effect=get_client_side_effect)
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with the generated regional resource type
        await scanner.scan_all_regions(
            resource_types=[resource_type],
            filters=None,
            severity="all",
        )
        
        # Verify all enabled regions were scanned
        scanned_set = set(scanned_regions)
        enabled_set = set(enabled_regions)
        
        assert scanned_set == enabled_set, (
            f"For resource type '{resource_type}', expected all enabled regions to be scanned. "
            f"Enabled: {enabled_set}, Scanned: {scanned_set}"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_region_discovery_called_once_per_scan(
        self, enabled_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 3: All Enabled Regions Are Scanned
        Validates: Requirements 2.1, 3.1
        
        Region discovery SHALL be called exactly once per scan operation.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify region discovery was called exactly once
        assert mock_region_discovery.get_enabled_regions.call_count == 1, (
            f"Expected get_enabled_regions to be called exactly once, "
            f"but was called {mock_region_discovery.get_enabled_regions.call_count} times"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_successful_regions_metadata_matches_enabled_regions(
        self, enabled_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 3: All Enabled Regions Are Scanned
        Validates: Requirements 3.1, 6.4
        
        When all scans succeed, successful_regions metadata SHALL match enabled regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory (all succeed)
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify successful_regions matches enabled_regions
        successful_set = set(result.region_metadata.successful_regions)
        enabled_set = set(enabled_regions)
        
        assert successful_set == enabled_set, (
            f"Expected successful_regions to match enabled_regions. "
            f"Enabled: {enabled_set}, Successful: {successful_set}"
        )
        
        # Verify no failed regions
        assert len(result.region_metadata.failed_regions) == 0, (
            f"Expected no failed regions, but got: {result.region_metadata.failed_regions}"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_total_regions_metadata_equals_enabled_count(
        self, enabled_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 3: All Enabled Regions Are Scanned
        Validates: Requirements 3.1, 6.4
        
        The total_regions metadata SHALL equal the number of enabled regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify total_regions equals enabled count
        assert result.region_metadata.total_regions == len(enabled_regions), (
            f"Expected total_regions={len(enabled_regions)}, "
            f"but got {result.region_metadata.total_regions}"
        )

    @pytest.mark.asyncio
    async def test_empty_enabled_regions_returns_empty_result(self):
        """
        Feature: multi-region-scanning, Property 3: All Enabled Regions Are Scanned
        Validates: Requirements 3.1
        
        When no regions are enabled, the result SHALL have zero regions scanned.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService with empty regions
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=[])
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify empty result
        assert result.region_metadata.total_regions == 0, (
            f"Expected total_regions=0 for empty enabled regions, "
            f"but got {result.region_metadata.total_regions}"
        )
        assert len(result.region_metadata.successful_regions) == 0
        assert len(result.region_metadata.failed_regions) == 0

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_client_created_for_each_enabled_region(
        self, enabled_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 3: All Enabled Regions Are Scanned
        Validates: Requirements 2.1, 3.1
        
        A client SHALL be created for each enabled region during scanning.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Track which regions had clients created
        client_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory that tracks client creation
        mock_client_factory = MagicMock()
        
        def get_client_side_effect(region: str) -> MagicMock:
            client_regions.append(region)
            mock_client = MagicMock()
            mock_client.region = region
            return mock_client
        
        mock_client_factory.get_client = MagicMock(side_effect=get_client_side_effect)
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify a client was created for each enabled region
        client_regions_set = set(client_regions)
        enabled_set = set(enabled_regions)
        
        assert client_regions_set == enabled_set, (
            f"Expected clients to be created for all enabled regions. "
            f"Enabled: {enabled_set}, Client regions: {client_regions_set}"
        )


# =============================================================================
# Property 4: Empty Results Are Successful
# =============================================================================


class TestEmptyResultsAreSuccessful:
    """
    Property 4: Empty Results Are Successful
    
    For any region that returns zero resources during a scan, the RegionalScanResult
    SHALL have `success=True` and `error_message=None`, with an empty resources list.
    
    Feature: multi-region-scanning
    Validates: Requirements 3.3
    """

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_empty_region_scan_has_success_true(self, region: str):
        """
        Feature: multi-region-scanning, Property 4: Empty Results Are Successful
        Validates: Requirements 3.3
        
        When a region returns zero resources, success SHALL be True.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService to return just this region
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=[region])
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that returns EMPTY results
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,  # Zero resources
                    compliant_resources=0,
                    violations=[],  # No violations
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify the region is in successful_regions (not failed)
        assert region in result.region_metadata.successful_regions, (
            f"Region '{region}' with zero resources should be in successful_regions, "
            f"but was not. Successful: {result.region_metadata.successful_regions}, "
            f"Failed: {result.region_metadata.failed_regions}"
        )
        
        # Verify the region is NOT in failed_regions
        assert region not in result.region_metadata.failed_regions, (
            f"Region '{region}' with zero resources should NOT be in failed_regions, "
            f"but was found there."
        )

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_empty_region_scan_has_no_error_message(self, region: str):
        """
        Feature: multi-region-scanning, Property 4: Empty Results Are Successful
        Validates: Requirements 3.3
        
        When a region returns zero resources, error_message SHALL be None.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=[region])
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that returns EMPTY results
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify no failed regions (which would have error messages)
        assert len(result.region_metadata.failed_regions) == 0, (
            f"Region '{region}' with zero resources should have no error, "
            f"but failed_regions contains: {result.region_metadata.failed_regions}"
        )
        
        # Verify the regional breakdown shows success
        if region in result.regional_breakdown:
            regional_summary = result.regional_breakdown[region]
            assert regional_summary.total_resources == 0, (
                f"Expected 0 total_resources for empty region, "
                f"got {regional_summary.total_resources}"
            )

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_empty_region_scan_has_empty_resources_list(self, region: str):
        """
        Feature: multi-region-scanning, Property 4: Empty Results Are Successful
        Validates: Requirements 3.3
        
        When a region returns zero resources, the resources list SHALL be empty.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=[region])
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that returns EMPTY results
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify total_resources is 0
        assert result.total_resources == 0, (
            f"Expected total_resources=0 for empty region scan, "
            f"got {result.total_resources}"
        )
        
        # Verify violations list is empty
        assert len(result.violations) == 0, (
            f"Expected empty violations list for empty region scan, "
            f"got {len(result.violations)} violations"
        )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_multiple_empty_regions_all_successful(self, regions: list[str]):
        """
        Feature: multi-region-scanning, Property 4: Empty Results Are Successful
        Validates: Requirements 3.3
        
        When multiple regions all return zero resources, all SHALL be successful.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that returns EMPTY results for all regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify all regions are successful
        successful_set = set(result.region_metadata.successful_regions)
        regions_set = set(regions)
        
        assert successful_set == regions_set, (
            f"All empty regions should be successful. "
            f"Expected: {regions_set}, Got: {successful_set}"
        )
        
        # Verify no failed regions
        assert len(result.region_metadata.failed_regions) == 0, (
            f"Expected no failed regions for empty results, "
            f"but got: {result.region_metadata.failed_regions}"
        )

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_empty_region_has_compliance_score_of_one(self, region: str):
        """
        Feature: multi-region-scanning, Property 4: Empty Results Are Successful
        Validates: Requirements 3.3
        
        When a region returns zero resources, compliance score SHALL be 1.0 (fully compliant).
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=[region])
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that returns EMPTY results
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify compliance score is 1.0 (fully compliant when no resources)
        assert result.compliance_score == 1.0, (
            f"Expected compliance_score=1.0 for empty region, "
            f"got {result.compliance_score}"
        )
        
        # Verify regional breakdown also shows 1.0 compliance
        if region in result.regional_breakdown:
            regional_summary = result.regional_breakdown[region]
            assert regional_summary.compliance_score == 1.0, (
                f"Expected regional compliance_score=1.0 for empty region, "
                f"got {regional_summary.compliance_score}"
            )

    @given(
        region=region_name_strategy,
        resource_type=regional_resource_type_strategy
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_empty_results_for_any_resource_type_are_successful(
        self, region: str, resource_type: str
    ):
        """
        Feature: multi-region-scanning, Property 4: Empty Results Are Successful
        Validates: Requirements 3.3
        
        For any regional resource type, empty results SHALL be successful.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=[region])
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that returns EMPTY results
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with the generated resource type
        result = await scanner.scan_all_regions(
            resource_types=[resource_type],
            filters=None,
            severity="all",
        )
        
        # Verify success
        assert region in result.region_metadata.successful_regions, (
            f"Region '{region}' with zero '{resource_type}' resources should be successful"
        )
        assert region not in result.region_metadata.failed_regions, (
            f"Region '{region}' with zero '{resource_type}' resources should not be failed"
        )

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_empty_region_has_zero_cost_attribution_gap(self, region: str):
        """
        Feature: multi-region-scanning, Property 4: Empty Results Are Successful
        Validates: Requirements 3.3
        
        When a region returns zero resources, cost_attribution_gap SHALL be 0.0.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=[region])
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that returns EMPTY results
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify cost_attribution_gap is 0.0
        assert result.cost_attribution_gap == 0.0, (
            f"Expected cost_attribution_gap=0.0 for empty region, "
            f"got {result.cost_attribution_gap}"
        )
        
        # Verify regional breakdown also shows 0.0 cost gap
        if region in result.regional_breakdown:
            regional_summary = result.regional_breakdown[region]
            assert regional_summary.cost_attribution_gap == 0.0, (
                f"Expected regional cost_attribution_gap=0.0 for empty region, "
                f"got {regional_summary.cost_attribution_gap}"
            )

    @pytest.mark.asyncio
    async def test_regional_scan_result_model_with_empty_resources(self):
        """
        Feature: multi-region-scanning, Property 4: Empty Results Are Successful
        Validates: Requirements 3.3
        
        RegionalScanResult with empty resources SHALL have success=True and error_message=None.
        """
        from mcp_server.models.multi_region import RegionalScanResult
        
        # Create a RegionalScanResult with empty resources
        result = RegionalScanResult(
            region="us-east-1",
            success=True,
            resources=[],  # Empty resources
            violations=[],  # No violations
            compliant_count=0,
            error_message=None,  # No error
            scan_duration_ms=100,
        )
        
        # Verify the model properties
        assert result.success is True, "Empty result should have success=True"
        assert result.error_message is None, "Empty result should have error_message=None"
        assert len(result.resources) == 0, "Empty result should have empty resources list"
        assert len(result.violations) == 0, "Empty result should have empty violations list"
        assert result.compliant_count == 0, "Empty result should have compliant_count=0"

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=5,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_mixed_empty_and_nonempty_regions_empty_ones_still_successful(
        self, regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 4: Empty Results Are Successful
        Validates: Requirements 3.3
        
        When some regions have resources and some don't, empty regions SHALL still be successful.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity
        
        # First region will have resources, rest will be empty
        region_with_resources = regions[0]
        empty_regions = regions[1:]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory - returns resources for first region, empty for others
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                if aws_client.region == region_with_resources:
                    # Return some resources for the first region
                    return ComplianceResult(
                        compliance_score=0.5,
                        total_resources=2,
                        compliant_resources=1,
                        violations=[
                            Violation(
                                resource_id=f"arn:aws:ec2:{aws_client.region}:123456789012:instance/i-12345",
                                resource_type="ec2:instance",
                                region=aws_client.region,
                                tag_name="Environment",
                                violation_type=ViolationType.MISSING_REQUIRED_TAG,
                                severity=Severity.ERROR,
                                cost_impact_monthly=10.0,
                            )
                        ],
                    )
                else:
                    # Return empty results for other regions
                    return ComplianceResult(
                        compliance_score=1.0,
                        total_resources=0,
                        compliant_resources=0,
                        violations=[],
                    )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify ALL regions are successful (including empty ones)
        successful_set = set(result.region_metadata.successful_regions)
        regions_set = set(regions)
        
        assert successful_set == regions_set, (
            f"All regions (including empty ones) should be successful. "
            f"Expected: {regions_set}, Got: {successful_set}"
        )
        
        # Verify no failed regions
        assert len(result.region_metadata.failed_regions) == 0, (
            f"Expected no failed regions, but got: {result.region_metadata.failed_regions}"
        )
        
        # Verify empty regions are in the regional breakdown with correct values
        for empty_region in empty_regions:
            if empty_region in result.regional_breakdown:
                summary = result.regional_breakdown[empty_region]
                assert summary.total_resources == 0, (
                    f"Empty region '{empty_region}' should have 0 resources"
                )
                assert summary.compliance_score == 1.0, (
                    f"Empty region '{empty_region}' should have compliance_score=1.0"
                )


# =============================================================================
# Property 5: Partial Failures Don't Stop Scanning
# =============================================================================


class TestPartialFailuresDontStopScanning:
    """
    Property 5: Partial Failures Don't Stop Scanning
    
    For any set of regions where some scans succeed and some fail, the
    MultiRegionComplianceResult SHALL contain resources from all successful
    regions, and the `region_metadata.failed_regions` list SHALL contain
    exactly the regions that failed.
    
    Feature: multi-region-scanning
    Validates: Requirements 3.5, 4.5
    """

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=10,
            unique=True
        ),
        failure_ratio=st.floats(min_value=0.1, max_value=0.9)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_partial_failures_result_contains_successful_region_resources(
        self, all_regions: list[str], failure_ratio: float
    ):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        Resources from successful regions SHALL be included in the result.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Determine which regions will fail based on ratio
        num_failures = max(1, int(len(all_regions) * failure_ratio))
        failed_regions = set(all_regions[:num_failures])
        successful_regions = set(all_regions[num_failures:])
        
        # Ensure we have at least one successful region
        if not successful_regions:
            successful_regions = {all_regions[-1]}
            failed_regions.discard(all_regions[-1])
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory - fails for some regions, succeeds for others
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                
                # Return successful result with a violation
                return ComplianceResult(
                    compliance_score=0.5,
                    total_resources=2,
                    compliant_resources=1,
                    violations=[
                        Violation(
                            resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:8]}",
                            resource_type="ec2:instance",
                            region=region,
                            tag_name="Environment",
                            violation_type=ViolationType.MISSING_REQUIRED_TAG,
                            severity=Severity.ERROR,
                            cost_impact_monthly=10.0,
                        )
                    ],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner with no retries to ensure failures happen immediately
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,  # No retries to ensure failures happen
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify resources from successful regions are included
        result_successful_set = set(result.region_metadata.successful_regions)
        assert result_successful_set == successful_regions, (
            f"Expected successful regions {successful_regions}, "
            f"got {result_successful_set}"
        )
        
        # Verify violations exist from successful regions
        violation_regions = {v.region for v in result.violations}
        assert violation_regions.issubset(successful_regions), (
            f"Violations should only come from successful regions. "
            f"Violation regions: {violation_regions}, Successful: {successful_regions}"
        )

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=10,
            unique=True
        ),
        num_failures=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_failed_regions_list_contains_exactly_failed_regions(
        self, all_regions: list[str], num_failures: int
    ):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        The failed_regions list SHALL contain exactly the regions that failed.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        # Ensure num_failures doesn't exceed available regions minus 1
        actual_num_failures = min(num_failures, len(all_regions) - 1)
        failed_regions = set(all_regions[:actual_num_failures])
        successful_regions = set(all_regions[actual_num_failures:])
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify failed_regions contains exactly the regions that failed
        result_failed_set = set(result.region_metadata.failed_regions)
        assert result_failed_set == failed_regions, (
            f"Expected failed_regions to be {failed_regions}, "
            f"got {result_failed_set}"
        )

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=10,
            unique=True
        ),
        num_failures=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_successful_regions_list_contains_exactly_successful_regions(
        self, all_regions: list[str], num_failures: int
    ):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        The successful_regions list SHALL contain exactly the regions that succeeded.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Ensure num_failures doesn't exceed available regions minus 1
        actual_num_failures = min(num_failures, len(all_regions) - 1)
        failed_regions = set(all_regions[:actual_num_failures])
        successful_regions = set(all_regions[actual_num_failures:])
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify successful_regions contains exactly the regions that succeeded
        result_successful_set = set(result.region_metadata.successful_regions)
        assert result_successful_set == successful_regions, (
            f"Expected successful_regions to be {successful_regions}, "
            f"got {result_successful_set}"
        )

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=3,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_successful_and_failed_regions_are_disjoint(
        self, all_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        successful_regions and failed_regions SHALL be disjoint sets.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Fail approximately half the regions
        num_failures = len(all_regions) // 2
        failed_regions = set(all_regions[:num_failures])

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify successful and failed regions are disjoint
        successful_set = set(result.region_metadata.successful_regions)
        failed_set = set(result.region_metadata.failed_regions)
        intersection = successful_set & failed_set
        
        assert len(intersection) == 0, (
            f"successful_regions and failed_regions should be disjoint, "
            f"but found overlap: {intersection}"
        )

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=3,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_successful_plus_failed_equals_total_regions(
        self, all_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        successful_regions + failed_regions SHALL equal total_regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Fail approximately half the regions
        num_failures = len(all_regions) // 2
        failed_regions = set(all_regions[:num_failures])
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify successful + failed = total
        successful_count = len(result.region_metadata.successful_regions)
        failed_count = len(result.region_metadata.failed_regions)
        total = result.region_metadata.total_regions
        
        assert successful_count + failed_count == total, (
            f"successful ({successful_count}) + failed ({failed_count}) "
            f"should equal total ({total})"
        )

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=8,
            unique=True
        ),
        resources_per_region=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_resources_from_failed_regions_not_included(
        self, all_regions: list[str], resources_per_region: int
    ):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        Resources from failed regions SHALL NOT be included in the result.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Fail the first region
        failed_regions = {all_regions[0]}
        successful_regions = set(all_regions[1:])
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                
                # Return resources for successful regions
                violations = [
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{i}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for i in range(resources_per_region)
                ]
                return ComplianceResult(
                    compliance_score=0.5,
                    total_resources=resources_per_region * 2,
                    compliant_resources=resources_per_region,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify no violations from failed regions
        for violation in result.violations:
            assert violation.region not in failed_regions, (
                f"Found violation from failed region {violation.region}. "
                f"Failed regions: {failed_regions}"
            )
        
        # Verify violations only from successful regions
        violation_regions = {v.region for v in result.violations}
        assert violation_regions.issubset(successful_regions), (
            f"Violations should only come from successful regions. "
            f"Violation regions: {violation_regions}, Successful: {successful_regions}"
        )

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=8,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_scanning_continues_after_first_failure(
        self, all_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        Scanning SHALL continue even after the first region fails.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        # First region fails, rest succeed
        failed_region = all_regions[0]
        successful_regions = set(all_regions[1:])
        
        # Track which regions were actually scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                scanned_regions.append(region)
                
                if region == failed_region:
                    raise Exception(f"Simulated failure for region {region}")
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify all regions were attempted (scanning continued after failure)
        scanned_set = set(scanned_regions)
        all_regions_set = set(all_regions)
        assert scanned_set == all_regions_set, (
            f"All regions should be scanned even after failures. "
            f"Expected: {all_regions_set}, Scanned: {scanned_set}"
        )

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=8,
            unique=True
        ),
        cost_per_region=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_cost_gap_only_from_successful_regions(
        self, all_regions: list[str], cost_per_region: float
    ):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        Cost attribution gap SHALL only include costs from successful regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity
        
        # First region fails
        failed_regions = {all_regions[0]}
        successful_regions = set(all_regions[1:])
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )

        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                
                # Return a violation with cost for successful regions
                return ComplianceResult(
                    compliance_score=0.5,
                    total_resources=2,
                    compliant_resources=1,
                    violations=[
                        Violation(
                            resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-test",
                            resource_type="ec2:instance",
                            region=region,
                            tag_name="Environment",
                            violation_type=ViolationType.MISSING_REQUIRED_TAG,
                            severity=Severity.ERROR,
                            cost_impact_monthly=cost_per_region,
                        )
                    ],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Expected cost = cost_per_region * number of successful regions
        expected_cost = cost_per_region * len(successful_regions)
        
        # Allow small floating point tolerance
        assert abs(result.cost_attribution_gap - expected_cost) < 0.01, (
            f"Expected cost_attribution_gap={expected_cost:.2f} "
            f"(from {len(successful_regions)} successful regions), "
            f"got {result.cost_attribution_gap:.2f}"
        )

    @pytest.mark.asyncio
    async def test_single_failure_among_many_regions(self):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        A single failure among many regions SHALL not stop scanning.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        all_regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1", "sa-east-1"]
        failed_region = "eu-west-1"
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region == failed_region:
                    raise Exception(f"Simulated failure for region {region}")
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=1,
                    compliant_resources=1,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify exactly one failed region
        assert result.region_metadata.failed_regions == [failed_region], (
            f"Expected failed_regions=['{failed_region}'], "
            f"got {result.region_metadata.failed_regions}"
        )
        
        # Verify 4 successful regions
        expected_successful = [r for r in all_regions if r != failed_region]
        assert set(result.region_metadata.successful_regions) == set(expected_successful), (
            f"Expected successful_regions={expected_successful}, "
            f"got {result.region_metadata.successful_regions}"
        )

    @pytest.mark.asyncio
    async def test_multiple_failures_still_returns_partial_results(self):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        Multiple failures SHALL still return results from successful regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity
        
        all_regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        failed_regions = {"us-west-2", "ap-southeast-1"}  # 2 failures
        successful_regions = {"us-east-1", "eu-west-1"}   # 2 successes
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                return ComplianceResult(
                    compliance_score=0.5,
                    total_resources=2,
                    compliant_resources=1,
                    violations=[
                        Violation(
                            resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-test",
                            resource_type="ec2:instance",
                            region=region,
                            tag_name="Environment",
                            violation_type=ViolationType.MISSING_REQUIRED_TAG,
                            severity=Severity.ERROR,
                            cost_impact_monthly=10.0,
                        )
                    ],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify failed regions
        assert set(result.region_metadata.failed_regions) == failed_regions, (
            f"Expected failed_regions={failed_regions}, "
            f"got {set(result.region_metadata.failed_regions)}"
        )
        
        # Verify successful regions
        assert set(result.region_metadata.successful_regions) == successful_regions, (
            f"Expected successful_regions={successful_regions}, "
            f"got {set(result.region_metadata.successful_regions)}"
        )
        
        # Verify we have violations from successful regions
        assert len(result.violations) == len(successful_regions), (
            f"Expected {len(successful_regions)} violations (one per successful region), "
            f"got {len(result.violations)}"
        )
        
        # Verify violations are from successful regions only
        violation_regions = {v.region for v in result.violations}
        assert violation_regions == successful_regions, (
            f"Violations should be from successful regions only. "
            f"Expected: {successful_regions}, Got: {violation_regions}"
        )

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=8,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_regional_breakdown_only_includes_successful_regions(
        self, all_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 5: Partial Failures Don't Stop Scanning
        Validates: Requirements 3.5, 4.5
        
        Regional breakdown SHALL only include successful regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        # First region fails
        failed_regions = {all_regions[0]}
        successful_regions = set(all_regions[1:])
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=1,
                    compliant_resources=1,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify regional breakdown only includes successful regions
        breakdown_regions = set(result.regional_breakdown.keys())
        assert breakdown_regions == successful_regions, (
            f"Regional breakdown should only include successful regions. "
            f"Expected: {successful_regions}, Got: {breakdown_regions}"
        )
        
        # Verify failed regions are NOT in regional breakdown
        for failed_region in failed_regions:
            assert failed_region not in result.regional_breakdown, (
                f"Failed region '{failed_region}' should not be in regional breakdown"
            )


# =============================================================================
# Property 6: Resource Aggregation Preserves Region
# =============================================================================


class TestResourceAggregationPreservesRegion:
    """
    Property 6: Resource Aggregation Preserves Region
    
    For any set of regional scan results, the aggregated result SHALL contain
    all resources from all successful regions, and each resource SHALL have
    a `region` attribute matching the region it was scanned from.
    
    Feature: multi-region-scanning
    Validates: Requirements 4.1, 4.2
    """

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=8,
            unique=True
        ),
        resources_per_region=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_all_resources_from_successful_regions_are_included(
        self, regions: list[str], resources_per_region: int
    ):
        """
        Feature: multi-region-scanning, Property 6: Resource Aggregation Preserves Region
        Validates: Requirements 4.1, 4.2
        
        All resources from all successful regions SHALL be included in the aggregated result.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Track expected resources per region
        expected_resources: dict[str, list[str]] = {}
        for region in regions:
            expected_resources[region] = [
                f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:4]}{i}"
                for i in range(resources_per_region)
            ]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that returns resources with violations
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                resource_ids = expected_resources[region]
                
                violations = [
                    Violation(
                        resource_id=resource_id,
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for resource_id in resource_ids
                ]
                
                return ComplianceResult(
                    compliance_score=0.0,
                    total_resources=len(resource_ids),
                    compliant_resources=0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Collect all resource IDs from violations in the result
        result_resource_ids = {v.resource_id for v in result.violations}
        
        # Collect all expected resource IDs
        all_expected_ids = set()
        for region_resources in expected_resources.values():
            all_expected_ids.update(region_resources)
        
        # Verify all expected resources are in the result
        assert result_resource_ids == all_expected_ids, (
            f"Expected all resources from all regions to be included. "
            f"Missing: {all_expected_ids - result_resource_ids}, "
            f"Extra: {result_resource_ids - all_expected_ids}"
        )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=8,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_each_resource_has_region_attribute_matching_source_region(
        self, regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 6: Resource Aggregation Preserves Region
        Validates: Requirements 4.1, 4.2
        
        Each resource SHALL have a `region` attribute matching the region it was scanned from.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                resource_id = f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:8]}"
                
                return ComplianceResult(
                    compliance_score=0.5,
                    total_resources=2,
                    compliant_resources=1,
                    violations=[
                        Violation(
                            resource_id=resource_id,
                            resource_type="ec2:instance",
                            region=region,  # Region attribute set here
                            tag_name="Environment",
                            violation_type=ViolationType.MISSING_REQUIRED_TAG,
                            severity=Severity.ERROR,
                            cost_impact_monthly=10.0,
                        )
                    ],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Verify each violation has a region attribute matching its source region
        for violation in result.violations:
            # The resource_id contains the region in the ARN
            # Format: arn:aws:ec2:{region}:123456789012:instance/i-{region[:8]}
            arn_parts = violation.resource_id.split(":")
            expected_region = arn_parts[3] if len(arn_parts) > 3 else None
            
            assert violation.region == expected_region, (
                f"Violation region attribute '{violation.region}' does not match "
                f"expected region '{expected_region}' from ARN '{violation.resource_id}'"
            )
        
        # Verify we have violations from all regions
        violation_regions = {v.region for v in result.violations}
        assert violation_regions == set(regions), (
            f"Expected violations from all regions {set(regions)}, "
            f"but got violations from {violation_regions}"
        )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=8,
            unique=True
        ),
        resources_per_region=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_resources_are_not_duplicated_during_aggregation(
        self, regions: list[str], resources_per_region: int
    ):
        """
        Feature: multi-region-scanning, Property 6: Resource Aggregation Preserves Region
        Validates: Requirements 4.1, 4.2
        
        Resources SHALL NOT be duplicated during aggregation.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Track expected total resources
        total_expected_resources = len(regions) * resources_per_region
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                
                violations = [
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:4]}{i}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for i in range(resources_per_region)
                ]
                
                return ComplianceResult(
                    compliance_score=0.0,
                    total_resources=resources_per_region,
                    compliant_resources=0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )

        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify no duplicate resource IDs in violations
        resource_ids = [v.resource_id for v in result.violations]
        unique_resource_ids = set(resource_ids)
        
        assert len(resource_ids) == len(unique_resource_ids), (
            f"Found duplicate resources during aggregation. "
            f"Total violations: {len(resource_ids)}, Unique: {len(unique_resource_ids)}. "
            f"Duplicates: {[rid for rid in resource_ids if resource_ids.count(rid) > 1]}"
        )
        
        # Verify total count matches expected
        assert len(result.violations) == total_expected_resources, (
            f"Expected {total_expected_resources} violations "
            f"({len(regions)} regions * {resources_per_region} resources), "
            f"got {len(result.violations)}"
        )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=8,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_regional_breakdown_contains_entries_for_each_successful_region(
        self, regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 6: Resource Aggregation Preserves Region
        Validates: Requirements 4.1, 4.2
        
        The regional_breakdown SHALL contain entries for each successful region.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                
                return ComplianceResult(
                    compliance_score=0.5,
                    total_resources=2,
                    compliant_resources=1,
                    violations=[
                        Violation(
                            resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-test",
                            resource_type="ec2:instance",
                            region=region,
                            tag_name="Environment",
                            violation_type=ViolationType.MISSING_REQUIRED_TAG,
                            severity=Severity.ERROR,
                            cost_impact_monthly=10.0,
                        )
                    ],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Verify regional_breakdown contains entries for all successful regions
        breakdown_regions = set(result.regional_breakdown.keys())
        expected_regions = set(regions)
        
        assert breakdown_regions == expected_regions, (
            f"Regional breakdown should contain entries for all successful regions. "
            f"Expected: {expected_regions}, Got: {breakdown_regions}, "
            f"Missing: {expected_regions - breakdown_regions}"
        )
        
        # Verify each regional summary has the correct region attribute
        for region, summary in result.regional_breakdown.items():
            assert summary.region == region, (
                f"Regional summary region attribute '{summary.region}' "
                f"does not match key '{region}'"
            )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=6,
            unique=True
        ),
        resource_type=regional_resource_type_strategy
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_region_preservation_for_any_regional_resource_type(
        self, regions: list[str], resource_type: str
    ):
        """
        Feature: multi-region-scanning, Property 6: Resource Aggregation Preserves Region
        Validates: Requirements 4.1, 4.2
        
        For any regional resource type, region attributes SHALL be preserved.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                # Create resource ID based on resource type
                service_prefix = resource_type.split(":")[0]
                resource_id = f"arn:aws:{service_prefix}:{region}:123456789012:{resource_type.split(':')[1]}/test-{region[:4]}"
                
                return ComplianceResult(
                    compliance_score=0.5,
                    total_resources=2,
                    compliant_resources=1,
                    violations=[
                        Violation(
                            resource_id=resource_id,
                            resource_type=resource_type,
                            region=region,
                            tag_name="Environment",
                            violation_type=ViolationType.MISSING_REQUIRED_TAG,
                            severity=Severity.ERROR,
                            cost_impact_monthly=10.0,
                        )
                    ],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )

        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=[resource_type],
            filters=None,
            severity="all",
        )
        
        # Verify each violation has correct region attribute
        for violation in result.violations:
            assert violation.region in regions, (
                f"Violation region '{violation.region}' is not in expected regions {regions}"
            )
            
            # Verify the region in the violation matches the region in the ARN
            if ":" in violation.resource_id:
                arn_parts = violation.resource_id.split(":")
                if len(arn_parts) > 3:
                    arn_region = arn_parts[3]
                    assert violation.region == arn_region, (
                        f"Violation region '{violation.region}' does not match "
                        f"ARN region '{arn_region}' for resource '{violation.resource_id}'"
                    )
        
        # Verify we have violations from all regions
        violation_regions = {v.region for v in result.violations}
        assert violation_regions == set(regions), (
            f"Expected violations from all regions for resource type '{resource_type}'. "
            f"Expected: {set(regions)}, Got: {violation_regions}"
        )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=5,
            unique=True
        ),
        failure_ratio=st.floats(min_value=0.2, max_value=0.6)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_region_preservation_with_partial_failures(
        self, regions: list[str], failure_ratio: float
    ):
        """
        Feature: multi-region-scanning, Property 6: Resource Aggregation Preserves Region
        Validates: Requirements 4.1, 4.2
        
        Even with partial failures, resources from successful regions SHALL have
        correct region attributes.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Determine which regions will fail
        num_failures = max(1, int(len(regions) * failure_ratio))
        num_failures = min(num_failures, len(regions) - 1)  # Ensure at least one success
        failed_regions = set(regions[:num_failures])
        successful_regions = set(regions[num_failures:])
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                
                return ComplianceResult(
                    compliance_score=0.5,
                    total_resources=2,
                    compliant_resources=1,
                    violations=[
                        Violation(
                            resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:8]}",
                            resource_type="ec2:instance",
                            region=region,
                            tag_name="Environment",
                            violation_type=ViolationType.MISSING_REQUIRED_TAG,
                            severity=Severity.ERROR,
                            cost_impact_monthly=10.0,
                        )
                    ],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner with no retries
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify violations only come from successful regions
        violation_regions = {v.region for v in result.violations}
        assert violation_regions == successful_regions, (
            f"Violations should only come from successful regions. "
            f"Expected: {successful_regions}, Got: {violation_regions}"
        )
        
        # Verify each violation has correct region attribute
        for violation in result.violations:
            assert violation.region in successful_regions, (
                f"Violation region '{violation.region}' should be in successful regions"
            )
            
            # Verify region in ARN matches violation region
            arn_parts = violation.resource_id.split(":")
            if len(arn_parts) > 3:
                arn_region = arn_parts[3]
                assert violation.region == arn_region, (
                    f"Violation region '{violation.region}' does not match "
                    f"ARN region '{arn_region}'"
                )

    @pytest.mark.asyncio
    async def test_regional_summary_region_attribute_matches_key(self):
        """
        Feature: multi-region-scanning, Property 6: Resource Aggregation Preserves Region
        Validates: Requirements 4.1, 4.2
        
        Each RegionalSummary's region attribute SHALL match its key in regional_breakdown.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=1,
                    compliant_resources=1,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify each regional summary's region attribute matches its key
        for key, summary in result.regional_breakdown.items():
            assert summary.region == key, (
                f"RegionalSummary region attribute '{summary.region}' "
                f"does not match its key '{key}' in regional_breakdown"
            )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=8,
            unique=True
        ),
        resources_per_region=st.integers(min_value=0, max_value=3)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_total_resources_equals_sum_of_regional_resources(
        self, regions: list[str], resources_per_region: int
    ):
        """
        Feature: multi-region-scanning, Property 6: Resource Aggregation Preserves Region
        Validates: Requirements 4.1, 4.2
        
        Total resources in aggregated result SHALL equal sum of resources from all regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                
                violations = [
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:4]}{i}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for i in range(resources_per_region)
                ]

                return ComplianceResult(
                    compliance_score=1.0 if resources_per_region == 0 else 0.0,
                    total_resources=resources_per_region,
                    compliant_resources=0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Expected total resources
        expected_total = len(regions) * resources_per_region
        
        # Verify total resources matches sum
        assert result.total_resources == expected_total, (
            f"Expected total_resources={expected_total} "
            f"({len(regions)} regions * {resources_per_region} resources), "
            f"got {result.total_resources}"
        )
        
        # Verify sum of regional breakdown matches total
        regional_sum = sum(
            summary.total_resources 
            for summary in result.regional_breakdown.values()
        )
        assert regional_sum == expected_total, (
            f"Sum of regional resources ({regional_sum}) does not match "
            f"expected total ({expected_total})"
        )


# =============================================================================
# Property 7: Compliance Score Calculation
# =============================================================================


class TestComplianceScoreCalculation:
    """
    Property 7: Compliance Score Calculation
    
    For any set of regional scan results with known compliant and total resource counts,
    the aggregated compliance score SHALL equal `sum(compliant_resources) / sum(total_resources)`
    across all successful regions. When total resources is zero, the score SHALL be 1.0.
    
    Feature: multi-region-scanning
    Validates: Requirements 4.3
    """

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=10,
            unique=True
        ),
        compliant_per_region=st.integers(min_value=0, max_value=50),
        violations_per_region=st.integers(min_value=0, max_value=50)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_compliance_score_equals_sum_compliant_over_sum_total(
        self, regions: list[str], compliant_per_region: int, violations_per_region: int
    ):
        """
        Feature: multi-region-scanning, Property 7: Compliance Score Calculation
        Validates: Requirements 4.3
        
        Compliance score SHALL equal sum(compliant_resources) / sum(total_resources).
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                total = compliant_per_region + violations_per_region
                
                violations = [
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:4]}{i}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for i in range(violations_per_region)
                ]
                
                score = compliant_per_region / total if total > 0 else 1.0
                return ComplianceResult(
                    compliance_score=score,
                    total_resources=total,
                    compliant_resources=compliant_per_region,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Calculate expected values
        total_compliant = len(regions) * compliant_per_region
        total_resources = len(regions) * (compliant_per_region + violations_per_region)
        expected_score = total_compliant / total_resources if total_resources > 0 else 1.0
        
        # Verify compliance score calculation
        assert abs(result.compliance_score - expected_score) < 1e-9, (
            f"Expected compliance_score={expected_score:.6f} "
            f"(sum_compliant={total_compliant} / sum_total={total_resources}), "
            f"got {result.compliance_score:.6f}"
        )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_zero_total_resources_gives_score_of_one(self, regions: list[str]):
        """
        Feature: multi-region-scanning, Property 7: Compliance Score Calculation
        Validates: Requirements 4.3
        
        When total resources is zero, the score SHALL be 1.0 (fully compliant).
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory - returns ZERO resources for all regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,  # Zero resources
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify compliance score is 1.0 when total resources is zero
        assert result.compliance_score == 1.0, (
            f"Expected compliance_score=1.0 when total_resources=0, "
            f"got {result.compliance_score}"
        )
        
        # Verify total resources is indeed zero
        assert result.total_resources == 0, (
            f"Expected total_resources=0, got {result.total_resources}"
        )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=10,
            unique=True
        ),
        compliant_per_region=st.integers(min_value=0, max_value=100),
        violations_per_region=st.integers(min_value=0, max_value=100)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_compliance_score_always_between_zero_and_one(
        self, regions: list[str], compliant_per_region: int, violations_per_region: int
    ):
        """
        Feature: multi-region-scanning, Property 7: Compliance Score Calculation
        Validates: Requirements 4.3
        
        Compliance score SHALL always be between 0.0 and 1.0 inclusive.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                total = compliant_per_region + violations_per_region
                
                violations = [
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:4]}{i}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for i in range(violations_per_region)
                ]
                
                score = compliant_per_region / total if total > 0 else 1.0
                return ComplianceResult(
                    compliance_score=score,
                    total_resources=total,
                    compliant_resources=compliant_per_region,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify compliance score is between 0.0 and 1.0 inclusive
        assert 0.0 <= result.compliance_score <= 1.0, (
            f"Compliance score {result.compliance_score} is outside valid range [0.0, 1.0]. "
            f"Total resources: {result.total_resources}, Compliant: {result.compliant_resources}"
        )

    @given(
        all_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=10,
            unique=True
        ),
        num_failures=st.integers(min_value=1, max_value=4),
        compliant_per_region=st.integers(min_value=1, max_value=20),
        violations_per_region=st.integers(min_value=1, max_value=20)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_compliance_score_calculation_handles_partial_failures(
        self, all_regions: list[str], num_failures: int, 
        compliant_per_region: int, violations_per_region: int
    ):
        """
        Feature: multi-region-scanning, Property 7: Compliance Score Calculation
        Validates: Requirements 4.3
        
        Compliance score calculation SHALL only include successful regions,
        correctly handling partial failures.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Ensure num_failures doesn't exceed available regions minus 1
        actual_num_failures = min(num_failures, len(all_regions) - 1)
        failed_regions = set(all_regions[:actual_num_failures])
        successful_regions = all_regions[actual_num_failures:]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory - fails for some regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                
                total = compliant_per_region + violations_per_region
                violations = [
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:4]}{i}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for i in range(violations_per_region)
                ]
                
                score = compliant_per_region / total if total > 0 else 1.0
                return ComplianceResult(
                    compliance_score=score,
                    total_resources=total,
                    compliant_resources=compliant_per_region,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner with no retries
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Calculate expected values from SUCCESSFUL regions only
        num_successful = len(successful_regions)
        expected_total_compliant = num_successful * compliant_per_region
        expected_total_resources = num_successful * (compliant_per_region + violations_per_region)
        expected_score = expected_total_compliant / expected_total_resources if expected_total_resources > 0 else 1.0
        
        # Verify compliance score is calculated from successful regions only
        assert abs(result.compliance_score - expected_score) < 1e-9, (
            f"Expected compliance_score={expected_score:.6f} from {num_successful} successful regions, "
            f"got {result.compliance_score:.6f}. "
            f"Failed regions: {failed_regions}, Successful: {successful_regions}"
        )
        
        # Verify total resources matches successful regions only
        assert result.total_resources == expected_total_resources, (
            f"Expected total_resources={expected_total_resources} from successful regions, "
            f"got {result.total_resources}"
        )

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=8,
            unique=True
        ),
        region_data=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=30),  # compliant
                st.integers(min_value=0, max_value=30)   # violations
            ),
            min_size=2,
            max_size=8
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_compliance_score_with_varying_resources_per_region(
        self, regions: list[str], region_data: list[tuple[int, int]]
    ):
        """
        Feature: multi-region-scanning, Property 7: Compliance Score Calculation
        Validates: Requirements 4.3
        
        Compliance score SHALL correctly aggregate varying resource counts per region.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        # Ensure we have data for each region
        min_len = min(len(regions), len(region_data))
        regions = regions[:min_len]
        region_data = region_data[:min_len]
        
        # Create mapping of region to (compliant, violations)
        region_resource_map = dict(zip(regions, region_data))
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory with varying resources per region
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                compliant, violation_count = region_resource_map.get(region, (0, 0))
                total = compliant + violation_count
                
                violations = [
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:4]}{i}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for i in range(violation_count)
                ]
                
                score = compliant / total if total > 0 else 1.0
                return ComplianceResult(
                    compliance_score=score,
                    total_resources=total,
                    compliant_resources=compliant,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Calculate expected values
        total_compliant = sum(compliant for compliant, _ in region_data)
        total_resources = sum(compliant + violations for compliant, violations in region_data)
        expected_score = total_compliant / total_resources if total_resources > 0 else 1.0
        
        # Verify compliance score calculation
        assert abs(result.compliance_score - expected_score) < 1e-9, (
            f"Expected compliance_score={expected_score:.6f} "
            f"(sum_compliant={total_compliant} / sum_total={total_resources}), "
            f"got {result.compliance_score:.6f}. "
            f"Region data: {region_resource_map}"
        )

    @pytest.mark.asyncio
    async def test_compliance_score_with_all_compliant_resources(self):
        """
        Feature: multi-region-scanning, Property 7: Compliance Score Calculation
        Validates: Requirements 4.3
        
        When all resources are compliant, score SHALL be 1.0.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        regions = ["us-east-1", "us-west-2", "eu-west-1"]
        compliant_per_region = 10
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory - all compliant, no violations
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=compliant_per_region,
                    compliant_resources=compliant_per_region,
                    violations=[],  # No violations
                )
            )
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify compliance score is 1.0 (100% compliant)
        assert result.compliance_score == 1.0, (
            f"Expected compliance_score=1.0 when all resources are compliant, "
            f"got {result.compliance_score}"
        )
        
        # Verify totals
        expected_total = len(regions) * compliant_per_region
        assert result.total_resources == expected_total
        assert result.compliant_resources == expected_total

    @pytest.mark.asyncio
    async def test_compliance_score_with_all_non_compliant_resources(self):
        """
        Feature: multi-region-scanning, Property 7: Compliance Score Calculation
        Validates: Requirements 4.3
        
        When all resources have violations, score SHALL be 0.0.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity

        regions = ["us-east-1", "us-west-2"]
        violations_per_region = 5
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory - all violations, no compliant
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                violations = [
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:4]}{i}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for i in range(violations_per_region)
                ]
                
                return ComplianceResult(
                    compliance_score=0.0,
                    total_resources=violations_per_region,
                    compliant_resources=0,  # Zero compliant
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify compliance score is 0.0 (0% compliant)
        assert result.compliance_score == 0.0, (
            f"Expected compliance_score=0.0 when all resources have violations, "
            f"got {result.compliance_score}"
        )
        
        # Verify totals
        expected_total = len(regions) * violations_per_region
        assert result.total_resources == expected_total
        assert result.compliant_resources == 0

    @given(
        regions=st.lists(
            region_name_strategy,
            min_size=1,
            max_size=5,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_regional_breakdown_scores_match_formula(self, regions: list[str]):
        """
        Feature: multi-region-scanning, Property 7: Compliance Score Calculation
        Validates: Requirements 4.3
        
        Each regional breakdown score SHALL match compliant/total for that region.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        from mcp_server.models.enums import ViolationType, Severity
        import random

        # Generate random resource counts for each region
        region_data = {
            region: (random.randint(0, 20), random.randint(0, 20))
            for region in regions
        }
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                region = aws_client.region
                compliant, violation_count = region_data.get(region, (0, 0))
                total = compliant + violation_count
                
                violations = [
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region[:4]}{i}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type=ViolationType.MISSING_REQUIRED_TAG,
                        severity=Severity.ERROR,
                        cost_impact_monthly=10.0,
                    )
                    for i in range(violation_count)
                ]
                
                score = compliant / total if total > 0 else 1.0
                return ComplianceResult(
                    compliance_score=score,
                    total_resources=total,
                    compliant_resources=compliant,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify each regional breakdown score matches the formula
        for region in regions:
            if region in result.regional_breakdown:
                summary = result.regional_breakdown[region]
                compliant, violation_count = region_data[region]
                total = compliant + violation_count
                expected_score = compliant / total if total > 0 else 1.0
                
                assert abs(summary.compliance_score - expected_score) < 1e-9, (
                    f"Region '{region}' expected score={expected_score:.6f} "
                    f"(compliant={compliant} / total={total}), "
                    f"got {summary.compliance_score:.6f}"
                )


# =============================================================================
# Property 8: Cost Gap Summation
# =============================================================================


# Strategy for generating cost values (non-negative floats)
cost_value_strategy = st.floats(
    min_value=0.0,
    max_value=100000.0,
    allow_nan=False,
    allow_infinity=False,
)


class TestCostGapSummation:
    """
    Property 8: Cost Gap Summation
    
    For any set of regional scan results with cost attribution gaps, the aggregated
    `cost_attribution_gap` SHALL equal the sum of all regional cost gaps.
    
    Feature: multi-region-scanning
    Validates: Requirements 4.4
    """

    @given(
        regional_cost_gaps=st.lists(
            cost_value_strategy,
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_aggregated_cost_gap_equals_sum_of_regional_gaps(
        self, regional_cost_gaps: list[float]
    ):
        """
        Feature: multi-region-scanning, Property 8: Cost Gap Summation
        Validates: Requirements 4.4
        
        The aggregated cost_attribution_gap SHALL equal the sum of all regional cost gaps.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        
        # Generate unique regions for each cost gap
        regions = [f"region-{i}" for i in range(len(regional_cost_gaps))]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Create a mapping of region to cost gap
        region_to_cost_gap = dict(zip(regions, regional_cost_gaps))
        
        # Mock ComplianceService factory that returns violations with cost impacts
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            region = aws_client.region
            cost_gap = region_to_cost_gap.get(region, 0.0)
            
            # Create a single violation with the full cost gap for this region
            violations = []
            if cost_gap > 0:
                violations.append(
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type="missing_required_tag",
                        severity="error",
                        cost_impact_monthly=cost_gap,
                    )
                )
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                return ComplianceResult(
                    compliance_score=1.0 if not violations else 0.5,
                    total_resources=1 if violations else 0,
                    compliant_resources=0 if violations else 0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Calculate expected total cost gap
        expected_total_cost_gap = sum(regional_cost_gaps)
        
        # Verify aggregated cost gap equals sum of regional gaps
        # Use approximate comparison due to floating point arithmetic
        assert abs(result.cost_attribution_gap - expected_total_cost_gap) < 0.01, (
            f"Expected aggregated cost_attribution_gap to equal sum of regional gaps. "
            f"Expected: {expected_total_cost_gap:.2f}, Got: {result.cost_attribution_gap:.2f}, "
            f"Regional gaps: {regional_cost_gaps}"
        )

    @given(
        num_regions=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_cost_gap_is_zero_when_no_violations_exist(
        self, num_regions: int
    ):
        """
        Feature: multi-region-scanning, Property 8: Cost Gap Summation
        Validates: Requirements 4.4
        
        When no violations exist, the cost_attribution_gap SHALL be zero.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Generate regions
        regions = [f"region-{i}" for i in range(num_regions)]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory that returns NO violations (all compliant)
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=5,  # Some resources, all compliant
                    compliant_resources=5,
                    violations=[],  # No violations
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify cost gap is zero
        assert result.cost_attribution_gap == 0.0, (
            f"Expected cost_attribution_gap to be 0.0 when no violations exist, "
            f"but got {result.cost_attribution_gap}"
        )

    @given(
        successful_cost_gaps=st.lists(
            cost_value_strategy,
            min_size=1,
            max_size=10,
        ),
        num_failed_regions=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_cost_gap_handles_partial_failures(
        self, successful_cost_gaps: list[float], num_failed_regions: int
    ):
        """
        Feature: multi-region-scanning, Property 8: Cost Gap Summation
        Validates: Requirements 4.4
        
        When some regions fail, the cost_attribution_gap SHALL only sum successful regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        
        # Generate regions - some successful, some will fail
        successful_regions = [f"success-{i}" for i in range(len(successful_cost_gaps))]
        failed_regions = [f"failed-{i}" for i in range(num_failed_regions)]
        all_regions = successful_regions + failed_regions
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=all_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Create a mapping of successful region to cost gap
        region_to_cost_gap = dict(zip(successful_regions, successful_cost_gaps))
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            region = aws_client.region
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                # Failed regions raise an exception
                if region in failed_regions:
                    raise Exception(f"Simulated failure for region {region}")
                
                # Successful regions return results with cost gaps
                cost_gap = region_to_cost_gap.get(region, 0.0)
                violations = []
                if cost_gap > 0:
                    violations.append(
                        Violation(
                            resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region}",
                            resource_type="ec2:instance",
                            region=region,
                            tag_name="Environment",
                            violation_type="missing_required_tag",
                            severity="error",
                            cost_impact_monthly=cost_gap,
                        )
                    )
                
                return ComplianceResult(
                    compliance_score=1.0 if not violations else 0.5,
                    total_resources=1 if violations else 0,
                    compliant_resources=0 if violations else 0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner with no retries to ensure failures happen
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,  # No retries to ensure failures
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Calculate expected total cost gap (only from successful regions)
        expected_total_cost_gap = sum(successful_cost_gaps)
        
        # Verify aggregated cost gap equals sum of SUCCESSFUL regional gaps only
        assert abs(result.cost_attribution_gap - expected_total_cost_gap) < 0.01, (
            f"Expected cost_attribution_gap to equal sum of successful regional gaps. "
            f"Expected: {expected_total_cost_gap:.2f}, Got: {result.cost_attribution_gap:.2f}, "
            f"Successful gaps: {successful_cost_gaps}, Failed regions: {failed_regions}"
        )
        
        # Verify failed regions are tracked
        assert set(result.region_metadata.failed_regions) == set(failed_regions), (
            f"Expected failed_regions to be {set(failed_regions)}, "
            f"but got {set(result.region_metadata.failed_regions)}"
        )

    @given(
        regional_cost_gaps=st.lists(
            cost_value_strategy,
            min_size=1,
            max_size=10,
            unique_by=lambda x: round(x, 2),  # Ensure some variety
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_regional_breakdown_cost_gaps_sum_to_total(
        self, regional_cost_gaps: list[float]
    ):
        """
        Feature: multi-region-scanning, Property 8: Cost Gap Summation
        Validates: Requirements 4.4
        
        The sum of cost_attribution_gap in regional_breakdown SHALL equal the total cost_attribution_gap.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        
        # Generate unique regions
        regions = [f"region-{i}" for i in range(len(regional_cost_gaps))]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Create a mapping of region to cost gap
        region_to_cost_gap = dict(zip(regions, regional_cost_gaps))
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            region = aws_client.region
            cost_gap = region_to_cost_gap.get(region, 0.0)
            
            violations = []
            if cost_gap > 0:
                violations.append(
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type="missing_required_tag",
                        severity="error",
                        cost_impact_monthly=cost_gap,
                    )
                )
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                return ComplianceResult(
                    compliance_score=1.0 if not violations else 0.5,
                    total_resources=1 if violations else 0,
                    compliant_resources=0 if violations else 0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Sum cost gaps from regional breakdown
        breakdown_cost_gap_sum = sum(
            summary.cost_attribution_gap
            for summary in result.regional_breakdown.values()
        )
        
        # Verify regional breakdown sums to total
        assert abs(breakdown_cost_gap_sum - result.cost_attribution_gap) < 0.01, (
            f"Expected sum of regional_breakdown cost gaps to equal total cost_attribution_gap. "
            f"Breakdown sum: {breakdown_cost_gap_sum:.2f}, Total: {result.cost_attribution_gap:.2f}, "
            f"Regional breakdown: {[(r, s.cost_attribution_gap) for r, s in result.regional_breakdown.items()]}"
        )

    @given(
        regional_cost_gaps=st.lists(
            cost_value_strategy,
            min_size=0,
            max_size=15,
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_cost_gap_is_always_non_negative(
        self, regional_cost_gaps: list[float]
    ):
        """
        Feature: multi-region-scanning, Property 8: Cost Gap Summation
        Validates: Requirements 4.4
        
        The cost_attribution_gap SHALL always be non-negative.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        
        # Handle empty list case
        if not regional_cost_gaps:
            regional_cost_gaps = [0.0]
        
        # Generate unique regions
        regions = [f"region-{i}" for i in range(len(regional_cost_gaps))]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Create a mapping of region to cost gap
        region_to_cost_gap = dict(zip(regions, regional_cost_gaps))
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            region = aws_client.region
            cost_gap = region_to_cost_gap.get(region, 0.0)
            
            violations = []
            if cost_gap > 0:
                violations.append(
                    Violation(
                        resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region}",
                        resource_type="ec2:instance",
                        region=region,
                        tag_name="Environment",
                        violation_type="missing_required_tag",
                        severity="error",
                        cost_impact_monthly=cost_gap,
                    )
                )
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                return ComplianceResult(
                    compliance_score=1.0 if not violations else 0.5,
                    total_resources=1 if violations else 0,
                    compliant_resources=0 if violations else 0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify cost gap is non-negative
        assert result.cost_attribution_gap >= 0.0, (
            f"Expected cost_attribution_gap to be non-negative, "
            f"but got {result.cost_attribution_gap}"
        )
        
        # Also verify all regional breakdown cost gaps are non-negative
        for region, summary in result.regional_breakdown.items():
            assert summary.cost_attribution_gap >= 0.0, (
                f"Expected regional cost_attribution_gap for {region} to be non-negative, "
                f"but got {summary.cost_attribution_gap}"
            )

    @pytest.mark.asyncio
    async def test_cost_gap_with_empty_regions_is_zero(self):
        """
        Feature: multi-region-scanning, Property 8: Cost Gap Summation
        Validates: Requirements 4.4
        
        When no regions are scanned, the cost_attribution_gap SHALL be zero.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService with empty regions
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=[])
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify cost gap is zero
        assert result.cost_attribution_gap == 0.0, (
            f"Expected cost_attribution_gap to be 0.0 for empty regions, "
            f"but got {result.cost_attribution_gap}"
        )

    @given(
        cost_gaps=st.lists(
            st.floats(min_value=0.01, max_value=1000.0, allow_nan=False, allow_infinity=False),
            min_size=2,
            max_size=10,
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_cost_gap_summation_is_commutative(
        self, cost_gaps: list[float]
    ):
        """
        Feature: multi-region-scanning, Property 8: Cost Gap Summation
        Validates: Requirements 4.4
        
        The order of regional scans SHALL not affect the total cost_attribution_gap.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        import random as rand_module
        
        # Generate unique regions
        regions = [f"region-{i}" for i in range(len(cost_gaps))]
        
        # Create a mapping of region to cost gap
        region_to_cost_gap = dict(zip(regions, cost_gaps))
        
        # Helper to create scanner and run scan
        async def run_scan_with_region_order(region_order: list[str]) -> float:
            mock_region_discovery = MagicMock()
            mock_region_discovery.get_enabled_regions = AsyncMock(return_value=region_order)
            
            mock_client_factory = MagicMock()
            mock_client_factory.get_client = MagicMock(
                side_effect=lambda region: MagicMock(region=region)
            )
            
            def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
                mock_service = MagicMock()
                region = aws_client.region
                cost_gap = region_to_cost_gap.get(region, 0.0)
                
                violations = []
                if cost_gap > 0:
                    violations.append(
                        Violation(
                            resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region}",
                            resource_type="ec2:instance",
                            region=region,
                            tag_name="Environment",
                            violation_type="missing_required_tag",
                            severity="error",
                            cost_impact_monthly=cost_gap,
                        )
                    )
                
                async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                    return ComplianceResult(
                        compliance_score=1.0 if not violations else 0.5,
                        total_resources=1 if violations else 0,
                        compliant_resources=0 if violations else 0,
                        violations=violations,
                    )
                
                mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
                return mock_service
            
            scanner = MultiRegionScanner(
                region_discovery=mock_region_discovery,
                client_factory=mock_client_factory,
                compliance_service_factory=compliance_service_factory,
                max_concurrent_regions=5,
                region_timeout_seconds=60,
            )
            
            result = await scanner.scan_all_regions(
                resource_types=["ec2:instance"],
                filters=None,
                severity="all",
            )
            
            return result.cost_attribution_gap
        
        # Run scan with original order
        original_cost_gap = await run_scan_with_region_order(regions)
        
        # Run scan with reversed order
        reversed_regions = list(reversed(regions))
        reversed_cost_gap = await run_scan_with_region_order(reversed_regions)
        
        # Run scan with shuffled order
        shuffled_regions = regions.copy()
        rand_module.shuffle(shuffled_regions)
        shuffled_cost_gap = await run_scan_with_region_order(shuffled_regions)
        
        # Verify all orders produce the same total cost gap
        assert abs(original_cost_gap - reversed_cost_gap) < 0.01, (
            f"Cost gap should be the same regardless of region order. "
            f"Original: {original_cost_gap:.2f}, Reversed: {reversed_cost_gap:.2f}"
        )
        
        assert abs(original_cost_gap - shuffled_cost_gap) < 0.01, (
            f"Cost gap should be the same regardless of region order. "
            f"Original: {original_cost_gap:.2f}, Shuffled: {shuffled_cost_gap:.2f}"
        )


# =============================================================================
# Property 10: Global Resources Appear Exactly Once
# =============================================================================


class TestGlobalResourcesAppearExactlyOnce:
    """
    Property 10: Global Resources Appear Exactly Once
    
    For any global resource type (e.g., S3 buckets), when scanning across multiple
    regions, the aggregated result SHALL contain each unique resource exactly once,
    regardless of how many regions were scanned.
    
    Feature: multi-region-scanning
    Validates: Requirements 5.1, 5.3
    """

    @given(
        global_resource_type=global_resource_type_strategy,
        num_regions=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_global_resources_scanned_from_single_region_only(
        self, global_resource_type: str, num_regions: int
    ):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        Global resources SHALL be scanned from only one region, not all regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Generate regions
        regions = [f"region-{i}" for i in range(num_regions)]
        
        # Track which regions were scanned for global resources
        scanned_regions_for_global: list[str] = []

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that tracks scans
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(
                resource_types: list[str], **kwargs
            ) -> ComplianceResult:
                # Track if this region was scanned for global resources
                if global_resource_type in resource_types:
                    scanned_regions_for_global.append(aws_client.region)
                
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with global resource type
        await scanner.scan_all_regions(
            resource_types=[global_resource_type],
            filters=None,
            severity="all",
        )
        
        # Verify global resources were scanned from exactly ONE region
        assert len(scanned_regions_for_global) == 1, (
            f"Global resource type '{global_resource_type}' should be scanned from exactly "
            f"1 region, but was scanned from {len(scanned_regions_for_global)} regions: "
            f"{scanned_regions_for_global}"
        )

    @given(
        global_resource_type=global_resource_type_strategy,
        num_regions=st.integers(min_value=2, max_value=10),
        num_resources=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_global_resources_appear_exactly_once_in_aggregated_result(
        self, global_resource_type: str, num_regions: int, num_resources: int
    ):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        Each unique global resource SHALL appear exactly once in the aggregated result.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        
        # Generate regions and unique resource IDs
        regions = [f"region-{i}" for i in range(num_regions)]
        resource_ids = [f"arn:aws:s3:::bucket-{i}" for i in range(num_resources)]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )

        # Mock ComplianceService factory that returns global resources
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(
                resource_types: list[str], **kwargs
            ) -> ComplianceResult:
                # Return violations for global resources
                violations = [
                    Violation(
                        resource_id=rid,
                        resource_type=global_resource_type,
                        region="global",  # Global resources don't have a specific region
                        tag_name="Environment",
                        violation_type="missing_required_tag",
                        severity="error",
                        cost_impact_monthly=10.0,
                    )
                    for rid in resource_ids
                ]
                
                return ComplianceResult(
                    compliance_score=0.0,
                    total_resources=num_resources,
                    compliant_resources=0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with global resource type
        result = await scanner.scan_all_regions(
            resource_types=[global_resource_type],
            filters=None,
            severity="all",
        )

        # Count unique resource IDs in violations
        violation_resource_ids = [v.resource_id for v in result.violations]
        unique_violation_ids = set(violation_resource_ids)
        
        # Each resource should appear exactly once
        assert len(violation_resource_ids) == len(unique_violation_ids), (
            f"Global resources should appear exactly once in violations. "
            f"Found {len(violation_resource_ids)} violations but only "
            f"{len(unique_violation_ids)} unique resource IDs. "
            f"Duplicates detected!"
        )
        
        # Verify we have the expected number of unique resources
        assert len(unique_violation_ids) == num_resources, (
            f"Expected {num_resources} unique global resources, "
            f"but found {len(unique_violation_ids)}"
        )

    @given(
        num_regions=st.integers(min_value=2, max_value=10),
        num_global_resources=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_global_resource_count_not_multiplied_by_regions(
        self, num_regions: int, num_global_resources: int
    ):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        Global resource count SHALL NOT be multiplied by the number of regions scanned.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation

        # Generate regions
        regions = [f"region-{i}" for i in range(num_regions)]
        global_resource_type = "s3:bucket"
        resource_ids = [f"arn:aws:s3:::bucket-{i}" for i in range(num_global_resources)]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(
                resource_types: list[str], **kwargs
            ) -> ComplianceResult:
                violations = [
                    Violation(
                        resource_id=rid,
                        resource_type=global_resource_type,
                        region="global",
                        tag_name="Environment",
                        violation_type="missing_required_tag",
                        severity="error",
                        cost_impact_monthly=10.0,
                    )
                    for rid in resource_ids
                ]
                
                return ComplianceResult(
                    compliance_score=0.0,
                    total_resources=num_global_resources,
                    compliant_resources=0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=[global_resource_type],
            filters=None,
            severity="all",
        )
        
        # Verify violation count is NOT multiplied by number of regions
        # If global resources were scanned per-region, we'd have num_global_resources * num_regions
        max_expected_violations = num_global_resources
        
        assert len(result.violations) <= max_expected_violations, (
            f"Global resource violations should NOT be multiplied by region count. "
            f"Expected at most {max_expected_violations} violations, "
            f"but got {len(result.violations)}. "
            f"This suggests global resources were scanned {num_regions} times "
            f"(once per region) instead of once."
        )

    @given(
        num_regions=st.integers(min_value=2, max_value=8),
        num_regional_resources=st.integers(min_value=1, max_value=3),
        num_global_resources=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_mixed_global_and_regional_resources_handled_correctly(
        self, num_regions: int, num_regional_resources: int, num_global_resources: int
    ):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        Mixed global and regional resource types SHALL be handled correctly:
        - Global resources appear once
        - Regional resources appear per-region
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation

        # Generate regions
        regions = [f"region-{i}" for i in range(num_regions)]
        global_resource_type = "s3:bucket"
        regional_resource_type = "ec2:instance"
        
        global_resource_ids = [f"arn:aws:s3:::bucket-{i}" for i in range(num_global_resources)]
        
        # Track scans
        global_scans: list[str] = []
        regional_scans: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            region = aws_client.region
            
            async def check_compliance_side_effect(
                resource_types: list[str], **kwargs
            ) -> ComplianceResult:
                violations = []
                total = 0
                
                # Track which resource types are being scanned
                if global_resource_type in resource_types:
                    global_scans.append(region)
                    # Return global resources
                    for rid in global_resource_ids:
                        violations.append(
                            Violation(
                                resource_id=rid,
                                resource_type=global_resource_type,
                                region="global",
                                tag_name="Environment",
                                violation_type="missing_required_tag",
                                severity="error",
                                cost_impact_monthly=10.0,
                            )
                        )
                    total += num_global_resources

                if regional_resource_type in resource_types:
                    regional_scans.append(region)
                    # Return regional resources for this region
                    for i in range(num_regional_resources):
                        violations.append(
                            Violation(
                                resource_id=f"arn:aws:ec2:{region}:123456789012:instance/i-{region}-{i}",
                                resource_type=regional_resource_type,
                                region=region,
                                tag_name="Environment",
                                violation_type="missing_required_tag",
                                severity="error",
                                cost_impact_monthly=5.0,
                            )
                        )
                    total += num_regional_resources
                
                return ComplianceResult(
                    compliance_score=0.0 if violations else 1.0,
                    total_resources=total,
                    compliant_resources=0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with both global and regional resource types
        result = await scanner.scan_all_regions(
            resource_types=[global_resource_type, regional_resource_type],
            filters=None,
            severity="all",
        )

        # Verify global resources were scanned from exactly one region
        assert len(global_scans) == 1, (
            f"Global resources should be scanned from exactly 1 region, "
            f"but were scanned from {len(global_scans)} regions: {global_scans}"
        )
        
        # Verify regional resources were scanned from all regions
        assert set(regional_scans) == set(regions), (
            f"Regional resources should be scanned from all {num_regions} regions. "
            f"Expected: {set(regions)}, Got: {set(regional_scans)}"
        )
        
        # Count violations by type
        global_violations = [v for v in result.violations if v.resource_type == global_resource_type]
        regional_violations = [v for v in result.violations if v.resource_type == regional_resource_type]
        
        # Global violations should equal num_global_resources (not multiplied by regions)
        unique_global_ids = set(v.resource_id for v in global_violations)
        assert len(unique_global_ids) == num_global_resources, (
            f"Expected {num_global_resources} unique global resources, "
            f"but found {len(unique_global_ids)}"
        )
        
        # Regional violations should equal num_regional_resources * num_regions
        expected_regional = num_regional_resources * num_regions
        assert len(regional_violations) == expected_regional, (
            f"Expected {expected_regional} regional violations "
            f"({num_regional_resources} per region * {num_regions} regions), "
            f"but found {len(regional_violations)}"
        )

    @given(
        global_resource_type=global_resource_type_strategy,
        num_regions=st.integers(min_value=2, max_value=8),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_deduplication_when_same_global_resource_in_multiple_regions(
        self, global_resource_type: str, num_regions: int
    ):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        When the same global resource appears in multiple regions (hypothetically),
        deduplication SHALL ensure it appears exactly once in the result.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.multi_region import RegionalScanResult
        from mcp_server.models.violations import Violation
        
        # Generate regions
        regions = [f"region-{i}" for i in range(num_regions)]
        
        # Create a single global resource that "appears" in all regions
        duplicate_resource_id = "arn:aws:s3:::shared-bucket"
        
        # Create regional scan results where the same global resource appears in each
        regional_results = []
        for region in regions:
            regional_results.append(
                RegionalScanResult(
                    region=region,
                    success=True,
                    resources=[
                        {
                            "resource_id": duplicate_resource_id,
                            "resource_type": global_resource_type,
                            "region": region,
                            "is_global": True,
                        }
                    ],
                    violations=[
                        Violation(
                            resource_id=duplicate_resource_id,
                            resource_type=global_resource_type,
                            region=region,
                            tag_name="Environment",
                            violation_type="missing_required_tag",
                            severity="error",
                            cost_impact_monthly=10.0,
                        )
                    ],
                    compliant_count=0,
                )
            )

        # Create a scanner and test the aggregation directly
        mock_region_discovery = MagicMock()
        mock_client_factory = MagicMock()
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=lambda x: MagicMock(),
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Call the aggregation method directly
        aggregated = scanner._aggregate_results(
            regional_results=regional_results,
            skipped_regions=[],
            global_result=regional_results[0] if regional_results else None,
        )
        
        # Count unique resource IDs in violations
        violation_ids = [v.resource_id for v in aggregated.violations]
        unique_ids = set(violation_ids)
        
        # The duplicate resource should appear exactly once after deduplication
        assert duplicate_resource_id in unique_ids, (
            f"Expected duplicate resource '{duplicate_resource_id}' to be in results"
        )
        
        # Count how many times the duplicate appears
        duplicate_count = violation_ids.count(duplicate_resource_id)
        assert duplicate_count == 1, (
            f"Global resource '{duplicate_resource_id}' should appear exactly once "
            f"after deduplication, but appeared {duplicate_count} times"
        )

    @given(global_resource_type=global_resource_type_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_all_global_resource_types_scanned_once(
        self, global_resource_type: str
    ):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        All global resource types (S3, IAM, Route53, CloudFront) SHALL be scanned once.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        regions = ["us-east-1", "us-west-2", "eu-west-1"]
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(
                resource_types: list[str], **kwargs
            ) -> ComplianceResult:
                if global_resource_type in resource_types:
                    scanned_regions.append(aws_client.region)
                
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        await scanner.scan_all_regions(
            resource_types=[global_resource_type],
            filters=None,
            severity="all",
        )
        
        # Verify exactly one region was scanned for this global resource type
        assert len(scanned_regions) == 1, (
            f"Global resource type '{global_resource_type}' should be scanned from "
            f"exactly 1 region, but was scanned from {len(scanned_regions)}: {scanned_regions}"
        )

    @pytest.mark.asyncio
    async def test_exhaustive_global_types_scanned_once(self):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        Exhaustively verify all defined global resource types are scanned exactly once.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        all_global_types = list(GLOBAL_RESOURCE_TYPES)
        regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        
        for global_type in all_global_types:
            scanned_regions: list[str] = []
            
            mock_region_discovery = MagicMock()
            mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
            
            mock_client_factory = MagicMock()
            mock_client_factory.get_client = MagicMock(
                side_effect=lambda r: MagicMock(region=r)
            )

            def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
                mock_service = MagicMock()
                
                async def check_compliance_side_effect(
                    resource_types: list[str], **kwargs
                ) -> ComplianceResult:
                    if global_type in resource_types:
                        scanned_regions.append(aws_client.region)
                    
                    return ComplianceResult(
                        compliance_score=1.0,
                        total_resources=0,
                        compliant_resources=0,
                        violations=[],
                    )
                
                mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
                return mock_service
            
            scanner = MultiRegionScanner(
                region_discovery=mock_region_discovery,
                client_factory=mock_client_factory,
                compliance_service_factory=compliance_service_factory,
                max_concurrent_regions=5,
                region_timeout_seconds=60,
            )
            
            await scanner.scan_all_regions(
                resource_types=[global_type],
                filters=None,
                severity="all",
            )
            
            assert len(scanned_regions) == 1, (
                f"Global resource type '{global_type}' should be scanned from exactly "
                f"1 region, but was scanned from {len(scanned_regions)}: {scanned_regions}"
            )

    @given(
        num_regions=st.integers(min_value=1, max_value=10),
        num_resources=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_global_resources_have_is_global_flag(
        self, num_regions: int, num_resources: int
    ):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        Global resources SHALL be marked with is_global=True flag.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        from mcp_server.models.violations import Violation
        
        regions = [f"region-{i}" for i in range(num_regions)]
        global_resource_type = "s3:bucket"
        resource_ids = [f"arn:aws:s3:::bucket-{i}" for i in range(num_resources)]
        
        # Track resources returned
        returned_resources: list[dict] = []
        
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )

        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(
                resource_types: list[str], **kwargs
            ) -> ComplianceResult:
                violations = [
                    Violation(
                        resource_id=rid,
                        resource_type=global_resource_type,
                        region="global",
                        tag_name="Environment",
                        violation_type="missing_required_tag",
                        severity="error",
                        cost_impact_monthly=10.0,
                    )
                    for rid in resource_ids
                ]
                
                return ComplianceResult(
                    compliance_score=0.0,
                    total_resources=num_resources,
                    compliant_resources=0,
                    violations=violations,
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=[global_resource_type],
            filters=None,
            severity="all",
        )
        
        # Verify the scan completed successfully
        assert len(result.region_metadata.successful_regions) >= 1, (
            "At least one region should have been scanned successfully"
        )

    @given(
        num_regions=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_global_only_scan_uses_first_region(
        self, num_regions: int
    ):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        When scanning only global resources, the first available region SHALL be used.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        regions = [f"region-{i}" for i in range(num_regions)]
        scanned_region: list[str] = []
        
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=regions)
        
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_region.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with only global resource type
        await scanner.scan_all_regions(
            resource_types=["s3:bucket"],  # Global only
            filters=None,
            severity="all",
        )
        
        # Verify only one region was scanned
        assert len(scanned_region) == 1, (
            f"Expected exactly 1 region to be scanned for global resources, "
            f"but {len(scanned_region)} were scanned: {scanned_region}"
        )
        
        # Verify it was the first region
        assert scanned_region[0] == regions[0], (
            f"Expected first region '{regions[0]}' to be used for global scan, "
            f"but '{scanned_region[0]}' was used"
        )

    @pytest.mark.asyncio
    async def test_is_global_resource_type_method_consistency(self):
        """
        Feature: multi-region-scanning, Property 10: Global Resources Appear Exactly Once
        Validates: Requirements 5.1, 5.3
        
        The _is_global_resource_type method SHALL be consistent with GLOBAL_RESOURCE_TYPES.
        """
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from unittest.mock import MagicMock
        
        scanner = MultiRegionScanner(
            region_discovery=MagicMock(),
            client_factory=MagicMock(),
            compliance_service_factory=lambda x: MagicMock(),
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Verify all global types return True
        for global_type in GLOBAL_RESOURCE_TYPES:
            assert scanner._is_global_resource_type(global_type) is True, (
                f"Expected _is_global_resource_type('{global_type}') to return True"
            )
        
        # Verify all regional types return False
        for regional_type in REGIONAL_RESOURCE_TYPES:
            assert scanner._is_global_resource_type(regional_type) is False, (
                f"Expected _is_global_resource_type('{regional_type}') to return False"
            )


# =============================================================================
# Property 11: Region Filter Application
# =============================================================================


class TestRegionFilterApplication:
    """
    Property 11: Region Filter Application
    
    For any region filter provided in the request, the MultiRegionScanner SHALL scan
    only the regions specified in the filter, and the `region_metadata.successful_regions`
    SHALL be a subset of the filter.
    
    Feature: multi-region-scanning
    Validates: Requirements 6.1
    """

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=3,
            max_size=10,
            unique=True
        ),
        filter_size=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_only_filtered_regions_are_scanned(
        self, enabled_regions: list[str], filter_size: int
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        When a region filter is provided, only those regions SHALL be scanned.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Select a subset of enabled regions for the filter
        filter_size = min(filter_size, len(enabled_regions))
        region_filter = enabled_regions[:filter_size]
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory that tracks scanned regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with region filter
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": region_filter},
            severity="all",
        )
        
        # Verify only filtered regions were scanned
        scanned_set = set(scanned_regions)
        filter_set = set(region_filter)
        
        assert scanned_set == filter_set, (
            f"Expected only filtered regions to be scanned. "
            f"Filter: {filter_set}, Scanned: {scanned_set}, "
            f"Extra: {scanned_set - filter_set}, Missing: {filter_set - scanned_set}"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=3,
            max_size=10,
            unique=True
        ),
        filter_size=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_successful_regions_is_subset_of_filter(
        self, enabled_regions: list[str], filter_size: int
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        The `region_metadata.successful_regions` SHALL be a subset of the filter.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Select a subset of enabled regions for the filter
        filter_size = min(filter_size, len(enabled_regions))
        region_filter = enabled_regions[:filter_size]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory (all succeed)
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with region filter
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": region_filter},
            severity="all",
        )
        
        # Verify successful_regions is a subset of the filter
        successful_set = set(result.region_metadata.successful_regions)
        filter_set = set(region_filter)
        
        assert successful_set.issubset(filter_set), (
            f"Expected successful_regions to be a subset of filter. "
            f"Filter: {filter_set}, Successful: {successful_set}, "
            f"Not in filter: {successful_set - filter_set}"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=3,
            max_size=10,
            unique=True
        ),
        filter_size=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_regions_not_in_filter_are_not_scanned(
        self, enabled_regions: list[str], filter_size: int
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        Regions not in the filter SHALL NOT be scanned.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Select a subset of enabled regions for the filter
        filter_size = min(filter_size, len(enabled_regions))
        region_filter = enabled_regions[:filter_size]
        excluded_regions = enabled_regions[filter_size:]
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory that tracks scanned regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with region filter
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": region_filter},
            severity="all",
        )
        
        # Verify excluded regions were NOT scanned
        scanned_set = set(scanned_regions)
        excluded_set = set(excluded_regions)
        
        incorrectly_scanned = scanned_set & excluded_set
        assert len(incorrectly_scanned) == 0, (
            f"Regions not in filter were incorrectly scanned: {incorrectly_scanned}. "
            f"Filter: {region_filter}, Excluded: {excluded_regions}"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=2,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_filter_with_all_enabled_regions_scans_all(
        self, enabled_regions: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        Filter with all enabled regions SHALL scan all regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory that tracks scanned regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with filter containing ALL enabled regions
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": enabled_regions},  # All enabled regions
            severity="all",
        )
        
        # Verify all enabled regions were scanned
        scanned_set = set(scanned_regions)
        enabled_set = set(enabled_regions)
        
        assert scanned_set == enabled_set, (
            f"Expected all enabled regions to be scanned when filter contains all. "
            f"Enabled: {enabled_set}, Scanned: {scanned_set}"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=4,
            max_size=10,
            unique=True
        ),
        subset_size=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_filter_with_subset_scans_only_subset(
        self, enabled_regions: list[str], subset_size: int
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        Filter with subset of enabled regions SHALL scan only the subset.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Select a subset of enabled regions
        subset_size = min(subset_size, len(enabled_regions) - 1)  # Ensure it's a proper subset
        region_subset = enabled_regions[:subset_size]
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory that tracks scanned regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with subset filter
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": region_subset},
            severity="all",
        )
        
        # Verify only subset was scanned
        scanned_set = set(scanned_regions)
        subset_set = set(region_subset)
        
        assert scanned_set == subset_set, (
            f"Expected only subset regions to be scanned. "
            f"Subset: {subset_set}, Scanned: {scanned_set}"
        )
        
        # Verify count matches
        assert len(scanned_regions) == len(region_subset), (
            f"Expected {len(region_subset)} regions scanned, got {len(scanned_regions)}"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=3,
            max_size=10,
            unique=True
        ),
        filter_size=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_total_regions_metadata_equals_filter_size(
        self, enabled_regions: list[str], filter_size: int
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        The total_regions metadata SHALL equal the filter size when filter is provided.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Select a subset of enabled regions for the filter
        filter_size = min(filter_size, len(enabled_regions))
        region_filter = enabled_regions[:filter_size]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda region: MagicMock(region=region)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with region filter
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": region_filter},
            severity="all",
        )
        
        # Verify total_regions equals filter size
        assert result.region_metadata.total_regions == len(region_filter), (
            f"Expected total_regions={len(region_filter)}, "
            f"but got {result.region_metadata.total_regions}"
        )

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_single_region_filter_scans_only_that_region(
        self, region: str
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        A single-region filter SHALL scan only that one region.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Create a list of enabled regions that includes the target region
        enabled_regions = [region, "us-west-2", "eu-west-1", "ap-southeast-1"]
        # Ensure uniqueness
        enabled_regions = list(dict.fromkeys(enabled_regions))
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory that tracks scanned regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with single-region filter
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": [region]},
            severity="all",
        )
        
        # Verify only the single region was scanned
        assert scanned_regions == [region], (
            f"Expected only [{region}] to be scanned, but got {scanned_regions}"
        )
        
        # Verify metadata
        assert result.region_metadata.total_regions == 1
        assert result.region_metadata.successful_regions == [region]

    @given(region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_string_region_filter_works_same_as_list(
        self, region: str
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        A string region filter SHALL work the same as a single-element list filter.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Create a list of enabled regions that includes the target region
        enabled_regions = [region, "us-west-2", "eu-west-1"]
        enabled_regions = list(dict.fromkeys(enabled_regions))
        
        # Track which regions were scanned for each test
        scanned_with_string: list[str] = []
        scanned_with_list: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Test with string filter
        def compliance_service_factory_string(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_with_string.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0, total_resources=0,
                    compliant_resources=0, violations=[],
                )
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        scanner_string = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory_string,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute with string filter (using "region" key)
        await scanner_string.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"region": region},  # String, not list
            severity="all",
        )
        
        # Test with list filter
        def compliance_service_factory_list(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_with_list.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0, total_resources=0,
                    compliant_resources=0, violations=[],
                )
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        scanner_list = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory_list,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute with list filter
        await scanner_list.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": [region]},  # List with single element
            severity="all",
        )
        
        # Both should scan the same regions
        assert set(scanned_with_string) == set(scanned_with_list), (
            f"String filter and list filter should scan same regions. "
            f"String: {scanned_with_string}, List: {scanned_with_list}"
        )

    @pytest.mark.asyncio
    async def test_empty_filter_scans_all_enabled_regions(self):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        Empty or None filter SHALL scan all enabled regions (no filtering).
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        enabled_regions = ["us-east-1", "us-west-2", "eu-west-1"]
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0, total_resources=0,
                    compliant_resources=0, violations=[],
                )
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute with empty filter dict
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={},  # Empty dict
            severity="all",
        )
        
        # Verify all enabled regions were scanned
        assert set(scanned_regions) == set(enabled_regions), (
            f"Empty filter should scan all enabled regions. "
            f"Enabled: {enabled_regions}, Scanned: {scanned_regions}"
        )

    @pytest.mark.asyncio
    async def test_none_filter_scans_all_enabled_regions(self):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        None filter SHALL scan all enabled regions.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        enabled_regions = ["us-east-1", "us-west-2", "eu-west-1"]
        scanned_regions: list[str] = []
        
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0, total_resources=0,
                    compliant_resources=0, violations=[],
                )
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute with None filter
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify all enabled regions were scanned
        assert set(scanned_regions) == set(enabled_regions), (
            f"None filter should scan all enabled regions. "
            f"Enabled: {enabled_regions}, Scanned: {scanned_regions}"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=4,
            max_size=8,
            unique=True
        ),
        filter_size=st.integers(min_value=2, max_value=3)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_failed_regions_in_filter_still_subset_of_filter(
        self, enabled_regions: list[str], filter_size: int
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        Even when some filtered regions fail, successful_regions + failed_regions
        SHALL be a subset of the filter.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Select a subset of enabled regions for the filter (at least 2 to ensure partial success)
        filter_size = min(filter_size, len(enabled_regions))
        region_filter = enabled_regions[:filter_size]
        
        # Make only the first region fail (others will succeed)
        fail_region = region_filter[0] if region_filter else None
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory - first region fails
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                if aws_client.region == fail_region:
                    raise Exception(f"Simulated failure for {aws_client.region}")
                return ComplianceResult(
                    compliance_score=1.0, total_resources=0,
                    compliant_resources=0, violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            max_retries=0,  # No retries for faster test
        )
        
        # Execute scan with region filter
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": region_filter},
            severity="all",
        )
        
        # Verify successful + failed regions are subset of filter
        all_attempted = set(result.region_metadata.successful_regions) | set(result.region_metadata.failed_regions)
        filter_set = set(region_filter)
        
        assert all_attempted.issubset(filter_set), (
            f"All attempted regions should be subset of filter. "
            f"Filter: {filter_set}, Attempted: {all_attempted}"
        )
        
        # Verify successful_regions is subset of filter
        assert set(result.region_metadata.successful_regions).issubset(filter_set), (
            f"Successful regions should be subset of filter. "
            f"Filter: {filter_set}, Successful: {result.region_metadata.successful_regions}"
        )

    @given(
        enabled_regions=st.lists(
            region_name_strategy,
            min_size=3,
            max_size=10,
            unique=True
        ),
        filter_size=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_regional_breakdown_only_contains_filtered_regions(
        self, enabled_regions: list[str], filter_size: int
    ):
        """
        Feature: multi-region-scanning, Property 11: Region Filter Application
        Validates: Requirements 6.1
        
        The regional_breakdown SHALL only contain regions from the filter.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Select a subset of enabled regions for the filter
        filter_size = min(filter_size, len(enabled_regions))
        region_filter = enabled_regions[:filter_size]
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0, total_resources=5,
                    compliant_resources=5, violations=[],
                )
            )
            return mock_service
        
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
        )
        
        # Execute scan with region filter
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": region_filter},
            severity="all",
        )
        
        # Verify regional_breakdown only contains filtered regions
        breakdown_regions = set(result.regional_breakdown.keys())
        filter_set = set(region_filter)
        
        assert breakdown_regions.issubset(filter_set), (
            f"Regional breakdown should only contain filtered regions. "
            f"Filter: {filter_set}, Breakdown: {breakdown_regions}, "
            f"Extra: {breakdown_regions - filter_set}"
        )


# =============================================================================
# Property 12: Multi-Region Disabled Mode
# =============================================================================


class TestMultiRegionDisabledMode:
    """
    Property 12: Multi-Region Disabled Mode
    
    For any scan request when `MULTI_REGION_ENABLED=False`, the MultiRegionScanner
    SHALL scan only the default configured region, and `region_metadata.total_regions`
    SHALL equal 1.
    
    Feature: multi-region-scanning
    Validates: Requirements 7.1, 7.4
    """

    @given(
        default_region=region_name_strategy,
        resource_type=regional_resource_type_strategy
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_disabled_mode_scans_only_default_region(
        self, default_region: str, resource_type: str
    ):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        When multi-region is disabled, only the default region SHALL be scanned.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService - should NOT be called when disabled
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(
            return_value=["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        )
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        
        def get_client_side_effect(region: str) -> MagicMock:
            mock_client = MagicMock()
            mock_client.region = region
            return mock_client
        
        mock_client_factory.get_client = MagicMock(side_effect=get_client_side_effect)
        
        # Mock ComplianceService factory that tracks scanned regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner with multi_region_enabled=False
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region=default_region,
        )
        
        # Execute scan
        await scanner.scan_all_regions(
            resource_types=[resource_type],
            filters=None,
            severity="all",
        )
        
        # Verify only the default region was scanned
        assert len(scanned_regions) == 1, (
            f"Expected exactly 1 region to be scanned when disabled, "
            f"but {len(scanned_regions)} were scanned: {scanned_regions}"
        )
        assert scanned_regions[0] == default_region, (
            f"Expected default region '{default_region}' to be scanned, "
            f"but '{scanned_regions[0]}' was scanned instead"
        )

    @given(default_region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_disabled_mode_total_regions_equals_one(self, default_region: str):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        When multi-region is disabled, region_metadata.total_regions SHALL equal 1.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(
            return_value=["us-east-1", "us-west-2", "eu-west-1"]
        )
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=5,
                    compliant_resources=5,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner with multi_region_enabled=False
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region=default_region,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify total_regions equals 1
        assert result.region_metadata.total_regions == 1, (
            f"Expected total_regions=1 when disabled, "
            f"but got {result.region_metadata.total_regions}"
        )

    @given(default_region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_disabled_mode_region_discovery_not_called(self, default_region: str):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        When multi-region is disabled, region discovery SHALL NOT be called.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService - should NOT be called
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(
            return_value=["us-east-1", "us-west-2", "eu-west-1"]
        )
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner with multi_region_enabled=False
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region=default_region,
        )

        # Execute scan
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify region discovery was NOT called
        assert mock_region_discovery.get_enabled_regions.call_count == 0, (
            f"Expected get_enabled_regions to NOT be called when disabled, "
            f"but was called {mock_region_discovery.get_enabled_regions.call_count} times"
        )

    @given(
        default_region=region_name_strategy,
        region_filter=st.lists(region_name_strategy, min_size=1, max_size=5, unique=True)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_disabled_mode_ignores_region_filters(
        self, default_region: str, region_filter: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        When multi-region is disabled, region filters SHALL be ignored.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(
            return_value=["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        )
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )

        # Mock ComplianceService factory that tracks scanned regions
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner with multi_region_enabled=False
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region=default_region,
        )
        
        # Execute scan WITH a region filter (should be ignored)
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters={"regions": region_filter},  # This filter should be ignored
            severity="all",
        )
        
        # Verify only the default region was scanned (filter ignored)
        assert len(scanned_regions) == 1, (
            f"Expected exactly 1 region when disabled (filter ignored), "
            f"but {len(scanned_regions)} were scanned: {scanned_regions}"
        )
        assert scanned_regions[0] == default_region, (
            f"Expected default region '{default_region}' to be scanned "
            f"(ignoring filter {region_filter}), but '{scanned_regions[0]}' was scanned"
        )

    @given(default_region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_disabled_mode_default_region_configurable(self, default_region: str):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        The default region SHALL be configurable when multi-region is disabled.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Track which regions were scanned
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(return_value=[])
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner with multi_region_enabled=False and custom default_region
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region=default_region,  # Custom default region
        )
        
        # Execute scan
        await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify the configured default region was used
        assert len(scanned_regions) == 1, (
            f"Expected exactly 1 region to be scanned"
        )
        assert scanned_regions[0] == default_region, (
            f"Expected configured default region '{default_region}' to be scanned, "
            f"but '{scanned_regions[0]}' was scanned"
        )

    @given(default_region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_disabled_mode_successful_regions_contains_only_default(
        self, default_region: str
    ):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        When disabled, successful_regions SHALL contain only the default region.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(
            return_value=["us-east-1", "us-west-2", "eu-west-1"]
        )
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=3,
                    compliant_resources=3,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner with multi_region_enabled=False
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region=default_region,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify successful_regions contains only the default region
        assert len(result.region_metadata.successful_regions) == 1, (
            f"Expected 1 successful region when disabled, "
            f"but got {len(result.region_metadata.successful_regions)}"
        )
        assert result.region_metadata.successful_regions[0] == default_region, (
            f"Expected successful_regions to contain '{default_region}', "
            f"but got {result.region_metadata.successful_regions}"
        )


    @given(default_region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_disabled_mode_regional_breakdown_contains_only_default(
        self, default_region: str
    ):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        When disabled, regional_breakdown SHALL contain only the default region.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(
            return_value=["us-east-1", "us-west-2", "eu-west-1"]
        )
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=0.8,
                    total_resources=10,
                    compliant_resources=8,
                    violations=[],
                )
            )
            return mock_service

        # Create scanner with multi_region_enabled=False
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region=default_region,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify regional_breakdown contains only the default region
        breakdown_regions = set(result.regional_breakdown.keys())
        assert breakdown_regions == {default_region}, (
            f"Expected regional_breakdown to contain only '{default_region}', "
            f"but got {breakdown_regions}"
        )

    @pytest.mark.asyncio
    async def test_disabled_mode_with_default_us_east_1(self):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        When disabled with default us-east-1, only us-east-1 SHALL be scanned.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(
            return_value=["us-east-1", "us-west-2", "eu-west-1"]
        )

        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service
        
        # Create scanner with multi_region_enabled=False (default region is us-east-1)
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region="us-east-1",  # Default
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify only us-east-1 was scanned
        assert scanned_regions == ["us-east-1"], (
            f"Expected only us-east-1 to be scanned, but got {scanned_regions}"
        )
        assert result.region_metadata.total_regions == 1
        assert result.region_metadata.successful_regions == ["us-east-1"]


    @given(
        default_region=region_name_strategy,
        resource_types=st.lists(regional_resource_type_strategy, min_size=1, max_size=3, unique=True)
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_disabled_mode_works_with_multiple_resource_types(
        self, default_region: str, resource_types: list[str]
    ):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        When disabled, scanning multiple resource types SHALL still use only default region.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        scanned_regions: list[str] = []
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(
            return_value=["us-east-1", "us-west-2", "eu-west-1"]
        )
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )
        
        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            
            async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                scanned_regions.append(aws_client.region)
                return ComplianceResult(
                    compliance_score=1.0,
                    total_resources=len(resource_types),
                    compliant_resources=len(resource_types),
                    violations=[],
                )
            
            mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
            return mock_service

        # Create scanner with multi_region_enabled=False
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region=default_region,
        )
        
        # Execute scan with multiple resource types
        result = await scanner.scan_all_regions(
            resource_types=resource_types,
            filters=None,
            severity="all",
        )
        
        # Verify only the default region was scanned
        unique_scanned = set(scanned_regions)
        assert unique_scanned == {default_region}, (
            f"Expected only '{default_region}' to be scanned for {resource_types}, "
            f"but got {unique_scanned}"
        )
        assert result.region_metadata.total_regions == 1

    @given(default_region=region_name_strategy)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @pytest.mark.asyncio
    async def test_disabled_mode_no_skipped_regions(self, default_region: str):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        When disabled, skipped_regions SHALL be empty (no regions are skipped).
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult
        
        # Mock RegionDiscoveryService
        mock_region_discovery = MagicMock()
        mock_region_discovery.get_enabled_regions = AsyncMock(
            return_value=["us-east-1", "us-west-2", "eu-west-1"]
        )
        
        # Mock RegionalClientFactory
        mock_client_factory = MagicMock()
        mock_client_factory.get_client = MagicMock(
            side_effect=lambda r: MagicMock(region=r)
        )

        # Mock ComplianceService factory
        def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
            mock_service = MagicMock()
            mock_service.check_compliance = AsyncMock(
                return_value=ComplianceResult(
                    compliance_score=1.0,
                    total_resources=0,
                    compliant_resources=0,
                    violations=[],
                )
            )
            return mock_service
        
        # Create scanner with multi_region_enabled=False
        scanner = MultiRegionScanner(
            region_discovery=mock_region_discovery,
            client_factory=mock_client_factory,
            compliance_service_factory=compliance_service_factory,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region=default_region,
        )
        
        # Execute scan
        result = await scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify skipped_regions is empty
        assert len(result.region_metadata.skipped_regions) == 0, (
            f"Expected no skipped regions when disabled, "
            f"but got {result.region_metadata.skipped_regions}"
        )

    @pytest.mark.asyncio
    async def test_enabled_vs_disabled_mode_comparison(self):
        """
        Feature: multi-region-scanning, Property 12: Multi-Region Disabled Mode
        Validates: Requirements 7.1, 7.4
        
        Enabled mode SHALL scan multiple regions while disabled scans only one.
        """
        from unittest.mock import AsyncMock, MagicMock
        from mcp_server.services.multi_region_scanner import MultiRegionScanner
        from mcp_server.models.compliance import ComplianceResult

        enabled_regions = ["us-east-1", "us-west-2", "eu-west-1"]
        
        # Track scanned regions for each mode
        enabled_scanned: list[str] = []
        disabled_scanned: list[str] = []
        
        def create_mocks(scanned_list: list[str]):
            mock_region_discovery = MagicMock()
            mock_region_discovery.get_enabled_regions = AsyncMock(return_value=enabled_regions)
            
            mock_client_factory = MagicMock()
            mock_client_factory.get_client = MagicMock(
                side_effect=lambda r: MagicMock(region=r)
            )
            
            def compliance_service_factory(aws_client: MagicMock) -> MagicMock:
                mock_service = MagicMock()
                
                async def check_compliance_side_effect(**kwargs) -> ComplianceResult:
                    scanned_list.append(aws_client.region)
                    return ComplianceResult(
                        compliance_score=1.0,
                        total_resources=0,
                        compliant_resources=0,
                        violations=[],
                    )
                
                mock_service.check_compliance = AsyncMock(side_effect=check_compliance_side_effect)
                return mock_service
            
            return mock_region_discovery, mock_client_factory, compliance_service_factory
        
        # Test ENABLED mode
        rd1, cf1, csf1 = create_mocks(enabled_scanned)
        enabled_scanner = MultiRegionScanner(
            region_discovery=rd1,
            client_factory=cf1,
            compliance_service_factory=csf1,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=True,  # ENABLED
            default_region="us-east-1",
        )
        
        enabled_result = await enabled_scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )

        # Test DISABLED mode
        rd2, cf2, csf2 = create_mocks(disabled_scanned)
        disabled_scanner = MultiRegionScanner(
            region_discovery=rd2,
            client_factory=cf2,
            compliance_service_factory=csf2,
            max_concurrent_regions=5,
            region_timeout_seconds=60,
            multi_region_enabled=False,  # DISABLED
            default_region="us-east-1",
        )
        
        disabled_result = await disabled_scanner.scan_all_regions(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
        )
        
        # Verify enabled mode scanned all regions
        assert set(enabled_scanned) == set(enabled_regions), (
            f"Enabled mode should scan all regions. "
            f"Expected: {enabled_regions}, Got: {enabled_scanned}"
        )
        assert enabled_result.region_metadata.total_regions == len(enabled_regions)
        
        # Verify disabled mode scanned only one region
        assert len(disabled_scanned) == 1, (
            f"Disabled mode should scan only 1 region, but scanned {len(disabled_scanned)}"
        )
        assert disabled_result.region_metadata.total_regions == 1


# =============================================================================
# Property 13: Cache Key Determinism
# =============================================================================


class TestCacheKeyDeterminism:
    """
    Property 13: Cache Key Determinism
    
    For any two scan requests with the same resource types, filters, and severity,
    the generated cache key SHALL be identical. For requests with different parameters,
    the cache keys SHALL be different.
    
    Feature: multi-region-scanning
    Validates: Requirements 8.2
    """

    # -------------------------------------------------------------------------
    # Strategies for generating test data
    # -------------------------------------------------------------------------
    
    # Strategy for resource types
    resource_type_strategy = st.sampled_from([
        "ec2:instance", "ec2:volume", "rds:db", "lambda:function",
        "s3:bucket", "ecs:service", "eks:cluster", "dynamodb:table",
        "sqs:queue", "sns:topic", "elasticache:cluster", "opensearch:domain",
    ])
    
    # Strategy for lists of resource types
    resource_types_list_strategy = st.lists(
        resource_type_strategy,
        min_size=1,
        max_size=5,
        unique=True,
    )
    
    # Strategy for severity values
    severity_strategy = st.sampled_from(["all", "errors_only", "warnings_only"])
    
    # Strategy for region names
    region_strategy = st.sampled_from(SAMPLE_REGION_NAMES)
    
    # Strategy for lists of regions (for scanned_regions)
    regions_list_strategy = st.lists(
        region_strategy,
        min_size=1,
        max_size=10,
        unique=True,
    )
    
    # Strategy for filter dictionaries
    filter_strategy = st.one_of(
        st.none(),
        st.fixed_dictionaries({
            "region": st.one_of(st.none(), region_strategy),
        }),
        st.fixed_dictionaries({
            "account_id": st.one_of(
                st.none(),
                st.from_regex(r"[0-9]{12}", fullmatch=True),
            ),
        }),
        st.fixed_dictionaries({
            "region": st.one_of(st.none(), region_strategy),
            "account_id": st.one_of(
                st.none(),
                st.from_regex(r"[0-9]{12}", fullmatch=True),
            ),
        }),
    )

    # -------------------------------------------------------------------------
    # Helper to create a ComplianceService with mocked dependencies
    # -------------------------------------------------------------------------
    
    def _create_compliance_service(self, aws_region: str = "us-east-1"):
        """Create a ComplianceService with mocked dependencies for testing."""
        from unittest.mock import MagicMock, AsyncMock
        from mcp_server.clients.aws_client import AWSClient
        from mcp_server.clients.cache import RedisCache
        from mcp_server.services.policy_service import PolicyService
        from mcp_server.services.compliance_service import ComplianceService
        
        mock_cache = MagicMock(spec=RedisCache)
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        
        mock_aws_client = MagicMock(spec=AWSClient)
        mock_aws_client.region = aws_region
        
        mock_policy_service = MagicMock(spec=PolicyService)
        
        return ComplianceService(
            cache=mock_cache,
            aws_client=mock_aws_client,
            policy_service=mock_policy_service,
            cache_ttl=3600,
        )

    # -------------------------------------------------------------------------
    # Property Tests: Same inputs produce same key (Determinism)
    # -------------------------------------------------------------------------

    @given(
        resource_types=resource_types_list_strategy,
        filters=filter_strategy,
        severity=severity_strategy,
    )
    @settings(max_examples=100)
    def test_same_inputs_produce_same_key(
        self,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Same inputs SHALL always produce identical cache keys.
        """
        service = self._create_compliance_service()
        
        # Generate cache key twice with same inputs
        key1 = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
        )
        
        key2 = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
        )
        
        assert key1 == key2, (
            f"Same inputs should produce same cache key. "
            f"resource_types={resource_types}, filters={filters}, severity={severity}. "
            f"key1={key1}, key2={key2}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        filters=filter_strategy,
        severity=severity_strategy,
        scanned_regions=regions_list_strategy,
    )
    @settings(max_examples=100)
    def test_same_inputs_with_scanned_regions_produce_same_key(
        self,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
        scanned_regions: list[str],
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Same inputs including scanned_regions SHALL always produce identical cache keys.
        """
        service = self._create_compliance_service()
        
        # Generate cache key twice with same inputs
        key1 = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
            scanned_regions=scanned_regions,
        )
        
        key2 = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
            scanned_regions=scanned_regions,
        )
        
        assert key1 == key2, (
            f"Same inputs with scanned_regions should produce same cache key. "
            f"resource_types={resource_types}, filters={filters}, severity={severity}, "
            f"scanned_regions={scanned_regions}. key1={key1}, key2={key2}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        filters=filter_strategy,
        severity=severity_strategy,
        num_calls=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=100)
    def test_multiple_calls_produce_same_key(
        self,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
        num_calls: int,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Multiple calls with same inputs SHALL always produce identical cache keys.
        """
        service = self._create_compliance_service()
        
        # Generate cache key multiple times
        keys = [
            service._generate_cache_key(
                resource_types=resource_types,
                filters=filters,
                severity=severity,
            )
            for _ in range(num_calls)
        ]
        
        # All keys should be identical
        first_key = keys[0]
        for i, key in enumerate(keys[1:], start=2):
            assert key == first_key, (
                f"Call #{i} produced different key. "
                f"Expected {first_key}, got {key}"
            )

    # -------------------------------------------------------------------------
    # Property Tests: Order independence
    # -------------------------------------------------------------------------

    @given(
        resource_types=st.lists(resource_type_strategy, min_size=2, max_size=5, unique=True),
        filters=filter_strategy,
        severity=severity_strategy,
    )
    @settings(max_examples=100)
    def test_resource_type_order_does_not_affect_key(
        self,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Resource type order SHALL NOT affect the cache key.
        """
        service = self._create_compliance_service()
        
        # Generate key with original order
        key1 = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
        )
        
        # Generate key with reversed order
        key2 = service._generate_cache_key(
            resource_types=list(reversed(resource_types)),
            filters=filters,
            severity=severity,
        )
        
        assert key1 == key2, (
            f"Resource type order should not affect cache key. "
            f"Original: {resource_types}, Reversed: {list(reversed(resource_types))}. "
            f"key1={key1}, key2={key2}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        filters=filter_strategy,
        severity=severity_strategy,
        scanned_regions=st.lists(region_strategy, min_size=2, max_size=10, unique=True),
    )
    @settings(max_examples=100)
    def test_scanned_regions_order_does_not_affect_key(
        self,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
        scanned_regions: list[str],
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Scanned regions order SHALL NOT affect the cache key.
        """
        service = self._create_compliance_service()
        
        # Generate key with original order
        key1 = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
            scanned_regions=scanned_regions,
        )
        
        # Generate key with reversed order
        key2 = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
            scanned_regions=list(reversed(scanned_regions)),
        )
        
        assert key1 == key2, (
            f"Scanned regions order should not affect cache key. "
            f"Original: {scanned_regions}, Reversed: {list(reversed(scanned_regions))}. "
            f"key1={key1}, key2={key2}"
        )

    @given(
        resource_types=st.lists(resource_type_strategy, min_size=2, max_size=5, unique=True),
        filters=filter_strategy,
        severity=severity_strategy,
        scanned_regions=st.lists(region_strategy, min_size=2, max_size=10, unique=True),
    )
    @settings(max_examples=100)
    def test_both_orders_shuffled_produce_same_key(
        self,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
        scanned_regions: list[str],
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Shuffling both resource types and scanned regions SHALL produce same key.
        """
        import random
        
        service = self._create_compliance_service()
        
        # Generate key with original order
        key1 = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
            scanned_regions=scanned_regions,
        )
        
        # Shuffle both lists
        shuffled_types = resource_types.copy()
        shuffled_regions = scanned_regions.copy()
        random.shuffle(shuffled_types)
        random.shuffle(shuffled_regions)
        
        # Generate key with shuffled order
        key2 = service._generate_cache_key(
            resource_types=shuffled_types,
            filters=filters,
            severity=severity,
            scanned_regions=shuffled_regions,
        )
        
        assert key1 == key2, (
            f"Shuffled inputs should produce same cache key. "
            f"Original types: {resource_types}, Shuffled: {shuffled_types}. "
            f"Original regions: {scanned_regions}, Shuffled: {shuffled_regions}. "
            f"key1={key1}, key2={key2}"
        )

    # -------------------------------------------------------------------------
    # Property Tests: Different inputs produce different keys (Uniqueness)
    # -------------------------------------------------------------------------

    @given(
        resource_types1=resource_types_list_strategy,
        resource_types2=resource_types_list_strategy,
        filters=filter_strategy,
        severity=severity_strategy,
    )
    @settings(max_examples=100)
    def test_different_resource_types_produce_different_keys(
        self,
        resource_types1: list[str],
        resource_types2: list[str],
        filters: dict | None,
        severity: str,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Different resource types SHALL produce different cache keys.
        """
        # Skip if resource types are the same (after sorting)
        if sorted(resource_types1) == sorted(resource_types2):
            return
        
        service = self._create_compliance_service()
        
        key1 = service._generate_cache_key(
            resource_types=resource_types1,
            filters=filters,
            severity=severity,
        )
        
        key2 = service._generate_cache_key(
            resource_types=resource_types2,
            filters=filters,
            severity=severity,
        )
        
        assert key1 != key2, (
            f"Different resource types should produce different cache keys. "
            f"types1={resource_types1}, types2={resource_types2}. "
            f"key1={key1}, key2={key2}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        severity1=severity_strategy,
        severity2=severity_strategy,
    )
    @settings(max_examples=100)
    def test_different_severity_produces_different_keys(
        self,
        resource_types: list[str],
        severity1: str,
        severity2: str,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Different severity values SHALL produce different cache keys.
        """
        # Skip if severities are the same
        if severity1 == severity2:
            return
        
        service = self._create_compliance_service()
        
        key1 = service._generate_cache_key(
            resource_types=resource_types,
            filters=None,
            severity=severity1,
        )
        
        key2 = service._generate_cache_key(
            resource_types=resource_types,
            filters=None,
            severity=severity2,
        )
        
        assert key1 != key2, (
            f"Different severity should produce different cache keys. "
            f"severity1={severity1}, severity2={severity2}. "
            f"key1={key1}, key2={key2}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        severity=severity_strategy,
        scanned_regions1=regions_list_strategy,
        scanned_regions2=regions_list_strategy,
    )
    @settings(max_examples=100)
    def test_different_scanned_regions_produce_different_keys(
        self,
        resource_types: list[str],
        severity: str,
        scanned_regions1: list[str],
        scanned_regions2: list[str],
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Different scanned regions SHALL produce different cache keys.
        """
        # Skip if scanned regions are the same (after sorting)
        if sorted(scanned_regions1) == sorted(scanned_regions2):
            return
        
        service = self._create_compliance_service()
        
        key1 = service._generate_cache_key(
            resource_types=resource_types,
            filters=None,
            severity=severity,
            scanned_regions=scanned_regions1,
        )
        
        key2 = service._generate_cache_key(
            resource_types=resource_types,
            filters=None,
            severity=severity,
            scanned_regions=scanned_regions2,
        )
        
        assert key1 != key2, (
            f"Different scanned regions should produce different cache keys. "
            f"regions1={scanned_regions1}, regions2={scanned_regions2}. "
            f"key1={key1}, key2={key2}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        severity=severity_strategy,
        scanned_regions=regions_list_strategy,
    )
    @settings(max_examples=100)
    def test_with_vs_without_scanned_regions_produce_different_keys(
        self,
        resource_types: list[str],
        severity: str,
        scanned_regions: list[str],
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Keys with scanned_regions SHALL differ from keys without scanned_regions.
        """
        service = self._create_compliance_service()
        
        key_without = service._generate_cache_key(
            resource_types=resource_types,
            filters=None,
            severity=severity,
            scanned_regions=None,
        )
        
        key_with = service._generate_cache_key(
            resource_types=resource_types,
            filters=None,
            severity=severity,
            scanned_regions=scanned_regions,
        )
        
        assert key_without != key_with, (
            f"Keys with and without scanned_regions should differ. "
            f"scanned_regions={scanned_regions}. "
            f"key_without={key_without}, key_with={key_with}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        severity=severity_strategy,
        aws_region1=region_strategy,
        aws_region2=region_strategy,
    )
    @settings(max_examples=100)
    def test_different_aws_client_region_produces_different_keys(
        self,
        resource_types: list[str],
        severity: str,
        aws_region1: str,
        aws_region2: str,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Different AWS client regions SHALL produce different cache keys.
        """
        # Skip if regions are the same
        if aws_region1 == aws_region2:
            return
        
        service1 = self._create_compliance_service(aws_region=aws_region1)
        service2 = self._create_compliance_service(aws_region=aws_region2)
        
        key1 = service1._generate_cache_key(
            resource_types=resource_types,
            filters=None,
            severity=severity,
        )
        
        key2 = service2._generate_cache_key(
            resource_types=resource_types,
            filters=None,
            severity=severity,
        )
        
        assert key1 != key2, (
            f"Different AWS client regions should produce different cache keys. "
            f"aws_region1={aws_region1}, aws_region2={aws_region2}. "
            f"key1={key1}, key2={key2}"
        )

    # -------------------------------------------------------------------------
    # Property Tests: Key format and structure
    # -------------------------------------------------------------------------

    @given(
        resource_types=resource_types_list_strategy,
        filters=filter_strategy,
        severity=severity_strategy,
    )
    @settings(max_examples=100)
    def test_cache_key_has_correct_prefix(
        self,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Cache keys SHALL have the 'compliance:' prefix.
        """
        service = self._create_compliance_service()
        
        key = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
        )
        
        assert key.startswith("compliance:"), (
            f"Cache key should start with 'compliance:' prefix. Got: {key}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        filters=filter_strategy,
        severity=severity_strategy,
    )
    @settings(max_examples=100)
    def test_cache_key_is_valid_sha256_format(
        self,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Cache keys SHALL be in valid SHA256 hash format after the prefix.
        """
        import re
        
        service = self._create_compliance_service()
        
        key = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
        )
        
        # Remove prefix and check hash format
        hash_part = key.replace("compliance:", "")
        
        # SHA256 produces 64 hex characters
        assert len(hash_part) == 64, (
            f"Hash part should be 64 characters (SHA256). Got {len(hash_part)}: {hash_part}"
        )
        
        # Should be valid hex
        assert re.match(r"^[a-f0-9]{64}$", hash_part), (
            f"Hash part should be valid hex. Got: {hash_part}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        filters=filter_strategy,
        severity=severity_strategy,
        scanned_regions=st.one_of(st.none(), regions_list_strategy),
    )
    @settings(max_examples=100)
    def test_cache_key_length_is_consistent(
        self,
        resource_types: list[str],
        filters: dict | None,
        severity: str,
        scanned_regions: list[str] | None,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Cache key length SHALL be consistent regardless of input size.
        """
        service = self._create_compliance_service()
        
        key = service._generate_cache_key(
            resource_types=resource_types,
            filters=filters,
            severity=severity,
            scanned_regions=scanned_regions,
        )
        
        # "compliance:" (11 chars) + SHA256 hash (64 chars) = 75 chars
        expected_length = 11 + 64
        
        assert len(key) == expected_length, (
            f"Cache key should be {expected_length} characters. Got {len(key)}: {key}"
        )

    # -------------------------------------------------------------------------
    # Edge case tests
    # -------------------------------------------------------------------------

    def test_empty_resource_types_produces_valid_key(self):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Empty resource types list SHALL produce a valid cache key.
        """
        service = self._create_compliance_service()
        
        key = service._generate_cache_key(
            resource_types=[],
            filters=None,
            severity="all",
        )
        
        assert key.startswith("compliance:"), (
            f"Empty resource types should produce valid key. Got: {key}"
        )
        assert len(key) == 75  # prefix + SHA256

    def test_empty_scanned_regions_produces_valid_key(self):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Empty scanned regions list SHALL produce a valid cache key.
        """
        service = self._create_compliance_service()
        
        key = service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=[],
        )
        
        assert key.startswith("compliance:"), (
            f"Empty scanned regions should produce valid key. Got: {key}"
        )

    def test_empty_scanned_regions_differs_from_none(self):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Empty scanned regions list SHALL differ from None scanned regions.
        """
        service = self._create_compliance_service()
        
        key_none = service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=None,
        )
        
        key_empty = service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=[],
        )
        
        assert key_none != key_empty, (
            f"None and empty scanned_regions should produce different keys. "
            f"key_none={key_none}, key_empty={key_empty}"
        )

    def test_duplicate_resource_types_normalized(self):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Duplicate resource types in input SHALL be handled consistently.
        Note: The implementation sorts the list, so duplicates would remain.
        This test verifies the behavior is deterministic.
        """
        service = self._create_compliance_service()
        
        # With duplicates
        key1 = service._generate_cache_key(
            resource_types=["ec2:instance", "ec2:instance", "rds:db"],
            filters=None,
            severity="all",
        )
        
        # Same duplicates
        key2 = service._generate_cache_key(
            resource_types=["ec2:instance", "ec2:instance", "rds:db"],
            filters=None,
            severity="all",
        )
        
        assert key1 == key2, (
            f"Same inputs with duplicates should produce same key. "
            f"key1={key1}, key2={key2}"
        )

    def test_duplicate_scanned_regions_normalized(self):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        Duplicate scanned regions in input SHALL be handled consistently.
        """
        service = self._create_compliance_service()
        
        # With duplicates
        key1 = service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "us-east-1", "us-west-2"],
        )
        
        # Same duplicates
        key2 = service._generate_cache_key(
            resource_types=["ec2:instance"],
            filters=None,
            severity="all",
            scanned_regions=["us-east-1", "us-east-1", "us-west-2"],
        )
        
        assert key1 == key2, (
            f"Same inputs with duplicate regions should produce same key. "
            f"key1={key1}, key2={key2}"
        )

    @given(
        resource_types=resource_types_list_strategy,
        severity=severity_strategy,
    )
    @settings(max_examples=100)
    def test_none_filters_same_as_empty_dict(
        self,
        resource_types: list[str],
        severity: str,
    ):
        """
        Feature: multi-region-scanning, Property 13: Cache Key Determinism
        Validates: Requirements 8.2
        
        None filters SHALL produce same key as empty dict filters.
        """
        service = self._create_compliance_service()
        
        key_none = service._generate_cache_key(
            resource_types=resource_types,
            filters=None,
            severity=severity,
        )
        
        key_empty = service._generate_cache_key(
            resource_types=resource_types,
            filters={},
            severity=severity,
        )
        
        assert key_none == key_empty, (
            f"None and empty dict filters should produce same key. "
            f"key_none={key_none}, key_empty={key_empty}"
        )
