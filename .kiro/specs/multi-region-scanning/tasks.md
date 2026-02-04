# Implementation Plan: Multi-Region Scanning

## Overview

This implementation plan adds multi-region scanning capability to the FinOps Tag Compliance MCP Server. The implementation follows a bottom-up approach: first building the foundational components (data models, region discovery, client factory), then the orchestration layer (multi-region scanner), and finally integrating with existing tools.

## Tasks

- [x] 1. Add multi-region data models and configuration
  - [x] 1.1 Create multi-region data models in `mcp_server/models/multi_region.py`
    - Add `RegionalScanResult`, `RegionScanMetadata`, `MultiRegionComplianceResult`, `RegionalSummary` Pydantic models
    - Add `GLOBAL_RESOURCE_TYPES` and `REGIONAL_RESOURCE_TYPES` constants
    - _Requirements: 4.1, 4.2, 4.5, 5.2_
  
  - [x] 1.2 Add multi-region configuration to `mcp_server/config.py`
    - Add `MULTI_REGION_ENABLED`, `MAX_CONCURRENT_REGIONS`, `REGION_SCAN_TIMEOUT_SECONDS`, `REGION_CACHE_TTL_SECONDS` settings
    - _Requirements: 7.1, 7.2, 7.3_
  
  - [x] 1.3 Write property test for global resource type identification
    - **Property 9: Global Resource Type Identification**
    - **Validates: Requirements 5.2**

- [x] 2. Implement RegionDiscoveryService
  - [x] 2.1 Create `mcp_server/services/region_discovery_service.py`
    - Implement `get_enabled_regions()` using EC2 DescribeRegions API
    - Implement region filtering by opt-in status
    - Implement caching with configurable TTL
    - Implement fallback to default region on failure
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  
  - [x] 2.2 Write property test for region filtering by opt-in status
    - **Property 1: Region Filtering by Opt-In Status**
    - **Validates: Requirements 1.2**
  
  - [x] 2.3 Write unit tests for RegionDiscoveryService
    - Test caching behavior
    - Test fallback on API failure
    - _Requirements: 1.3, 1.4_

- [x] 3. Implement RegionalClientFactory
  - [x] 3.1 Create `mcp_server/clients/regional_client_factory.py`
    - Implement `get_client(region)` method
    - Implement client caching/reuse within session
    - Apply consistent boto3 configuration across all clients
    - _Requirements: 2.1, 2.2, 2.3_
  
  - [x] 3.2 Write property test for client reuse idempotence
    - **Property 2: Client Reuse Idempotence**
    - **Validates: Requirements 2.2**
  
  - [x] 3.3 Write unit tests for RegionalClientFactory
    - Test client creation
    - Test configuration consistency
    - _Requirements: 2.3_

- [x] 4. Checkpoint - Ensure foundational components work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement MultiRegionScanner
  - [x] 5.1 Create `mcp_server/services/multi_region_scanner.py`
    - Implement `scan_all_regions()` with parallel execution using asyncio
    - Implement `_scan_region()` with retry logic
    - Implement `_aggregate_results()` for combining regional results
    - Implement `_is_global_resource_type()` for global resource handling
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3_
  
  - [x] 5.2 Write property test for all enabled regions are scanned
    - **Property 3: All Enabled Regions Are Scanned**
    - **Validates: Requirements 2.1, 3.1, 6.4**
  
  - [x] 5.3 Write property test for empty results are successful
    - **Property 4: Empty Results Are Successful**
    - **Validates: Requirements 3.3**
  
  - [x] 5.4 Write property test for partial failures don't stop scanning
    - **Property 5: Partial Failures Don't Stop Scanning**
    - **Validates: Requirements 3.5, 4.5**
  
  - [x] 5.5 Write property test for resource aggregation preserves region
    - **Property 6: Resource Aggregation Preserves Region**
    - **Validates: Requirements 4.1, 4.2**
  
  - [x] 5.6 Write property test for compliance score calculation
    - **Property 7: Compliance Score Calculation**
    - **Validates: Requirements 4.3**
  
  - [x] 5.7 Write property test for cost gap summation
    - **Property 8: Cost Gap Summation**
    - **Validates: Requirements 4.4**
  
  - [x] 5.8 Write property test for global resources appear exactly once
    - **Property 10: Global Resources Appear Exactly Once**
    - **Validates: Requirements 5.1, 5.3**

- [x] 6. Implement region filtering and disabled mode
  - [x] 6.1 Add region filter support to MultiRegionScanner
    - Implement filtering to scan only specified regions
    - Validate filtered regions against enabled regions
    - Return error for invalid/disabled regions in filter
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  
  - [x] 6.2 Add disabled mode support to MultiRegionScanner
    - When `MULTI_REGION_ENABLED=False`, scan only default region
    - _Requirements: 7.1, 7.4_
  
  - [x] 6.3 Write property test for region filter application
    - **Property 11: Region Filter Application**
    - **Validates: Requirements 6.1**
  
  - [x] 6.4 Write property test for multi-region disabled mode
    - **Property 12: Multi-Region Disabled Mode**
    - **Validates: Requirements 7.1, 7.4**

- [x] 7. Checkpoint - Ensure multi-region scanner works
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Update caching for multi-region results
  - [x] 8.1 Update cache key generation in ComplianceService
    - Include scanned regions in cache key
    - Ensure deterministic key generation
    - _Requirements: 8.1, 8.2_
  
  - [x] 8.2 Write property test for cache key determinism
    - **Property 13: Cache Key Determinism**
    - **Validates: Requirements 8.2**
  
  - [x] 8.3 Write unit tests for cache behavior
    - Test cache hit/miss with multi-region results
    - Test force_refresh bypass
    - Test cache invalidation
    - _Requirements: 8.1, 8.3, 8.4_

- [x] 9. Integrate multi-region scanning with existing tools
  - [x] 9.1 Update `check_tag_compliance` tool to use MultiRegionScanner
    - Inject MultiRegionScanner dependency
    - Route regional resource types through multi-region scanner
    - Preserve backward compatibility for single-region mode
    - _Requirements: 3.1, 7.4_
  
  - [x] 9.2 Update `find_untagged_resources` tool for multi-region support
    - Use MultiRegionScanner for regional resource discovery
    - _Requirements: 3.1_
  
  - [x] 9.3 Update `validate_resource_tags` tool for multi-region support
    - Support ARNs from any region
    - _Requirements: 3.1_
  
  - [x] 9.4 Write integration tests for multi-region tool flows
    - Test check_tag_compliance with multi-region
    - Test find_untagged_resources with multi-region
    - Test partial failure handling
    - _Requirements: 3.1, 3.5_

- [x] 10. Final checkpoint - Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tasks including tests are required for comprehensive coverage
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- The implementation follows the project's existing patterns (services, models, tools separation)
- All new code should use async/await for I/O operations
- Use Hypothesis for property-based testing with minimum 100 iterations
