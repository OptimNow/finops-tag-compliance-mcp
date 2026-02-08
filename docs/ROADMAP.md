# FinOps Tag Compliance MCP Server - Implementation Roadmap

**Strategy**: Start Simple, Scale Later
**Total Timeline**: ~10 weeks remaining (Phase 2: ~1.5 weeks, Phase 3: ~8 weeks)
**Approach**: Incremental delivery with user feedback loops

---

## Philosophy

Rather than building a complex multi-cloud system upfront, we take an iterative approach:

1. **Phase 1 (Months 1-2)**: Deliver a working AWS-only MCP on a single EC2 instance ✅
2. **Phase 2 (~1.5 weeks)**: Add remediation script generation + compliance tools (parallel), then scale to production ECS Fargate
3. **Phase 3 (Months 7-8)**: Add Azure, GCP, multi-account AWS, and policy enforcement automation

Each phase delivers working software that provides value. We learn from real usage before investing in complexity.

---

## Phase 1: MVP - AWS-Only on EC2 (Months 1-2) ✅ COMPLETE

**Status**: ✅ **COMPLETE** (January 9, 2026)

**Goal**: Get a working MCP server deployed and gathering user feedback

**Scope**: AWS tag compliance only, single EC2 instance, Docker container

### Deliverables

✅ **Core MCP Server**
- 8 essential tools (compliance checking, violation finding, basic reporting)
- AWS SDK integration (boto3)
- Tagging policy validation engine
- Cost attribution gap calculation
- State-aware cost attribution (EC2 stopped instances = $0 compute)
- ML-powered tag suggestions with confidence scores

✅ **Multi-Region Scanning**
- Parallel scanning across all enabled AWS regions
- Region discovery via EC2 API with fallback
- Configurable concurrency (`MAX_CONCURRENT_REGIONS`)
- Global vs regional resource handling (S3, IAM always scanned)
- Regional compliance breakdown in results

✅ **Infrastructure**
- Dockerized application
- Single EC2 t3.medium instance
- Redis container for caching (configurable TTL)
- SQLite for audit logs and compliance history
- IAM role-based authentication (no credentials in code)

✅ **Security & Guardrails**
- API key authentication middleware (HTTP transport)
- CORS origin allowlist enforcement
- Request sanitization (injection prevention, size limits)
- Error sanitization (no sensitive data in responses)
- Input validation (ARN format, string length, path traversal)
- Budget tracking (max 100 tool calls per session)
- Loop detection (max 3 identical calls per window)

✅ **Observability**
- Correlation ID tracing across all requests
- CloudWatch logging and custom metrics integration
- SQLite-based audit logging for all tool invocations
- Compliance history tracking with trend analysis

✅ **AWS Organizations Tag Policy Integration (Phase 1.5)**
- Manual converter script (`scripts/convert_aws_policy.py`)
- Converts AWS Organizations tag policies to MCP format
- Example AWS policy for testing
- Documentation for conversion process
- Zero-friction onboarding for existing AWS customers

✅ **Documentation**
- API documentation for 8 tools
- Deployment guide for EC2
- Sample tagging policy JSON
- User guide for MCP client setup
- Tagging policy configuration guide
- AWS policy conversion guide

### Success Metrics

- MCP server running on EC2 with 99% uptime
- <2 second response time for compliance checks
- 5+ internal users testing with Claude Desktop
- 10+ tag compliance audits completed

### Detailed Spec

See [PHASE-1-SPECIFICATION.md](./PHASE-1-SPECIFICATION.md)

### Phase 1.5: AWS Organizations Integration (Week 7-8)

**Goal**: Remove adoption friction for organizations with existing AWS tag policies

**Deliverables**:
- ✅ Manual converter script (`scripts/convert_aws_policy.py`)
- ✅ Example AWS Organizations tag policy
- ✅ Documentation in Tagging Policy Guide
- ✅ UAT protocol updated with conversion instructions

**Success Metrics**:
- Converter script successfully converts 3+ real AWS policies
- Documentation enables self-service conversion
- Zero manual policy recreation required for AWS customers

**Status**: ✅ Completed (January 2026)

