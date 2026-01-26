# Refactoring Plan: Core Library + MCP Server Separation

## Executive Summary

This plan describes how to refactor `finops-tag-compliance-mcp` from a monolithic FastAPI HTTP server into two cleanly separated layers:

1. **Core Library** (`finops_tag_compliance`) -- pure Python, importable, zero HTTP/MCP dependency
2. **MCP Server** (`finops_tag_compliance_mcp`) -- thin wrapper exposing the core library via MCP protocol (stdio primary, HTTP optional)

---

## Phase 1: Current Architecture Analysis

### 1.1 What Exists Today

```
mcp_server/
  main.py              FastAPI app + lifespan (service init + HTTP routes + middleware)
  mcp_handler.py       1475-line monolith (tool registration, validation, budget, loops, audit, security, error handling)
  config.py            Pydantic Settings (mixes core config with HTTP config)
  models/              16 Pydantic model files (35+ models)
  services/            9 service classes (core business logic)
  tools/               8 tool adapter functions (thin wrappers)
  clients/             AWSClient (boto3 wrapper), RedisCache
  middleware/           BudgetTracker, AuditMiddleware, RequestSanitization
  utils/               ARN utils, correlation IDs, loop detection, input validation, error sanitization, CloudWatch
```

### 1.2 Coupling Assessment

**Already well-separated (low coupling):**
- `services/` -- ZERO knowledge of MCP or HTTP. Pure business logic. These are the core of the library.
- `models/` -- Pydantic models with no protocol dependency (except a few HTTP-specific ones like `HealthStatus`, `BudgetExhaustedResponse`).
- `clients/` -- `AWSClient` and `RedisCache` are protocol-agnostic.
- `tools/` -- Thin async functions that call services. No HTTP or MCP imports. These are essentially the **public API** of the core library.
- `utils/arn_utils.py`, `utils/resource_utils.py`, `utils/resource_type_config.py`, `utils/input_validation.py`, `utils/error_sanitization.py` -- All reusable, no HTTP dependency.

**Tightly coupled (needs splitting):**

| Component | Problem | What to do |
|---|---|---|
| `main.py` (272 lines) | FastAPI app creation, lifespan (service initialization), HTTP routes, middleware stack, global exception handler -- all in one file. | Split: service initialization goes to core library's `ServiceContainer`. HTTP routes stay in MCP server layer. |
| `mcp_handler.py` (1475 lines) | Combines MCP-specific concerns (tool registration, JSON schemas, response formatting) with reusable concerns (input validation, budget tracking, loop detection, audit logging, security monitoring, error sanitization). | Split: reusable orchestration logic becomes a core library component. MCP-specific tool registration and response formatting stays in server layer. |
| `config.py` (272 lines) | Mixes core settings (AWS region, policy path, Redis URL, DB paths) with HTTP settings (host, port, CORS) and MCP-session settings (budget, loop detection). | Split into `CoreSettings` (core library) and `ServerSettings` (MCP server, extends CoreSettings). |
| `middleware/sanitization_middleware.py` | Pure HTTP middleware (validates headers, request size, CORS). | Stays in MCP server layer only. |
| `middleware/budget_middleware.py` | `BudgetTracker` is session management, not HTTP-specific. Uses Redis. Could be core or server. | Move to core library as a reusable session manager. |
| `utils/correlation.py` | `CorrelationIDMiddleware` is HTTP-specific. `get_correlation_id()` / `set_correlation_id()` are reusable. | Split: utility functions to core, middleware stays in server layer. |
| `utils/loop_detection.py` | `LoopDetector` is session management. Not HTTP-specific. | Move to core library. |
| `utils/cloudwatch_logger.py` | Reusable logging, but has CloudWatch dependency. | Move to core library (optional dependency). |
| `models/health.py` | `HealthStatus`, `BudgetHealthInfo`, etc. are HTTP endpoint models. | Stay in MCP server layer. |
| `models/budget.py` | `BudgetExhaustedResponse` has `to_mcp_content()` method (MCP-specific). `BudgetStatus` is generic. | Split: `BudgetStatus` to core, `BudgetExhaustedResponse` to server. |
| `models/loop_detection.py` | `LoopDetectedResponse` has `to_mcp_content()` method (MCP-specific). `LoopDetectionMetrics` is generic. | Split: metrics to core, MCP response to server. |
| `pyproject.toml` | Lists `fastapi` and `uvicorn` as core dependencies. | Core library should only depend on `pydantic`, `boto3`, `redis`. FastAPI/uvicorn become server-only deps. |

