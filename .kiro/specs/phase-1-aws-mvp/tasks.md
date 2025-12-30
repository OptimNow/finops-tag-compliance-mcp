# Implementation Plan: Phase 1 - AWS Tag Compliance MVP

## Overview

This plan breaks down the Phase 1 MVP into discrete, incremental tasks. Each task builds on the previous ones, ensuring we always have working code that can be tested. The implementation uses Python 3.11 with FastAPI for the MCP server, boto3 for AWS integration, and Hypothesis for property-based testing.

For detailed code examples and infrastructure setup, see [PHASE-1-SPECIFICATION.md](../../../PHASE-1-SPECIFICATION.md).

## Tasks

- [ ] 1. Project Setup and Core Infrastructure
  - [x] 1.1 Initialize Python project structure with pyproject.toml and dependencies `[Haiku]`
    - Create project directory structure (mcp_server/, tests/, policies/)
    - Set up pyproject.toml with dependencies: fastapi, uvicorn, boto3, redis, pydantic, hypothesis
    - Create requirements.txt for Docker compatibility
    - _Requirements: 14.1, 14.2_

  - [x] 1.2 Create core data models using Pydantic `[Sonnet]`
    - Implement Violation, ComplianceResult, TagSuggestion, TagPolicy models
    - Implement ViolationType and Severity enums
    - Add model validation and serialization
    - _Requirements: 1.2, 3.2, 3.3_

  - [x] 1.3 Write property tests for data models `[Opus]`

    - **Property 2: Violation Detail Completeness**
    - **Validates: Requirements 1.2, 3.2, 3.3, 3.4**

  - [x] 1.4 Create Dockerfile and docker-compose.yml `[Haiku]`
    - Dockerfile with Python 3.11-slim base
    - docker-compose.yml with MCP server and Redis services
    - Environment variable configuration
    - _Requirements: 14.1, 14.3_

  - [x] 1.5 Set up test infrastructure and regression test runner `[Haiku]`
    - Configure pytest with pytest.ini or pyproject.toml
    - Create tests/ directory structure (tests/unit/, tests/property/, tests/integration/)
    - Add test runner script that executes full regression suite
    - Configure test coverage reporting (target: 80%)
    - _Requirements: Testing Strategy_

- [ ] 2. Tagging Policy Engine
  - [x] 2.1 Implement PolicyService to load and manage tagging policies `[Sonnet]`
    - Load policy from JSON file
    - Validate policy structure on load
    - Provide policy retrieval interface
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 9.1_

  - [x] 2.2 Write property tests for policy loading `[Opus]`

    - **Property 7: Policy Structure Completeness**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

  - [x] 2.3 Implement tag validation logic `[Sonnet]`
    - Check required tag presence
    - Validate against allowed values list
    - Validate against regex patterns
    - Apply rules only to applicable resource types
    - _Requirements: 9.2, 9.3, 9.4, 9.5_

  - [x] 2.4 Write property tests for tag validation `[Opus]`

    - **Property 10: Policy Validation Correctness**
    - **Validates: Requirements 9.2, 9.3, 9.4, 9.5**

  - [x] 2.5 Create sample tagging policy JSON file `[Haiku]`
    - Include required tags: CostCenter, Owner, Environment, Application
    - Include optional tags: Project, Compliance
    - Define tag naming rules
    - _Requirements: 6.1_

- [x] 3. Checkpoint - Policy Engine Complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. AWS Integration Layer
  - [x] 4.1 Implement AWSClient wrapper for boto3 `[Sonnet]`
    - Create clients for EC2, RDS, S3, Lambda, ECS, Cost Explorer
    - Use IAM instance profile for authentication (no hardcoded credentials)
    - Implement rate limiting and backoff
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 4.2 Implement resource fetching methods `[Sonnet]`
    - get_ec2_instances() with tag extraction
    - get_rds_instances() with tag extraction
    - get_s3_buckets() with tag extraction
    - get_lambda_functions() with tag extraction
    - get_ecs_services() with tag extraction
    - _Requirements: 10.2_

  - [x] 4.3 Implement cost data retrieval from Cost Explorer `[Sonnet]`
    - get_cost_data() for resource cost lookup
    - Support time period filtering
    - _Requirements: 10.3, 4.4_

  - [x] 4.4 Write unit tests for AWS client (using moto mocks) `[Haiku]`

    - Test resource fetching with various tag states
    - Test cost data retrieval
    - Test error handling for API failures
    - _Requirements: 10.2, 10.3_

