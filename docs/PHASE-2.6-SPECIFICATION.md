# Phase 2.6 Specification: Multi-Tenant Cross-Account Client Deployment

**Version**: 1.0
**Timeline**: ~8-12 working days
**Status**: Ready for Development
**Prerequisites**: Phase 2.5 (ECS Fargate + RDS + ElastiCache) successfully deployed

---

## Overview

Phase 2.6 transforms the MCP server from a single-account tool into a **multi-tenant SaaS platform** where multiple customers connect their AWS accounts via cross-account IAM roles (100% read-only). This is the **production client deployment model** — the customer deploys nothing except a lightweight IAM role via CloudFormation, and OptimNow's centralized MCP server handles all scanning, analysis, and reporting.

This architecture is directly inspired by the **CloudZero connection model**, adapted for tag compliance. It is strictly less intrusive than CloudZero — we store only aggregated compliance scores, never raw CUR data or resource metadata.

**Key Principles**:
- **100% read-only**: Zero write/modify/delete permissions on customer accounts
- **Least-privilege IAM**: ~20 read actions only
- **Customer-revocable**: Delete CloudFormation stack → instant access revocation
- **Open-source IAM policy**: Published on GitHub for security review transparency
- **No raw data storage**: Only compliance scores and aggregated metrics are persisted
- **Remediation is external**: Tag writing is handled by Cloud Custodian / AWS Tag Policies, not by the MCP server

---

## Architecture

### Overall System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         OPTIMNOW ACCOUNT (Control Plane)                        │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                          ECS Fargate Cluster                              │   │
│  │                                                                          │   │
│  │  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐      │   │
│  │  │   ECS Task 1    │    │   ECS Task 2    │    │   ECS Task N    │      │   │
│  │  │                 │    │                 │    │   (auto-scaled) │      │   │
│  │  │  MCP Server     │    │  MCP Server     │    │  MCP Server     │      │   │
│  │  │  + CrossAccount │    │  + CrossAccount │    │  + CrossAccount │      │   │
│  │  │    Client       │    │    Client       │    │    Client       │      │   │
│  │  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘      │   │
│  └───────────┼──────────────────────┼──────────────────────┼────────────────┘   │
│              │                      │                      │                    │
│              └──────────────────────┼──────────────────────┘                    │
│                                     │                                           │
│    ┌────────────────┐    ┌──────────┴──────────┐    ┌────────────────────┐      │
│    │ ElastiCache    │    │  RDS PostgreSQL     │    │  Secrets Manager   │      │
│    │ (Redis)        │    │                     │    │                    │      │
│    │ Prefixed by    │    │  - client_registry  │    │  - API keys        │      │
│    │ client:{id}:   │    │  - audit_logs       │    │  - OAuth secrets   │      │
│    │                │    │  - compliance_history│    │  - License keys    │      │
│    └────────────────┘    │  - license_state    │    └────────────────────┘      │
│                          └─────────────────────┘                                │
│                                                                                 │
│    ┌────────────────────────────────────────────────────────────┐               │
│    │                  Client Onboarding API                      │               │
│    │                                                            │               │
│    │  POST /clients/register    → Generate External ID + CFN URL │               │
│    │  POST /clients/verify      → Test AssumeRole health check   │               │
│    │  GET  /clients/{id}/status → Connection health              │               │
│    │  DELETE /clients/{id}      → Remove from registry           │               │
│    └────────────────────────────────────────────────────────────┘               │
│                                                                                 │
│              │ STS AssumeRole (per client, with unique External ID)              │
└──────────────┼──────────────────────────────────────────────────────────────────┘
               │
    ┌──────────┴────────────────────────────────────────────┐
    │                    │                    │              │
    ▼                    ▼                    ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ CLIENT A     │  │ CLIENT B     │  │ CLIENT C     │  │ CLIENT N     │
│              │  │              │  │              │  │              │
│ IAM Role     │  │ IAM Role     │  │ IAM Role     │  │ IAM Role     │
│ (read-only)  │  │ (read-only)  │  │ (read-only)  │  │ (read-only)  │
│              │  │              │  │              │  │              │
│ ExtID: abc.. │  │ ExtID: def.. │  │ ExtID: ghi.. │  │ ExtID: xyz.. │
│              │  │              │  │              │  │              │
│ 0 compute    │  │ 0 compute    │  │ 0 compute    │  │ 0 compute    │
│ 0 storage    │  │ 0 storage    │  │ 0 storage    │  │ 0 storage    │
│ 0 data copied│  │ 0 data copied│  │ 0 data copied│  │ 0 data copied│
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

