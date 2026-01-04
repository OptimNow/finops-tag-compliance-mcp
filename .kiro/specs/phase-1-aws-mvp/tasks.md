# Implementation Plan: Phase 1 - AWS Tag Compliance MVP

## Overview

This plan breaks down the Phase 1 MVP into discrete, incremental tasks. Each task builds on the previous ones, ensuring we always have working code that can be tested. The implementation uses Python 3.11 with FastAPI for the MCP server, boto3 for AWS integration, and Hypothesis for property-based testing.

For detailed code examples and infrastructure setup, see [PHASE-1-SPECIFICATION.md](../../../docs/PHASE-1-SPECIFICATION.md).

## Tasks

- [x] 1. Project Setup and Core Infrastructure
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

- [x] 2. Tagging Policy Engine
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

- [x] 5. Caching Layer
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

- [x] 7. Core Compliance Service
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

- [x] 8. MCP Tool: check_tag_compliance
  - [x] 8.1 Implement check_tag_compliance tool `[Sonnet]`
    - Accept resource_types, filters, severity parameters
    - Call ComplianceService
    - Return ComplianceResult
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 8.2 Write integration tests for check_tag_compliance `[Haiku]`

    - Test with various filter combinations
    - Test performance with 1000 resources
    - _Requirements: 1.5_

- [x] 9. MCP Tool: find_untagged_resources
  - [x] 9.1 Implement find_untagged_resources tool `[Sonnet]`
    - Find resources with no tags or missing required tags
    - Include cost estimates
    - Support cost threshold filtering
    - Include resource age
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 9.2 Write property tests for untagged resource discovery `[Opus]`

    - **Property 4: Resource Metadata Completeness**
    - **Validates: Requirements 2.1, 2.2, 2.5**

- [x] 10. MCP Tool: validate_resource_tags
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

- [x] 12. Cost Attribution Service
  - [x] 12.1 Implement CostService `[Sonnet]`
    - Calculate total cloud spend
    - Calculate attributable spend (tagged resources)
    - Calculate attribution gap
    - Support grouping by resource type, region, account
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 12.2 Write property tests for cost calculations `[Opus]`

    - **Property 5: Cost Attribution Calculation**
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 13. MCP Tool: get_cost_attribution_gap
  - [x] 13.1 Implement get_cost_attribution_gap tool `[Sonnet]`
    - Accept time_period and grouping parameters
    - Call CostService
    - Return gap analysis with breakdown
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x] 13.2 Write unit tests for cost attribution tool `[Haiku]`

    - Test with various grouping options
    - Test time period filtering
    - _Requirements: 4.3, 4.5_

- [x] 14. Tag Suggestion Service
  - [x] 14.1 Implement SuggestionService `[Opus]`
    - Analyze VPC/subnet naming patterns
    - Analyze IAM user/role patterns
    - Find similar tagged resources
    - Calculate confidence scores
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 14.2 Write property tests for suggestions `[Opus]`

    - **Property 6: Suggestion Quality**
    - **Validates: Requirements 5.1, 5.2, 5.3**

- [x] 15. MCP Tool: suggest_tags
  - [x] 15.1 Implement suggest_tags tool `[Opus]`
    - Accept resource ARN
    - Call SuggestionService
    - Return suggestions with confidence and reasoning
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 15.2 Write unit tests for suggestion tool `[Haiku]`

    - Test suggestion generation
    - Test confidence scoring
    - _Requirements: 5.2_

- [x] 16. MCP Tool: get_tagging_policy
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

- [x] 18. Report Generation Service
  - [x] 18.1 Implement ReportService `[Sonnet]`
    - Generate compliance summary
    - Rank violations by count and cost
    - Generate recommendations
    - Support JSON, CSV, Markdown output
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 18.2 Write property tests for reports `[Opus]`

    - **Property 8: Report Content Completeness**
    - **Validates: Requirements 7.1, 7.3, 7.4, 7.5**

- [x] 19. MCP Tool: generate_compliance_report
  - [x] 19.1 Implement generate_compliance_report tool `[Sonnet]`
    - Accept format and include_recommendations parameters
    - Call ReportService
    - Return formatted report
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 19.2 Write unit tests for report generation `[Haiku]`


    - Test each output format
    - Test recommendation inclusion
    - _Requirements: 7.2, 7.3_