### Expanded Resource Coverage (Included in Phase 1)

**Note**: Originally planned as Phase 1.7, this capability has been implemented as part of Phase 1 completion.

**Status**: ✅ Complete (January 2026)

**Deliverables**:
- ✅ AWS Resource Groups Tagging API integration for universal resource discovery
- ✅ 50+ AWS resource types supported (including Bedrock agents, knowledge bases, guardrails)
- ✅ Resource type filter with "all" option
- ✅ Universal tagging policy (applies_to: [] = wildcard for all resource types)
- ✅ Performance optimization with pagination for large-scale scans

**Important Note**: The Resource Groups Tagging API only returns resources that have at least one tag. For completely untagged resources, users should use specific resource types (ec2:instance, s3:bucket, etc.).

See [PHASE-1-SPECIFICATION.md](./PHASE-1-SPECIFICATION.md) for full details on supported resource types.

---

## Phase 1.9: Core Library Extraction (Pre-Phase 2 Foundation) ✅ COMPLETE

**Status**: ✅ **COMPLETE** (January 2026)
**Goal**: Separate protocol-agnostic business logic from MCP/HTTP transport to unblock Phase 2

**Problem Statement**:
Phase 1 shipped as a monolithic FastAPI HTTP server where business logic was coupled with HTTP routing and MCP protocol handling. Phase 1.9 established a clean separation between reusable core logic and protocol-specific wrappers.

**Deliverables**:
- ✅ **ServiceContainer** (`container.py`) -- Centralizes all service initialization with explicit dependency injection, replaces scattered globals in `main.py` lifespan
- ✅ **CoreSettings / ServerSettings split** (`config.py`) -- Protocol-agnostic config separated from HTTP-specific settings, with `extra="ignore"` for coexistence
- ✅ **stdio_server.py** -- FastMCP SDK-based stdio transport with all 8 tools, compatible with Claude Desktop and MCP Inspector
- ✅ **pyproject.toml** -- Updated with `mcp>=1.0.0` dependency and `finops-tag-compliance` CLI entry point

**Deferred to Phase 3** (Tier 2 refactoring — not needed for Phase 2 tool additions, becomes valuable when adding multi-cloud SDKs):
- `src/` layout reorganization for pip-installable core library package
- Decompose `mcp_handler.py` (1504 lines) into modular FastMCP server
- Session management extraction (BudgetTracker, LoopDetector to `session/` module)
- HTTP backwards-compat wrapper using core library
- Dual package setup in pyproject.toml (core lib + MCP server)
- Test import updates after layout change

**Detailed Plan**: See [REFACTORING_PLAN.md](../archive/specs/REFACTORING_PLAN.md) for full analysis, implementation steps, file-by-file mapping, and priority tiers.

---

## Phase 2: Enhanced Compliance + Production Scale (~1.5 weeks)

**Goal**: Add 6 new tools (remediation scripts, compliance scheduling, drift detection, export, policy import), server-side automation, then deploy to production ECS Fargate

**Scope**: AWS-only functionality, enterprise-ready infrastructure, 14 total tools

**Development Model**: AI-assisted development (Claude builds tools, tests, and infrastructure in parallel; user performs UAT and deployment). Sub-phases 2.1-2.4 are developed in parallel as independent features, then validated together in UAT 1 before production deployment in 2.5.

### Tool Summary

| # | Tool | Sub-Phase |
|---|------|-----------|
| 1-8 | Phase 1 tools (unchanged) | — |
| 9 | `generate_custodian_policy` | 2.1 |
| 10 | `generate_openops_workflow` | 2.1 |
| 11 | `schedule_compliance_audit` | 2.2 |
| 12 | `detect_tag_drift` | 2.2 |
| 13 | `export_violations_csv` | 2.3 |
| 14 | `import_aws_tag_policy` | 2.3 |

### Deliverables

✅ **Enhanced MCP Server** (14 total tools)
- 6 new tools: remediation script generation, drift detection, scheduling, CSV export, AWS policy import
- Improved caching and performance
- OAuth 2.0 + PKCE authentication
- **Agent Safety Enhancements** - Intent disambiguation, cost thresholds, dry run mode
- **Automated Daily Compliance Snapshots** - Server-side scheduled scans for consistent trend tracking