### Data Flow — Compliance Scan Request

```
┌────────────┐     ┌────────────────┐     ┌────────────────────┐     ┌──────────────┐
│            │     │                │     │                    │     │              │
│  Claude    │ MCP │   ALB / ECS    │ STS │  Client Account    │ API │  AWS Services │
│  Desktop   │────►│   MCP Server   │────►│  IAM Role          │────►│  in Client    │
│            │     │                │     │  (AssumeRole)      │     │  Account      │
│  with      │     │  Identifies    │     │                    │     │              │
│  API Key   │     │  client via    │     │  Returns temp      │     │  EC2, RDS,   │
│            │     │  API key       │     │  credentials       │     │  S3, Lambda, │
│            │     │                │     │  (1h session)      │     │  ECS, CE     │
└────────────┘     └────────────────┘     └────────────────────┘     └──────────────┘
                           │                                                │
                           │◄───────────────────────────────────────────────┘
                           │  Tags, costs, resource metadata (in memory only)
                           │
                           ▼
                   ┌────────────────┐
                   │                │
                   │  Compliance    │     ┌──────────────────┐
                   │  Engine        │────►│  Redis Cache      │
                   │                │     │  client:A:scan:.. │
                   │  - Validate    │     └──────────────────┘
                   │    against     │
                   │    policy      │     ┌──────────────────┐
                   │  - Calculate   │────►│  RDS PostgreSQL   │
                   │    scores      │     │  compliance_scans │
                   │  - Aggregate   │     │  audit_logs       │
                   │                │     └──────────────────┘
                   └───────┬────────┘
                           │
                           │  Scores + violations (aggregated, no raw data)
                           ▼
                   ┌────────────────┐
                   │  Claude        │
                   │  Desktop       │
                   │  (displays     │
                   │   results)     │
                   └────────────────┘
```

**What flows where**:

| Data | Source | Destination | Persisted? |
|------|--------|-------------|:----------:|
| API Key | Customer → Claude Desktop | ALB → MCP Server | No (in-memory) |
| STS Session | STS → MCP Server | In-memory only | No (cached 15 min) |
| Resource tags | Client AWS Account → MCP Server | In-memory during scan | **No** |
| Resource metadata | Client AWS Account → MCP Server | In-memory during scan | **No** |
| Cost data | Client Cost Explorer → MCP Server | In-memory during scan | **No** |
| Compliance score | MCP Server (computed) | RDS (per client) | **Yes** (aggregated only) |
| Violation summary | MCP Server (computed) | Redis cache (TTL 1h) | **Yes** (temporary) |
| Audit log | MCP Server | RDS (per client) | **Yes** |

**Key guarantee**: Raw resource tags, metadata, and cost data are **never persisted**. They exist in memory only during the scan, are used to compute compliance scores, and are then discarded. Only the aggregated results (scores, violation counts, cost attribution gaps) are stored.

---

## Customer Onboarding Path

### Step-by-Step Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     CUSTOMER ONBOARDING JOURNEY                              │
│                     Total time: ~5-10 minutes                                │
└──────────────────────────────────────────────────────────────────────────────┘

  STEP 1                  STEP 2                  STEP 3
  Sign Up                 Deploy IAM Role          Connect
  ┌──────────┐           ┌──────────────┐         ┌──────────────┐
  │          │           │              │         │              │
  │ optimnow │ External  │ AWS Console  │ Role    │ optimnow.io  │
  │ .io      │───ID────► │ CloudForm.   │──ARN──► │ verify       │
  │ sign up  │ + CFN URL │ 1-click      │         │ connection   │
  │          │           │ deploy       │         │              │
  └──────────┘           └──────────────┘         └──────────────┘
      2 min                  2 min                    1 min

  STEP 4                  STEP 5
  Configure Client        Start Scanning
  ┌──────────────┐       ┌──────────────┐
  │              │       │              │
  │ Claude       │       │ "Check my    │
  │ Desktop      │       │  compliance" │
  │ config       │       │              │
  │ (API key)    │       │ Results ✅    │
  │              │       │              │
  └──────────────┘       └──────────────┘
      2 min                  Instant