- [ ] 5. Caching Layer
  - [x] 5.1 Implement Redis cache wrapper `[Haiku]`
    - Connect to Redis with configurable URL
    - Implement get/set with TTL
    - Handle connection failures gracefully
    - _Requirements: 11.1, 10.5_

  - [x] 5.2 Implement violation caching logic `[Sonnet]`
    - Cache compliance results by query parameters
    - Implement cache invalidation on new scans
    - Fall back to direct API calls on cache miss
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 5.3 Write property tests for cache behavior `[Opus]`

    - **Property 11: Cache Behavior**
    - **Validates: Requirements 11.1, 11.3**

- [x] 6. Checkpoint - Infrastructure Complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Core Compliance Service
  - [x] 7.1 Implement ComplianceService `[Sonnet]`
    - Orchestrate resource scanning across resource types
    - Apply policy validation to each resource
    - Calculate compliance score
    - Aggregate violations
    - _Requirements: 1.1, 1.2_

  - [x] 7.2 Write property tests for compliance scoring `[Opus]`

    - **Property 1: Compliance Score Bounds**
    - **Validates: Requirements 1.1**

  - [x] 7.3 Implement filtering logic `[Sonnet]`
    - Filter by region
    - Filter by account
    - Filter by severity
    - Filter by resource type
    - _Requirements: 1.3, 1.4_

  - [x] 7.4 Write property tests for filtering `[Opus]`

    - **Property 3: Filter Consistency**
    - **Validates: Requirements 1.3, 1.4, 2.3, 2.4**

- [-] 8. MCP Tool: check_tag_compliance
  - [x] 8.1 Implement check_tag_compliance tool `[Sonnet]`
    - Accept resource_types, filters, severity parameters
    - Call ComplianceService
    - Return ComplianceResult
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 8.2 Write integration tests for check_tag_compliance `[Haiku]`

    - Test with various filter combinations
    - Test performance with 1000 resources
    - _Requirements: 1.5_

- [ ] 9. MCP Tool: find_untagged_resources
  - [x] 9.1 Implement find_untagged_resources tool `[Sonnet]`
    - Find resources with no tags or missing required tags
    - Include cost estimates
    - Support cost threshold filtering
    - Include resource age
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 9.2 Write property tests for untagged resource discovery `[Opus]`

    - **Property 4: Resource Metadata Completeness**
    - **Validates: Requirements 2.1, 2.2, 2.5**

- [ ] 10. MCP Tool: validate_resource_tags
  - [x] 10.1 Implement validate_resource_tags tool `[Sonnet]`
    - Accept list of resource ARNs
    - Validate each against policy
    - Return detailed violation information
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 10.2 Write unit tests for resource validation `[Haiku]`

    - Test missing tags detection
    - Test invalid value detection
    - Test regex validation
    - _Requirements: 3.2, 3.3_

- [x] 11. Checkpoint - Core Tools Complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Cost Attribution Service
  - [x] 12.1 Implement CostService `[Sonnet]`
    - Calculate total cloud spend
    - Calculate attributable spend (tagged resources)
    - Calculate attribution gap
    - Support grouping by resource type, region, account
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 12.2 Write property tests for cost calculations `[Opus]`

    - **Property 5: Cost Attribution Calculation**
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [ ] 13. MCP Tool: get_cost_attribution_gap
  - [x] 13.1 Implement get_cost_attribution_gap tool `[Sonnet]`
    - Accept time_period and grouping parameters
    - Call CostService
    - Return gap analysis with breakdown
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x] 13.2 Write unit tests for cost attribution tool `[Haiku]`

    - Test with various grouping options
    - Test time period filtering
    - _Requirements: 4.3, 4.5_