### 1.3 Dependency Map

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          HTTP/MCP LAYER (current main.py)                     │
│  FastAPI app, routes, CORS, RequestSanitization, CorrelationIDMiddleware      │
│  Prometheus metrics endpoint, health endpoint                                 │
└──────────────────────────────────────────┬───────────────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      MCP HANDLER (current mcp_handler.py)                     │
│  Tool registration, JSON schema definitions, MCPToolResult formatting         │
│  Budget check, loop check, security check, input validation, audit logging    │
│  Error sanitization for client responses                                      │
└──────────────────────────────────────────┬───────────────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         TOOLS (current tools/)                                │
│  8 async functions: check_tag_compliance, find_untagged_resources, etc.       │
│  Each calls services + returns Pydantic models                                │
└──────────────────────────────────────────┬───────────────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       SERVICES (current services/)                            │
│  ComplianceService, PolicyService, CostService, SuggestionService,            │
│  ReportService, HistoryService, AuditService, SecurityService, MetricsService │
└──────────────────────────────────────────┬───────────────────────────────────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                   MODELS + CLIENTS + UTILS (current)                          │
│  35+ Pydantic models, AWSClient (boto3), RedisCache, ARN utils, etc.          │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key insight:** The bottom 3 layers (tools, services, models/clients/utils) have **no knowledge of HTTP or MCP**. They are already a de facto core library. The refactoring is primarily about:
1. Formalizing the boundary
2. Extracting the reusable parts of `mcp_handler.py`
3. Splitting `config.py`
4. Adding a proper MCP stdio server using the `mcp` Python SDK
5. Restructuring the package layout

---

## Phase 2: Target Architecture Design

### 2.1 Package Layout