```

### Detailed Steps

#### Step 1: Customer Registration

**Trigger**: Customer signs up on optimnow.io or contacts sales

**API Call**: `POST /clients/register`

**Request**:
```json
{
  "company_name": "Acme Corp",
  "contact_email": "finops@acme.com",
  "plan": "professional",
  "license_key": "OPT-PRO-3A9F2-B4C1D"
}
```

**Response**:
```json
{
  "client_id": "cl_8f3a2b1c",
  "external_id": "optimnow-cl_8f3a2b1c-x7k9m2p4q6r8",
  "api_key": "sk_live_abc123def456...",
  "cloudformation_url": "https://console.aws.amazon.com/cloudformation/home#/stacks/create/review?templateURL=https://optimnow-cfn-templates.s3.amazonaws.com/client-readonly.yaml&param_OptimNowAccountId=123456789012&param_ExternalId=optimnow-cl_8f3a2b1c-x7k9m2p4q6r8",
  "cloudformation_template_url": "https://github.com/optimnow/finops-tag-compliance-mcp/blob/main/infrastructure/cloudformation-client-readonly.yaml",
  "setup_instructions": "1. Click the CloudFormation URL above\n2. Review the IAM permissions (read-only)\n3. Check 'I acknowledge that this template creates IAM resources'\n4. Click 'Create stack'\n5. Copy the Role ARN from the Outputs tab\n6. Come back here and paste the Role ARN"
}
```

**What happens on the server**:
1. Validate license key against license server
2. Generate unique `client_id` (format: `cl_` + 8 hex chars)
3. Generate unique `external_id` (format: `optimnow-{client_id}-{random}`, 16+ chars)
4. Generate unique API key for this client
5. Store in `client_registry` table (RDS):
   ```sql
   INSERT INTO client_registry (
     client_id, company_name, contact_email, plan,
     external_id, api_key_hash, license_key,
     status, created_at
   ) VALUES (
     'cl_8f3a2b1c', 'Acme Corp', 'finops@acme.com', 'professional',
     'optimnow-cl_8f3a2b1c-x7k9m2p4q6r8', sha256('sk_live_abc123...'),
     'OPT-PRO-3A9F2-B4C1D',
     'pending_setup', NOW()
   );
   ```
6. Build CloudFormation 1-click URL with pre-filled parameters

#### Step 2: IAM Role Deployment (Customer Action)

**Customer clicks the CloudFormation URL** → lands in AWS Console with pre-filled template.

**What the template creates** (see `infrastructure/cloudformation-client-readonly.yaml`):
- 1 IAM Role (`OptimNow-TagCompliance-ReadOnly`)
- 1 IAM Policy with 20 read-only actions
- Trust policy: only OptimNow account + matching External ID can assume

**Customer actions**:
1. Review the template (all permissions visible)
2. Check "I acknowledge that this template creates IAM resources"
3. Click "Create stack"
4. Wait ~60 seconds for stack creation
5. Go to Outputs tab → copy Role ARN

**What is NOT created**: No compute (EC2, Lambda, ECS), no storage (S3, RDS), no networking (VPC, subnets), no data transfer.

#### Step 3: Connection Verification

**Customer provides Role ARN back to OptimNow**

**API Call**: `POST /clients/verify`

```json
{
  "client_id": "cl_8f3a2b1c",
  "role_arn": "arn:aws:iam::987654321098:role/OptimNow-TagCompliance-ReadOnly"
}
```

**What the server does**:
1. Validate ARN format
2. Extract account ID from ARN (must be 12 digits)
3. Attempt STS AssumeRole with stored External ID:
   ```python
   sts_client.assume_role(
       RoleArn="arn:aws:iam::987654321098:role/OptimNow-TagCompliance-ReadOnly",
       RoleSessionName="optimnow-verify-cl_8f3a2b1c",
       ExternalId="optimnow-cl_8f3a2b1c-x7k9m2p4q6r8",
       DurationSeconds=900  # 15 min for verification
   )
   ```
4. If successful, test a lightweight API call (`sts:GetCallerIdentity`)
5. Update client status to `active`
6. Return verification result

**Response** (success):
```json
{
  "status": "connected",
  "client_id": "cl_8f3a2b1c",
  "aws_account_id": "987654321098",
  "role_arn": "arn:aws:iam::987654321098:role/OptimNow-TagCompliance-ReadOnly",
  "verified_at": "2026-02-12T15:30:00Z",
  "permissions_verified": [
    "tag:GetResources",
    "ec2:DescribeRegions",
    "sts:GetCallerIdentity"
  ]
}
```

**Response** (failure):
```json
{
  "status": "connection_failed",
  "error": "access_denied",
  "message": "Cannot assume role. Please verify: (1) The CloudFormation stack completed successfully, (2) The Role ARN is correct, (3) The External ID matches.",
  "troubleshooting_url": "https://docs.optimnow.io/troubleshooting/connection"
}
```

#### Step 4: Claude Desktop Configuration

Customer configures their Claude Desktop to use OptimNow:

```json
{
  "mcpServers": {
    "optimnow-finops": {
      "command": "python",
      "args": ["mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://mcp.optimnow.io",
        "API_KEY": "sk_live_abc123def456..."
      }
    }
  }
}
```

The API key identifies the client, which maps to their Role ARN and External ID on the server side. The customer never handles AWS credentials directly.

#### Step 5: First Scan

Customer asks Claude: *"Check my tag compliance"*

Behind the scenes:
1. MCP bridge sends request to `https://mcp.optimnow.io` with API key header
2. Server identifies client from API key → retrieves `role_arn` and `external_id`
3. Server calls STS AssumeRole (or uses cached session)
4. Server scans client's AWS resources using temporary credentials
5. Compliance engine validates tags against policy
6. Results returned to Claude Desktop
7. Scores stored in RDS (per client), raw data discarded

