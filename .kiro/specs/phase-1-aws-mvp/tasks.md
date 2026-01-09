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

- [x] 26.1 Docker Build Verification `[Haiku]`
  - Start Docker Desktop on local machine
  - Run `docker build -t finops-tag-compliance-mcp:test .`
  - Verify image builds successfully
  - Run `docker-compose up -d` to start services
  - Test health endpoint at http://localhost:8080/health
  - Verify Redis container is running and healthy
  - _Requirements: 14.1, 14.3_

- [ ] 27. AWS Infrastructure Provisioning
  - [x] 27.1 Deploy CloudFormation stack `[Haiku]`
    - Deploy infrastructure/cloudformation.yaml
    - Provision EC2 instance (t3.medium), IAM role, security group
    - Wait for stack creation to complete
    - Stack name: `tagging-mcp-server`
    - Instance ID: `i-0dc314272ccf812db`
    - IAM Role: `arn:aws:iam::382598791951:role/tagging-mcp-server-role-dev`
    - Security Group: `sg-0bd742e0695eb6d5d`
    - CloudWatch Log Group: `/tagging-mcp-server/dev`
    - _Requirements: 14.1, 14.4, 10.1_

  - [x] 27.1.1 Attach Elastic IP to EC2 instance `[Manual]`
    - Allocated Elastic IP named `tagging-mcp`: `100.50.91.35`
    - Associated EIP with the EC2 instance
    - MCP Endpoint: `http://100.50.91.35:8080`
    - Note: Can optionally add EIP to CloudFormation template later
    - _Requirements: 14.4_

  - [x] 27.2 Configure EC2 instance `[Haiku]`
    - SSH into instance and verify Docker is installed
    - Clone repository to /opt/tagging-mcp
    - Create .env file with production settings
    - _Requirements: 14.2_

  - [x] 27.3 Deploy application to EC2 `[Haiku]`
    - Run docker-compose up -d
    - Verify containers are running
    - Test health endpoint responds
    - Note: Use `docker build -t tagging-mcp-server .` instead of `docker-compose build` (buildx version issue on Amazon Linux)
    - _Requirements: 14.1, 14.5_

- [ ] 28. Production Verification
  - [x] 28.1 Verify MCP server is accessible `[Haiku]`
    - Test health endpoint from external IP: `curl http://100.50.91.35:8080/health`
    - Health check confirmed: status=healthy, redis_connected=true, sqlite_connected=true
    - Verify IAM role can access AWS resources
    - Test one compliance check against real resources
    - _Requirements: 13.1, 10.1_

  - [x] 28.2 Configure Claude Desktop connection `[Haiku]`
    - Add MCP server to Claude Desktop config using bridge script
    - Test tool invocation through Claude
    - Verified: get_tagging_policy, check_tag_compliance, find_untagged_resources all working
    - _Requirements: 14.5_

- [x] 29. Deployment Complete Checkpoint
  - Verify server runs stable for 1 hour
  - Document any issues encountered
  - Confirm all 8 tools work against real AWS resources

- [x] 30. User Acceptance Testing (UAT)
  - [x] 30.1 Execute UAT protocol
    - Follow test scenarios in docs/UAT_PROTOCOL.md
    - Test all 8 MCP tools through Claude Desktop
    - Validate business value for each feature
    - Document results in UAT checklist
    - _Requirements: All user stories (1-8)_

  - [x] 30.2 UAT Sign-off
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