- [x] 20. History Tracking Service
  - [x] 20.1 Implement HistoryService with SQLite storage `[Sonnet]`
    - Store compliance scan results
    - Query historical data by time range
    - Group by day/week/month
    - Calculate trend direction
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 20.2 Write property tests for history tracking `[Opus]`

    - **Property 9: History Tracking Correctness**
    - **Validates: Requirements 8.1, 8.2, 8.3**

- [x] 21. MCP Tool: get_violation_history
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

- [x] 23. Audit Logging
  - [x] 23.1 Implement audit logging middleware `[Sonnet]`
    - Log every tool invocation
    - Include timestamp, tool name, parameters
    - Include result status and errors
    - Store in SQLite
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [x] 23.2 Write property tests for audit logging `[Opus]`

    - **Property 12: Audit Log Completeness**
    - **Validates: Requirements 12.1, 12.3, 12.4**

- [x] 24. Health Check and Monitoring
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
    - Follow test scenarios in docs/UAT_PROTOCOL.md
    - Test all 8 MCP tools through Claude Desktop
    - Validate business value for each feature
    - Document results in UAT checklist
    - _Requirements: All user stories (1-8)_

  - [ ] 30.2 UAT Sign-off
    - Review all test results
    - Document any issues or feedback
    - Confirm MVP meets business requirements
    - Sign off on Phase 1 completion

## Code Quality Remediation Tasks

Based on code assessment report (Quality Score: 7.5/10)

### Critical Priority (Fix Before Deployment)

- [x] 31. Security: Replace eval() with json.loads()
  - [x] 31.1 Fix audit_service.py:154 - Replace `eval(row[3])` with `json.loads(row[3])`
    - Store parameters as JSON string instead of str(dict)
    - Update `log_invocation()` to use `json.dumps()` when storing
    - Update `get_audit_logs()` to use `json.loads()` when retrieving
    - _Severity: CRITICAL - Security vulnerability_

- [x] 32. Fix AuditStatus Type Mismatch
  - [x] 32.1 Fix main.py:196-201 - Use AuditStatus enum instead of string
    - Import AuditStatus from models.audit
    - Change `status="failure"` to `status=AuditStatus.FAILURE`
    - Change `status="success"` to `status=AuditStatus.SUCCESS`
  - [x] 32.2 Fix mcp_handler.py:397-412 - Use AuditStatus enum
    - Same changes as main.py
    - _Severity: HIGH - Runtime errors_

### High Priority (Fix Before Production)

- [x] 33. Use Centralized Settings Configuration
  - [x] 33.1 Refactor main.py to use Settings class from config.py
    - Replace `os.getenv("REDIS_URL", ...)` with `settings.redis_url`
    - Replace `os.getenv("AUDIT_DB_PATH", ...)` with `settings.audit_db_path`
    - Replace `os.getenv("AWS_REGION", ...)` with `settings.aws_region`
    - Replace `os.getenv("POLICY_PATH", ...)` with `settings.policy_path`
    - _Files: main.py:91, 100, 109, 118_

- [x] 34. Fix Redis Cache Async/Sync Mismatch
  - [x] 34.1 Update cache.py to use truly async Redis operations
    - Option A: Use `redis.asyncio` instead of synchronous `redis`
    - Option B: Wrap sync calls with `asyncio.to_thread()`
    - Update all `self._client.get()`, `self._client.setex()` calls
    - _File: mcp_server/clients/cache.py_

- [x] 35. Fix Dockerfile - Copy policies directory
  - [x] 35.1 Add `COPY policies/ ./policies/` to Dockerfile
    - Ensure tagging_policy.json is available in container
    - _File: Dockerfile:34-35_

- [x] 36. Fix EC2 ARN Format
  - [x] 36.1 Fix aws_client.py:188 - Include account ID in ARN
    - Change `arn:aws:ec2:{region}::instance/{id}` to include account
    - Fetch account ID from STS or instance metadata
    - _File: mcp_server/clients/aws_client.py:188_

### Medium Priority (Code Quality)

- [x] 37. Move hypothesis to dev dependencies
  - [x] 37.1 Update pyproject.toml
    - Move `hypothesis>=6.80.0` from `dependencies` to `[project.optional-dependencies].dev`
    - _File: pyproject.toml:32_

- [x] 38. Extract Duplicated Code to Shared Utilities
  - [x] 38.1 Create shared utility for `_fetch_resources_by_type`
    - Extract from compliance_service.py:331-365 and cost_service.py:237-271
    - Create `mcp_server/utils/resource_utils.py`
  - [x] 38.2 Create shared utility for `_extract_account_from_arn`
    - Extract from both services to shared utility