---

## Deliverables

### 1. Client CloudFormation Template

**File**: `infrastructure/cloudformation-client-readonly.yaml`
**Status**: ✅ Created

IAM role with:
- Trust policy → OptimNow account + External ID condition
- 20 read-only actions across 7 AWS services
- Zero write permissions
- 1-hour maximum session duration
- Self-documenting outputs (Role ARN, permissions summary, revocation instructions)

### 2. Cross-Account Client Module

**File**: `mcp_server/clients/cross_account_client.py`

```python
class CrossAccountClient:
    """Manages STS AssumeRole sessions for multi-tenant cross-account access."""

    def __init__(self, sts_client, session_cache_ttl: int = 900):
        self._sts_client = sts_client
        self._session_cache: dict[str, CachedSession] = {}
        self._session_cache_ttl = session_cache_ttl  # 15 min default

    async def get_client_for(
        self, client_id: str, role_arn: str, external_id: str
    ) -> AWSClient:
        """
        Returns an AWSClient authenticated as the client's cross-account role.
        Uses cached STS sessions when available (15-min TTL).
        """
        ...

    async def verify_access(
        self, role_arn: str, external_id: str
    ) -> VerifyResult:
        """
        Tests AssumeRole and basic API access.
        Used during onboarding to confirm the connection works.
        """
        ...

    def revoke_session(self, client_id: str) -> None:
        """Immediately invalidates cached session for a client."""
        ...
```

**Session lifecycle**:

```
                    ┌──────────────────────────────────┐
                    │        Session Cache              │
                    │                                  │
   Request for      │   client_id → CachedSession      │
   client A ──────► │     ├─ credentials (temp)         │
                    │     ├─ expiry (created + 15min)   │
                    │     └─ aws_client (reusable)      │
                    │                                  │
                    │   if expired or missing:          │
                    │     → STS AssumeRole              │
                    │     → create new AWSClient        │
                    │     → cache for 15 min            │
                    └──────────────────────────────────┘
```

**Error handling**:

| Error | Cause | Action |
|-------|-------|--------|
| `AccessDenied` | Role doesn't exist or External ID mismatch | Return clear error, suggest re-deploying CloudFormation |
| `MalformedPolicyDocument` | Role permissions changed | Return error, suggest re-deploying template |
| `ExpiredTokenException` | Cached session expired | Auto-refresh (transparent to user) |
| `RegionDisabledException` | Region not enabled in client account | Skip region, note in results |
| `Throttling` | Too many STS calls | Exponential backoff + cache warming |