- [-] 14. Tag Suggestion Service
  - [x] 14.1 Implement SuggestionService `[Opus]`
    - Analyze VPC/subnet naming patterns
    - Analyze IAM user/role patterns
    - Find similar tagged resources
    - Calculate confidence scores
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 14.2 Write property tests for suggestions `[Opus]`

    - **Property 6: Suggestion Quality**
    - **Validates: Requirements 5.1, 5.2, 5.3**

- [ ] 15. MCP Tool: suggest_tags
  - [x] 15.1 Implement suggest_tags tool `[Opus]`
    - Accept resource ARN
    - Call SuggestionService
    - Return suggestions with confidence and reasoning
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 15.2 Write unit tests for suggestion tool `[Haiku]`

    - Test suggestion generation
    - Test confidence scoring
    - _Requirements: 5.2_

- [ ] 16. MCP Tool: get_tagging_policy
  - [x] 16.1 Implement get_tagging_policy tool `[Sonnet]`
    - Return complete policy configuration
    - Include required and optional tags
    - Include naming rules
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 16.2 Write unit tests for policy retrieval `[Haiku]`

    - Test complete policy structure
    - _Requirements: 6.1_

- [x] 17. Checkpoint - All Query Tools Complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 18. Report Generation Service
  - [x] 18.1 Implement ReportService `[Sonnet]`
    - Generate compliance summary
    - Rank violations by count and cost
    - Generate recommendations
    - Support JSON, CSV, Markdown output
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 18.2 Write property tests for reports `[Opus]`

    - **Property 8: Report Content Completeness**
    - **Validates: Requirements 7.1, 7.3, 7.4, 7.5**

- [ ] 19. MCP Tool: generate_compliance_report
  - [x] 19.1 Implement generate_compliance_report tool `[Sonnet]`
    - Accept format and include_recommendations parameters
    - Call ReportService
    - Return formatted report
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 19.2 Write unit tests for report generation `[Haiku]`


    - Test each output format
    - Test recommendation inclusion
    - _Requirements: 7.2, 7.3_

- [ ] 20. History Tracking Service
  - [x] 20.1 Implement HistoryService with SQLite storage `[Sonnet]`
    - Store compliance scan results
    - Query historical data by time range
    - Group by day/week/month
    - Calculate trend direction
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 20.2 Write property tests for history tracking `[Opus]`

    - **Property 9: History Tracking Correctness**
    - **Validates: Requirements 8.1, 8.2, 8.3**

- [ ] 21. MCP Tool: get_violation_history
  - [x] 21.1 Implement get_violation_history tool `[Sonnet]`
    - Accept days_back and group_by parameters
    - Call HistoryService
    - Return history with trend analysis
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 21.2 Write unit tests for history tool `[Haiku]`

    - Test grouping options
    - Test trend calculation
    - _Requirements: 8.2, 8.3_

- [x] 22. Checkpoint - All 8 Tools Complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 23. Audit Logging
  - [x] 23.1 Implement audit logging middleware `[Sonnet]`
    - Log every tool invocation
    - Include timestamp, tool name, parameters
    - Include result status and errors
    - Store in SQLite
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [x] 23.2 Write property tests for audit logging `[Opus]`

    - **Property 12: Audit Log Completeness**
    - **Validates: Requirements 12.1, 12.3, 12.4**