✅ **Production Infrastructure**
- ECS Fargate deployment (2+ tasks)
- Application Load Balancer
- Amazon ElastiCache (Redis)
- Amazon RDS (PostgreSQL for audit logs)
- AWS Secrets Manager integration
- CloudWatch monitoring and alarms
- Auto-scaling policies

✅ **Enterprise Features**
- Scheduled compliance audits
- **Automated daily compliance snapshots** - Server runs a full compliance scan daily at a configurable time, storing results in history database for accurate trend tracking (independent of user ad-hoc queries)
- Enhanced audit logging
- Rate limiting and quotas
- **Dry run mode** - Preview operations without executing
- **Cost/risk thresholds** - Require approval for expensive operations

### Success Metrics

- 99.9% uptime SLA
- <1 second response time for compliance checks
- 20+ users across FinOps and DevOps teams
- 100+ compliance audits per month
- Zero security incidents
- Cloud Custodian policies generated from compliance violations
- OpenOps workflows generated from compliance data

### Detailed Spec

See [PHASE-2-SPECIFICATION.md](./PHASE-2-SPECIFICATION.md)

> **⚡ Parallelization Note**: Phases 2.1, 2.2, 2.3, and 2.4 are developed in parallel (Days 1-3). Each sub-phase produces independent tools/features that touch different files — no merge conflicts. All are validated together in UAT 1 on Day 4.

### Phase 2.1: Remediation Script Generation (Days 1-3, parallel)

**Goal**: Generate Cloud Custodian policies and OpenOps workflows from compliance violations

**Problem Statement**:
Users identify compliance violations but lack automated tooling to remediate them. Generating ready-to-use Cloud Custodian policies and OpenOps workflows from violation data bridges the gap between detection and remediation.

**Deliverables**:
- **Tool 9: `generate_custodian_policy`** - Generate Cloud Custodian YAML policies from compliance violations
  - Input: resource types, violation types, target tags
  - Output: Valid Cloud Custodian policy YAML with filters, actions, and scheduling
  - Supports: tag enforcement, tag normalization, missing tag remediation
  - Dry-run mode: generates `notify` actions instead of `tag` actions
- **Tool 10: `generate_openops_workflow`** - Generate OpenOps-compatible automation workflows
  - Input: compliance violations, remediation strategy
  - Output: OpenOps YAML workflow with triggers, conditions, and actions
  - Supports: compliance score thresholds, resource type filters, scheduled execution

**Example Cloud Custodian Policy Output**:
```yaml
policies:
  - name: enforce-required-tags-ec2
    resource: ec2
    filters:
      - or:
        - "tag:Environment": absent
        - "tag:Owner": absent
        - "tag:CostCenter": absent
    actions:
      - type: tag
        tags:
          Environment: "unknown"
          Owner: "unassigned"
```

**Example OpenOps Workflow Output**:
```yaml
name: "Fix EC2 Tagging Violations"
triggers:
  - compliance_score_below: 0.8
steps:
  - name: "Tag EC2 Instances"
    action: "aws_cli"
    script: |
      aws ec2 create-tags --resources {resource_id} \
        --tags Key=CostCenter,Value=Engineering
```

**Success Metrics**:
- Generated Cloud Custodian policies are syntactically valid and executable
- Generated OpenOps workflows conform to platform schema
- Users can go from "check compliance" → "generate remediation" in one conversation

### Phase 2.2: Compliance Tools (Days 1-3, parallel)

**Goal**: Add scheduled compliance audits and tag drift detection

**Deliverables**:
- **Tool 11: `schedule_compliance_audit`** - Configure recurring compliance scans
  - Configurable schedule (cron format)
  - Full or filtered resource type coverage
  - Results stored with "scheduled" flag in history
  - CloudWatch metrics for scan success/failure
- **Tool 12: `detect_tag_drift`** - Detect unexpected tag changes since last scan
  - Compares current tags against last known state
  - Reports: tags added, removed, or changed
  - Filters by resource type, region, tag key
  - Severity classification (required tag removed = critical)