### 3. Client Registry (Database Schema)

**Tables added to RDS PostgreSQL**:

```sql
-- Client registration and connection state
CREATE TABLE client_registry (
    client_id         VARCHAR(20) PRIMARY KEY,       -- cl_8f3a2b1c
    company_name      VARCHAR(255) NOT NULL,
    contact_email     VARCHAR(255) NOT NULL,
    plan              VARCHAR(50) NOT NULL,           -- starter, professional, enterprise
    external_id       VARCHAR(64) NOT NULL UNIQUE,    -- STS External ID
    api_key_hash      VARCHAR(64) NOT NULL,           -- SHA256 of API key
    license_key       VARCHAR(50),
    role_arn          VARCHAR(255),                    -- Set after verification
    aws_account_id    VARCHAR(12),                     -- Extracted from Role ARN
    status            VARCHAR(20) NOT NULL DEFAULT 'pending_setup',
                      -- pending_setup → active → suspended → revoked
    max_resources     INTEGER NOT NULL DEFAULT 1000,   -- Tier limit
    max_accounts      INTEGER NOT NULL DEFAULT 1,      -- Multi-account limit
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    verified_at       TIMESTAMP,
    last_scan_at      TIMESTAMP,
    last_health_check TIMESTAMP,
    scan_count        INTEGER NOT NULL DEFAULT 0,
    total_resources_scanned BIGINT NOT NULL DEFAULT 0
);

-- Per-client compliance history (extends existing compliance_scans)
CREATE TABLE client_compliance_scans (
    id                  SERIAL PRIMARY KEY,
    client_id           VARCHAR(20) NOT NULL REFERENCES client_registry(client_id),
    timestamp           TIMESTAMP NOT NULL DEFAULT NOW(),
    compliance_score    FLOAT NOT NULL,
    total_resources     INTEGER NOT NULL,
    compliant_resources INTEGER NOT NULL,
    violation_count     INTEGER NOT NULL,
    cost_attribution_gap FLOAT,
    regions_scanned     INTEGER,
    scan_type           VARCHAR(20) DEFAULT 'ad_hoc',  -- ad_hoc, scheduled
    scan_duration_ms    INTEGER,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_client_scans_client_id ON client_compliance_scans(client_id);
CREATE INDEX idx_client_scans_timestamp ON client_compliance_scans(timestamp);

-- Per-client audit logs (extends existing audit_log)
CREATE TABLE client_audit_logs (
    id                SERIAL PRIMARY KEY,
    client_id         VARCHAR(20) NOT NULL REFERENCES client_registry(client_id),
    timestamp         TIMESTAMP NOT NULL DEFAULT NOW(),
    correlation_id    VARCHAR(36),
    tool_name         VARCHAR(100) NOT NULL,
    parameters        JSONB,
    status            VARCHAR(20) NOT NULL,            -- success, error
    execution_time_ms FLOAT,
    error_message     TEXT,
    resources_scanned INTEGER
);

CREATE INDEX idx_client_audit_client_id ON client_audit_logs(client_id);

-- Usage metering for billing
CREATE TABLE client_usage_metering (
    id                  SERIAL PRIMARY KEY,
    client_id           VARCHAR(20) NOT NULL REFERENCES client_registry(client_id),
    period_start        DATE NOT NULL,                   -- First day of month
    period_end          DATE NOT NULL,                   -- Last day of month
    scan_count          INTEGER NOT NULL DEFAULT 0,
    resources_scanned   BIGINT NOT NULL DEFAULT 0,
    regions_scanned     INTEGER NOT NULL DEFAULT 0,
    api_calls_made      BIGINT NOT NULL DEFAULT 0,
    peak_resources      INTEGER NOT NULL DEFAULT 0,      -- Max resources in single scan
    UNIQUE(client_id, period_start)
);
```

### 4. Client Onboarding API

**Endpoints added to FastAPI** (`mcp_server/api/clients.py`):

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| `POST` | `/clients/register` | Create new client, generate External ID | Admin API key |
| `POST` | `/clients/verify` | Test AssumeRole, activate client | Client API key |
| `GET` | `/clients/{id}/status` | Connection health + usage stats | Client API key |
| `DELETE` | `/clients/{id}` | Deactivate client (soft delete) | Admin API key |
| `GET` | `/clients/{id}/usage` | Monthly usage metering | Client API key |
| `POST` | `/clients/{id}/health-check` | Re-test AssumeRole connection | Client API key |

