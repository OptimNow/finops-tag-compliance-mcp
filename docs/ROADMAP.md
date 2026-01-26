# FinOps Tag Compliance MCP Server - Implementation Roadmap

**Strategy**: Start Simple, Scale Later
**Total Timeline**: 6 months
**Approach**: Incremental delivery with user feedback loops

---

## Philosophy

Rather than building a complex multi-cloud system upfront, we take an iterative approach:

1. **Phase 1 (Months 1-2)**: Deliver a working AWS-only MCP on a single EC2 instance
2. **Phase 2 (Months 3-4)**: Scale to production-grade infrastructure on ECS Fargate
3. **Phase 3 (Months 5-6)**: Add Azure and GCP support to the proven foundation

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

✅ **Infrastructure**
- Dockerized application
- Single EC2 t3.medium instance
- Redis container for caching
- SQLite for audit logs
- IAM role-based authentication (no credentials in code)

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

**Status**: ✅ Completed (January 2025)

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

## Phase 1.9: Core Library Extraction (Pre-Phase 2 Foundation)

**Status**: Planned
**Goal**: Separate protocol-agnostic business logic from MCP/HTTP transport to unblock Phase 2

**Problem Statement**:
Phase 1 ships as a monolithic FastAPI HTTP server where business logic is coupled with HTTP routing and MCP protocol handling. Before Phase 2 adds 7 new tools, OAuth 2.0, ECS Fargate, agent safety, and multi-account support, the architecture needs a clean separation between reusable core logic and protocol-specific wrappers.

**Deliverables**:
- **Core Library** (`finops_tag_compliance`) -- Pure Python package, pip-installable, importable without HTTP/MCP dependencies. Contains all services, models, clients, and utilities.
- **MCP Server** (`finops_tag_compliance_mcp`) -- Thin wrapper using the `mcp` Python SDK with stdio transport (AWS Labs pattern) and optional HTTP backwards compatibility.
- **ServiceContainer** -- Replaces global state and scattered initialization with explicit dependency injection.
- **stdio transport** -- Native Claude Desktop integration via stdio (like AWS Labs MCP servers), in addition to HTTP.

**Key Changes**:
- `mcp_handler.py` (1475 lines) refactored into `server.py` (~200 lines) using `mcp` SDK's `FastMCP`
- `main.py` lifespan service initialization extracted into `ServiceContainer`
- `config.py` split into `CoreSettings` (AWS, Redis, policy) and `ServerSettings` (host, port, transport)
- Global singleton patterns (`set_budget_tracker()`, `get_loop_detector()`, etc.) eliminated
- No business logic changes; all 8 tools, 9 services, 35+ models unchanged

**Why Before Phase 2**:
| Phase 2 Feature | Without Refactoring | With Refactoring |
|---|---|---|
| Add 7 new tools | Modify 1475-line `mcp_handler.py` | Add one `@mcp.tool()` function each |
| stdio for Claude Desktop | Build separate server | Built-in via `mcp` SDK |
| Multi-account AssumeRole | Hack global state in lifespan | `ServiceContainer` manages clients |
| Agent safety middleware | Entangled with HTTP routing | Composable service decorators |
| CLI/Lambda integration | Impossible (HTTP-only) | Import core library directly |

**Detailed Plan**: See [REFACTORING_PLAN.md](../REFACTORING_PLAN.md) for full analysis, 11 implementation steps, file-by-file mapping, and priority tiers.

**Success Metrics**:
- Core library importable without fastapi/uvicorn/mcp installed
- All existing tests pass with 0 logic changes
- stdio MCP server works with Claude Desktop
- HTTP endpoints preserved for backwards compatibility
- MCP server layer < 300 lines of code

---

## Phase 2: Production Scale - ECS Fargate (Months 3-4)

**Goal**: Production-grade deployment with high availability and managed services

**Scope**: Same AWS-only functionality, but enterprise-ready infrastructure

