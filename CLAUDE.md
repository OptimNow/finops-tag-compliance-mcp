# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

| Action | Command |
|--------|---------|
| Run MCP server (stdio) | `python -m mcp_server.stdio_server` |
| Run all tests | `pytest tests/unit tests/property --ignore=tests/unit/test_aws_client.py` |
| Run unit tests only | `pytest tests/unit --ignore=tests/unit/test_aws_client.py` |
| Format code | `black mcp_server/ tests/` |
| Lint | `ruff check mcp_server/ tests/` |
| Type check | `mypy mcp_server/` |
| Test with MCP Inspector | `npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server` |

**Critical Files:**
- `mcp_server/stdio_server.py` - MCP entry point (Claude Desktop)
- `mcp_server/container.py` - Service container (dependency injection)
- `mcp_server/services/compliance_service.py` - Core compliance logic
- `mcp_server/services/multi_region_scanner.py` - Multi-region orchestration
- `policies/tagging_policy.json` - Tagging policy configuration
- `config/resource_types.json` - Resource types configuration

## Project Overview

This is a **FinOps Tag Compliance MCP Server** — an open-source Model Context Protocol server that provides intelligent AWS resource tagging validation and compliance checking to AI assistants like Claude Desktop. It goes beyond basic tag reading to provide schema validation, cost attribution analysis, and ML-powered tag suggestions.

