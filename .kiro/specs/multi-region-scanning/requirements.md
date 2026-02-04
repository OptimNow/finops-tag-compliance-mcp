# Requirements Document

## Introduction

This feature enables the FinOps Tag Compliance MCP Server to scan AWS resources across ALL enabled regions in an AWS account, rather than being limited to a single configured region. Currently, the server only scans resources in the region specified by the `AWS_REGION` environment variable (defaulting to `us-east-1`). Users need complete visibility into tag compliance across their entire AWS footprint to accurately assess compliance posture and cost attribution gaps.

Regional AWS services (EC2, RDS, Lambda, ECS, OpenSearch) require separate API calls per region. This feature implements parallel multi-region scanning with proper error handling for disabled regions, empty results, and rate limiting considerations.

## Glossary

- **Multi_Region_Scanner**: The component responsible for orchestrating resource scanning across multiple AWS regions in parallel
- **Region_Discovery_Service**: The component that discovers all enabled AWS regions for the account
- **Regional_Client_Factory**: The component that creates and manages AWS clients for different regions
- **Aggregated_Result**: A compliance result that combines resources and violations from all scanned regions
- **Disabled_Region**: An AWS region that has been opted-out in the account settings and cannot be accessed
- **Regional_Resource**: An AWS resource that exists in a specific region (e.g., EC2 instances, RDS databases)
- **Global_Resource**: An AWS resource that is not region-specific (e.g., S3 buckets, IAM roles)

## Requirements

### Requirement 1: Discover Enabled AWS Regions

**User Story:** As a FinOps engineer, I want the system to automatically discover all enabled AWS regions in my account, so that I don't have to manually configure which regions to scan.

#### Acceptance Criteria

1. WHEN the system initializes a multi-region scan, THE Region_Discovery_Service SHALL call the EC2 DescribeRegions API to retrieve all enabled regions
2. WHEN a region is disabled in the account, THE Region_Discovery_Service SHALL exclude it from the list of scannable regions
3. WHEN the region discovery fails, THE Multi_Region_Scanner SHALL fall back to scanning only the configured default region
4. THE Region_Discovery_Service SHALL cache the list of enabled regions for a configurable TTL to minimize API calls

### Requirement 2: Create Regional AWS Clients

**User Story:** As a system architect, I want the system to efficiently manage AWS clients for multiple regions, so that resources can be scanned without excessive client instantiation overhead.

#### Acceptance Criteria

1. WHEN a multi-region scan is requested, THE Regional_Client_Factory SHALL create AWS clients for each enabled region
2. THE Regional_Client_Factory SHALL reuse existing clients for regions that have already been initialized within the same session
3. WHEN creating a regional client, THE Regional_Client_Factory SHALL apply the same boto3 configuration (retries, timeouts) as the default client
4. THE Regional_Client_Factory SHALL use IAM instance profile credentials that work across all regions

### Requirement 3: Scan Resources Across All Regions

**User Story:** As a FinOps engineer, I want to scan EC2 instances and other regional resources across all AWS regions, so that I get a complete picture of tag compliance.

#### Acceptance Criteria

1. WHEN `check_tag_compliance` is called with regional resource types, THE Multi_Region_Scanner SHALL scan resources in all enabled regions
2. WHEN scanning multiple regions, THE Multi_Region_Scanner SHALL execute region scans in parallel to minimize total scan time
3. WHEN a region returns zero resources, THE Multi_Region_Scanner SHALL treat this as a successful empty result, not an error
4. WHEN a region scan fails due to a transient error, THE Multi_Region_Scanner SHALL retry with exponential backoff before marking the region as failed
5. IF a region scan fails after retries, THEN THE Multi_Region_Scanner SHALL continue scanning other regions and include the failure in the result metadata

### Requirement 4: Aggregate Multi-Region Results

**User Story:** As a FinOps engineer, I want compliance results aggregated across all regions, so that I can see my overall compliance posture in a single view.

#### Acceptance Criteria

1. WHEN multi-region scanning completes, THE Multi_Region_Scanner SHALL aggregate all resources into a single Aggregated_Result
2. THE Aggregated_Result SHALL include the region attribute for each resource to identify where it resides
3. THE Aggregated_Result SHALL calculate a single compliance score across all regions
4. THE Aggregated_Result SHALL sum cost attribution gaps from all regions
5. WHEN some regions fail to scan, THE Aggregated_Result SHALL include metadata indicating which regions were successfully scanned and which failed

### Requirement 5: Handle Global Resources Correctly

**User Story:** As a FinOps engineer, I want global resources like S3 buckets to be scanned only once, so that they are not duplicated in multi-region results.

#### Acceptance Criteria

1. WHEN scanning S3 buckets, THE Multi_Region_Scanner SHALL fetch them only once since they are global resources
2. THE Multi_Region_Scanner SHALL identify global resource types and exclude them from per-region scanning
3. WHEN aggregating results, THE Multi_Region_Scanner SHALL ensure global resources appear exactly once in the Aggregated_Result

### Requirement 6: Support Region Filtering

**User Story:** As a FinOps engineer, I want to optionally filter scans to specific regions, so that I can focus on particular geographic areas when needed.

#### Acceptance Criteria

1. WHEN a region filter is provided in the request, THE Multi_Region_Scanner SHALL scan only the specified regions
2. WHEN multiple regions are specified in the filter, THE Multi_Region_Scanner SHALL scan all specified regions in parallel
3. WHEN a filtered region is disabled or invalid, THE Multi_Region_Scanner SHALL return an error indicating the invalid region
4. WHEN no region filter is provided, THE Multi_Region_Scanner SHALL scan all enabled regions by default

### Requirement 7: Configure Multi-Region Scanning Behavior

**User Story:** As a system administrator, I want to configure multi-region scanning behavior, so that I can control parallelism and timeouts based on my environment.

#### Acceptance Criteria

1. THE system SHALL support a `MULTI_REGION_ENABLED` configuration to enable or disable multi-region scanning
2. THE system SHALL support a `MAX_CONCURRENT_REGIONS` configuration to limit parallel region scans (default: 5)
3. THE system SHALL support a `REGION_SCAN_TIMEOUT_SECONDS` configuration for per-region timeout (default: 60)
4. WHEN multi-region scanning is disabled, THE Multi_Region_Scanner SHALL scan only the default configured region

### Requirement 8: Cache Multi-Region Results

**User Story:** As a FinOps engineer, I want multi-region scan results to be cached, so that repeated queries don't incur excessive API costs.

#### Acceptance Criteria

1. WHEN a multi-region scan completes, THE system SHALL cache the Aggregated_Result with a configurable TTL
2. THE cache key SHALL include the list of scanned regions to differentiate full scans from filtered scans
3. WHEN `force_refresh=True` is specified, THE system SHALL bypass the cache and perform a fresh multi-region scan
4. WHEN the cache is invalidated, THE system SHALL clear cached results for all region combinations