```
finops-tag-compliance-mcp/
│
├── src/
│   ├── finops_tag_compliance/                  # CORE LIBRARY (pip-installable)
│   │   ├── __init__.py                         # Public API exports
│   │   ├── config.py                           # CoreSettings (AWS, Redis, policy, DB paths)
│   │   │
│   │   ├── models/                             # All Pydantic data models
│   │   │   ├── __init__.py
│   │   │   ├── compliance.py                   # ComplianceResult
│   │   │   ├── violations.py                   # Violation, ViolationType, Severity
│   │   │   ├── policy.py                       # TagPolicy, RequiredTag, OptionalTag
│   │   │   ├── enums.py                        # ViolationType, Severity
│   │   │   ├── resource.py                     # Resource
│   │   │   ├── untagged.py                     # UntaggedResource, UntaggedResourcesResult
│   │   │   ├── cost_attribution.py             # CostAttributionGapResult, CostBreakdown
│   │   │   ├── validation.py                   # ResourceValidationResult, ValidateResourceTagsResult
│   │   │   ├── suggestions.py                  # TagSuggestion
│   │   │   ├── report.py                       # ComplianceReport, ReportFormat, ViolationRanking
│   │   │   ├── history.py                      # ComplianceHistoryEntry, ComplianceHistoryResult
│   │   │   ├── audit.py                        # AuditLogEntry, AuditStatus
│   │   │   └── budget.py                       # BudgetStatus (generic, no MCP methods)
│   │   │
│   │   ├── services/                           # Core business logic (unchanged)
│   │   │   ├── __init__.py
│   │   │   ├── compliance_service.py
│   │   │   ├── policy_service.py
│   │   │   ├── cost_service.py
│   │   │   ├── suggestion_service.py
│   │   │   ├── report_service.py
│   │   │   ├── audit_service.py
│   │   │   ├── history_service.py
│   │   │   └── security_service.py             # (remove set_security_service/get_ global state)
│   │   │
│   │   ├── api/                                # Public function API (renamed from tools/)
│   │   │   ├── __init__.py                     # Exports: check_compliance, find_untagged, etc.
│   │   │   ├── check_compliance.py             # Was: tools/check_tag_compliance.py
│   │   │   ├── find_untagged.py                # Was: tools/find_untagged_resources.py
│   │   │   ├── validate_tags.py                # Was: tools/validate_resource_tags.py
│   │   │   ├── cost_attribution.py             # Was: tools/get_cost_attribution_gap.py
│   │   │   ├── suggest_tags.py                 # Was: tools/suggest_tags.py
│   │   │   ├── tagging_policy.py               # Was: tools/get_tagging_policy.py
│   │   │   ├── compliance_report.py            # Was: tools/generate_compliance_report.py
│   │   │   └── violation_history.py            # Was: tools/get_violation_history.py
│   │   │
│   │   ├── clients/                            # External clients (unchanged)
│   │   │   ├── __init__.py
│   │   │   ├── aws_client.py
│   │   │   └── cache.py
│   │   │
│   │   ├── utils/                              # Shared utilities
│   │   │   ├── __init__.py
│   │   │   ├── arn_utils.py
│   │   │   ├── resource_utils.py
│   │   │   ├── resource_type_config.py
│   │   │   ├── input_validation.py
│   │   │   ├── error_sanitization.py
│   │   │   ├── correlation.py                  # Just get/set_correlation_id (no HTTP middleware)
│   │   │   └── cloudwatch_logger.py
│   │   │
│   │   ├── session/                            # Session management (extracted from middleware)
│   │   │   ├── __init__.py
│   │   │   ├── budget_tracker.py               # Was: middleware/budget_middleware.py
│   │   │   └── loop_detector.py                # Was: utils/loop_detection.py
│   │   │
│   │   └── container.py                        # ServiceContainer: initializes all services
│   │
│   └── finops_tag_compliance_mcp/              # MCP SERVER (thin wrapper)
│       ├── __init__.py
│       ├── server.py                           # FastMCP server with stdio transport
│       ├── http_server.py                      # Optional FastAPI HTTP transport (backwards compat)
│       ├── config.py                           # ServerSettings extends CoreSettings (host, port)
│       ├── models/                             # MCP-specific response models
│       │   ├── __init__.py
│       │   ├── health.py                       # HealthStatus, BudgetHealthInfo
│       │   ├── mcp_responses.py                # BudgetExhaustedResponse, LoopDetectedResponse
│       │   └── observability.py                # GlobalMetrics, SessionMetrics, etc.
│       └── middleware/                          # HTTP-only middleware
│           ├── __init__.py
│           └── sanitization.py                 # RequestSanitizationMiddleware
│
├── policies/                                   # Tagging policy definitions
│   └── tagging_policy.json
│
├── config/                                     # Resource type configuration
│   └── resource_types.json
│
├── tests/                                      # All tests
│   ├── unit/
│   ├── property/
│   ├── integration/
│   └── conftest.py
│
├── pyproject.toml                              # Dual package configuration
├── README.md
└── CLAUDE.md
```

### 2.2 Dependency Diagram (Target)

```
┌───────────────────────────────────────────────────────────────────┐
│                    finops_tag_compliance_mcp                       │
│               (MCP Server - thin wrapper)                         │
│                                                                   │
│  server.py     -- FastMCP + stdio transport, tool registration    │
│  http_server.py -- Optional FastAPI HTTP transport                │
│  config.py     -- ServerSettings(host, port, cors, transport)     │
│  middleware/   -- HTTP request sanitization                       │
│  models/       -- HealthStatus, MCP response models               │
│                                                                   │
│  Dependencies: mcp>=1.0, fastapi (optional), uvicorn (optional)   │
└──────────────────────────────┬────────────────────────────────────┘
                               │ imports
                               ▼
┌───────────────────────────────────────────────────────────────────┐
│                    finops_tag_compliance                           │
│               (Core Library - pure Python)                        │
│                                                                   │
│  api/          -- 8 public functions (the "tool" logic)           │
│  services/     -- 9 service classes (business logic)              │
│  models/       -- 35+ Pydantic data models                        │
│  clients/      -- AWSClient, RedisCache                           │
│  utils/        -- ARN parsing, validation, error handling         │
│  session/      -- BudgetTracker, LoopDetector                     │
│  container.py  -- ServiceContainer (dependency wiring)            │
│  config.py     -- CoreSettings (AWS, Redis, policy, DB paths)     │
│                                                                   │
│  Dependencies: pydantic, boto3, redis, python-dotenv              │
│  NO: fastapi, uvicorn, mcp                                        │
└───────────────────────────────────────────────────────────────────┘
```