- [x] 39. Fix/Remove SSE Endpoint Placeholder
  - [x] 39.1 Either implement actual SSE or remove placeholder
    - Current endpoint at main.py:334-348 returns static JSON
    - _File: mcp_server/main.py:334-348_

- [x] 40. Update Pydantic Config to v2 Style
  - [x] 40.1 Replace deprecated `class Config` with `model_config`
    - Update config.py:98-122 to use Pydantic v2 patterns
    - Use `alias` on fields instead of `fields` mapping
    - _File: mcp_server/config.py:98-122_

### Low Priority (Cleanup)

- [x] 41. Code Cleanup
  - [x] 41.1 Define confidence score constants in suggestion_service.py
    - Replace magic numbers (0.85, 0.80, 0.75, 0.65, 0.50) with named constants
    - _File: mcp_server/services/suggestion_service.py:394-409_
  - [x] 41.2 Remove unused import in mcp_handler.py
    - Remove `from .middleware.audit_middleware import audit_tool`
    - _File: mcp_server/mcp_handler.py:43_
  - [x] 41.3 Remove duplicate pytest markers from conftest.py
    - Already defined in pyproject.toml:68-73
    - _File: tests/conftest.py:164-177_
  - [x] 41.4 Fix hardcoded port in log message
    - Use configuration value instead of hardcoded "8080"
    - _File: mcp_server/main.py:149_
  - [x] 41.5 Fix type hint: `callable` → `Callable`
    - _File: mcp_server/mcp_handler.py:72_

## Phase 2: Agent Observability and Security Enhancement

### High Priority (GenAI/Agentic System Requirements)

- [x] 42. Correlation ID Generation and Propagation
  - [x] 42.1 Create correlation ID utility module `[Haiku]`
    - Create `mcp_server/utils/correlation.py` with UUID4-based ID generation
    - Add correlation ID to request context using FastAPI middleware
    - _Requirements: 15.1_

  - [x] 42.2 Update audit logging to include correlation IDs `[Sonnet]`
    - Modify `AuditLogEntry` model to include `correlation_id` field
    - Update `AuditService.log_invocation()` to capture correlation ID from context
    - Update all audit log queries to include correlation ID
    - _Requirements: 15.1_

  - [x] 42.3 Add correlation ID to all log entries `[Sonnet]`
    - Update logging configuration to include correlation ID in log format
    - Modify all logger calls to include correlation ID from context
    - Update CloudWatch logging to include correlation ID as structured field
    - _Requirements: 15.1_

  - [x] 42.4 Write property tests for correlation ID propagation `[Opus]`
    - **Property 16: Correlation ID Propagation**
    - **Validates: Requirements 15.1**

- [x] 43. Tool-Call Budget Enforcement
  - [x] 43.1 Create budget tracking middleware `[Sonnet]`
    - Create `mcp_server/middleware/budget_middleware.py`
    - Track tool calls per session using Redis with TTL
    - Add configuration for `MAX_TOOL_CALLS_PER_SESSION` (default: 100)
    - _Requirements: 15.3_

  - [x] 43.2 Implement graceful budget exhaustion responses `[Sonnet]`
    - Create structured response model for budget exhaustion
    - Return helpful message with current usage and limit
    - Log budget exhaustion events for monitoring
    - _Requirements: 15.5_

  - [x] 43.3 Add budget status to health endpoint `[Haiku]`
    - Include current session count and budget utilization in health response
    - Add budget configuration to health endpoint
    - _Requirements: 15.3_

  - [x] 43.4 Write property tests for budget enforcement `[Opus]`
    - **Property 14: Tool Budget Enforcement**
    - **Validates: Requirements 15.3, 15.5**

- [x] 44. Loop Detection for Repeated Tool Calls
  - [x] 44.1 Implement call signature tracking `[Sonnet]`
    - Create `mcp_server/utils/loop_detection.py`
    - Generate call signatures from tool name + parameters hash
    - Track recent calls per session in Redis with sliding window
    - _Requirements: 15.4_

  - [x] 44.2 Add loop detection middleware `[Sonnet]`
    - Integrate loop detection into MCP handler
    - Configure `MAX_IDENTICAL_CALLS` (default: 3)
    - Return structured response when loop detected
    - _Requirements: 15.4_

  - [x] 44.3 Add loop detection metrics and logging `[Haiku]`
    - Log loop detection events with call signature and count
    - Add loop detection stats to health endpoint
    - Track loop detection frequency for monitoring
    - _Requirements: 15.4_

  - [x] 44.4 Write property tests for loop detection `[Opus]`
    - **Property 15: Loop Detection**
    - **Validates: Requirements 15.4**

