# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **FinOps Tag Compliance MCP Server** - a remote Model Context Protocol server that provides intelligent AWS resource tagging validation and compliance checking to AI assistants like Claude Desktop. It goes beyond basic tag reading to provide schema validation, cost attribution analysis, and ML-powered tag suggestions.

**Phase**: Phase 1 MVP Complete (AWS support only)

## Development Commands

### Running the Server

```bash
# Local development with Docker
docker-compose up -d

# Run directly with Python
python run_server.py

# Run as module
python -m mcp_server
```

Server runs on `http://localhost:8080` by default.

### Testing

```bash
# Run all tests
python run_tests.py

# Test by type
python run_tests.py --unit          # Fast isolated tests (mock dependencies)
python run_tests.py --property      # Property-based tests (Hypothesis)
python run_tests.py --integration   # End-to-end tests (real AWS calls)

# Fast mode (skip slow tests)
python run_tests.py --fast

# With coverage report
python run_tests.py --coverage

# Using pytest directly
pytest tests/                                          # All tests
pytest tests/unit/test_compliance_service.py          # Specific file
pytest tests/ --cov=mcp_server --cov-report=html     # Coverage HTML report
pytest tests/ -m "not integration"                    # Exclude integration tests
```

### Code Quality

```bash
# Format code
black mcp_server/ tests/

# Lint
ruff check mcp_server/ tests/

# Type checking
mypy mcp_server/
```

## Architecture

### High-Level Structure

```
mcp_server/
├── main.py              # FastAPI app entry point, lifespan management
├── config.py            # Pydantic Settings configuration
├── mcp_handler.py       # MCP protocol handler, tool registration
├── models/              # Pydantic data models
├── services/            # Business logic layer
├── tools/               # 8 MCP tool implementations
├── clients/             # AWS client wrapper, Redis cache
├── middleware/          # Audit, budget, sanitization middleware
└── utils/               # Correlation IDs, CloudWatch, error sanitization
```

### Service Layer Architecture

The application follows a **service-oriented architecture** with clear separation of concerns:

**Core Services** (initialized in `main.py` lifespan):
- `AWSClient` - Wrapper around boto3 with rate limiting and exponential backoff
- `RedisCache` - Caching layer for compliance results (1-hour TTL)
- `PolicyService` - Loads and validates tagging policy from `policies/tagging_policy.json`
- `ComplianceService` - Core compliance checking logic (uses AWS + Policy services)
- `AuditService` - SQLite-based audit logging for all tool invocations
- `HistoryService` - SQLite-based storage for compliance scan history
- `SecurityService` - Security event monitoring and rate limiting
- `BudgetTracker` - Tool call budget enforcement (max 100 calls/session)
- `LoopDetector` - Detects repeated identical tool calls (max 3 identical calls)

**Service Dependencies**:
```
MCPHandler
  ├── ComplianceService
  │     ├── AWSClient
  │     ├── PolicyService
  │     └── RedisCache (optional)
  ├── AuditService
  ├── HistoryService
  └── SecurityService
```

### MCP Tools (8 Total)

All tools are registered in `MCPHandler` and exposed via `/mcp/tools/call`:

1. `check_tag_compliance` - Scan resources, calculate compliance score
2. `find_untagged_resources` - Find resources missing required tags
3. `validate_resource_tags` - Validate specific resources by ARN
4. `get_cost_attribution_gap` - Calculate financial impact of tagging gaps
5. `suggest_tags` - ML-powered tag value suggestions
6. `get_tagging_policy` - Return policy configuration
7. `generate_compliance_report` - Generate JSON/CSV/Markdown reports
8. `get_violation_history` - Historical compliance trends

Each tool is implemented in `mcp_server/tools/<tool_name>.py` with:
- Input validation using Pydantic models
- Result models in `mcp_server/models/`
- Integration with audit logging
- Budget tracking and loop detection

### AWS Client Design

The `AWSClient` (`mcp_server/clients/aws_client.py`) wraps boto3 with:
- **Authentication**: IAM instance profile (no hardcoded credentials)
- **Rate limiting**: 100ms minimum interval between calls to same service
- **Exponential backoff**: Automatic retries with adaptive mode
- **Multi-service**: EC2, RDS, S3, Lambda, ECS, Cost Explorer, Resource Groups Tagging API

**Important**: Cost Explorer client is always `us-east-1` regardless of resource region.

### Caching Strategy

Redis caching (`mcp_server/clients/cache.py`) is used for:
- Compliance scan results (1-hour TTL by default)
- Budget tracking session state
- Loop detection call history
- Security event tracking