### 2.3 Public API of Core Library

The core library's `__init__.py` should export a clean, usable API:

```python
# finops_tag_compliance/__init__.py

# High-level API functions (the 8 tools, renamed for Pythonic usage)
from .api import (
    check_compliance,
    find_untagged_resources,
    validate_resource_tags,
    get_cost_attribution_gap,
    suggest_tags,
    get_tagging_policy,
    generate_compliance_report,
    get_violation_history,
)

# Service classes (for advanced usage / direct instantiation)
from .services import (
    ComplianceService,
    PolicyService,
    CostService,
    SuggestionService,
    ReportService,
    HistoryService,
    AuditService,
)

# Clients
from .clients import AWSClient, RedisCache

# Configuration
from .config import CoreSettings

# Service container
from .container import ServiceContainer

# Models
from .models import (
    ComplianceResult,
    Violation,
    ViolationType,
    Severity,
    Resource,
    UntaggedResource,
    TagPolicy,
    TagSuggestion,
    CostAttributionGapResult,
    ComplianceReport,
    # ... etc
)
```

**Usage example (without MCP):**

```python
from finops_tag_compliance import ServiceContainer, check_compliance

# Initialize all services
container = ServiceContainer(
    aws_region="us-east-1",
    policy_path="policies/tagging_policy.json",
)
await container.initialize()

# Use the high-level API
result = await check_compliance(
    compliance_service=container.compliance_service,
    resource_types=["ec2:instance", "rds:db"],
    severity="errors_only",
)

print(f"Score: {result.compliance_score}")
print(f"Violations: {len(result.violations)}")
```

### 2.4 ServiceContainer

A new class that handles dependency wiring. This replaces the service initialization code currently in `main.py`'s lifespan:

```python
# finops_tag_compliance/container.py

class ServiceContainer:
    """
    Wires together all services with proper dependency injection.
    Replaces the scattered initialization in main.py lifespan.
    """

    def __init__(
        self,
        aws_region: str = "us-east-1",
        policy_path: str = "policies/tagging_policy.json",
        redis_url: str | None = "redis://localhost:6379/0",
        audit_db_path: str = "audit_logs.db",
        history_db_path: str = "compliance_history.db",
        settings: CoreSettings | None = None,
    ):
        ...

    async def initialize(self) -> None:
        """Initialize all services (Redis, AWS, policy, etc.)"""
        ...

    async def shutdown(self) -> None:
        """Clean up connections."""
        ...

    # Accessor properties
    @property
    def aws_client(self) -> AWSClient: ...
    @property
    def policy_service(self) -> PolicyService: ...
    @property
    def compliance_service(self) -> ComplianceService: ...
    @property
    def cost_service(self) -> CostService: ...
    @property
    def audit_service(self) -> AuditService: ...
    @property
    def history_service(self) -> HistoryService: ...
    # ... etc
```

### 2.5 MCP Server (stdio)

The MCP server becomes a thin wrapper using the `mcp` Python SDK:

```python
# finops_tag_compliance_mcp/server.py

from mcp.server.fastmcp import FastMCP
from finops_tag_compliance import ServiceContainer

mcp = FastMCP("finops-tag-compliance")
container: ServiceContainer | None = None

@mcp.tool()
async def check_tag_compliance(
    resource_types: list[str],
    filters: dict | None = None,
    severity: str = "all",
    store_snapshot: bool = False,
    force_refresh: bool = False,
) -> dict:
    """Check tag compliance for AWS resources. ..."""
    from finops_tag_compliance import check_compliance

    result = await check_compliance(
        compliance_service=container.compliance_service,
        resource_types=resource_types,
        filters=filters,
        severity=severity,
        history_service=container.history_service,
        store_snapshot=store_snapshot,
        force_refresh=force_refresh,
    )
    return result.model_dump(mode="json")

# ... 7 more tool registrations ...

if __name__ == "__main__":
    mcp.run()  # stdio transport by default
```

