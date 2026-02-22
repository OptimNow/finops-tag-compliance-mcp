# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

| Action | Command |
|--------|---------|
| Run MCP server (stdio) | `python -m mcp_server.stdio_server` |
| Run HTTP server | `python run_server.py` |
| Run all tests | `python run_tests.py` |
| Run unit tests only | `python run_tests.py --unit` |
| Format code | `black mcp_server/ tests/` |
| Type check | `mypy mcp_server/` |
| Test with MCP Inspector | `npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server` |
| Run regression tests (promptfoo) | `cd tests/regression && npx promptfoo@latest eval` |
| Deploy to ECS Fargate | `./scripts/deploy_ecs.sh` |
| Deploy (image only) | `./scripts/deploy_ecs.sh --deploy-only` |

**Critical Files:**
- `mcp_server/stdio_server.py` - MCP entry point (Claude Desktop)
- `mcp_server/container.py` - Service container (dependency injection)
- `mcp_server/services/compliance_service.py` - Core compliance logic
- `mcp_server/services/multi_region_scanner.py` - Multi-region orchestration
- `policies/tagging_policy.json` - Tagging policy configuration
- `config/resource_types.json` - Resource types configuration

## Project Overview

This is a **FinOps Tag Compliance MCP Server** - a remote Model Context Protocol server that provides intelligent AWS resource tagging validation and compliance checking to AI assistants like Claude Desktop. It goes beyond basic tag reading to provide schema validation, cost attribution analysis, and ML-powered tag suggestions.

**Phase**: Phase 2 Complete ✅ (February 22, 2026) — 14 tools, ECS Fargate live at https://mcp.optimnow.io
**Refactoring**: Deferred to Phase 3 (see [REFACTORING_PLAN.md](REFACTORING_PLAN.md))

## Development Commands

### Running the Server

```bash
# Stdio transport (standard MCP — for Claude Desktop / MCP Inspector)
python -m mcp_server.stdio_server

# Test with MCP Inspector
npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server

# HTTP transport (for remote deployment)
python run_server.py          # FastAPI on http://localhost:8080
docker-compose up -d          # Docker with Redis
```

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

# Regression tests (promptfoo — requires MCP HTTP server running)
cd tests/regression && npx promptfoo@latest eval      # Run 34 regression tests
cd tests/regression && npx promptfoo@latest view       # View results in browser
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

### Design Philosophy: Core Library + MCP Layer