- [x] 45. Input Schema Validation Enhancement
  - [x] 45.1 Strengthen input validation in MCP handler `[Sonnet]`
    - Add comprehensive JSON schema validation before tool execution
    - Create detailed validation error responses with field-level feedback
    - Update all tool schemas to be more restrictive
    - _Requirements: 16.3_

  - [x] 45.2 Add validation bypass detection `[Sonnet]`
    - Log attempts to bypass validation or inject malicious payloads
    - Add input sanitization for string fields
    - Implement parameter size limits
    - _Requirements: 16.3_

  - [x] 45.3 Write property tests for input validation `[Opus]`
    - **Property 17: Input Schema Validation**
    - **Validates: Requirements 16.3**

- [x] 46. Unknown Tool Rejection and Security Logging
  - [x] 46.1 Enhance unknown tool handling `[Sonnet]`
    - Update MCP handler to explicitly reject unknown tools
    - Create security event logging for unauthorized tool attempts
    - Add rate limiting for repeated unknown tool requests
    - _Requirements: 16.4_

  - [x] 46.2 Implement security monitoring `[Sonnet]`
    - Create `mcp_server/services/security_service.py`
    - Log security events to separate security log stream
    - Add security metrics to health endpoint
    - _Requirements: 16.4_

  - [x] 46.3 Write property tests for unknown tool rejection `[Opus]` ✅
    - **Property 18: Unknown Tool Rejection**
    - **Validates: Requirements 16.1, 16.4**
    - Created `tests/property/test_unknown_tool_rejection.py` with 9 property tests
    - Tests verify: unknown tools rejected with error, security logging, rate limiting, audit logging

- [x] 47. Agent Observability Dashboard Data
  - [x] 47.1 Create observability data models `[Haiku]`
    - Create `mcp_server/models/observability.py`
    - Add models for session metrics, tool usage stats, error rates
    - Include budget utilization and loop detection stats
    - _Requirements: 15.2_

  - [x] 47.2 Implement metrics collection service `[Sonnet]`
    - Create `mcp_server/services/metrics_service.py`
    - Aggregate tool usage, execution times, error rates
    - Calculate session-level and global statistics
    - _Requirements: 15.2_

  - [x] 47.3 Add metrics endpoint for observability `[Haiku]`
    - Create `/metrics` endpoint returning Prometheus-compatible metrics
    - Include tool call counts, execution times, error rates
    - Add budget and loop detection metrics
    - _Requirements: 15.2_

- [x] 48. Security Hardening
  - [x] 48.1 Implement request sanitization `[Sonnet]`
    - Add input sanitization middleware
    - Validate request headers and prevent header injection
    - Implement request size limits
    - _Requirements: 16.2, 16.5_

  - [x] 48.2 Enhance error message security `[Haiku]`
    - Audit all error messages to remove sensitive information
    - Create sanitized error response utility
    - Never expose internal paths, credentials, or stack traces
    - _Requirements: 16.5_

  - [x] 48.3 Add security configuration `[Haiku]`
    - Add security-related environment variables
    - Configure rate limiting, request size limits, timeout values
    - Document security configuration options
    - _Requirements: 16.1, 16.2_

- [x] 49. Checkpoint - Agent Observability and Security Complete
  - Ensure all new property tests pass
  - Verify correlation IDs appear in all logs and audit entries
  - Test budget enforcement with various limits
  - Confirm loop detection blocks repeated calls
  - Validate input schema rejection works correctly
  - Test unknown tool rejection and security logging
  - Run security penetration tests against the enhanced server

## Bug Fixes and Enhancements (Discovered During UAT)

### High Priority (Fix Before Phase 1 Completion)

- [ ] 50. Fix S3 Bucket ARN Support in suggest_tags Tool
  - [ ] 50.1 Update ARN validation pattern to support S3 bucket ARNs `[Sonnet]`
    - S3 bucket ARNs have format: `arn:aws:s3:::bucket-name` (empty region and account fields)
    - Current pattern requires account ID: `\d{12}` which rejects S3 ARNs
    - Update `InputValidator.ARN_PATTERN` in `mcp_server/utils/input_validation.py`
    - Change pattern from `(\d{12})` to `(\d{12}|)` to allow empty account ID
    - _Files: mcp_server/utils/input_validation.py_
    - _Severity: HIGH - Tool unusable for S3 resources_

  - [ ] 50.2 Verify ARN validation in all tools `[Haiku]`
    - Check `suggest_tags.py` and `validate_resource_tags.py` for additional validation
    - Ensure MCP handler doesn't have duplicate ARN validation
    - Test with S3 bucket ARN: `arn:aws:s3:::zombiescan-cur-zs551762956371`
    - _Files: mcp_server/tools/suggest_tags.py, mcp_server/tools/validate_resource_tags.py, mcp_server/mcp_handler.py_

  - [ ] 50.3 Add comprehensive ARN validation tests `[Haiku]`
    - Add test cases for S3 bucket ARNs (no account ID)
    - Add test cases for IAM ARNs (no region)
    - Add test cases for global service ARNs
    - Update `tests/unit/test_input_validation.py`
    - _Requirements: 16.3_