**Status transitions**:

```
  pending_setup ──── verify ────► active
                                    │
                    ┌───────────────┤
                    ▼               ▼
                suspended       revoked
                    │               │
                    ▼               │
                  active            │
                    │               │
                    └───────────────┘
                    (delete client)
```

### 5. Client Isolation

**Cache isolation** (Redis):
```
# Before (single-tenant)
cache_key = sha256(f"{resource_types}:{regions}:{severity}")

# After (multi-tenant)
cache_key = f"client:{client_id}:" + sha256(f"{resource_types}:{regions}:{severity}")
```

**Rate limiting** (per client):
```python
# Per-client limits (configurable by plan)
RATE_LIMITS = {
    "starter":      {"scans_per_hour": 10,  "resources_per_scan": 1_000},
    "professional": {"scans_per_hour": 50,  "resources_per_scan": 10_000},
    "enterprise":   {"scans_per_hour": 200, "resources_per_scan": 100_000},
}
```

**API key → client_id resolution**:
```python
# In auth middleware
async def resolve_client(api_key: str) -> ClientInfo:
    """Look up client from API key. Cached in Redis for 5 min."""
    cache_key = f"apikey:{sha256(api_key)}"
    cached = await redis.get(cache_key)
    if cached:
        return ClientInfo.parse_raw(cached)

    # Database lookup
    client = await db.query(
        "SELECT * FROM client_registry WHERE api_key_hash = %s AND status = 'active'",
        sha256(api_key)
    )
    if not client:
        raise AuthenticationError("Invalid or inactive API key")

    await redis.setex(cache_key, 300, client.json())
    return client
```

### 6. Licensing & Metering

**Resource counting** (per scan):
```python
async def check_resource_quota(client: ClientInfo, resource_count: int):
    """Enforce tier resource limits."""
    if resource_count > client.max_resources:
        raise QuotaExceededError(
            f"Your {client.plan} plan supports up to {client.max_resources} resources. "
            f"This scan found {resource_count} resources. "
            f"Upgrade to Professional or Enterprise for higher limits."
        )
```

**Monthly metering** (for billing):
```python
async def record_usage(client_id: str, scan_result: ComplianceResult):
    """Record usage for monthly billing."""
    await db.execute("""
        INSERT INTO client_usage_metering (client_id, period_start, period_end,
            scan_count, resources_scanned, regions_scanned, api_calls_made, peak_resources)
        VALUES (%s, date_trunc('month', NOW()), (date_trunc('month', NOW()) + interval '1 month' - interval '1 day'),
            1, %s, %s, %s, %s)
        ON CONFLICT (client_id, period_start)
        DO UPDATE SET
            scan_count = client_usage_metering.scan_count + 1,
            resources_scanned = client_usage_metering.resources_scanned + EXCLUDED.resources_scanned,
            regions_scanned = GREATEST(client_usage_metering.regions_scanned, EXCLUDED.regions_scanned),
            api_calls_made = client_usage_metering.api_calls_made + EXCLUDED.api_calls_made,
            peak_resources = GREATEST(client_usage_metering.peak_resources, EXCLUDED.peak_resources)
    """, client_id, scan_result.total_resources, scan_result.regions_scanned,
         scan_result.api_calls, scan_result.total_resources)
```

---

## Security Model

### Threat Analysis