### Deliverables

✅ **Enhanced MCP Server**
- 16 total tools (add bulk tagging, ML suggestions, scheduling, AWS policy import)
- Step-up authorization for write operations
- Improved caching and performance
- OAuth 2.0 + PKCE authentication
- **Agent Safety Enhancements** - Intent disambiguation, approval workflows, cost thresholds
- **AWS Organizations Integration** - Tool 16: `import_aws_tag_policy` for runtime import
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
- Approval workflows for bulk tagging
- Scheduled compliance audits
- **Automated daily compliance snapshots** - Server runs a full compliance scan daily at a configurable time, storing results in history database for accurate trend tracking (independent of user ad-hoc queries)
- Enhanced audit logging
- Rate limiting and quotas
- **Intent commit pattern** - Agents describe what they'll do before executing
- **Clarification loops** - Resolve ambiguous requests before execution
- **Dry run mode** - Preview operations without executing
- **Cost/risk thresholds** - Require approval for expensive operations

✅ **AWS Organizations Tag Policy Integration (Phase 2.1)**
- **Tool 16: `import_aws_tag_policy`** - Fetch and convert AWS policies at runtime
- User-initiated import via Claude Desktop ("Import my AWS tag policy")
- Lists available policies if policy_id not provided
- Automatic conversion and file saving
- IAM permission guidance for insufficient access

✅ **Automatic Policy Detection (Phase 2.2)**
- Zero-touch policy setup on server startup
- Automatically detects AWS Organizations tag policies
- Converts and saves to `policies/tagging_policy.json`
- Falls back to default policy if no AWS policy found
- Configurable via `config.yaml`
- Periodic re-import to stay in sync with AWS
- Policy source logged in `/health` endpoint

### Success Metrics

- 99.9% uptime SLA
- <1 second response time for compliance checks
- 20+ users across FinOps and DevOps teams
- 100+ compliance audits per month
- Zero security incidents

### Detailed Spec

See [PHASE-2-SPECIFICATION.md](./PHASE-2-SPECIFICATION.md)

### Phase 2.1: AWS Policy Import Tool (Week 1-2)

**Goal**: Enable runtime import of AWS Organizations tag policies via MCP tool

**Deliverables**:
- Tool 16: `import_aws_tag_policy` - Fetch and convert AWS policies
- IAM permissions for `organizations:DescribePolicy` and `organizations:ListPolicies`
- Error handling for missing permissions and invalid policy IDs
- Integration with existing converter logic

**Success Metrics**:
- Users can import AWS policies via Claude Desktop
- "Import my AWS tag policy" command works end-to-end
- Proper error messages guide users through permission issues

### Phase 2.2: Automatic Policy Detection (Week 3-4)

**Goal**: Zero-touch policy setup for production deployments

**Deliverables**:
- Startup logic to detect AWS Organizations tag policies
- Automatic conversion and file saving
- Fallback to default policy if no AWS policy found
- Configuration options in `config.yaml`
- Policy source reporting in `/health` endpoint
- Periodic re-import for policy sync

**Success Metrics**:
- New deployments work without manual policy configuration
- Server automatically finds and uses AWS policies
- Policy changes in AWS Organizations sync to MCP server
- Health endpoint shows policy source and last sync time

### Phase 2.3: Automated Daily Compliance Snapshots (Week 5-6)

**Goal**: Provide consistent, reliable compliance trend data independent of user queries

**Problem Statement**:
Ad-hoc compliance checks (e.g., "check EC2 only" or "check us-east-1") pollute the history database with partial scans. Averaging these partial scans produces meaningless trend data. Users need a consistent daily baseline for accurate trend tracking.