**Success Metrics**:
- Daily compliance snapshots stored consistently
- Trend analysis shows accurate week-over-week and month-over-month changes
- Tag drift detected within 24 hours of change

### Phase 2.3: Export & Policy Tools (Days 1-3, parallel)

**Goal**: CSV export and runtime AWS Organizations policy import

**Deliverables**:
- **Tool 13: `export_violations_csv`** - Export violation data to CSV format
  - Configurable columns and filters
  - Supports large datasets with pagination
  - Download-ready format for spreadsheet analysis
- **Tool 14: `import_aws_tag_policy`** - Fetch and convert AWS Organizations tag policies at runtime
  - User-initiated import via Claude Desktop ("Import my AWS tag policy")
  - Lists available policies if policy_id not provided
  - Automatic conversion and file saving
  - IAM permission guidance for insufficient access
  - Requires: `organizations:DescribePolicy` and `organizations:ListPolicies`

**Success Metrics**:
- CSV exports work for datasets with 1000+ violations
- Users can import AWS policies via Claude Desktop end-to-end
- Proper error messages guide users through permission issues

### Phase 2.4: Automatic Policy Detection + Daily Snapshots (Days 1-3, parallel)

**Goal**: Zero-touch policy setup and server-side automated compliance scanning

**Deliverables**:

**Automatic Policy Detection**:
- Startup logic to detect AWS Organizations tag policies
- Automatic conversion and saving to `policies/tagging_policy.json`
- Falls back to default policy if no AWS policy found
- Configurable via `config.yaml`
- Periodic re-import to stay in sync with AWS
- Policy source logged in `/health` endpoint