| # | Threat | Severity | Mitigation | Residual Risk |
|---|--------|----------|------------|---------------|
| 1 | **Confused deputy attack** — Attacker tricks OptimNow into assuming a role in their account | Critical | External ID unique per client, validated by STS | Very Low |
| 2 | **Privilege escalation** — MCP server writes/deletes resources in client account | Critical | 100% read-only IAM policy, zero write actions. Policy is open-source for audit. | None (by design) |
| 3 | **Cross-client data leakage** — Client A sees Client B's data | High | STS sessions isolated per client. Cache prefixed by `client_id`. Audit logs partitioned. Database queries always filtered by `client_id`. | Low |
| 4 | **OptimNow account compromise** — Attacker gains access to OptimNow AWS account | High | Blast radius = read-only on all clients. No write access = no destructive actions. Clients can revoke independently. | Medium (read access to tags/costs) |
| 5 | **Data exfiltration** — Raw resource data exported | Medium | Raw data never persisted. Only scores stored. Audit logs track every scan. | Low |
| 6 | **Stale access** — Client departs but role remains | Medium | Health check endpoint. Monthly connection validation. Client notification if role expires. | Low |
| 7 | **API key theft** — Attacker steals client API key | Medium | API keys hashed in database. Rate limiting per key. IP allowlisting (enterprise). Key rotation via API. | Low |
| 8 | **Denial of service** — Attacker floods API | Medium | Per-client rate limiting. Global rate limiting. WAF on ALB. | Low |

### Comparison with CloudZero Security Model

| Security Aspect | CloudZero | OptimNow | Notes |
|----------------|-----------|----------|-------|
| Access model | Cross-account IAM role | Cross-account IAM role | Identical |
| Permission scope | Read-only (~40 actions) | Read-only (~20 actions) | **We request fewer permissions** |
| External ID | Yes | Yes | Identical |
| Data persisted | Full CUR + resource metadata | Compliance scores only | **We store less data** |
| Provisioning | CloudFormation | CloudFormation | Identical |
| Policy transparency | Open-source on GitHub | Open-source on GitHub | Identical |
| Revocation method | Delete CloudFormation stack | Delete CloudFormation stack | Identical |
| Session duration | Not disclosed | 1 hour max, 15-min cache | Documented |
| Write access | None | None | Identical |
| SOC 2 compliance | Yes | Target (Phase 3) | Gap |

### IAM Permissions — Complete List

The client IAM role requests exactly **20 read-only actions** across 7 AWS services:

```
Service                      Action                          Purpose
─────────────────────────────────────────────────────────────────────────
Resource Groups Tagging API  tag:GetResources                Universal tag discovery
                             tag:GetTagKeys                  List all tag keys
                             tag:GetTagValues                List values for a key

EC2                          ec2:DescribeInstances           Instance tag reading
                             ec2:DescribeTags                Tag listing
                             ec2:DescribeVolumes             Volume tag reading
                             ec2:DescribeRegions             Region discovery

RDS                          rds:DescribeDBInstances         Database tag reading
                             rds:ListTagsForResource         Tag listing

S3                           s3:ListAllMyBuckets             Bucket listing
                             s3:GetBucketTagging             Bucket tag reading
                             s3:GetBucketLocation            Bucket region

Lambda                       lambda:ListFunctions            Function listing
                             lambda:ListTags                 Function tag reading

ECS                          ecs:ListClusters                Cluster listing
                             ecs:ListServices                Service listing
                             ecs:DescribeServices            Service details
                             ecs:ListTagsForResource         Service tag reading

Cost Explorer                ce:GetCostAndUsage              Cost data
                             ce:GetCostAndUsageWithResources  Per-resource costs

STS                          sts:GetCallerIdentity           Health check
─────────────────────────────────────────────────────────────────────────
TOTAL: 21 actions, ALL read-only, ZERO write/modify/delete
```

---

## Configuration

### Environment Variables (OptimNow Server)

```bash
# Cross-account settings
CROSS_ACCOUNT_ENABLED=true                    # Enable multi-tenant mode
STS_SESSION_CACHE_TTL_SECONDS=900             # 15 min session cache
STS_SESSION_DURATION_SECONDS=3600             # 1 hour max session
MAX_CONCURRENT_CLIENT_SCANS=10                # Parallel client scans

# Client onboarding
CLIENT_CFN_TEMPLATE_BUCKET=optimnow-cfn-templates  # S3 bucket for CFN template
CLIENT_CFN_TEMPLATE_KEY=client-readonly.yaml        # Template key in bucket

# Rate limiting (per client, per hour)
STARTER_SCANS_PER_HOUR=10
PROFESSIONAL_SCANS_PER_HOUR=50
ENTERPRISE_SCANS_PER_HOUR=200
```

### Client Configuration (Claude Desktop)

```json
{
  "mcpServers": {
    "optimnow-finops": {
      "command": "python",
      "args": ["mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "https://mcp.optimnow.io",
        "API_KEY": "sk_live_..."
      }
    }
  }
}
```