- [ ] 24. Health Check and Monitoring
  - [x] 24.1 Implement health check endpoint `[Haiku]`
    - Expose /health endpoint
    - Return status, version, cloud providers
    - Check Redis and SQLite connectivity
    - _Requirements: 13.1, 13.2_

  - [x] 24.2 Write property tests for health endpoint `[Opus]`

    - **Property 13: Health Response Completeness**
    - **Validates: Requirements 13.2**

  - [x] 24.3 Implement CloudWatch logging integration `[Haiku]`
    - Configure structured logging
    - Send logs to CloudWatch
    - _Requirements: 13.3_

- [x] 25. MCP Server Integration
  - [x] 25.1 Create FastAPI application with MCP protocol handler `[Sonnet]`
    - Register all 8 tools
    - Configure CORS and middleware
    - Set up error handling
    - _Requirements: 14.5_

  - [x] 25.2 Create main entry point and configuration `[Sonnet]`
    - Load environment variables
    - Initialize services
    - Start server on port 8080
    - _Requirements: 14.2, 14.5_

  - [x] 25.3 Write end-to-end integration tests `[Opus]`

    - Test MCP protocol communication
    - Test tool invocation flow
    - _Requirements: 14.5_

- [x] 26. Final Checkpoint - MVP Complete
  - Run full regression test suite (`pytest tests/` - all unit, property, and integration tests)
  - Ensure all tests pass, ask the user if questions arise.
  - Verify Docker container builds and runs
  - Verify all 8 tools respond correctly
  - Run load test with 1000 resources

- [ ] 26.1 Docker Build Verification `[Haiku]`
  - Start Docker Desktop on local machine
  - Run `docker build -t finops-tag-compliance-mcp:test .`
  - Verify image builds successfully
  - Run `docker-compose up -d` to start services
  - Test health endpoint at http://localhost:8080/health
  - Verify Redis container is running and healthy
  - _Requirements: 14.1, 14.3_

- [ ] 27. AWS Infrastructure Provisioning
  - [ ] 27.1 Deploy CloudFormation stack `[Haiku]`
    - Deploy infrastructure/cloudformation.yaml
    - Provision EC2 instance (t3.medium), IAM role, security group
    - Wait for stack creation to complete
    - _Requirements: 14.1, 14.4, 10.1_

  - [ ] 27.2 Configure EC2 instance `[Haiku]`
    - SSH into instance and verify Docker is installed
    - Clone repository to /opt/finops-mcp
    - Create .env file with production settings
    - _Requirements: 14.2_

  - [ ] 27.3 Deploy application to EC2 `[Haiku]`
    - Run docker-compose up -d
    - Verify containers are running
    - Test health endpoint responds
    - _Requirements: 14.1, 14.5_

- [ ] 28. Production Verification
  - [ ] 28.1 Verify MCP server is accessible `[Haiku]`
    - Test health endpoint from external IP
    - Verify IAM role can access AWS resources
    - Test one compliance check against real resources
    - _Requirements: 13.1, 10.1_

  - [ ] 28.2 Configure Claude Desktop connection `[Haiku]`
    - Add MCP server to Claude Desktop config
    - Test tool invocation through Claude
    - _Requirements: 14.5_

- [ ] 29. Deployment Complete Checkpoint
  - Verify server runs stable for 1 hour
  - Document any issues encountered
  - Confirm all 8 tools work against real AWS resources

- [ ] 30. User Acceptance Testing (UAT)
  - [ ] 30.1 Execute UAT protocol
    - Follow test scenarios in UAT_PROTOCOL.md
    - Test all 8 MCP tools through Claude Desktop
    - Validate business value for each feature
    - Document results in UAT checklist
    - _Requirements: All user stories (1-8)_

  - [ ] 30.2 UAT Sign-off
    - Review all test results
    - Document any issues or feedback
    - Confirm MVP meets business requirements
    - Sign off on Phase 1 completion

## Notes

- Tasks marked with `*` are optional test tasks that can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation throughout development
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- **Model tags**: `[Haiku]` for boilerplate/simple tasks, `[Sonnet]` for business logic, `[Opus]` for complex reasoning/property tests
- **Regression testing**: Run `pytest tests/` at any checkpoint to execute the full test suite