Cache keys are SHA256 hashes of normalized query parameters. Use `force_refresh=True` to bypass cache.

### Middleware Pipeline

Middleware is applied in this order (from `main.py`):
1. **CORS** - Allow all origins for MCP protocol
2. **RequestSanitization** - Validates headers, size limits, prevents injection
3. **CorrelationID** - Adds correlation IDs for request tracing
4. **BudgetTracking** - Enforces tool call limits per session
5. **LoopDetection** - Detects repeated identical calls

### Error Handling

All errors go through sanitization (`mcp_server/utils/error_sanitization.py`):
- **Internal logging**: Full details including stack traces, paths, context
- **User response**: Sanitized error codes and user-friendly messages
- **No sensitive data**: Paths, credentials, and internal details are never exposed

Custom exceptions:
- `TagComplianceError` - General compliance errors
- `PolicyValidationError` - Policy validation failures
- `AWSAPIError` - AWS API call failures
- `BudgetExhaustedError` - Tool call budget exceeded
- `LoopDetectedError` - Repeated identical calls detected
- `ValidationError` - Input validation failures
- `SecurityViolationError` - Security policy violations

## Configuration

All configuration is via environment variables (see `mcp_server/config.py`):

**Critical Settings**:
- `POLICY_PATH` or `POLICY_FILE_PATH` - Path to tagging policy JSON (default: `policies/tagging_policy.json`)
- `AWS_REGION` - Default AWS region (default: `us-east-1`)
- `REDIS_URL` - Redis connection URL (default: `redis://localhost:6379/0`)
- `HISTORY_DB_PATH` - SQLite database for compliance history (default: `compliance_history.db`)
- `AUDIT_DB_PATH` - SQLite database for audit logs (default: `audit_logs.db`)

**Feature Flags**:
- `BUDGET_TRACKING_ENABLED` - Enable tool call budgets (default: `true`)
- `LOOP_DETECTION_ENABLED` - Enable loop detection (default: `true`)
- `SECURITY_MONITORING_ENABLED` - Enable security event monitoring (default: `true`)
- `CLOUDWATCH_ENABLED` - Enable CloudWatch logging (default: `false`)

Settings are loaded from:
1. Environment variables
2. `.env` file (if present)
3. Default values in `config.py`

## Tagging Policy Structure

The tagging policy (`policies/tagging_policy.json`) defines required and optional tags:

```json
{
  "required_tags": [
    {
      "name": "Environment",
      "description": "Deployment environment",
      "allowed_values": ["production", "staging", "development"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db"]
    }
  ],
  "optional_tags": [...]
}
```

**Key fields**:
- `allowed_values` - If set, tag value must be in this list (case-sensitive)
- `validation_regex` - If set, tag value must match this regex pattern
- `applies_to` - Resource types this tag applies to (empty list = all types)

Supported resource types: `ec2:instance`, `rds:db`, `s3:bucket`, `lambda:function`, `ecs:service`, `opensearch:domain`

## Cost Attribution Logic

Cost calculation varies by AWS service (`find_untagged_resources`, `get_cost_attribution_gap`):

**Per-Resource Costs** (actual granularity from Cost Explorer):
- EC2 instances
- RDS databases

**Service-Level Costs** (distributed evenly - estimates):
- S3 buckets - Total S3 cost ÷ bucket count
- Lambda functions - Total Lambda cost ÷ function count
- ECS services - Total ECS cost ÷ service count

The `cost_source` field in results indicates: `actual`, `service_average`, or `estimated`.

## Testing Philosophy

This project uses a **3-layer testing strategy**:

1. **Unit Tests** (`tests/unit/`) - Fast, isolated, mock all dependencies
   - Test individual functions and classes
   - Mock AWS, Redis, SQLite
   - Target: <100ms per test

2. **Property Tests** (`tests/property/`) - Hypothesis-based generative testing
   - Test invariants and properties that should always hold
   - Generate hundreds of test cases automatically
   - Example: Compliance score is always 0.0-1.0 regardless of inputs

3. **Integration Tests** (`tests/integration/`) - End-to-end with real services
   - Test full workflows with actual AWS, Redis, SQLite
   - Use `moto` for AWS mocking where possible
   - Marked with `@pytest.mark.integration`

**Writing Tests**:
- Every new tool must have unit, property, and integration tests
- Use fixtures from `tests/conftest.py` for common test data
- Property tests should reference requirement numbers in docstrings
- Integration tests should clean up resources after completion