- [x] 50. Fix S3 Bucket ARN Support in suggest_tags Tool
  - [x] 50.1 Update ARN validation pattern to support S3 bucket ARNs `[Sonnet]`
    - S3 bucket ARNs have format: `arn:aws:s3:::bucket-name` (empty region and account fields)
    - Current pattern requires account ID: `\d{12}` which rejects S3 ARNs
    - Update `InputValidator.ARN_PATTERN` in `mcp_server/utils/input_validation.py`
    - Change pattern from `(\d{12})` to `(\d{12}|)` to allow empty account ID
    - _Files: mcp_server/utils/input_validation.py_
    - _Severity: HIGH - Tool unusable for S3 resources_

  - [x] 50.2 Verify ARN validation in all tools `[Haiku]`
    - Check `suggest_tags.py` and `validate_resource_tags.py` for additional validation
    - Ensure MCP handler doesn't have duplicate ARN validation
    - Test with S3 bucket ARN: `arn:aws:s3:::zombiescan-cur-zs551762956371`
    - _Files: mcp_server/tools/suggest_tags.py, mcp_server/tools/validate_resource_tags.py, mcp_server/mcp_handler.py_

  - [x] 50.3 Add comprehensive ARN validation tests `[Haiku]`
    - Add test cases for S3 bucket ARNs (no account ID)
    - Add test cases for IAM ARNs (no region)
    - Add test cases for global service ARNs
    - Update `tests/unit/test_input_validation.py`
    - _Requirements: 16.3_

- [x] 51. Add OpenSearch/Elasticsearch Support to find_untagged_resources
  - [x] 51.1 Implement OpenSearch domain fetching in AWSClient `[Sonnet]`
    - Add `get_opensearch_domains()` method to `mcp_server/clients/aws_client.py`
    - Use boto3 OpenSearch client to list domains and get tags
    - Extract domain ARN, name, tags, and creation date
    - _Files: mcp_server/clients/aws_client.py_

  - [x] 51.2 Add OpenSearch to resource type enum and compliance service `[Sonnet]`
    - Add "opensearch" to supported resource types
    - Update `ComplianceService._fetch_resources_by_type()` to handle OpenSearch
    - Update `find_untagged_resources` tool to include OpenSearch in scans
    - _Files: mcp_server/services/compliance_service.py, mcp_server/tools/find_untagged_resources.py_

  - [x] 51.3 Add OpenSearch IAM permissions to policy `[Haiku]`
    - Add `es:ListDomainNames`, `es:DescribeDomain`, `es:ListTags` to IAM policy
    - Update `policies/iam/MCP_Tagging_Policy.json`
    - Update `docs/IAM_PERMISSIONS.md` with OpenSearch permissions
    - _Files: policies/iam/MCP_Tagging_Policy.json, docs/IAM_PERMISSIONS.md_

  - [x] 51.4 Add tests for OpenSearch support `[Haiku]`
    - Add unit tests with moto mocks for OpenSearch domain fetching
    - Add integration test for OpenSearch in compliance checks
    - _Files: tests/unit/test_aws_client.py, tests/integration/test_check_tag_compliance.py_
    - _Severity: MEDIUM - Missing $84.80/month in cost analysis_

- [x] 52. Improve ARN Validation for All AWS Resource Types
  - [x] 52.1 Create comprehensive ARN validation utility `[Sonnet]`
    - Research ARN formats for all AWS services (EC2, RDS, S3, Lambda, ECS, OpenSearch, IAM, etc.)
    - Create flexible ARN pattern that handles:
      - Services with no region (IAM, S3, CloudFront)
      - Services with no account ID (S3)
      - Services with resource type prefix (ec2:instance/, rds:db/)
      - Services with simple resource names
    - Update `InputValidator.ARN_PATTERN` with comprehensive regex
    - _Files: mcp_server/utils/input_validation.py_

  - [x] 52.2 Add ARN format documentation `[Haiku]`
    - Document supported ARN formats in code comments
    - Add examples for each AWS service type
    - Create reference table in `docs/IAM_PERMISSIONS.md`
    - _Files: mcp_server/utils/input_validation.py, docs/IAM_PERMISSIONS.md_

  - [x] 52.3 Expand ARN validation test coverage `[Opus]`
    - Add test cases for all supported AWS service ARN formats
    - Test edge cases: global services, cross-region resources, cross-account ARNs
    - Add property test for ARN format validation
    - _Files: tests/unit/test_input_validation.py, tests/property/test_input_validation.py_
    - _Requirements: 16.3_
    - _Severity: MEDIUM - Improves tool reliability across all AWS services_