**Solution**:
- Server-side scheduled job runs a full compliance scan daily
- Scans ALL resource types across ALL regions
- Results stored with `store_snapshot=True` flag
- User ad-hoc queries default to `store_snapshot=False` (don't affect history)
- Users can explicitly request `store_snapshot=True` for custom snapshots

**Deliverables**:
- Background scheduler (APScheduler or similar) for daily compliance scans
- Configurable scan time (default: 02:00 UTC)
- Full resource type coverage in scheduled scans
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
- Daily compliance snapshots stored consistently
- Trend analysis shows accurate week-over-week and month-over-month changes
- No pollution from ad-hoc partial scans
- Users can distinguish scheduled vs ad-hoc scans in history

### Phase 2.4: Multi-Account Support via AssumeRole (Week 7-8)

**Goal**: Enable enterprise customers to scan multiple AWS accounts within an organization

**Problem Statement**:
Enterprise customers typically manage 10-100+ AWS accounts within an AWS Organization. Phase 1 only supports scanning a single account. Customers need consolidated compliance reporting across all accounts without deploying separate MCP instances per account.

**Solution**:
Implement cross-account access using AWS AssumeRole pattern. The MCP server assumes a role in each target account to perform compliance scans.

**Deliverables**:
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

**Tool Updates**:
All compliance scanning tools will support the new `accounts` parameter:
```python
async def check_tag_compliance(
    resource_types: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    accounts: Optional[List[str]] = None  # NEW
) -> Dict
```

**IAM Requirements**:
- Main account role needs `sts:AssumeRole` permission
- Target account roles need trust relationship with main account
- Target account roles need read permissions for Resource Groups Tagging API

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

**Success Metrics**:
- Successfully scan 10+ accounts in a single compliance check
- Aggregated reporting shows per-account and total compliance scores
- AssumeRole session caching reduces STS API calls by 80%
- Documentation enables self-service setup for enterprise customers

**Timeline**: Week 7-8 of Phase 2 (2 weeks development + testing)

**Documentation**: See [DEPLOY_MULTI_ACCOUNT.md](./DEPLOY_MULTI_ACCOUNT.md) for complete deployment guide and three deployment options.

---

## Phase 3: Multi-Cloud - Azure + GCP (Months 5-6)

**Goal**: Extend proven MCP server to support Azure and GCP

**Scope**: Same functionality across all three clouds, unified reporting

### Deliverables

✅ **Multi-Cloud MCP Server**
- All 15 tools now support `cloud_provider` parameter (aws, azure, gcp, all)
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

### Success Metrics

- All 3 clouds supported with feature parity
- Cross-cloud compliance reports generated
- 50+ users across multi-cloud teams
- 500+ compliance audits per month across all clouds

### Detailed Spec

See [PHASE-3-SPECIFICATION.md](./PHASE-3-SPECIFICATION.md)

---

## Phase 4: Automation Integration - Script Generation (Months 7-8)

**Goal**: Bridge the gap between compliance intelligence and automated remediation

**Scope**: Generate executable scripts and integrate with automation platforms

### Deliverables

✅ **Script Generation Service**
- Generate AWS CLI scripts for bulk tagging operations
- Generate Terraform/CloudFormation templates for policy enforcement
- Generate PowerShell/Bash scripts for cross-platform automation
- Support for custom script templates and organization standards

✅ **Automation Platform Integration**
- **OpenOps Integration**: Generate OpenOps-compatible automation workflows
- **wiv.ai Integration**: Export compliance data in wiv.ai format for AI-driven remediation
- **Ansible Integration**: Generate Ansible playbooks for infrastructure tagging
- **Terraform Integration**: Generate .tf files for tag enforcement policies

✅ **New MCP Tools (5 Additional - 20 Total)**
- `generate_remediation_script` - Create executable scripts from compliance violations
- `export_for_automation` - Export data for external automation platforms
- `generate_terraform_policy` - Create Terraform tag enforcement policies
- `generate_config_rules` - Create AWS Config rules for automated compliance
- `create_automation_workflow` - Generate platform-specific automation workflows

✅ **Script Generation Features**
- **Multi-format output**: AWS CLI, Terraform, CloudFormation, Ansible, PowerShell, Bash
- **Dry-run mode**: Generate scripts with validation checks before execution
- **Approval workflows**: Integration with existing Phase 2 approval system
- **Custom templates**: Organization-specific script templates and standards
- **Rollback scripts**: Generate undo scripts for safe remediation

### Integration Examples

**OpenOps Workflow Generation**:
```yaml
# Generated OpenOps workflow
name: "Fix EC2 Tagging Violations"
triggers:
  - compliance_score_below: 0.8
steps:
  - name: "Tag EC2 Instances"
    action: "aws_cli"
    script: |
      aws ec2 create-tags --resources i-1234567890abcdef0 \
        --tags Key=CostCenter,Value=Engineering
```

**wiv.ai Data Export**:
```json
{
  "violations": [
    {
      "resource_arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
      "suggested_tags": {"CostCenter": "Engineering"},
      "confidence": 0.85,
      "automation_priority": "high"
    }
  ]
}
```

**Terraform Policy Generation**:
```hcl
# Generated Terraform policy
resource "aws_config_config_rule" "required_tags" {
  name = "required-tags-ec2"
  
  source {
    owner             = "AWS"
    source_identifier = "REQUIRED_TAGS"
  }
  
  input_parameters = jsonencode({
    tag1Key = "CostCenter"
    tag2Key = "Environment"
    tag3Key = "Owner"
  })
}
```

### Success Metrics

- 10+ automation platform integrations working
- 100+ generated scripts executed successfully
- 80% reduction in manual remediation time
- Integration with 3+ external automation platforms

### Detailed Spec

See [PHASE-4-SPECIFICATION.md](./PHASE-4-SPECIFICATION.md)

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

### Phase 3: Multi-Cloud
```
┌──────────────────────────────────────┐
│ Application Load Balancer            │
└────────┬──────────────┬──────────────┘
         │              │
┌────────▼────┐    ┌────▼────┐
│ ECS Task 1  │    │ECS Task 2│
│ Multi-Cloud │    │Multi-Cloud│
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

### Phase 4: Automation Integration
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
    │  - Automation API keys │
    │  - Platform tokens     │
    └────────────────────────┘
         │           │        │        │
         ▼           ▼        ▼        ▼
    ┌────────┐  ┌──────┐  ┌─────┐  ┌──────────┐
    │  AWS   │  │Azure │  │ GCP │  │Automation│
    └────────┘  └──────┘  └─────┘  │Platforms │
                                   │- OpenOps │
                                   │- wiv.ai  │
                                   │- Ansible │
                                   └──────────┘
```

**Cost**: ~$200-280/month

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

### Phase 3 Risks

| Risk | Mitigation |
|------|-----------|
| Azure/GCP API complexity | Start with read-only tools, add write later |
| Credential management | Use managed secrets services, rotate regularly |
| Cross-cloud policy conflicts | Design flexible schema, allow cloud-specific overrides |
| Testing across 3 clouds | Automated integration tests in CI/CD pipeline |

### Phase 4 Risks

| Risk | Mitigation |
|------|-----------|
| Generated script errors | Extensive testing, dry-run mode, rollback scripts |
| Automation platform API changes | Version pinning, adapter pattern, fallback options |
| Security concerns with script execution | Approval workflows, least-privilege, audit logging |
| Integration complexity | Start with 1-2 platforms, expand gradually |

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

### After Phase 2 (Month 4)

**Go/No-Go Decision**: Do users need multi-cloud support?

**Criteria**:
- ✅ Users requesting Azure/GCP support
- ✅ Phase 2 infrastructure stable (99.5%+ uptime for 2 weeks)
- ✅ Budget approved for multi-cloud ($50/month additional)
- ✅ Azure/GCP credentials available for testing

**If NO**: Invest in Phase 2 enhancements (better ML, more automation)

**If YES**: Proceed to Phase 3

### After Phase 3 (Month 6)

**Go/No-Go Decision**: Do users need automation integration and script generation?

**Criteria**:
- ✅ Users requesting automated remediation capabilities
- ✅ Manual tagging workload becoming bottleneck (>20 hours/month)
- ✅ Integration requests from automation platforms (OpenOps, wiv.ai, etc.)
- ✅ Phase 3 multi-cloud functionality stable and adopted

**If NO**: Focus on Phase 3 enhancements (better cross-cloud features, ML improvements)

**If YES**: Proceed to Phase 4

---

## Team Structure

### Phase 1
- 1 Backend Developer (Python, MCP, AWS)
- 0.5 DevOps Engineer (Docker, EC2)
- 0.25 FinOps Practitioner (Requirements, testing)

### Phase 2
- 1 Backend Developer
- 0.5 DevOps Engineer (Terraform, ECS)
- 0.25 Security Engineer (OAuth, secrets management)
- 0.25 FinOps Practitioner

### Phase 3
- 1 Backend Developer
- 0.5 Cloud Engineer (Azure + GCP expertise)
- 0.25 DevOps Engineer
- 0.25 FinOps Practitioner

### Phase 4
- 1 Backend Developer (Script generation, automation APIs)
- 0.5 Integration Engineer (OpenOps, wiv.ai, Ansible expertise)
- 0.25 DevOps Engineer (Terraform, CloudFormation)
- 0.25 Security Engineer (Script validation, approval workflows)

---

## Timeline Summary

| Phase | Duration | Key Milestone | Go-Live Date |
|-------|----------|--------------|--------------|
| **Phase 1** | 8 weeks | AWS-only MCP on EC2 | ✅ Complete (Jan 2026) |
| **Phase 1.5** | (included) | AWS policy converter | ✅ Complete |
| **Phase 1.9** | 2-3 weeks | Core library extraction + stdio server | Before Phase 2 |
| **Phase 2.1** | 2 weeks | AWS policy import tool | End of Week 10 |
| **Phase 2.2** | 2 weeks | Automatic policy detection | End of Week 12 |
| **Phase 2** | 8 weeks total | Production ECS deployment | End of Month 4 |
| **Phase 3** | 8 weeks | Multi-cloud support | End of Month 6 |
| **Phase 4** | 8 weeks | Automation integration | End of Month 8 |

**Total**: ~34 weeks (8.5 months) from kickoff to full automation-integrated deployment

---

## Next Steps

1. **Review this roadmap** with stakeholders
2. **Assign Phase 1 to Kiro** using [PHASE-1-SPECIFICATION.md](./PHASE-1-SPECIFICATION.md)
3. **Set up development environment** (AWS account, Docker, Git repo)
4. **Identify 3-5 beta users** for Phase 1 testing
5. **Schedule weekly check-ins** to track progress

---

## Success Criteria (End of Phase 4)

✅ **Functionality**
- 20 MCP tools working across AWS, Azure, GCP
- Script generation for 5+ automation platforms
- Sub-second response times for compliance checks
- Automated remediation workflows with approval gates
- ML-powered tag suggestions and script optimization

✅ **Adoption**
- 100+ active users across FinOps, DevOps, and platform teams
- 1000+ compliance audits per month
- 500+ generated automation scripts executed
- Integration with 3+ external automation platforms
- Measurable reduction in untagged resources (target: 80% reduction)

✅ **Operations**
- 99.9% uptime
- <5 minute mean time to recovery
- Zero security incidents
- Automated deployments via CI/CD
- Comprehensive audit trail for all generated scripts

✅ **Business Impact**
- $200K+ annual cost attribution improvement
- 50+ hours/month saved on manual tagging work
- Compliance audit time reduced from 2 days to 30 minutes
- 90% reduction in manual remediation effort
- ROI of 300%+ within 12 months

---

**Document Version**: 1.0
**Last Updated**: December 2024
**Owner**: FinOps Engineering Team