**License**: Apache 2.0
**Transport**: stdio (standard MCP, for Claude Desktop and MCP Inspector)
**Production deployment**: For HTTP/API deployment on AWS (ECS Fargate, CloudFormation), see the private [finops-tag-compliance-deploy](https://github.com/OptimNow/finops-tag-compliance-deploy) repo.

## Development Commands

### Running the Server

```bash
# Stdio transport (standard MCP — for Claude Desktop / MCP Inspector)
python -m mcp_server.stdio_server

# Or after pip install:
finops-tag-compliance

# Test with MCP Inspector
npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server
```

### Testing

```bash
# Run unit + property tests
pytest tests/unit tests/property --ignore=tests/unit/test_aws_client.py

# Specific file
pytest tests/unit/test_compliance_service.py

# With coverage
pytest tests/ --cov=mcp_server --cov-report=html --ignore=tests/unit/test_aws_client.py

# Exclude integration tests (require real AWS credentials)
pytest tests/ -m "not integration" --ignore=tests/unit/test_aws_client.py
```

**Note**: `tests/unit/test_aws_client.py` requires `moto` which is not installed by default. Always `--ignore` it unless you have `pip install moto[aws]`.

### Code Quality

```bash
black mcp_server/ tests/
ruff check mcp_server/ tests/
mypy mcp_server/
```

## Architecture

### Design Philosophy: Core Library + MCP Layer

This project deliberately separates **protocol-agnostic business logic** (reusable core library) from **MCP-specific code**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     MCP PROTOCOL / TRANSPORT LAYER                      │
├─────────────────────────────────────────────────────────────────────────┤
│  stdio_server.py     → FastMCP stdio transport (Claude Desktop/Inspector│
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
│  CoreSettings (protocol-agnostic configuration via env vars)            │
├─────────────────────────────────────────────────────────────────────────┤
│  config.py → CoreSettings (all configuration)                           │
│  models/   → 17 Pydantic model files with strict typing + JSON schemas  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          CLIENTS LAYER                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  clients/aws_client.py   → Boto3 wrapper with rate limiting, backoff    │
│  clients/cache.py        → Redis caching layer (optional)               │
└─────────────────────────────────────────────────────────────────────────┘
```

**Why this separation matters:**
- Services can be imported directly without MCP: `from mcp_server.services import ComplianceService`
- Easy to add CLI, REST API, webhook, or Lambda interface without touching business logic
- Services are testable in isolation (unit tests mock only clients, not MCP layer)

### Repository structure

```
finops-tag-compliance-mcp/
├── mcp_server/
│   ├── stdio_server.py      # ★ FastMCP stdio entry point (Claude Desktop / Inspector)
│   ├── container.py         # ★ ServiceContainer (dependency injection + lifecycle)
│   ├── config.py            # CoreSettings (environment-based configuration)
│   ├── models/              # Pydantic data models (17 files)
│   ├── services/            # Core business logic (12 services, protocol-agnostic)
│   ├── tools/               # 14 MCP tool adapters (thin wrappers)
│   ├── clients/             # AWS client wrapper, Redis cache, regional factory
│   └── utils/               # Correlation IDs, validation, error sanitization
├── policies/
│   └── tagging_policy.json  # Tagging policy configuration
├── config/
│   ├── resource_types.json        # Resource types configuration
│   └── resource_types.schema.json # JSON Schema for resource types
├── examples/
│   ├── claude_desktop_config_stdio.json  # Claude Desktop config example
│   └── aws_tag_policy_example.json      # AWS Organizations policy example
├── scripts/
│   └── convert_aws_policy.py  # Convert AWS Organizations policy to MCP format
├── tests/
│   ├── unit/                # Unit tests (mock all dependencies)
│   ├── property/            # Hypothesis-based property tests
│   ├── integration/         # End-to-end tests (require AWS credentials)
│   └── uat/                 # UAT scenario definitions
├── docs/
│   ├── USER_MANUAL.md
│   ├── TOOL_LOGIC_REFERENCE.md
│   ├── TAGGING_POLICY_GUIDE.md
│   ├── TESTING_QUICK_START.md
│   ├── RESOURCE_TYPE_CONFIGURATION.md
│   ├── security/IAM_PERMISSIONS.md
│   └── diagrams/            # Architecture, sequence, state, component diagrams
├── pyproject.toml           # Package configuration (pip install)
├── LICENSE                  # Apache 2.0
└── README.md
```

### Multi-Region Scanning

The server supports scanning AWS resources across all enabled regions in parallel.

**Key Components:**
- `MultiRegionScanner` - Coordinates parallel scanning across regions using asyncio
- `RegionDiscoveryService` - Queries EC2 to find enabled regions in the account
- `RegionalClientFactory` - Creates and caches regional `AWSClient` instances

**How It Works:**
1. `RegionDiscoveryService` queries EC2 to get all enabled regions
2. `RegionalClientFactory` creates an `AWSClient` for each region (cached)
3. `MultiRegionScanner.scan_all_regions()` runs compliance checks in parallel
4. Results are aggregated into a `MultiRegionComplianceResult` with regional breakdown

**Configuration:**
- Multi-region scanning is **always enabled** by default
- `ALLOWED_REGIONS` - Restrict scanning to specific regions (comma-separated)
- `MAX_CONCURRENT_REGIONS` - Maximum regions to scan in parallel (default: `5`)
- `REGION_SCAN_TIMEOUT_SECONDS` - Timeout per region (default: `60`)
- `AWS_REGION` - Default region for Cost Explorer (always `us-east-1` for costs)

**Global vs Regional Resources:**
- **Global resources** (S3, IAM): Always scanned regardless of region filters, reported as region="global"
- **Regional resources** (EC2, RDS, Lambda): Respect region filters

**Region Discovery Fallback:**
If EC2 DescribeRegions fails, the scanner falls back to the default region only. Check `region_metadata.discovery_failed` to detect this.

### Service Layer Details

**Core Services** (initialized by `ServiceContainer` in `container.py`):
- `AWSClient` - Wrapper around boto3 with rate limiting and exponential backoff
- `RedisCache` - Optional caching layer for compliance results (1-hour TTL)
- `PolicyService` - Loads and validates tagging policy from `policies/tagging_policy.json`
- `ComplianceService` - Core compliance checking logic
- `MultiRegionScanner` - Orchestrates parallel multi-region compliance scans
- `AuditService` - SQLite-based audit logging for all tool invocations
- `HistoryService` - SQLite-based storage for compliance scan history
- `BudgetTracker` - Tool call budget enforcement (max 100 calls/session)
- `LoopDetector` - Detects repeated identical tool calls (max 3 identical calls)

### MCP Tools (14 Total)

Tools are registered in `stdio_server.py` via `@mcp.tool()` decorators:

1. `check_tag_compliance` - Scan resources, calculate compliance score
2. `find_untagged_resources` - Find resources missing required tags
3. `validate_resource_tags` - Validate specific resources by ARN
4. `get_cost_attribution_gap` - Calculate financial impact of tagging gaps
5. `suggest_tags` - ML-powered tag value suggestions
6. `get_tagging_policy` - Return policy configuration
7. `generate_compliance_report` - Generate JSON/CSV/Markdown reports
8. `get_violation_history` - Historical compliance trends
9. `detect_tag_drift` - Find unexpected tag changes
10. `generate_custodian_policy` - Create Cloud Custodian YAML
11. `generate_openops_workflow` - Build remediation workflows
12. `schedule_compliance_audit` - Configure recurring audits
13. `export_violations_csv` - Export violations for spreadsheets
14. `import_aws_tag_policy` - Import from AWS Organizations

Each tool is implemented in `mcp_server/tools/<tool_name>.py` with:
- Input validation using Pydantic models
- Result models in `mcp_server/models/`
- Integration with audit logging
- Budget tracking and loop detection

### AWS Client Design

The `AWSClient` (`mcp_server/clients/aws_client.py`) wraps boto3 with:
- **Authentication**: Uses standard AWS credential chain (env vars, profiles, instance profiles)
- **Rate limiting**: 100ms minimum interval between calls to same service
- **Exponential backoff**: Automatic retries with adaptive mode
- **Multi-service**: EC2, RDS, S3, Lambda, ECS, Cost Explorer, Resource Groups Tagging API

**Important**: Cost Explorer client is always `us-east-1` regardless of resource region.

### Caching Strategy

Redis caching (`mcp_server/clients/cache.py`) is optional. Without Redis, the server works fine but doesn't cache results between invocations.

With Redis:
- Compliance scan results cached (configurable TTL, default 1 hour)
- Enabled regions list cached
- Use `force_refresh=true` to bypass cache

### Error Handling

All errors go through sanitization (`mcp_server/utils/error_sanitization.py`):
- **Internal logging**: Full details including stack traces
- **User response**: Sanitized error codes and user-friendly messages
- **No sensitive data**: Paths, credentials, and internal details are never exposed

## Configuration

All configuration is via environment variables (see `mcp_server/config.py`):

**Core Settings**:
- `POLICY_PATH` or `POLICY_FILE_PATH` - Path to tagging policy JSON (default: `policies/tagging_policy.json`)
- `AWS_REGION` - Default AWS region (default: `us-east-1`)
- `REDIS_URL` - Redis connection URL (default: `redis://localhost:6379/0`, optional)
- `HISTORY_DB_PATH` - SQLite database for compliance history (default: `compliance_history.db`)
- `AUDIT_DB_PATH` - SQLite database for audit logs (default: `audit_logs.db`)
- `RESOURCE_TYPES_CONFIG_PATH` - Path to resource types configuration (default: `config/resource_types.json`)

**Feature Flags**:
- `BUDGET_TRACKING_ENABLED` - Enable tool call budgets (default: `true`)
- `LOOP_DETECTION_ENABLED` - Enable loop detection (default: `true`)

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

## Cost Attribution Logic

Cost calculation varies by AWS service:

**EC2 Instances** (state-aware):
- **Tier 1**: Uses Cost Explorer per-resource data when available
- **Tier 2**: State-aware distribution (stopped = $0, running = proportional)
- **Tier 3**: Proportional fallback when all instances are stopped but costs exist

**RDS/S3/Lambda/ECS**: Per-resource costs when available, otherwise evenly distributed.

The `cost_source` field in results indicates: `actual`, `estimated`, or `stopped`.

## Testing Philosophy

This project uses a **3-layer testing strategy**:

1. **Unit Tests** (`tests/unit/`) - Fast, isolated, mock all dependencies
2. **Property Tests** (`tests/property/`) - Hypothesis-based generative testing
3. **Integration Tests** (`tests/integration/`) - End-to-end with real AWS (requires credentials)

**Writing Tests**:
- Every new tool must have unit and property tests
- Use fixtures from `tests/conftest.py` for common test data
- Property tests should reference requirement numbers in docstrings

## Important Patterns

### Async/Await Consistency

All I/O operations use `async`/`await`. When adding new AWS calls, use `asyncio.to_thread()` to run boto3 sync calls in thread pool.

### Pydantic Models Everywhere

All data structures are Pydantic models for automatic validation, serialization, and type safety.

### Correlation IDs

Every request gets a correlation ID (auto-generated UUID):
- Propagated through all logs
- Included in audit logs
- Available via `get_correlation_id()` utility

### Input Validation

All user inputs go through validation (`mcp_server/utils/input_validation.py`):
- Maximum string lengths (1000 chars)
- Maximum list sizes (100 items)
- No SQL injection patterns
- No path traversal attempts
- ARN format validation

### Dependency Injection Pattern

Tools support optional service injection for testability:

```python
async def suggest_tags(
    aws_client: AWSClient,
    policy_service: PolicyService,
    resource_arn: str,
    suggestion_service: Optional[SuggestionService] = None,
) -> SuggestTagsResult:
    service = suggestion_service or SuggestionService(policy_service)
    return await service.suggest_tags(...)
```

## AWS Permissions Required

Read-only permissions (see `docs/security/IAM_PERMISSIONS.md`):
- `ec2:DescribeInstances`, `ec2:DescribeTags`, `ec2:DescribeRegions`
- `rds:DescribeDBInstances`, `rds:ListTagsForResource`
- `s3:ListAllMyBuckets`, `s3:GetBucketTagging`
- `lambda:ListFunctions`, `lambda:ListTags`
- `ecs:ListServices`, `ecs:ListTagsForResource`
- `ce:GetCostAndUsage` (for cost data)
- `tag:GetResources` (Resource Groups Tagging API)

**No write permissions required.**

## Common Tasks

### Adding a New MCP Tool

1. Create tool module in `mcp_server/tools/<tool_name>.py`
2. Define input/output Pydantic models in `mcp_server/models/`
3. Implement tool function with async signature
4. Register tool in `stdio_server.py` via `@mcp.tool()` decorator
5. Write unit and property tests

### Modifying the Tagging Policy

Edit `policies/tagging_policy.json` directly. Changes take effect on server restart.

### Adding Support for New AWS Resource Types

1. Add boto3 client to `AWSClient.__init__()`
2. Implement `list_<resource>` method in `AWSClient`
3. Add resource type to `ResourceType` enum in `mcp_server/models/enums.py`
4. Update policy validation to support new resource type
5. Add cost fetching logic if Cost Explorer supports per-resource costs

### Debugging Tool Invocations

1. Review audit logs in `audit_logs.db`
2. Check correlation ID in logs to trace request
3. Use `LOG_LEVEL=DEBUG` environment variable for verbose output
4. For AWS errors, check IAM permissions

## Key Files Reference

- `mcp_server/stdio_server.py` - **FastMCP stdio entry point** (Claude Desktop / MCP Inspector)
- `mcp_server/container.py` - **ServiceContainer** (dependency injection + lifecycle)
- `mcp_server/config.py` - CoreSettings (environment-based configuration)
- `mcp_server/tools/check_tag_compliance.py` - Core compliance scanning tool
- `mcp_server/services/compliance_service.py` - Compliance checking logic
- `mcp_server/services/multi_region_scanner.py` - Multi-region scanning orchestration
- `mcp_server/clients/aws_client.py` - AWS API wrapper
- `mcp_server/clients/regional_client_factory.py` - Regional client creation and caching
- `docs/TOOL_LOGIC_REFERENCE.md` - Detailed logic for each tool
- `docs/TESTING_QUICK_START.md` - Testing guide

## Common Pitfalls & Lessons Learned

Development mistakes encountered during this project. **Claude must check this section before making changes** to avoid repeating known issues.

### Configuration

- **Pydantic Settings + .env conflict**: `CoreSettings` rejects unknown env vars unless `extra="ignore"` is set in `model_config`. Always use `extra="ignore"` in any Settings subclass. (`mcp_server/config.py`)
- **Policy file path hyphen/underscore mismatch**: Always check actual filenames match env var values exactly.
- **BOM characters corrupt Python files**: Invisible Byte Order Mark (U+FEFF) from copy-paste causes `SyntaxError`. Use UTF-8 without BOM.
- **New features must default to disabled**: All new features get `FEATURE_NAME_ENABLED=false` by default.

### AWS API

- **Cost Explorer is always us-east-1**: The CE client must target `us-east-1` regardless of resource region.
- **Resource Groups Tagging API doesn't return creation dates**: `age_days` must be `Optional[int] = None`, not required.
- **Stopped EC2 instances have zero compute cost**: Use 3-tier distribution: actual → state-aware → proportional fallback.
- **IAM permissions must match actual API calls**: Wrong IAM role → no resources found despite correct code.

### Architecture & Business Logic

- **Don't import MCP into service layer**: Services must be protocol-agnostic. MCP stays in `tools/` and `stdio_server.py` only.
- **Always use injected services, never create new instances**: Use DI consistently through the `ServiceContainer`.
- **Wire all service dependencies through entry points**: Always wire new services through `stdio_server.py`.
- **Free resources pollute compliance metrics**: Use `config/resource_types.json` to separate cost-generating, free, and unattributable resources.
- **Hide meaningless $0.00 cost columns**: Conditionally hide cost sections when all values are zero.

### Testing

- **moto not installed by default**: `tests/unit/test_aws_client.py` fails on import. Skip with `--ignore`.
- **Unit tests that make real AWS calls will hang**: Always mock boto3 in unit tests.
- **Property tests catch edge cases unit tests miss**: Use Hypothesis for validation logic.
- **AI agents wrap single values in arrays**: Claude sometimes sends `severity: ["errors_only"]` instead of `"errors_only"`. Add auto-unwrapping for single-element string arrays in input validation.

### Performance & Caching

- **Never hardcode `force_refresh=True`**: Propagate the parameter through all function calls.
- **Include all context in cache keys**: Region, resource types, filters, severity, scanned regions — changing any must produce a different cache key.
- **Claude Desktop has a 60-second MCP client timeout**: This is hardcoded in the MCP TypeScript SDK and cannot be changed. Our server-side timeout (300s) is irrelevant if the client gives up at 60s. Tool docstrings must instruct LLMs to scan in batches of 4-6 resource types, never use `["all"]` on Claude Desktop. (`mcp_server/stdio_server.py` docstrings)
- **`tool_execution_timeout_seconds` is dead code**: The config field exists but is never referenced anywhere. Real timeouts are per-region in `multi_region_scanner.py` via `asyncio.wait_for()` with `ALL_MODE_DEFAULT_TIMEOUT_SECONDS = 180`.
- **LLMs guess resource types instead of reading the policy**: When told to "check compliance", Claude picks common types (EC2, S3, Lambda) and misses Bedrock, DynamoDB, ECS, etc. Tool docstrings now instruct LLMs to call `get_tagging_policy` first. The `get_tagging_policy` response includes an `all_applicable_resource_types` helper field.

### Git & Repository Hygiene

- **Gitignored files can still be tracked**: If a file was committed before the `.gitignore` rule was added, git continues tracking it. Use `git rm --cached <file>` to remove from tracking without deleting the file. Always verify with `git ls-files` after adding gitignore rules.
- **Never commit `.claude/settings.local.json`**: This file can contain sensitive data (API keys, tokens, paths). It should be in `.gitignore` and never tracked. If accidentally committed, remove with `git rm --cached` and rotate any exposed credentials.
- **Hypothesis cache pollutes git history**: The `.hypothesis/` directory generates hundreds of cache files. Ensure it's in `.gitignore` before running property tests for the first time.

### Compatibility

- **Python 3.10: `datetime.UTC` doesn't exist**: Use `from datetime import timezone` and `timezone.utc` instead. `datetime.UTC` is Python 3.11+ only.
- **Don't use `aws_client.session`**: `AWSClient` doesn't expose a boto3 `Session` object. Use `boto3.client("service", region_name=aws_client.region)` to create ad-hoc clients.

## End-of-Session Protocol

**At the end of every coding session**, Claude must:

1. **Review errors encountered** during the session
2. **Check if any are new** (not already in "Common Pitfalls" above)
3. **Append new pitfalls** to the appropriate category

**Format for new entries:**
```
- **[Short title]**: [What went wrong]. [What to do instead]. ([File or component affected])
```