---

## Phase 3: Implementation Steps

### Step 1: Create `src/` layout and move core code

**What:** Create `src/finops_tag_compliance/` and move existing code into it.

**Files to move (essentially unchanged):**
- `mcp_server/models/` → `src/finops_tag_compliance/models/`
  - All 16 model files move as-is
  - Exception: `health.py`, `observability.py`, `loop_detection.py` (MCP response parts), `budget.py` (MCP response parts) need splitting
- `mcp_server/services/` → `src/finops_tag_compliance/services/`
  - All 9 service files move as-is
  - `security_service.py`: remove `get_security_service()`/`set_security_service()` global state pattern, pass explicitly
- `mcp_server/clients/` → `src/finops_tag_compliance/clients/`
  - Both files move as-is
- `mcp_server/tools/` → `src/finops_tag_compliance/api/`
  - All 8 tool files move as-is, just update import paths
- `mcp_server/utils/` → `src/finops_tag_compliance/utils/`
  - Move all except `CorrelationIDMiddleware` class (HTTP-specific)
  - `correlation.py`: keep `get_correlation_id()`, `set_correlation_id()`, remove the HTTP middleware class

**Estimated changes:** ~50 files moved, import path updates only. No logic changes.

### Step 2: Split configuration

**What:** Create `CoreSettings` in core library, `ServerSettings` in MCP server.

**Core settings (`finops_tag_compliance/config.py`):**
```
aws_region, redis_url, redis_password, redis_ttl,
policy_path, audit_db_path, history_db_path,
resource_types_config_path, log_level, environment, debug,
cloudwatch_enabled, cloudwatch_log_group, cloudwatch_log_stream,
budget_tracking_enabled, max_tool_calls_per_session, session_budget_ttl_seconds,
loop_detection_enabled, max_identical_calls, loop_detection_window_seconds,
security_monitoring_enabled, max_unknown_tool_attempts, security_event_window_seconds,
tool_execution_timeout_seconds, aws_api_timeout_seconds, redis_timeout_seconds
```

**Server settings (`finops_tag_compliance_mcp/config.py`):**
```
host, port,
max_request_size_bytes, max_header_size_bytes, max_header_count,
max_query_string_length, max_path_length,
request_sanitization_enabled,
rate_limit_enabled, rate_limit_requests_per_minute, rate_limit_burst_size,
http_request_timeout_seconds,
transport (stdio | http)
```

### Step 3: Create ServiceContainer

**What:** Extract service initialization from `main.py` lifespan into `ServiceContainer`.

**Current location:** `mcp_server/main.py` lines 108-263 (the `lifespan` function).

**Changes:**
- Move all service initialization logic into `ServiceContainer.__init__()` and `ServiceContainer.initialize()`
- Remove global state variables (`redis_cache`, `audit_service`, etc.) from `main.py`
- Remove `set_security_service()` / `get_security_service()` module-level singletons
- Container holds all service references

### Step 4: Split MCP-specific models

**What:** Move MCP-specific response models to the server package.

**Models to split:**
1. `models/health.py` → `finops_tag_compliance_mcp/models/health.py` (HealthStatus, BudgetHealthInfo, LoopDetectionHealthInfo, SecurityHealthInfo)
2. `models/budget.py` → Split: `BudgetStatus`, `BudgetConfiguration` stay in core; `BudgetExhaustedResponse` (has `to_mcp_content()`) moves to server
3. `models/loop_detection.py` → Split: `LoopDetectionMetrics` stays in core; `LoopDetectedResponse` (has `to_mcp_content()`) moves to server
4. `models/observability.py` → `finops_tag_compliance_mcp/models/observability.py` (GlobalMetrics, SessionMetrics, etc. -- these are HTTP endpoint models)

### Step 5: Create session management module

**What:** Extract `BudgetTracker` and `LoopDetector` into `finops_tag_compliance/session/`.