- [x] 53. Implement Automatic History Storage for Compliance Scans
  - [x] 53.1 Add history storage to check_tag_compliance tool `[Sonnet]`
    - Initialize HistoryService in the tool or pass it as a parameter
    - Call `history_service.store_scan_result()` after each compliance check
    - Handle storage errors gracefully (log but don't fail the compliance check)
    - Add configuration for history database path
    - _Files: mcp_server/tools/check_tag_compliance.py_
    - _Requirements: 8.1_
    - _Severity: HIGH - History tracking completely non-functional without this_

  - [x] 53.2 Update main.py to initialize HistoryService `[Haiku]`
    - Add HistoryService initialization in startup
    - Pass history_service to check_tag_compliance tool
    - Add HISTORY_DB_PATH to configuration
    - Ensure database is created on startup
    - _Files: mcp_server/main.py, mcp_server/config.py_

  - [x] 53.3 Add integration test for automatic history storage `[Haiku]`
    - Test that compliance checks automatically store results
    - Verify stored data matches compliance result
    - Test that get_violation_history returns stored data
    - _Files: tests/integration/test_check_tag_compliance.py_
    - _Requirements: 8.1, 8.2_

  - [x] 53.4 Update documentation for history tracking `[Haiku]`
    - Document that history is automatically stored
    - Explain database location and configuration
    - Add troubleshooting for history database issues
    - _Files: docs/PHASE-1-SPECIFICATION.md, README.md_

- [x] 54. Checkpoint - Bug Fixes Complete
  - Test suggest_tags with S3 bucket ARNs
  - Verify OpenSearch domains appear in find_untagged_resources results
  - Validate ARN patterns work for all AWS service types
  - Verify compliance scans automatically store history
  - Test get_violation_history returns actual data
  - Run full regression test suite
  - Rebuild Docker container and verify fixes

## Documentation and Naming Standardization

- [-] 55. Standardize Naming to "tagging-mcp-server" (Post-UAT)
  - **Prerequisite**: Complete UAT first, then do this rename before Phase 2
  - **Scope**: Rename all `finops-mcp-server` references to `tagging-mcp-server` across codebase and AWS
  
  - [x] 55.1 Update CloudFormation template naming `[Haiku]`
    - Rename all resources from `finops-mcp-server` to `tagging-mcp-server`
    - Update IAM role name, security group name, CloudWatch log group
    - Update stack name references in documentation
    - _Files: infrastructure/cloudformation.yaml_

  - [x] 55.2 Update all code and config files `[Haiku]`
    - Update container names in docker-compose.yml
    - Update any hardcoded references in .env.example
    - Update Phase 2 spec references
    - _Files: docker-compose.yml, .env.example, docs/PHASE-2-SPECIFICATION.md_

  - [x] 55.3 Update all documentation `[Haiku]`
    - Update `docs/DEPLOYMENT.md` with new naming convention
    - Update `docs/PHASE-1-SPECIFICATION.md` references
    - Update `docs/IAM_PERMISSIONS.md` references
    - Update `docs/UAT_PROTOCOL.md` references
    - Update `docs/DEVELOPMENT_JOURNAL.md` references
    - Update `TOMORROW_MORNING_PLAN.md` references
    - Update all example commands with `tagging-mcp-server` stack name
    - _Files: ~13 files with finops-mcp-server references_

  - [ ] 55.4 Redeploy locally and verify `[Manual]`
    - Run `docker-compose down` to stop old containers
    - Run `docker-compose up -d --build` with new naming
    - Verify health endpoint: `curl http://localhost:8080/health`
    - Test all 8 MCP tools via Claude Desktop

  - [ ] 55.5 Redeploy to AWS with new naming `[Manual]`
    - Delete old CloudFormation stack: `aws cloudformation delete-stack --stack-name tagging-mcp-server`
    - Wait for deletion to complete
    - Deploy new stack with updated template
    - SSH to EC2 and rebuild Docker container
    - Verify health endpoint: `curl http://<elastic-ip>:8080/health`

  - [ ] 55.6 Final UAT round with new naming `[Manual]`
    - Run through UAT protocol with Claude Desktop
    - Verify all 8 tools work correctly
    - Document any issues found
    - _Reference: docs/UAT_PROTOCOL.md_

- [x] 56. Create User Manual and Update Deployment Guide `[Sonnet]`
  - Created `docs/USER_MANUAL.md` for FinOps practitioners
    - Documented all 8 MCP tools with descriptions and use cases
    - Included example prompts for Claude Desktop
    - Documented common workflows (compliance check → remediation → tracking)
    - Added troubleshooting guide (common errors, connectivity, permissions)
  - Updated `docs/DEPLOYMENT.md` with local deployment section
    - Added clear step-by-step instructions for local Docker deployment
    - Included prerequisites (Docker Desktop, AWS credentials)
    - Added .env configuration examples
    - Documented how to connect Claude Desktop to local server
  - Updated main README.md with links to both guides
  - _Files: docs/USER_MANUAL.md, docs/DEPLOYMENT.md, README.md_

## Phase 1.7: Expanded Resource Coverage (Resource Groups Tagging API)

**Goal**: Extend tag compliance checking from 6 resource types to 50+ using AWS Resource Groups Tagging API

**Background**: The current implementation uses individual service APIs (EC2, RDS, S3, Lambda, ECS, OpenSearch) which limits coverage. The Resource Groups Tagging API provides a unified way to discover and manage tags across all taggable AWS resources.

- [x] 57. Implement Resource Groups Tagging API Client
  - [x] 57.1 Add Resource Groups Tagging API client to AWSClient `[Sonnet]`
    - Add `resourcegroupstaggingapi` boto3 client initialization
    - Implement `get_all_tagged_resources()` method using `tag:GetResources`
    - Handle pagination for large accounts (1000+ resources)
    - Extract resource type, region, and resource ID from ARN
    - _Files: mcp_server/clients/aws_client.py_
    - _Requirements: 17.1, 17.5_

  - [x] 57.2 Add IAM permissions for Resource Groups Tagging API `[Haiku]`
    - Add `tag:GetResources` permission to IAM policy
    - Add `tag:GetTagKeys` and `tag:GetTagValues` for future use
    - Update `policies/iam/MCP_Tagging_Policy.json`
    - Update `docs/IAM_PERMISSIONS.md` with new permissions
    - _Files: policies/iam/MCP_Tagging_Policy.json, docs/IAM_PERMISSIONS.md_
    - _Requirements: 17.1_

  - [x] 57.3 Write unit tests for Resource Groups Tagging API client `[Haiku]`
    - Test `get_all_tagged_resources()` with mocked responses
    - Test pagination handling with multiple pages
    - Test resource type filtering
    - Test ARN parsing for various resource types
    - _Files: tests/unit/test_aws_client.py_
    - _Requirements: 17.1, 17.5_

- [x] 58. Integrate Resource Groups Tagging API into Compliance Service
  - [x] 58.1 Update ComplianceService to use Resource Groups Tagging API `[Sonnet]`
    - Modify `_fetch_resources_by_type()` to use `get_all_tagged_resources()` when `resource_types` includes "all"
    - Keep individual service API calls as fallback for specific resource types
    - Add configuration flag to prefer Resource Groups Tagging API
    - _Files: mcp_server/services/compliance_service.py_
    - _Requirements: 17.2, 17.3, 17.6_

  - [x] 58.2 Update find_untagged_resources tool `[Sonnet]`
    - Support `resource_types: ["all"]` to scan all taggable resources
    - Use Resource Groups Tagging API for comprehensive discovery
    - Maintain backward compatibility with specific resource type filters
    - _Files: mcp_server/tools/find_untagged_resources.py_
    - _Requirements: 17.3, 17.4_

  - [x] 58.3 Update check_tag_compliance tool `[Sonnet]`
    - Support `resource_types: ["all"]` parameter
    - Use Resource Groups Tagging API for comprehensive compliance checks
    - Handle large result sets efficiently
    - _Files: mcp_server/tools/check_tag_compliance.py_
    - _Requirements: 17.3, 17.7_

  - [x] 58.4 Write integration tests for expanded resource coverage `[Opus]`
    - Test compliance check with `resource_types: ["all"]`
    - Test that 50+ resource types are discovered
    - Test performance with large accounts
    - **Property 19: Resource Groups Tagging API Coverage**
    - Added 8 new integration tests:
      - `test_check_compliance_all_resource_types` - Basic "all" resource type test
      - `test_check_compliance_all_discovers_many_resource_types` - 10+ resource types
      - `test_check_compliance_all_with_violations` - Violations with "all"
      - `test_check_compliance_all_empty_account` - Empty account handling
      - `test_check_compliance_all_with_region_filter` - Region filtering with "all"
      - `test_property_19_tagging_api_returns_consistent_format` - Property 19 format
      - `test_property_19_tagging_api_handles_pagination` - Property 19 pagination
      - `test_property_19_tagging_api_vs_specific_types_consistency` - Property 19 consistency
    - _Files: tests/integration/test_check_tag_compliance.py_
    - _Requirements: 17.2, 17.3_

- [ ] 58.5 Clean Slate - Delete All AWS Resources for Fresh Redeploy `[Manual]`
  - **Purpose**: Remove all existing AWS resources to do a clean redeployment
  - **Resources to Delete**:
    1. **Elastic IP**: Release `tagging-mcp` EIP (100.50.91.35) - $3.60/month if not attached
    2. **CloudFormation Stack**: Delete `tagging-mcp-server` stack (this deletes EC2, IAM role, security group, CloudWatch log group)
    3. **Local Docker**: Stop and remove containers if running locally
  
  - **Step-by-step Commands**:
    ```bash
    # 1. Release Elastic IP (from AWS Console or CLI)
    aws ec2 describe-addresses --filters "Name=tag:Name,Values=tagging-mcp"
    aws ec2 release-address --allocation-id <allocation-id-from-above>
    
    # 2. Delete CloudFormation stack (this deletes EC2, IAM, SG, CloudWatch)
    aws cloudformation delete-stack --stack-name tagging-mcp-server --region us-east-1
    
    # 3. Wait for stack deletion to complete
    aws cloudformation wait stack-delete-complete --stack-name tagging-mcp-server --region us-east-1
    
    # 4. Verify deletion
    aws cloudformation describe-stacks --stack-name tagging-mcp-server --region us-east-1
    # Should return "Stack with id tagging-mcp-server does not exist"
    
    # 5. (Optional) Stop local Docker containers
    docker-compose down
    docker system prune -f
    ```
  
  - **What Gets Deleted**:
    - EC2 Instance: `i-0dc314272ccf812db`
    - IAM Role: `tagging-mcp-server-role-dev`
    - IAM Policy: `tagging-mcp-server-policy-dev`
    - Instance Profile: `tagging-mcp-server-profile-dev`
    - Security Group: `tagging-mcp-server-sg-dev`
    - CloudWatch Log Group: `/tagging-mcp-server/dev`
    - EBS Volume (20GB) - auto-deleted with instance
  
  - **After Cleanup**: Proceed to Task 59 to redeploy fresh

- [ ] 59. Phase 1.7 Checkpoint - Expanded Resource Coverage Complete
  - [ ] 59.1 Verify Resource Groups Tagging API integration `[Manual]`
    - Test `check_tag_compliance` with `resource_types: ["all"]`
    - Verify resources from 10+ different AWS services are discovered
    - Confirm pagination works for accounts with 1000+ resources
    - _Requirements: 17.1, 17.2, 17.5_

  - [ ] 59.2 Update documentation `[Haiku]`
    - Update `docs/PHASE-1-SPECIFICATION.md` with expanded resource coverage
    - Update `docs/USER_MANUAL.md` with new `resource_types: ["all"]` option
    - Update `docs/ROADMAP.md` to mark Phase 1.7 as truly complete
    - _Files: docs/PHASE-1-SPECIFICATION.md, docs/USER_MANUAL.md, docs/ROADMAP.md_

  - [ ] 59.3 Redeploy and verify `[Manual]`
    - Rebuild Docker container with new code
    - Deploy to EC2 instance
    - Run quick smoke test with expanded resource coverage
    - Verify all 8 MCP tools respond correctly

  - [ ] 59.4 Full UAT with Expanded Resource Coverage `[Manual]`
    - Update `docs/UAT_PROTOCOL.md` with new test scenarios:
      - Test `check_tag_compliance` with `resource_types: ["all"]`
      - Test `find_untagged_resources` with `resource_types: ["all"]`
      - Verify resources from DynamoDB, ElastiCache, SNS, SQS, CloudWatch appear
      - Test performance with large result sets
      - Test filtering by specific new resource types (e.g., `dynamodb:table`)
    - Execute full UAT protocol through Claude Desktop
    - Document results for all 8 tools with expanded coverage
    - Sign off on Phase 1.7 completion
    - _Files: docs/UAT_PROTOCOL.md_
    - _Requirements: 17.1, 17.2, 17.3, All user stories (1-8)_

## Phase 1.8: Cost Attribution Gap "All" Resource Type Support

**Goal**: Extend `get_cost_attribution_gap` tool to support `resource_types: ["all"]` for comprehensive cost attribution analysis

**Background**: The `check_tag_compliance` and `find_untagged_resources` tools now support `resource_types: ["all"]` via the Resource Groups Tagging API, but `get_cost_attribution_gap` still only supports the original 5 resource types (ec2:instance, rds:db, s3:bucket, lambda:function, ecs:service). This causes Claude to fall back to listing specific types, missing costs from services like Bedrock, CloudWatch, OpenSearch, etc.

**Issue Discovered**: When user asks "What's my cost attribution gap?", Claude sends `resource_types: ["all"]` which is rejected with:
```
Invalid resource types: ['all']. Valid types are: ['ec2:instance', 'ecs:service', 'lambda:function', 'rds:db', 's3:bucket']
```

- [ ] 60. Add "all" Resource Type Support to get_cost_attribution_gap
  - [ ] 60.1 Update input validation to allow "all" for cost attribution `[Sonnet]`
    - Update `InputValidator.VALID_RESOURCE_TYPES` to include "all" (already done in Task 57)
    - Update `get_cost_attribution_gap` tool validation to accept "all"
    - _Files: mcp_server/tools/get_cost_attribution_gap.py_
    - _Requirements: 4.1, 17.3_

  - [ ] 60.2 Implement total account spend retrieval in CostService `[Sonnet]`
    - Add `get_total_account_spend()` method to AWSClient
    - Query Cost Explorer without service filter to get total account spend
    - This captures ALL services including Bedrock, CloudWatch, Data Transfer, etc.
    - _Files: mcp_server/clients/aws_client.py_
    - _Requirements: 4.1, 4.4_

  - [ ] 60.3 Update CostService.calculate_attribution_gap() for "all" mode `[Sonnet]`
    - When `resource_types` includes "all":
      1. Get total account spend from Cost Explorer (all services)
      2. Use Resource Groups Tagging API to get all tagged resources
      3. Calculate attributable spend from properly tagged resources
      4. Gap = Total Account Spend - Attributable Spend
    - This captures costs from ALL services, not just the 5 we scan
    - _Files: mcp_server/services/cost_service.py_
    - _Requirements: 4.1, 4.2, 4.3, 17.3_

  - [ ] 60.4 Add unit tests for "all" resource type cost attribution `[Haiku]`
    - Test `get_cost_attribution_gap` with `resource_types: ["all"]`
    - Test that total account spend includes all services
    - Test gap calculation with mixed tagged/untagged resources
    - _Files: tests/unit/test_get_cost_attribution_gap.py, tests/unit/test_cost_service.py_
    - _Requirements: 4.1, 4.2_

  - [ ] 60.5 Update documentation for "all" cost attribution `[Haiku]`
    - Update `docs/USER_MANUAL.md` with new capability
    - Add example: "What's my total cost attribution gap across all services?"
    - _Files: docs/USER_MANUAL.md_

- [ ] 61. Phase 1.8 Checkpoint - Cost Attribution "All" Support Complete
  - Test `get_cost_attribution_gap` with `resource_types: ["all"]`
  - Verify total account spend includes all AWS services
  - Verify gap calculation captures costs from Bedrock, CloudWatch, etc.
  - Run full regression test suite
  - Rebuild Docker container and verify fix

## Notes

- Tasks marked with `*` are optional test tasks that can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation throughout development
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- **Model tags**: `[Haiku]` for boilerplate/simple tasks, `[Sonnet]` for business logic, `[Opus]` for complex reasoning/property tests
- **Regression testing**: Run `pytest tests/` at any checkpoint to execute the full test suite