---

## Implementation Plan

### Day-by-Day Breakdown

| Day | Deliverable | Files |
|-----|-------------|-------|
| **Day 1** | Client CloudFormation template (done) + DB schema | `infrastructure/cloudformation-client-readonly.yaml`, SQL migrations |
| **Day 2-3** | Cross-account client module | `mcp_server/clients/cross_account_client.py` |
| **Day 4-5** | Client onboarding API | `mcp_server/api/clients.py`, route registration |
| **Day 6-7** | Client isolation (cache, audit, rate limiting) | `mcp_server/clients/cache.py`, `mcp_server/middleware/` |
| **Day 8** | MCP tools integration (pass client context through all tools) | `mcp_server/tools/*.py`, `mcp_server/stdio_server.py` |
| **Day 9-10** | Licensing, metering, quota enforcement | `mcp_server/services/license_service.py`, `mcp_server/services/metering_service.py` |
| **Day 11** | Integration testing (multi-client scans, isolation, error cases) | `tests/integration/test_cross_account.py` |
| **Day 12** | Documentation + onboarding guide | `docs/CLIENT_ONBOARDING.md` |

### Dependencies

```
Phase 2.5 (ECS + RDS + Redis)
    │
    ├── Day 1: DB schema (requires RDS)
    │
    ├── Day 2-3: CrossAccountClient (requires working STS)
    │
    ├── Day 4-5: Onboarding API (requires DB schema + CrossAccountClient)
    │
    ├── Day 6-7: Isolation (requires Redis + DB)
    │
    ├── Day 8: Tool integration (requires CrossAccountClient + Isolation)
    │
    ├── Day 9-10: Licensing (requires Onboarding API + Metering tables)
    │
    ├── Day 11: Integration tests (requires all above)
    │
    └── Day 12: Documentation
```

---

## Success Criteria

| Criterion | Target | Measurement |
|-----------|--------|-------------|
| Onboarding time | < 10 minutes | Time from sign-up to first scan |
| Connection verification | < 30 seconds | Time for AssumeRole health check |
| Client isolation | Zero cross-leakage | Penetration testing |
| Concurrent clients | 10+ simultaneous | Load testing |
| Scan response time | < 5 seconds (cached) | Performance testing |
| Session refresh | Transparent to user | No errors during session rotation |
| Quota enforcement | Block at limit | Unit tests |
| Revocation | Immediate on CFN delete | Manual verification |

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|:-----------:|:------:|------------|
| STS rate limiting under load | Medium | High | Session caching (15 min), limit concurrent AssumeRole calls |
| Customer deploys wrong CFN template | Low | Medium | Pre-filled 1-click URL, clear error messages on verification |
| Cross-client data leak via cache bug | Low | Critical | Cache keys always prefixed with `client_id`, integration test coverage |
| Customer role permissions too restrictive | Medium | Low | Clear permission error messages, troubleshooting guide |
| License server downtime blocks scans | Low | High | Cache license validation result for 24h, graceful degradation |
| STS session expiry during long scan | Medium | Medium | Auto-refresh before expiry, no scan takes > 1 hour |

---

## Open Questions

1. **Multi-account per client**: Should a single client (e.g., Acme Corp) connect multiple AWS accounts (dev, staging, prod)? If yes, the registry needs a `client_accounts` join table. *Recommendation*: Yes for Professional and Enterprise plans.

2. **Custom tagging policies per client**: Should each client have their own tagging policy, or use a shared default? *Recommendation*: Start with shared default, allow custom policy upload in Enterprise plan.

3. **Scheduled scans for clients**: Should the server run daily compliance snapshots for all connected clients, or only on-demand? *Recommendation*: On-demand only for now (Phase 2.4 scheduler can be extended to multi-tenant later).

4. **Dashboard MVP**: What does the first version of the client dashboard look like? *Recommendation*: Defer to a later phase. Start with Claude Desktop as the only interface.

---

**Document Version**: 1.0
**Last Updated**: February 2026
**Owner**: FinOps Engineering Team
**Related**: [ROADMAP.md](./ROADMAP.md) (Phase 2.6), [cloudformation-client-readonly.yaml](../infrastructure/cloudformation-client-readonly.yaml)