**Current locations:**
- `middleware/budget_middleware.py` → `session/budget_tracker.py`
- `utils/loop_detection.py` → `session/loop_detector.py`

**Changes:**
- Remove the `get_budget_tracker()` / `set_budget_tracker()` module-level singleton pattern
- Remove the `get_loop_detector()` / `set_loop_detector()` module-level singleton pattern
- These become regular classes held by `ServiceContainer`

### Step 6: Decompose `mcp_handler.py`

This is the most complex step. The 1475-line `MCPHandler` currently does:

| Responsibility | Lines | Where it goes |
|---|---|---|
| Tool JSON schema definitions | ~540 | MCP server: `server.py` tool decorators (schemas auto-generated from type hints) |
| Tool handler methods (8 `_handle_*` methods) | ~250 | MCP server: `server.py` tool functions (call core library API) |
| Input validation orchestration | ~120 | Core library: stays in `utils/input_validation.py` (already there, just called differently) |
| Budget tracking check | ~40 | MCP server: middleware or pre-call hook |
| Loop detection check | ~40 | MCP server: middleware or pre-call hook |
| Security monitoring | ~70 | MCP server: middleware or pre-call hook |
| Audit logging | ~30 | Core library: `ServiceContainer` or decorator pattern |
| Error sanitization | ~40 | Core library: stays in `utils/error_sanitization.py` |
| Unknown tool rejection + rate limiting | ~100 | MCP server: handled by MCP SDK (only registered tools callable) |
| Response formatting (`MCPToolResult`) | ~50 | MCP server: handled by MCP SDK (automatic serialization) |

**The MCP SDK's `FastMCP` eliminates most of this code:**
- Tool registration via `@mcp.tool()` decorator (auto-generates JSON schemas from type hints + docstrings)
- Unknown tool rejection is built-in
- Response serialization is automatic
- Error handling is built-in

**Estimated reduction:** `mcp_handler.py` (1475 lines) → `server.py` (~200 lines) + moved code already exists elsewhere.

### Step 7: Create stdio MCP server

**What:** Create `finops_tag_compliance_mcp/server.py` using `mcp` Python SDK.

**Key design decisions:**
- Primary transport: **stdio** (matches AWS Labs pattern, works with Claude Desktop)
- Optional transport: **streamable-http** (for web-based clients)
- Each of the 8 tools is registered via `@mcp.tool()` decorator
- Tool functions call core library's `api/` functions
- Service initialization happens at server startup
- Environment variable `FINOPS_MCP_TRANSPORT` controls transport (default: stdio)

**Dependencies added to MCP server package:**
- `mcp>=1.0.0` (the MCP Python SDK)
- `fastapi>=0.104.0` (optional, for HTTP transport)
- `uvicorn>=0.24.0` (optional, for HTTP transport)

### Step 8: Create HTTP server (backwards compatibility)

**What:** Create `finops_tag_compliance_mcp/http_server.py` that provides the current FastAPI HTTP endpoints.

This preserves backwards compatibility for existing users of the HTTP API. It uses the same core library but serves via FastAPI + uvicorn.

**Endpoints preserved:**
- `GET /health` -- health check
- `GET /metrics` -- Prometheus metrics
- `POST /mcp/tools` -- list tools
- `POST /mcp/tools/call` -- invoke tool
- `GET /` -- API info
- `POST /api/v1/compliance/check` -- direct API
- `GET /api/v1/policy` -- direct API

### Step 9: Update `pyproject.toml`

**What:** Configure dual-package build with proper dependency groups.

```toml
[project]
name = "finops-tag-compliance"
dependencies = [
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "boto3>=1.28.0",
    "redis>=5.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
mcp = [
    "mcp>=1.0.0",
]
http = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
]
server = [
    "finops-tag-compliance[mcp,http]",
]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    # ... etc
]

[project.scripts]
finops-mcp = "finops_tag_compliance_mcp.server:main"
finops-http = "finops_tag_compliance_mcp.http_server:main"

[tool.setuptools.packages.find]
where = ["src"]
```

### Step 10: Update tests

**What:** Update import paths in all test files. No test logic changes needed.