This project deliberately separates **protocol-agnostic business logic** (reusable core library) from **MCP-specific code**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     MCP PROTOCOL / TRANSPORT LAYER                      │
│  Two entry points — choose based on deployment model                    │
├─────────────────────────────────────────────────────────────────────────┤
│  stdio_server.py     → FastMCP stdio transport (Claude Desktop/Inspector│
│  main.py             → FastAPI HTTP transport (/mcp/* endpoints)        │
│  mcp_handler.py      → Legacy MCP protocol handler (HTTP transport)     │
│  middleware/         → Request sanitization, budget tracking (HTTP only)│
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         TOOLS LAYER (Adapters)                          │
│  Thin wrappers that translate MCP tool calls → service method calls     │
├─────────────────────────────────────────────────────────────────────────┤
│  tools/check_tag_compliance.py    → calls ComplianceService             │
│  tools/find_untagged_resources.py → calls ComplianceService             │
│  tools/get_cost_attribution_gap.py→ calls CostService                   │
│  tools/suggest_tags.py            → calls SuggestionService             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   SERVICE CONTAINER + SERVICES LAYER                    │
│  ★ ServiceContainer initializes all services in dependency order        │
│  ★ ZERO knowledge of MCP - pure business logic                          │
│  ★ Reusable: `from mcp_server.services import ComplianceService`        │
├─────────────────────────────────────────────────────────────────────────┤
│  container.py                    → ServiceContainer (DI + lifecycle)     │
│  services/compliance_service.py  → Resource scanning, policy validation │
│  services/cost_service.py        → Cost attribution calculations        │
│  services/policy_service.py      → Tagging policy management            │
│  services/suggestion_service.py  → ML-powered tag suggestions           │
│  services/audit_service.py       → Audit logging                        │
│  services/history_service.py     → Compliance trend tracking            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CONFIGURATION + MODELS LAYER                         │
│  CoreSettings (protocol-agnostic) / ServerSettings (HTTP-specific)      │
├─────────────────────────────────────────────────────────────────────────┤
│  config.py → CoreSettings + ServerSettings (split configuration)        │
│  models/   → 17 Pydantic model files with strict typing + JSON schemas  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          CLIENTS LAYER                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  clients/aws_client.py   → Boto3 wrapper with rate limiting, backoff    │
│  clients/cache.py        → Redis caching layer                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Why this separation matters:**
- Services can be imported directly without MCP: `from mcp_server.services import ComplianceService`
- Easy to add CLI, REST API, webhook, or Lambda interface without touching business logic
- Services are testable in isolation (unit tests mock only clients, not MCP layer)
- Clear boundaries for future extraction into a standalone package

### High-Level File Structure

```
mcp_server/
├── stdio_server.py      # ★ FastMCP stdio entry point (Claude Desktop / Inspector)
├── main.py              # FastAPI HTTP entry point, lifespan management
├── container.py         # ★ ServiceContainer (dependency injection + lifecycle)
├── config.py            # CoreSettings + ServerSettings (split configuration)
├── mcp_handler.py       # Legacy MCP protocol handler (HTTP transport)
├── models/              # Pydantic data models (17 files)
├── services/            # Core business logic (protocol-agnostic)
├── tools/               # 8 MCP tool adapters (thin wrappers)
├── clients/             # AWS client wrapper, Redis cache
├── middleware/          # Audit, budget, sanitization middleware (HTTP only)
└── utils/               # Correlation IDs, CloudWatch, error sanitization
```

### Multi-Region Scanning

The server supports scanning AWS resources across all enabled regions in parallel. This is critical for organizations with resources distributed globally.

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│                      MULTI-REGION SCANNING                              │
├─────────────────────────────────────────────────────────────────────────┤
│  services/multi_region_scanner.py  → Orchestrates parallel regional scans│
│  services/region_discovery.py      → Discovers enabled AWS regions       │
│  clients/regional_client_factory.py→ Creates/caches regional AWS clients │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Components:**
- `MultiRegionScanner` - Coordinates parallel scanning across regions using asyncio
- `RegionDiscoveryService` - Queries EC2 to find enabled regions in the account
- `RegionalClientFactory` - Creates and caches regional `AWSClient` instances

**How It Works:**
1. `RegionDiscoveryService` queries EC2 to get all enabled regions
2. `RegionalClientFactory` creates an `AWSClient` for each region (cached)
3. `MultiRegionScanner.scan_all_regions()` runs compliance checks in parallel
4. Results are aggregated into a `MultiRegionComplianceResult` with regional breakdown

**Tools with Multi-Region Support:**
| Tool | Multi-Region | Notes |
|------|-------------|-------|
| `check_tag_compliance` | ✅ Full | Returns regional breakdown and metadata |
| `find_untagged_resources` | ✅ Full | Searches all regions in parallel |
| `validate_resource_tags` | ✅ Via ARN | Uses regional client based on ARN region |
| `get_cost_attribution_gap` | ✅ Full | Fetches resources from all regions |
| `suggest_tags` | ✅ Via ARN | Uses regional client based on ARN region |
| `get_tagging_policy` | N/A | No AWS calls |
| `generate_compliance_report` | ✅ Inherits | Uses check_tag_compliance internally |
| `get_violation_history` | N/A | Local database only |

**Configuration:**
- Multi-region scanning is **always enabled** by default (no toggle)
- `ALLOWED_REGIONS` - Restrict scanning to specific regions (comma-separated, e.g., `us-east-1,us-west-2,eu-west-1`). If not set, all enabled regions in the AWS account are scanned.
- `MAX_CONCURRENT_REGIONS` - Maximum regions to scan in parallel (default: `5`, range: 1-20)
- `REGION_SCAN_TIMEOUT_SECONDS` - Timeout for scanning a single region (default: `60`, range: 10-300)
- `REGION_CACHE_TTL_SECONDS` - TTL for caching enabled regions list (default: `3600`)
- `AWS_REGION` - Default region for Cost Explorer (always `us-east-1` for costs)

**Region Hierarchy:**
1. AWS enabled regions (discovered via EC2 API)
2. `ALLOWED_REGIONS` infrastructure restriction (limits available regions)
3. User query filter (further narrows within allowed regions)

**Global vs Regional Resources:**

AWS has two categories of resources:
- **Global resources** (S3 buckets, IAM roles/users/policies, CloudFront distributions, Route53 hosted zones): These exist at the account level, not in specific regions. They are **always scanned regardless of region filters** and reported as region="global" in results.
- **Regional resources** (EC2 instances, RDS databases, Lambda functions, etc.): These exist in specific AWS regions and respect region filters.

Example: If you filter to `regions=["us-east-1"]`, you will get:
- All S3 buckets (global resources, ignore the filter)
- Only EC2 instances in us-east-1 (regional resources, respect the filter)

This behavior is intentional - global resources have no region, so filtering them by region would cause them to be missed entirely.

**Region Discovery Fallback:**

If the EC2 DescribeRegions API call fails (e.g., due to permissions or network issues), the scanner falls back to scanning only the default region (us-east-1). When this happens:
- `region_metadata.discovery_failed` will be `true`
- `region_metadata.discovery_error` will contain the error message
- Results may be incomplete (only default region scanned)

Check these fields to detect when discovery fell back silently.

**Response Format (Multi-Region):**
```json
{
  "compliance_score": 0.75,
  "total_resources": 150,
  "region_metadata": {
    "total_regions": 5,
    "successful_regions": ["us-east-1", "us-west-2", "eu-west-1", "eu-west-3", "global"],
    "failed_regions": [],
    "skipped_regions": [],
    "discovery_failed": false,
    "discovery_error": null
  },
  "regional_breakdown": {
    "us-east-1": { "total_resources": 50, "compliance_score": 0.80 },
    "eu-west-3": { "total_resources": 30, "compliance_score": 0.70 },
    "global": { "total_resources": 20, "compliance_score": 0.65 }
  }
}
```

### Service Layer Details

The application follows a **service-oriented architecture** with clear separation of concerns:

**Core Services** (initialized by `ServiceContainer` in `container.py`):
- `AWSClient` - Wrapper around boto3 with rate limiting and exponential backoff
- `RedisCache` - Caching layer for compliance results (1-hour TTL)
- `PolicyService` - Loads and validates tagging policy from `policies/tagging_policy.json`
- `ComplianceService` - Core compliance checking logic (uses AWS + Policy services)
- `MultiRegionScanner` - Orchestrates parallel multi-region compliance scans
- `AuditService` - SQLite-based audit logging for all tool invocations
- `HistoryService` - SQLite-based storage for compliance scan history
- `SecurityService` - Security event monitoring and rate limiting
- `BudgetTracker` - Tool call budget enforcement (max 100 calls/session)
- `LoopDetector` - Detects repeated identical tool calls (max 3 identical calls)

**Service Dependencies** (managed by `ServiceContainer`):
```
ServiceContainer
  ├── ComplianceService
  │     ├── AWSClient
  │     ├── PolicyService
  │     └── RedisCache (optional)
  ├── MultiRegionScanner
  │     ├── RegionalClientFactory
  │     │     └── AWSClient (per region, cached)
  │     ├── RegionDiscoveryService
  │     └── ComplianceService
  ├── AuditService
  ├── HistoryService
  ├── SecurityService
  ├── BudgetTracker
  └── LoopDetector
```

### MCP Tools (8 Total)

Tools are available via two transports:
- **stdio**: Registered in `stdio_server.py` via `@mcp.tool()` decorators (for Claude Desktop / MCP Inspector)
- **HTTP**: Registered in `mcp_handler.py` and exposed via `/mcp/tools/call` (for remote deployment)

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
- Compliance scan results (configurable TTL, default 1 hour)
- Budget tracking session state
- Loop detection call history
- Security event tracking
- Enabled regions list (for region discovery)

**Cache Configuration:**
- `COMPLIANCE_CACHE_TTL_SECONDS` - TTL for compliance results (default: `3600`, range: 60-86400)
- `REGION_CACHE_TTL_SECONDS` - TTL for enabled regions list (default: `3600`)
- `REDIS_URL` - Redis connection URL (default: `redis://localhost:6379/0`)

**Cache Key Generation:**
Cache keys are SHA256 hashes of normalized query parameters including:
- AWS region
- Resource types (sorted)
- Filters (region, account_id, etc.)
- Severity level
- Scanned regions list (for multi-region)

This ensures that changing any parameter invalidates cached results.

**Bypassing Cache:**
- Use `force_refresh=true` parameter in tool calls to bypass cache
- Multi-region scanner respects the `force_refresh` parameter
- Useful for real-time compliance checks or after infrastructure changes

**Cache Performance:**
- First scan: 3-60 seconds (depending on regions and resource count)
- Cached scan: < 1 second

### Middleware Pipeline

Middleware is applied in this order (from `main.py`):
1. **Authentication** - API key validation (when `AUTH_ENABLED=true`)
2. **CORS** - Origin allowlist enforcement (configurable via `CORS_ALLOWED_ORIGINS`)
3. **RequestSanitization** - Validates headers, size limits, prevents injection
4. **CorrelationID** - Adds correlation IDs for request tracing
5. **BudgetTracking** - Enforces tool call limits per session
6. **LoopDetection** - Detects repeated identical calls

### Production Security (Phase 1.9+)

**Authentication** (`mcp_server/middleware/auth_middleware.py`):
- API key authentication with Bearer token support
- RFC 6750-compliant WWW-Authenticate headers on 401 responses
- Configurable public endpoints bypass (`/health`, `/`, `/docs`)
- Support for multiple API keys via comma-separated `API_KEYS` env var
- CloudWatch metrics emission on authentication failures

**CORS Restriction** (`mcp_server/middleware/cors_middleware.py`):
- Origin allowlist via `CORS_ALLOWED_ORIGINS` env var
- Violation logging to security service
- CloudWatch metrics for CORS violations
- Default permissive (`*`) for backward compatibility

**Bridge Configuration** (`scripts/mcp_bridge.py`):
- `MCP_SERVER_URL` - URL of the MCP server (default: `http://localhost:8080`)
- `MCP_API_KEY` - API key for authentication (optional)
- `MCP_VERIFY_TLS` - Enable TLS certificate verification (default: `true`)
- `MCP_TIMEOUT` - Request timeout in seconds (default: `120`, increased for multi-region scans)
- Proper error handling for 401/403 responses

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
- `RESOURCE_TYPES_CONFIG_PATH` - Path to resource types configuration (default: `config/resource_types.json`)

**Resource Types Configuration** (`config/resource_types.json`):
External JSON file that defines which AWS resource types to scan and how to categorize them:
- `cost_generating_resources` - Resources that generate direct AWS costs (EC2, RDS, S3, etc.)
- `free_resources` - Taggable resources with no direct cost (VPC, Subnet, Security Group, etc.)
- `unattributable_services` - Services with costs but no taggable resources (Bedrock API, Tax, Support, etc.)
- `service_name_mapping` - Maps resource types to Cost Explorer service names

See `docs/RESOURCE_TYPE_CONFIGURATION.md` for full documentation.

**Security Settings** (HTTP transport only):
- `AUTH_ENABLED` - Enable API key authentication (default: `false`)
- `API_KEYS` - Comma-separated list of valid API keys
- `AUTH_REALM` - Realm for WWW-Authenticate header (default: `mcp-server`)
- `CORS_ALLOWED_ORIGINS` - Comma-separated allowed origins (default: `*`)
- `TLS_ENABLED` - Enable TLS/HTTPS (default: `false`)

**Feature Flags**:
- `BUDGET_TRACKING_ENABLED` - Enable tool call budgets (default: `true`)
- `LOOP_DETECTION_ENABLED` - Enable loop detection (default: `true`)
- `SECURITY_MONITORING_ENABLED` - Enable security event monitoring (default: `true`)
- `CLOUDWATCH_ENABLED` - Enable CloudWatch logging (default: `false`)
- `CLOUDWATCH_METRICS_ENABLED` - Enable CloudWatch custom metrics (default: `false`)

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

**EC2 Instances** (state-aware distribution):
- **Tier 1 - Actual Costs**: Uses Cost Explorer per-resource data when available (source: `actual`)
- **Tier 2 - State-Aware Distribution**: For instances without Cost Explorer data:
  - **Stopped instances** (stopped, stopping, terminated, shutting-down): Assigned $0 (compute costs only; EBS costs tracked separately)
  - **Running instances** (running, pending, unknown): Remaining service costs distributed proportionally (source: `estimated`)
  - **Conservative handling**: Unknown states treated as running to avoid underestimation
- **Tier 3 - Proportional Fallback**: When all instances are stopped but service has costs, distributes proportionally with warning (suggests incomplete Cost Explorer data or other EC2 costs like NAT, EBS)

**RDS Databases** (per-resource costs):
- Uses Cost Explorer per-resource data when available (source: `actual`)
- Falls back to even distribution among instances (source: `estimated`)

**Service-Level Costs** (distributed evenly - estimates):
- S3 buckets - Total S3 cost ÷ bucket count
- Lambda functions - Total Lambda cost ÷ function count
- ECS services - Total ECS cost ÷ service count

The `cost_source` field in results indicates: `actual`, `estimated`, or `stopped`.

**Key Changes (2025-01-21)**:
- Implemented state-aware cost attribution for EC2 instances to prevent stopped instances from being incorrectly assigned compute costs
- Added `instance_state` and `instance_type` fields to Resource and UntaggedResource models
- Cost notes now explain state-aware methodology for transparency
- External configuration file for resource types (`config/resource_types.json`)
- Removed free resources (VPC, Subnet, Security Group, etc.) from compliance scans
- Added unattributable services separation (Bedrock API, Tax, Support, etc.)
- Cost attribution now uses Name tag matching instead of RESOURCE_ID dimension (not available in standard Cost Explorer)
- Real production results: 58% attribution gap on $47.99 spend, directly correlating with 55% tagging compliance
- Compliance reports now hide "Cost Impact" column and "Top Violations by Cost Impact" section when all violation costs are $0.00 (typical when using Tagging API which doesn't provide per-resource cost data)
- `age_days` field is now optional (None) when `created_at` is not available (Resource Groups Tagging API doesn't provide creation dates)

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

4. **Regression Tests** (`tests/regression/`) - promptfoo-based API regression
   - 34 test cases validating all 8 MCP tool response structures
   - Custom Python provider calls `POST /mcp/tools/call` on HTTP server
   - Structural assertions (JSON shape, types, value ranges)
   - Business logic assertions (mathematical consistency, cross-field validation) — to be formalized during UAT 1
   - Run with: `cd tests/regression && npx promptfoo@latest eval`
   - Requires HTTP server running: `python run_server.py`
   - CI-compatible: promptfoo returns exit code 1 on assertion failures

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

### ARN Utilities and Shared Code Patterns

**Centralized ARN Parsing** (`mcp_server/utils/arn_utils.py`):

This module provides shared utilities for working with AWS ARNs across all tools, eliminating code duplication and ensuring consistent behavior:

```python
from ..utils.arn_utils import is_valid_arn, parse_arn, service_to_resource_type, extract_resource_id
```

**Available Functions:**
- `is_valid_arn(arn: str) -> bool` - Validate ARN format (supports S3, IAM, EC2, etc.)
- `parse_arn(arn: str) -> dict` - Parse ARN into components (partition, service, region, account, resource, resource_type, resource_id)
- `service_to_resource_type(service: str, resource: str) -> str` - Map AWS service to internal type (e.g., "ec2" + "instance/i-123" → "ec2:instance")
- `extract_resource_id(resource: str) -> str` - Extract resource ID from ARN resource part
- `get_account_from_arn(arn: str) -> str` - Extract AWS account ID
- `get_region_from_arn(arn: str) -> str` - Extract AWS region

**Usage Example:**
```python
arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-abc123"

if is_valid_arn(arn):
    parsed = parse_arn(arn)
    # {
    #   'partition': 'aws',
    #   'service': 'ec2',
    #   'region': 'us-east-1',
    #   'account': '123456789012',
    #   'resource': 'instance/i-abc123',
    #   'resource_type': 'ec2:instance',
    #   'resource_id': 'i-abc123'
    # }
```

**Batch Tag Fetching** (`AWSClient.get_tags_for_arns()`):

Efficient batch API for fetching tags using Resource Groups Tagging API:

```python
# Fetch tags for multiple resources in one API call
tags_by_arn = await aws_client.get_tags_for_arns([arn1, arn2, arn3])
# Returns: {"arn1": {"Owner": "team", ...}, "arn2": {...}, ...}
```

**Performance Benefits:**
- Processes up to 100 ARNs per AWS API call
- **10x faster** than fetching all resources to find specific ones
- Reduces AWS API costs (fewer calls)

**Before (Inefficient):**
```python
# Fetches ALL EC2 instances to find one
resources = await aws_client.get_ec2_instances({})
for resource in resources:
    if resource["resource_id"] == target_id:
        return resource.get("tags", {})
```

**After (Efficient):**
```python
# Fetches only specific ARNs in batch
tags_by_arn = await aws_client.get_tags_for_arns([arn])
tags = tags_by_arn.get(arn, {})
```

**Pydantic Tool Results:**

All tool result classes now use Pydantic models for automatic validation and serialization:

```python
from pydantic import BaseModel, Field, computed_field

class SuggestTagsResult(BaseModel):
    """Result from the suggest_tags tool."""

    resource_arn: str = Field(..., description="ARN of the resource")
    resource_type: str = Field(..., description="Type of resource")
    suggestions: list[TagSuggestion] = Field(default_factory=list)
    current_tags: dict[str, str] = Field(default_factory=dict)
    suggestion_count: int = Field(0)

    def model_post_init(self, __context) -> None:
        """Compute suggestion_count after initialization."""
        object.__setattr__(self, "suggestion_count", len(self.suggestions))
```

**Serialization:**
```python
result = await suggest_tags(...)
json_data = result.model_dump(mode='json')  # Automatic JSON serialization
```

**Benefits:**
- Automatic type validation
- Consistent serialization across all tools
- Better IDE support with auto-completion
- `@computed_field` for derived values
- JSON schema generation for documentation

**Dependency Injection Pattern:**

All tools support optional service injection for better testability:

```python
async def suggest_tags(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_arn: str,
    suggestion_service: Optional[SuggestionService] = None,  # Optional injection
) -> SuggestTagsResult:
    # Use injected service or create one
    service = suggestion_service
    if service is None:
        service = SuggestionService(policy_service)

    return await service.suggest_tags(...)
```

**Tools with DI support:**
- `suggest_tags(suggestion_service=None)`
- `generate_compliance_report(report_service=None)`
- `get_cost_attribution_gap(cost_service=None)`
- `get_violation_history(history_service=None)`

**Testing Benefits:**
```python
# Easy mocking in unit tests
from unittest.mock import Mock

mock_service = Mock()
mock_service.suggest_tags.return_value = [...]

result = await suggest_tags(
    aws_client=client,
    policy_service=policy,
    resource_arn=arn,
    suggestion_service=mock_service  # Injected for testing
)
```

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

## Production Deployment (ECS Fargate)

The production deployment runs on ECS Fargate behind an ALB at `https://mcp.optimnow.io`.

**Architecture:**
- **ECS Cluster**: `mcp-tagging-cluster-prod` (Fargate, Container Insights)
- **Task Definition**: 512 CPU / 1024 MB, two containers:
  - `mcp-server`: Application container from ECR, port 8080
  - `redis`: Redis 7 Alpine sidecar, port 6379 (localhost)
- **EFS**: Persistent storage for SQLite databases (`/mnt/efs`)
- **ECR**: `382598791951.dkr.ecr.us-east-1.amazonaws.com/mcp-tagging-prod`
- **ALB**: TLS termination with ACM certificate, IP-type target group
- **Auto-scaling**: 1-4 tasks, CPU target 70%
- **CloudFormation stack**: `mcp-tagging-prod` (all infrastructure as code)

**Deploy new code:**
```bash
# Full build + push + deploy
./scripts/deploy_ecs.sh

# Just force a new deployment (e.g., after config change)
./scripts/deploy_ecs.sh --deploy-only

# Push existing image only (skip build)
./scripts/deploy_ecs.sh --push-only
```

**ECS Exec (debugging):**
```bash
# Get running task ID
TASK_ID=$(aws ecs list-tasks --cluster mcp-tagging-cluster-prod --service mcp-tagging-service-prod --query 'taskArns[0]' --output text --region us-east-1)

# Shell into MCP server container
aws ecs execute-command --cluster mcp-tagging-cluster-prod --task $TASK_ID --container mcp-server --interactive --command "/bin/sh" --region us-east-1

# Shell into Redis sidecar
aws ecs execute-command --cluster mcp-tagging-cluster-prod --task $TASK_ID --container redis --interactive --command "/bin/sh" --region us-east-1
```

**Key ECS Environment Variables** (set in CloudFormation task definition):
- `REDIS_URL=redis://localhost:6379/0` (sidecar)
- `AUDIT_DB_PATH=/mnt/efs/audit_logs.db` (EFS)
- `HISTORY_DB_PATH=/mnt/efs/compliance_history.db` (EFS)
- `AUTH_ENABLED=true`
- `SCHEDULER_ENABLED=false` (avoid duplicate cron with multiple tasks)
- `API_KEYS` — injected from Secrets Manager

**Note**: EC2 instance and legacy target group were removed in Phase 2.5 cleanup.
ECS Fargate is the sole compute platform.

## Docker Local Development

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

## Phase 1.9 Refactoring Status

Phase 1.9 separates core business logic from the MCP/HTTP transport layer. See [REFACTORING_PLAN.md](REFACTORING_PLAN.md) for the full plan.

**Completed:**
- `ServiceContainer` (`container.py`) -- centralizes all service initialization, replaces scattered globals in `main.py` lifespan
- `CoreSettings` / `ServerSettings` split -- protocol-agnostic config separated from HTTP-specific settings
- `stdio_server.py` -- standard MCP server using FastMCP SDK with all 8 tools, compatible with Claude Desktop and MCP Inspector
- `pyproject.toml` updated with `mcp>=1.0.0` dependency and `finops-tag-compliance` script entry point

**Deferred to Phase 3** (not needed for Phase 2 tool additions, becomes valuable when adding multi-cloud SDKs; see [REFACTORING_PLAN.md](REFACTORING_PLAN.md)):
- `src/` layout reorganization and test import updates
- MCP-specific model extraction
- Session management module (`BudgetTracker`, `LoopDetector`)
- Full decomposition of `mcp_handler.py` (1475 lines) into smaller modules
- HTTP backwards-compatibility server wrapper

## Key Files Reference

- `mcp_server/stdio_server.py` - **FastMCP stdio entry point** (Claude Desktop / MCP Inspector)
- `mcp_server/container.py` - **ServiceContainer** (dependency injection + lifecycle)
- `mcp_server/config.py` - CoreSettings + ServerSettings (split configuration)
- `run_server.py` - HTTP entry point with banner and startup
- `mcp_server/main.py` - FastAPI app, lifespan, HTTP endpoints
- `mcp_server/mcp_handler.py` - Legacy MCP protocol handler (HTTP transport)
- `mcp_server/middleware/auth_middleware.py` - API key authentication middleware
- `mcp_server/middleware/cors_middleware.py` - CORS logging middleware
- `mcp_server/tools/check_tag_compliance.py` - Core compliance scanning tool
- `mcp_server/services/compliance_service.py` - Compliance checking logic
- `mcp_server/services/multi_region_scanner.py` - **Multi-region scanning orchestration**
- `mcp_server/services/region_discovery.py` - AWS region discovery service
- `mcp_server/clients/aws_client.py` - AWS API wrapper
- `mcp_server/clients/regional_client_factory.py` - Regional client creation and caching
- `infrastructure/cloudformation-production.yaml` - Production CloudFormation template (VPC + ALB + ECS Fargate + EFS + ECR)
- `scripts/deploy_ecs.sh` - ECS Fargate deployment script (build → push → deploy)
- `docs/TOOL_LOGIC_REFERENCE.md` - Detailed logic for each tool
- `docs/TESTING_QUICK_START.md` - Testing guide
- `docs/SECURITY_CONFIGURATION.md` - Production security configuration guide
- `docs/ROADMAP.md` - Overall project roadmap (4 phases + Phase 1.9)

## Common Pitfalls & Lessons Learned

Development mistakes encountered during this project. **Claude must check this section before making changes** to avoid repeating known issues.

### Configuration

- **Pydantic Settings + .env conflict**: `CoreSettings` rejects HTTP-specific env vars unless `extra="ignore"` is set in `model_config`. Always use `extra="ignore"` in any Settings subclass that may share an .env file with other Settings classes. (`mcp_server/config.py`)
- **Policy file path hyphen/underscore mismatch**: `.env` had `tagging-policy.json` (hyphen) but actual file was `tagging_policy.json` (underscore). Always check actual filenames match env var values exactly.
- **BOM characters corrupt Python files**: Invisible Byte Order Mark (U+FEFF) from copy-paste causes `SyntaxError: invalid non-printable character`. Use UTF-8 without BOM. Prefer template-based file creation over direct character manipulation.
- **New features must default to disabled**: If a new security feature defaults to enabled, existing deployments break. All new features get `FEATURE_NAME_ENABLED=false` by default.
- **Docker paths differ on Windows vs Linux**: Use `${USERPROFILE}/.aws` on Windows, `~/.aws` on Linux in `docker-compose.yml`. Document both.

### AWS API

- **Cost Explorer is always us-east-1**: The CE client must target `us-east-1` regardless of resource region. Don't create regional CE clients.
- **Resource Groups Tagging API doesn't return creation dates**: `age_days` must be `Optional[int] = None`, not required. Don't show "0 days" when data is unavailable — use `None`.
- **Stopped EC2 instances have zero compute cost**: Don't distribute service costs evenly across all instances. Check `instance_state` first: stopped/terminated = $0 compute. Use 3-tier distribution: actual → state-aware → proportional fallback.
- **IAM permissions must match actual API calls**: Wrong IAM role → no resources found despite correct code. Test all AWS API calls before deploying; document exact permissions in `docs/IAM_PERMISSIONS.md`.
- **SSM Session Manager mangles special characters**: Pipes, quotes, curly braces get corrupted. Use base64-encoded Python one-liners for complex remote commands.
- **AWS credentials file corruption**: Multiple profiles mixed together causes `IncompleteSignature`. Delete and recreate `~/.aws/credentials` if you get signature errors.

### Architecture & Business Logic

- **Don't import MCP into service layer**: Services must be protocol-agnostic. Never `from mcp import ...` inside `mcp_server/services/`. MCP stays in `tools/` and `stdio_server.py` only.
- **Always use injected services, never create new instances**: `get_violation_history` once created a new `HistoryService` instead of using the injected one, reading from a wrong database path. Use DI consistently.
- **Wire all service dependencies through entry points**: Multi-region scanner was built but not passed to tools in `stdio_server.py`. Always wire new services through the full chain.
- **Multi-region conditions can silently disable features**: A `not use_tagging_api` condition blocked multi-region for "all" mode. Remove conditions that disable features without clear warnings.
- **Free resources pollute compliance metrics**: VPC, Subnet, Security Groups inflate violation counts without financial impact. Use `config/resource_types.json` to separate cost-generating, free, and unattributable resources.
- **Hide meaningless $0.00 cost columns**: When Tagging API provides no cost data, displaying "$0.00 Cost Impact" is misleading. Conditionally hide cost sections when all values are zero.
- **Audit BOTH transport entry points when wiring services**: `stdio_server.py` and `mcp_handler.py` are independent entry points. Fixing one doesn't fix the other. When adding `multi_region_scanner` support, 5 of 8 HTTP handlers were missing it while stdio was correct. Always grep both files for the parameter name after wiring. (`mcp_server/mcp_handler.py`, `mcp_server/stdio_server.py`)

### Testing

- **moto not installed by default**: `tests/unit/test_aws_client.py` fails on import. Install with `pip install moto[all]` or skip with `--ignore`.
- **Unit tests that make real AWS calls will hang**: Always mock boto3 in unit tests. Use `asyncio.to_thread()` + mock.
- **Property tests catch edge cases unit tests miss**: Use Hypothesis for validation logic — it generates 100+ test cases automatically and finds boundary conditions.
- **Always test through the full HTTP stack**: Unit tests on services may pass while the HTTP handler has different validation. Use curl/Postman to validate real endpoints.
- **Cross-verify multi-tool consistency during UAT**: `check_tag_compliance` and `find_untagged_resources` use different discovery methods (Tagging API vs service-specific APIs). Small count differences (e.g., 33 vs 29) may be explained by different discovery mechanisms, not bugs. Always document the reason for discrepancies.

### Performance & Caching

- **Never hardcode `force_refresh=True`**: This was left from debugging and made every multi-region scan take 50-60 seconds. Propagate the parameter through all function calls.
- **Include all context in cache keys**: Region, resource types, filters, severity, scanned regions — changing any of these must produce a different cache key. Missing region in cache key returned stale results for wrong region.

### Git & CI

- **Branch protection blocks self-merge**: PRs require an approving review. Cannot self-approve with `gh`. Either have user approve, or bypass in repo settings.
- **Infracost skips docs-only PRs**: This is correct behavior, not an error. Don't debug Infracost "Skipped" status on non-IaC changes.

### Compatibility

- **Python 3.10: `datetime.UTC` doesn't exist**: Use `from datetime import timezone` and `timezone.utc` instead. `datetime.UTC` is Python 3.11+ only.
- **Docker buildx 0.17+ required for compose build**: On older EC2 instances, use `docker build -t image-name .` directly instead of `docker-compose build`.
- **AI agents wrap single values in arrays**: Claude sometimes sends `severity: ["errors_only"]` instead of `"errors_only"`. Add auto-unwrapping for single-element string arrays in input validation.
- **CloudFormation EFSVolumeConfiguration uses `FilesystemId` (lowercase 's')**: The EFS resource itself uses `FileSystemId` (capital 'S'), but the ECS TaskDefinition's `EFSVolumeConfiguration` uses `FilesystemId`. CloudFormation may accept both but logs a validation warning. Always use `FilesystemId` in task definitions. (`infrastructure/cloudformation-production.yaml`)

### Handler Defaults Must Match Function Validation

- **Handler defaults must match tool function's valid set**: `schedule_compliance_audit` handler defaulted `notification_format` to `"markdown"` but the function only accepts `{"email", "slack", "both"}`. Always verify handler defaults against the function's validation logic. (`mcp_server/mcp_handler.py`, `mcp_server/stdio_server.py`)
- **Schema enums must match function validation**: The MCP schema for `schedule_compliance_audit` had `enum: ["markdown", "json", "csv"]` but the function validates against `{"email", "slack", "both"}`. Keep schemas and function validation in sync.
- **Handler must supply defaults when function params are required**: `generate_openops_workflow` defines `resource_types: list[str]` (required) but the handler passes `arguments.get("resource_types")` which is `None` when omitted. Use `arguments.get("resource_types") or ["all"]` in the handler.
- **Don't use `aws_client.session`**: `AWSClient` doesn't expose a boto3 `Session` object. Use `boto3.client("service", region_name=aws_client.region)` to create ad-hoc clients for services not pre-initialized in AWSClient. (`mcp_server/tools/import_aws_tag_policy.py`)

### Documentation

- **Specifications drift quickly**: The Phase 2 spec still referenced 15 tools, bulk tagging, and 8-week timelines months after those decisions changed. Run grep checks after roadmap updates to catch stale references.
- **Always comment hardcoded values**: Cost Explorer's us-east-1 requirement wasn't documented, causing confusion during multi-region setup. If a value is hardcoded for a reason, comment why.

## End-of-Session Protocol

**At the end of every coding session**, Claude must:

1. **Review errors encountered** during the session (failed commands, bugs hit, unexpected behavior)
2. **Check if any are new** (not already listed in "Common Pitfalls & Lessons Learned" above)
3. **Append new pitfalls** to the appropriate category in this section, following the format:
   `- **Short title**: One-line description of what went wrong and what to do instead.`
4. If the pitfall doesn't fit an existing category, create a new one

This ensures the knowledge base grows with each session and mistakes are never repeated.

**Format for new entries:**
```
- **[Short title]**: [What went wrong]. [What to do instead]. ([File or component affected])
```