**Automated Daily Compliance Snapshots**:
- Background scheduler (APScheduler or similar) for daily compliance scans
- Configurable scan time (default: 02:00 UTC)
- Scans ALL resource types across ALL regions
- Results stored with `store_snapshot=True` flag
- User ad-hoc queries default to `store_snapshot=False` (don't affect history)
- Separate "scheduled" vs "ad-hoc" flag in history records
- Health endpoint shows last scheduled scan time and next scheduled run
- CloudWatch metrics for scheduled scan success/failure

**Configuration**:
```yaml
# config.yaml
scheduled_compliance:
  enabled: true
  schedule: "0 2 * * *"  # Cron format: 2:00 AM UTC daily
  resource_types: "all"  # Or specific list
  regions: "all"         # Or specific list
  store_snapshot: true   # Always store scheduled scans
  notify_on_failure: true
  notification_email: "finops-team@company.com"
```

**Success Metrics**:
- New deployments work without manual policy configuration
- Policy changes in AWS Organizations sync to MCP server automatically
- Daily compliance snapshots stored consistently
- No pollution from ad-hoc partial scans

### 🧪 UAT 1: Functional Validation (Day 4)

**Goal**: Validate all new tools and features on existing EC2 infrastructure before production deployment

**Owner**: User (FinOps Engineer)

**Scope**:
- Deploy updated code to EC2 (existing infrastructure, `git pull` + restart)
- **New tool validation**: Test all 6 new tools (9-14) against real AWS account
- **Regression check (automated)**: Run `python run_tests.py` — all 51+ test files must pass
- **Regression check (manual)**: Run all 8 Phase 1 tools and verify results match baseline
- **Server features**: Verify daily snapshot scheduler starts and auto-policy detection works

**Go/No-Go for Phase 2.5**:
- ✅ All new tools return valid results
- ✅ All Phase 1 tools still work (no regressions)
- ✅ Automated test suite passes 100%
- ✅ No blocking issues identified

**If FAIL**: Claude fixes issues same day, re-deploy and re-test

### Phase 2.5: Production Infrastructure - ECS Fargate (Days 5-6)

**Goal**: Deploy to production-grade ECS Fargate infrastructure with all 14 tools

**Rationale**: ECS Fargate is placed at the end of Phase 2 because:
- Tools 9-14 don't require ECS (they work on EC2/local development)
- Faster iteration developing and testing tools on EC2/local before deploying to production
- Daily snapshots (Phase 2.4) benefit most from persistent infrastructure
- Deploying a stable, feature-complete application minimizes deployment iterations

**Deliverables**:
- ECS Fargate deployment (2+ tasks, auto-scaling)
- Application Load Balancer with TLS
- Amazon ElastiCache (Redis) replacing local Redis
- Amazon RDS (PostgreSQL) replacing SQLite for audit logs and history
- AWS Secrets Manager for API keys and configuration
- CloudWatch monitoring, alarms, and dashboards
- CI/CD pipeline for automated deployments
- OAuth 2.0 + PKCE authentication (replacing API key auth)

**Success Metrics**:
- 99.9% uptime SLA achieved
- <1 second response time for cached compliance checks
- Zero-downtime deployments via blue/green ECS strategy
- All secrets managed via Secrets Manager (no env vars)
- All 14 tools functional in production environment

### 🧪 UAT 2: Production Validation (Day 7)

**Goal**: Validate that all 14 tools work correctly on ECS Fargate production infrastructure

**Owner**: User (FinOps Engineer)

**Scope**:
- Deploy to ECS Fargate (CloudFormation/CDK stack)
- **Same-results test**: Re-run the exact same tool queries from UAT 1 on production
- **Infrastructure validation**: Verify ElastiCache (Redis), RDS (PostgreSQL), OAuth 2.0, ALB all functioning
- **Performance check**: Confirm <1 second response time for cached queries
- **Regression check (automated)**: Run `python run_tests.py` against production endpoint

**Pass Criteria**:
- ✅ All 14 tools return same results as UAT 1 (same inputs → same outputs)
- ✅ OAuth authentication flow works end-to-end
- ✅ Data persists in RDS (audit logs, compliance history)
- ✅ Cache hits via ElastiCache (second query faster than first)
- ✅ Health endpoint reports all services healthy

**If FAIL**: Roll back to EC2, Claude fixes issues, redeploy

---

## Phase 3: Multi-Cloud, Multi-Account & Automation (Months 7-10)

**Goal**: Extend to Azure + GCP, add multi-account AWS support, and complete automation tooling

**Scope**: Multi-cloud support, multi-account AWS scanning, policy enforcement tools, unified reporting

### Tool Summary

| # | Tool | Category |
|---|------|----------|
| 1-14 | Phase 2 tools (unchanged) | — |
| 15 | `export_for_automation` | Automation |
| 16 | `generate_terraform_policy` | Policy Enforcement |
| 17 | `generate_config_rules` | Policy Enforcement |

**Phase 3 total: 17 tools** (14 from Phase 2 + 3 new)

### Deliverables

✅ **Multi-Account AWS Support**
- Enhanced `aws_client.py` with `MultiAccountAWSClient` class
- AssumeRole session management with automatic token refresh
- Session caching (15-minute TTL) to avoid repeated STS calls
- Multi-account parameters added to all scan tools: `accounts: Optional[List[str]]`
- IAM trust relationship automation for cross-account roles
- Aggregated compliance reporting across accounts
- Per-account violation breakdown in reports

**Architecture**:
```
┌──────────────────┐
│  MCP Server      │
│  (Main Account)  │
│                  │
│  IAM Role:       │
│  mcp-server-role │
└────────┬─────────┘
         │ AssumeRole
         ├────────────────────────────┐
         │                            │
         ▼                            ▼
┌─────────────────┐          ┌─────────────────┐
│  Account 1      │          │  Account 2      │
│                 │          │                 │
│  IAM Role:      │          │  IAM Role:      │
│  mcp-cross-     │          │  mcp-cross-     │
│  account-role   │          │  account-role   │
│                 │          │                 │
│  Trust Policy:  │          │  Trust Policy:  │
│  Main Account   │          │  Main Account   │
└─────────────────┘          └─────────────────┘
```

**Configuration**:
```yaml
# config.yaml
multi_account:
  enabled: true
  cross_account_role_name: "mcp-cross-account-role"  # Role name in target accounts
  session_duration_seconds: 3600  # 1 hour
  session_cache_ttl_seconds: 900  # 15 minutes
  max_parallel_accounts: 5  # Scan 5 accounts concurrently
```

**Documentation**: See [DEPLOY_MULTI_ACCOUNT.md](./DEPLOY_MULTI_ACCOUNT.md) for complete deployment guide and three deployment options.

✅ **Multi-Cloud MCP Server**
- All 14 Phase 2 tools now support `cloud_provider` parameter (aws, azure, gcp, all)
- Azure SDK integration (azure-mgmt-*)
- GCP SDK integration (google-cloud-*)
- Cross-cloud tag consistency checking
- Unified tagging policy schema

✅ **Multi-Cloud Credentials**
- AWS: IAM role (existing)
- Azure: Service Principal via Azure Key Vault
- GCP: Service Account via GCP Secret Manager
- Centralized credential rotation

✅ **Cross-Cloud Features**
- Unified compliance dashboard (all clouds)
- Cross-cloud tag consistency enforcement
- Multi-cloud cost attribution gap analysis
- Cloud-agnostic tagging policy

✅ **Codebase Modernization** (deferred from Phase 1.9 / Phase 2)
- `src/` layout reorganization for pip-installable core library package
- Decompose `mcp_handler.py` (1504 lines) into modular FastMCP server (~200 lines)
- Session management extraction (BudgetTracker, LoopDetector to `session/` module)
- HTTP backwards-compat wrapper using core library
- Dual package setup in pyproject.toml (core lib + MCP server)
- Test import updates after layout change

**Rationale**: Deferred from Phase 2 because the current codebase (`stdio_server.py` with `@mcp.tool()` decorators) handles 14 tools cleanly. The `src/` layout and pip-installable package become valuable in Phase 3 when adding multi-cloud SDKs and the codebase grows significantly.

✅ **Automation & Policy Enforcement Tools** (absorbed from former Phase 4)
- **Tool 15: `export_for_automation`** - Export compliance data for external automation platforms (wiv.ai, Ansible, etc.)
- **Tool 16: `generate_terraform_policy`** - Generate Terraform tag enforcement policies (AWS Config rules, Azure Policy, GCP Org Policy)
- **Tool 17: `generate_config_rules`** - Generate cloud-native policy enforcement rules (AWS Config, Azure Policy, GCP Organization Constraints)

### Success Metrics

- All 3 clouds supported with feature parity
- Cross-cloud compliance reports generated
- 10+ AWS accounts scanned in a single compliance check
- 50+ users across multi-cloud teams
- 500+ compliance audits per month across all clouds
- Terraform policies generated and deployable across clouds
- Config/policy rules generated for all 3 cloud providers

### Detailed Spec

See [PHASE-3-SPECIFICATION.md](./PHASE-3-SPECIFICATION.md)

---

## Deployment Evolution

### Phase 1: Single EC2
```
┌─────────────────────────────────┐
│ EC2 Instance (t3.medium)        │
│  ┌──────────────────────────┐  │
│  │ Docker Container         │  │
│  │  - MCP Server (AWS)      │  │
│  │  - Redis (cache)         │  │
│  │  - SQLite (logs)         │  │
│  └──────────────────────────┘  │
└─────────────────────────────────┘
         ↓ IAM Role
    ┌─────────┐
    │   AWS   │
    └─────────┘
```

**Cost**: ~$40/month

### Phase 2: ECS Fargate
```
┌──────────────────────────────────────┐
│ Application Load Balancer            │
└────────┬──────────────┬──────────────┘
         │              │
┌────────▼────┐    ┌────▼────┐
│ ECS Task 1  │    │ECS Task 2│
└────────┬────┘    └────┬─────┘
         │              │
    ┌────▼──────────────▼────┐
    │ ElastiCache (Redis)    │
    └────────────────────────┘
    ┌────────────────────────┐
    │ RDS (PostgreSQL)       │
    └────────────────────────┘
         ↓ IAM Role
    ┌─────────┐
    │   AWS   │
    └─────────┘
```

**Cost**: ~$150-200/month

### Phase 3: Multi-Cloud + Automation
```
┌──────────────────────────────────────┐
│ Application Load Balancer            │
└────────┬──────────────┬──────────────┘
         │              │
┌────────▼────┐    ┌────▼────┐
│ ECS Task 1  │    │ECS Task 2│
│ Multi-Cloud │    │Multi-Cloud│
│ + Automation│    │ + Automation│
└────────┬────┘    └────┬─────┘
         │              │
    ┌────▼──────────────▼────┐
    │ ElastiCache (Redis)    │
    └────────────────────────┘
    ┌────────────────────────┐
    │ RDS (PostgreSQL)       │
    └────────────────────────┘
    ┌────────────────────────┐
    │ AWS Secrets Manager    │
    │  - Azure credentials   │
    │  - GCP credentials     │
    └────────────────────────┘
         │           │        │
         ▼           ▼        ▼
    ┌────────┐  ┌──────┐  ┌─────┐
    │  AWS   │  │Azure │  │ GCP │
    └────────┘  └──────┘  └─────┘
```

**Cost**: ~$180-250/month

---

## Risk Mitigation

### Phase 1 Risks

| Risk | Mitigation |
|------|-----------|
| EC2 instance failure | Accept for MVP, manual restart acceptable |
| AWS API rate limits | Implement caching, respect rate limits |
| Slow development | Use existing MCP server templates, copy proven patterns |
| No user adoption | Get 3 committed beta users before starting development |

### Phase 2 Risks

| Risk | Mitigation |
|------|-----------|
| ECS complexity | Use Terraform/CDK for reproducible infrastructure |
| Cost overruns | Set CloudWatch billing alarms, start with 2 tasks only |
| Migration issues | Blue/green deployment, test thoroughly in staging |
| Performance degradation | Load testing before launch, optimize caching |
| Generated script errors (Custodian/OpenOps) | Dry-run mode, syntax validation, template testing |
| Automation platform schema changes | Version pinning, adapter pattern for each platform |

### Phase 3 Risks

| Risk | Mitigation |
|------|-----------|
| Azure/GCP API complexity | Start with read-only tools, add write later |
| Credential management | Use managed secrets services, rotate regularly |
| Cross-cloud policy conflicts | Design flexible schema, allow cloud-specific overrides |
| Testing across 3 clouds | Automated integration tests in CI/CD pipeline |
| Multi-account credential sprawl | Centralized AssumeRole with session caching |

---

## Regression Testing Strategy

Regression prevention is critical during Phase 2, where 6 new tools and server-side features could break existing Phase 1 functionality.

### Automated (run by Claude before every handoff)

| Check | Command | What it validates |
|-------|---------|-------------------|
| Full test suite | `python run_tests.py` | All 51+ test files pass (unit + property + integration) |
| Regression harness | `pytest tests/regression/` | Phase 1 tool outputs match expected schemas and values |
| Type checking | `mypy mcp_server/` | No type errors introduced |
| Code formatting | `black --check mcp_server/ tests/` | Consistent code style |

**Regression test harness** (`tests/regression/`):
- Created at the start of Phase 2, before any new tools are added
- Captures exact inputs → expected output structure for all 8 Phase 1 tools
- Uses snapshot testing: known inputs produce known output schemas
- Fails if any tool's response structure changes unexpectedly
- CI-compatible: can be integrated into GitHub Actions

### Manual (run by user during UAT)

**UAT 1 Regression Checklist** (8 Phase 1 tools):
1. `check_tag_compliance` — compliance score and violation count match expectations
2. `find_untagged_resources` — returns known untagged resources
3. `validate_resource_tags` — validates specific ARN correctly
4. `get_cost_attribution_gap` — cost numbers are reasonable
5. `suggest_tags` — returns suggestions with confidence scores
6. `get_tagging_policy` — returns current policy
7. `generate_compliance_report` — report format is correct
8. `get_violation_history` — history data is present and accurate

**UAT 2 Regression Checklist**: Same 8 checks, run on ECS Fargate production. Results should match UAT 1.

---

## Decision Points

### After Phase 1 (Month 2)

**Go/No-Go Decision**: Do we have enough user adoption and value to justify Phase 2?

**Criteria**:
- ✅ 5+ active users
- ✅ Positive user feedback (NPS > 30)
- ✅ Clear cost attribution value demonstrated
- ✅ No blocking technical issues

**If NO**: Iterate on Phase 1, add more AWS tools, improve UX

**If YES**: Proceed to Phase 2 planning

### After Phase 2 (Month 6)

**Go/No-Go Decision**: Do users need multi-cloud and multi-account support?

**Criteria**:
- ✅ Users requesting Azure/GCP support or multi-account scanning
- ✅ Phase 2 infrastructure stable (99.5%+ uptime for 2 weeks)
- ✅ Budget approved for multi-cloud ($50/month additional)
- ✅ Azure/GCP credentials available for testing

**If NO**: Invest in Phase 2 enhancements (better ML, more automation platforms)

**If YES**: Proceed to Phase 3

---

## Team Structure

### Phase 1
- 1 Backend Developer (Python, MCP, AWS)
- 0.5 DevOps Engineer (Docker, EC2)
- 0.25 FinOps Practitioner (Requirements, testing)

### Phase 2
- 1 AI Developer (Claude) — builds tools, tests, services, infrastructure templates
- 1 FinOps Engineer — requirements, UAT, deployment, go/no-go decisions

### Phase 3
- 1 Backend Developer (multi-cloud SDKs, automation exports)
- 0.5 Cloud Engineer (Azure + GCP expertise)
- 0.25 DevOps Engineer (Terraform, CloudFormation)
- 0.25 FinOps Practitioner

---

## Timeline Summary

| Phase | Duration | Key Milestone | Schedule |
|-------|----------|--------------|----------|
| **Phase 1** | 8 weeks | AWS-only MCP on EC2 | ✅ Complete (Jan 2026) |
| **Phase 1.5** | (included) | AWS policy converter | ✅ Complete |
| **Phase 1.9** | 2-3 weeks | Core library extraction + stdio server | ✅ Complete (Jan 2026) |
| **Phase 2.1-2.4** | 3 days | 6 new tools + server features (parallel) | Days 1-3 |
| **🧪 UAT 1** | 1 day | Functional validation on EC2 | Day 4 |
| **Phase 2.5** | 2 days | ECS Fargate production deployment | Days 5-6 |
| **🧪 UAT 2** | 1 day | Production validation on ECS | Day 7 |
| **Phase 2 total** | ~1.5 weeks | Production deployment + 14 tools | End of Week 2 |
| **Phase 3** | 8 weeks | Multi-cloud + multi-account + 17 tools | End of Month 4 |

**Total**: ~10 weeks from Phase 2 kickoff to Phase 3 completion

---

## Next Steps

1. **Days 1-3: Phases 2.1-2.4** — Build all 6 new tools + server features in parallel (+ regression test harness)
2. **Day 4: UAT 1** — User deploys to EC2, validates new tools + regression checks
3. **Days 5-6: Phase 2.5** — ECS Fargate deployment (CloudFormation/CDK)
4. **Day 7: UAT 2** — User validates production deployment

---

## Success Criteria (End of Phase 3)

✅ **Functionality**
- 17 MCP tools working across AWS, Azure, GCP
- Cloud Custodian + OpenOps + Terraform policy generation
- Sub-second response times for compliance checks
- ML-powered tag suggestions and remediation script optimization
- Multi-account scanning across 10+ AWS accounts

✅ **Adoption**
- 50+ active users across FinOps, DevOps, and platform teams
- 500+ compliance audits per month
- 100+ generated remediation scripts executed
- Measurable reduction in untagged resources (target: 80% reduction)

✅ **Operations**
- 99.9% uptime
- <5 minute mean time to recovery
- Zero security incidents
- Automated deployments via CI/CD
- Comprehensive audit trail for all tool invocations

✅ **Business Impact**
- $200K+ annual cost attribution improvement
- 50+ hours/month saved on manual tagging work
- Compliance audit time reduced from 2 days to 30 minutes
- 80% reduction in manual remediation effort
- ROI of 300%+ within 12 months

---

**Document Version**: 2.2
**Last Updated**: February 2026
**Owner**: FinOps Engineering Team