**Changes:**
- All `from mcp_server.` → `from finops_tag_compliance.` for core library tests
- MCP server-specific tests import from `finops_tag_compliance_mcp.`
- Add new tests for `ServiceContainer`
- Add new tests for stdio MCP server (using `mcp` SDK test utilities)

### Step 11: Update documentation and entry points

**What:** Update README, CLAUDE.md, Docker, scripts.

**Changes:**
- `README.md`: New usage instructions showing both library and server usage
- `CLAUDE.md`: Update architecture section, file structure, commands
- `Dockerfile`: Update to build from `src/` layout
- `docker-compose.yml`: Update command for new entry point
- `run_server.py`: Update to call new entry point (or deprecate in favor of `finops-mcp` / `finops-http` commands)

---

## Phase 4: Migration Strategy

### Recommended Order

Execute steps in this order to minimize breakage and maintain a working state at each step:

1. **Step 1** (move files) + **Step 10** (update test imports) -- Do together. Run tests after.
2. **Step 2** (split config) -- Small, isolated change. Run tests after.
3. **Step 3** (ServiceContainer) -- Extract from main.py. Run tests after.
4. **Step 4** (split MCP models) -- Small, isolated. Run tests after.
5. **Step 5** (session management) -- Extract budget/loop. Run tests after.
6. **Step 6** (decompose mcp_handler) -- Biggest change. Run tests after.
7. **Step 7** (stdio server) -- New code, additive. Run tests after.
8. **Step 8** (HTTP server) -- Restructure existing HTTP code. Run tests after.
9. **Step 9** (pyproject.toml) -- Packaging changes. Verify install works.
10. **Step 11** (docs) -- Final documentation updates.

### Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Import path breakage in 50+ test files | Medium | Do steps 1+10 together, run full test suite |
| Breaking existing HTTP API | High | Step 8 preserves all endpoints; integration tests validate |
| Missing re-exports in `__init__.py` | Medium | Comprehensive import tests; check all public API symbols |
| `mcp` SDK version incompatibility | Low | Pin version; test with Claude Desktop |
| Redis session management during transition | Low | BudgetTracker/LoopDetector logic unchanged, just moved |
| Global state removal (set/get singletons) | Medium | ServiceContainer replaces all global state; test all entry points |

### What NOT to Change

- **Service implementations** -- All 9 services stay exactly as-is (logic, signatures, behavior)
- **Tool function signatures** -- All 8 tool functions keep their current signatures
- **Pydantic models** -- All data models keep their current fields and validation
- **AWSClient methods** -- All 19+ methods stay exactly as-is
- **Test logic** -- Only import paths change; assertions, fixtures, mocks all stay

---

## Phase 5: Validation Criteria

The refactoring is successful when:

1. **Core library is importable without HTTP/MCP:**
   ```python
   # This must work without fastapi, uvicorn, or mcp installed:
   from finops_tag_compliance import ServiceContainer, check_compliance
   ```

2. **All existing tests pass** with updated imports (0 test logic changes)

3. **stdio MCP server works with Claude Desktop:**
   ```json
   {
     "mcpServers": {
       "finops-tag-compliance": {
         "command": "finops-mcp",
         "env": { "AWS_REGION": "us-east-1" }
       }
     }
   }
   ```

4. **HTTP server preserves backwards compatibility:**
   - All existing endpoints return same responses
   - Docker deployment still works

5. **Core library dependency footprint:**
   - Required: `pydantic`, `pydantic-settings`, `boto3`, `redis`, `python-dotenv`
   - NOT required: `fastapi`, `uvicorn`, `mcp`

6. **Lines of code in MCP server layer:** < 300 (down from ~1750 in main.py + mcp_handler.py)

---

## Appendix A: File-by-File Mapping