- [ ] 51. Add OpenSearch/Elasticsearch Support to find_untagged_resources
  - [ ] 51.1 Implement OpenSearch domain fetching in AWSClient `[Sonnet]`
    - Add `get_opensearch_domains()` method to `mcp_server/clients/aws_client.py`
    - Use boto3 OpenSearch client to list domains and get tags
    - Extract domain ARN, name, tags, and creation date
    - _Files: mcp_server/clients/aws_client.py_

  - [ ] 51.2 Add OpenSearch to resource type enum and compliance service `[Sonnet]`
    - Add "opensearch" to supported resource types
    - Update `ComplianceService._fetch_resources_by_type()` to handle OpenSearch
    - Update `find_untagged_resources` tool to include OpenSearch in scans
    - _Files: mcp_server/services/compliance_service.py, mcp_server/tools/find_untagged_resources.py_

  - [ ] 51.3 Add OpenSearch IAM permissions to policy `[Haiku]`
    - Add `es:ListDomainNames`, `es:DescribeDomain`, `es:ListTags` to IAM policy
    - Update `policies/iam/MCP_Tagging_Policy.json`
    - Update `docs/IAM_PERMISSIONS.md` with OpenSearch permissions
    - _Files: policies/iam/MCP_Tagging_Policy.json, docs/IAM_PERMISSIONS.md_

  - [ ] 51.4 Add tests for OpenSearch support `[Haiku]`
    - Add unit tests with moto mocks for OpenSearch domain fetching
    - Add integration test for OpenSearch in compliance checks
    - _Files: tests/unit/test_aws_client.py, tests/integration/test_check_tag_compliance.py_
    - _Severity: MEDIUM - Missing $84.80/month in cost analysis_

- [ ] 52. Improve ARN Validation for All AWS Resource Types
  - [ ] 52.1 Create comprehensive ARN validation utility `[Sonnet]`
    - Research ARN formats for all AWS services (EC2, RDS, S3, Lambda, ECS, OpenSearch, IAM, etc.)
    - Create flexible ARN pattern that handles:
      - Services with no region (IAM, S3, CloudFront)
      - Services with no account ID (S3)
      - Services with resource type prefix (ec2:instance/, rds:db/)
      - Services with simple resource names
    - Update `InputValidator.ARN_PATTERN` with comprehensive regex
    - _Files: mcp_server/utils/input_validation.py_

  - [ ] 52.2 Add ARN format documentation `[Haiku]`
    - Document supported ARN formats in code comments
    - Add examples for each AWS service type
    - Create reference table in `docs/IAM_PERMISSIONS.md`
    - _Files: mcp_server/utils/input_validation.py, docs/IAM_PERMISSIONS.md_

  - [ ] 52.3 Expand ARN validation test coverage `[Opus]`
    - Add test cases for all supported AWS service ARN formats
    - Test edge cases: global services, cross-region resources, cross-account ARNs
    - Add property test for ARN format validation
    - _Files: tests/unit/test_input_validation.py, tests/property/test_input_validation.py_
    - _Requirements: 16.3_
    - _Severity: MEDIUM - Improves tool reliability across all AWS services_

- [ ] 53. Checkpoint - Bug Fixes Complete
  - Test suggest_tags with S3 bucket ARNs
  - Verify OpenSearch domains appear in find_untagged_resources results
  - Validate ARN patterns work for all AWS service types
  - Run full regression test suite
  - Rebuild Docker container and verify fixes

## Notes

- Tasks marked with `*` are optional test tasks that can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation throughout development
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- **Model tags**: `[Haiku]` for boilerplate/simple tasks, `[Sonnet]` for business logic, `[Opus]` for complex reasoning/property tests
- **Regression testing**: Run `pytest tests/` at any checkpoint to execute the full test suite