## Important Patterns

### Async/Await Consistency

All I/O operations use `async`/`await`:
- AWS API calls
- Redis operations
- Tool invocations
- Service methods

When adding new AWS calls, use `asyncio.to_thread()` to run boto3 sync calls in thread pool.

### Pydantic Models Everywhere

All data structures are Pydantic models:
- Tool inputs/outputs
- Service method parameters/returns
- Configuration settings
- API request/response bodies

This provides automatic validation, serialization, and type safety.

### Correlation IDs

Every request gets a correlation ID (`x-correlation-id` header or auto-generated UUID):
- Propagated through all logs
- Included in audit logs
- Available via `get_correlation_id()` utility

Use correlation IDs when logging to trace requests across services.

### Input Validation

All user inputs go through validation (`mcp_server/utils/input_validation.py`):
- Maximum string lengths (1000 chars)
- Maximum list sizes (100 items)
- No SQL injection patterns
- No path traversal attempts
- ARN format validation

Security violations are logged to CloudWatch security stream (if enabled).

## Database Schemas

**Audit Logs** (`audit_logs.db`):
```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    correlation_id TEXT,
    tool_name TEXT,
    parameters TEXT,
    status TEXT,
    execution_time_ms REAL,
    error_message TEXT
)
```

**Compliance History** (`compliance_history.db`):
```sql
CREATE TABLE compliance_scans (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    compliance_score REAL,
    total_resources INTEGER,
    compliant_resources INTEGER,
    violation_count INTEGER,
    cost_attribution_gap REAL,
    created_at TEXT
)
```

History is automatically populated when `check_tag_compliance` is called.

## AWS Permissions Required

The IAM role/user needs read-only permissions (see `docs/IAM_PERMISSIONS.md`):
- `ec2:DescribeInstances`, `ec2:DescribeTags`
- `rds:DescribeDBInstances`, `rds:ListTagsForResource`
- `s3:ListAllMyBuckets`, `s3:GetBucketTagging`
- `lambda:ListFunctions`, `lambda:ListTags`
- `ecs:ListServices`, `ecs:ListTagsForResource`
- `ce:GetCostAndUsage` (for cost data)
- `tag:GetResources` (Resource Groups Tagging API)

**No write permissions required** for Phase 1.

## Docker Deployment

The `docker-compose.yml` includes:
- Redis service (port 6379)
- MCP server service (port 8080)
- Volume mounts for policies, data, logs
- AWS credentials mount (`~/.aws` → `/root/.aws`)

**Important**: On Windows, use `${USERPROFILE}/.aws`. On Linux/Mac, use `~/.aws`.

## Common Tasks

### Adding a New MCP Tool

1. Create tool module in `mcp_server/tools/<tool_name>.py`
2. Define input/output Pydantic models in `mcp_server/models/`
3. Implement tool function with async signature
4. Register tool in `MCPHandler.__init__()` and `_register_tools()`
5. Add MCP tool definition with JSON schema
6. Write unit, property, and integration tests
7. Update `run_server.py` banner with new tool count

### Modifying the Tagging Policy

Edit `policies/tagging_policy.json` directly. Changes take effect on next policy load (policy is cached after first load - restart server to reload).

### Adding Support for New AWS Resource Types

1. Add boto3 client to `AWSClient.__init__()`
2. Implement `list_<resource>` method in `AWSClient`
3. Add resource type to `ResourceType` enum in `mcp_server/models/enums.py`
4. Update policy validation to support new resource type
5. Add cost fetching logic if Cost Explorer supports per-resource costs
6. Update documentation with new resource type

### Debugging Tool Invocations

1. Check `/health` endpoint for service connectivity
2. Review audit logs in `audit_logs.db`
3. Check correlation ID in logs to trace request
4. Use `LOG_LEVEL=DEBUG` environment variable for verbose output
5. For AWS errors, check IAM permissions

## Key Files Reference

- `run_server.py` - Main entry point with banner and startup
- `mcp_server/main.py` - FastAPI app, lifespan, endpoints
- `mcp_server/mcp_handler.py` - MCP protocol implementation
- `mcp_server/config.py` - All configuration settings
- `mcp_server/tools/check_tag_compliance.py` - Core compliance scanning tool
- `mcp_server/services/compliance_service.py` - Compliance checking logic
- `mcp_server/clients/aws_client.py` - AWS API wrapper
- `docs/TOOL_LOGIC_REFERENCE.md` - Detailed logic for each tool
- `docs/TESTING_QUICK_START.md` - Testing guide