| Current Path | Target Path | Notes |
|---|---|---|
| `mcp_server/__init__.py` | `src/finops_tag_compliance/__init__.py` | Rewrite: export public API |
| `mcp_server/config.py` | `src/finops_tag_compliance/config.py` | Split: core settings only |
| `mcp_server/main.py` | `src/finops_tag_compliance_mcp/http_server.py` | Rewrite: HTTP server only, uses ServiceContainer |
| `mcp_server/mcp_handler.py` | `src/finops_tag_compliance_mcp/server.py` | Rewrite: FastMCP stdio server |
| `mcp_server/models/*.py` | `src/finops_tag_compliance/models/*.py` | Move (split MCP-specific parts) |
| `mcp_server/services/*.py` | `src/finops_tag_compliance/services/*.py` | Move (remove global state) |
| `mcp_server/tools/*.py` | `src/finops_tag_compliance/api/*.py` | Move (rename directory) |
| `mcp_server/clients/*.py` | `src/finops_tag_compliance/clients/*.py` | Move as-is |
| `mcp_server/utils/arn_utils.py` | `src/finops_tag_compliance/utils/arn_utils.py` | Move as-is |
| `mcp_server/utils/resource_utils.py` | `src/finops_tag_compliance/utils/resource_utils.py` | Move as-is |
| `mcp_server/utils/resource_type_config.py` | `src/finops_tag_compliance/utils/resource_type_config.py` | Move as-is |
| `mcp_server/utils/input_validation.py` | `src/finops_tag_compliance/utils/input_validation.py` | Move as-is |
| `mcp_server/utils/error_sanitization.py` | `src/finops_tag_compliance/utils/error_sanitization.py` | Move as-is |
| `mcp_server/utils/cloudwatch_logger.py` | `src/finops_tag_compliance/utils/cloudwatch_logger.py` | Move as-is |
| `mcp_server/utils/correlation.py` | `src/finops_tag_compliance/utils/correlation.py` | Split: remove HTTP middleware |
| `mcp_server/utils/loop_detection.py` | `src/finops_tag_compliance/session/loop_detector.py` | Move + remove global state |
| `mcp_server/middleware/budget_middleware.py` | `src/finops_tag_compliance/session/budget_tracker.py` | Move + remove global state |
| `mcp_server/middleware/audit_middleware.py` | `src/finops_tag_compliance/utils/audit_decorator.py` | Move |
| `mcp_server/middleware/sanitization_middleware.py` | `src/finops_tag_compliance_mcp/middleware/sanitization.py` | Move (HTTP-only) |
| `mcp_server/__main__.py` | `src/finops_tag_compliance_mcp/__main__.py` | Rewrite: launch stdio server |
| `run_server.py` | Keep (or deprecate) | Update to call new entry point |

## Appendix B: Global State to Eliminate

The current codebase uses several module-level singleton patterns that should be replaced with explicit dependency injection via `ServiceContainer`:

| Current Pattern | Location | Replacement |
|---|---|---|
| `_settings: Settings \| None = None` + `settings()` | `config.py` | `ServiceContainer` holds settings |
| `set_budget_tracker()` / `get_budget_tracker()` | `middleware/budget_middleware.py` | `ServiceContainer.budget_tracker` |
| `set_loop_detector()` / `get_loop_detector()` | `utils/loop_detection.py` | `ServiceContainer.loop_detector` |
| `set_security_service()` / `get_security_service()` | `services/security_service.py` | `ServiceContainer.security_service` |
| Global variables in `main.py` (`redis_cache`, `audit_service`, etc.) | `main.py` lines 76-83 | `ServiceContainer` properties |

## Appendix C: Estimated Effort

| Step | Description | Estimated File Changes | Complexity |
|---|---|---|---|
| 1 | Move files to src/ layout | ~50 files (path changes) | Low (mechanical) |
| 2 | Split configuration | 2 files modified, 1 new | Low |
| 3 | Create ServiceContainer | 1 new file, 1 modified (main.py) | Medium |
| 4 | Split MCP-specific models | 4 files split | Low |
| 5 | Extract session management | 2 files moved, singletons removed | Low-Medium |
| 6 | Decompose mcp_handler.py | 1 file deleted, 1 new (server.py) | High |
| 7 | Create stdio MCP server | 1 new file (~200 lines) | Medium |
| 8 | Create HTTP server | 1 new file (refactored from main.py) | Medium |
| 9 | Update pyproject.toml | 1 file | Low |
| 10 | Update tests | ~50 files (import paths) | Low (mechanical) |
| 11 | Update documentation | 3-4 files | Low |
