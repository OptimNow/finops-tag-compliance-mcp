# Phase 2 Specification: Enhanced Compliance + Production Scale

**Version**: 2.0
**Timeline**: ~1.5 weeks (7 working days)
**Status**: Ready for Development
**Prerequisites**: Phase 1 + Phase 1.9 successfully deployed and validated

---

## Overview

Phase 2 adds 6 new tools (remediation script generation, compliance scheduling, drift detection, CSV export, policy import) and server-side automation features, then deploys to production-grade ECS Fargate infrastructure. The functionality remains AWS-only, but the infrastructure is designed for reliability, security, and scale.

**Development Model**: AI-assisted development (Claude builds tools/tests/infrastructure in parallel; user performs UAT and deployment). Sub-phases 2.1-2.4 are developed in parallel (Days 1-3), validated together in UAT 1 (Day 4), then production infrastructure deployed in 2.5 (Days 5-6) and validated in UAT 2 (Day 7).

**Key Improvements from Phase 1**:
- ✅ 6 additional tools (14 total) — Cloud Custodian policies, OpenOps workflows, compliance scheduling, drift detection, CSV export, AWS policy import
- ✅ **Automated daily compliance snapshots** — Server-side scheduled scans for consistent trend tracking
- ✅ **Automatic AWS policy detection** — Zero-touch policy setup on startup
- ✅ ECS Fargate (serverless containers) instead of single EC2
- ✅ Application Load Balancer with SSL/TLS
- ✅ Managed Redis (ElastiCache) and PostgreSQL (RDS)
- ✅ OAuth 2.0 + PKCE authentication (replaces simple API keys)
- ✅ **Agent Safety Enhancements** - Intent disambiguation, cost thresholds, dry run mode
- ✅ Auto-scaling based on load
- ✅ Comprehensive monitoring and alerting
- ✅ Infrastructure as Code (Terraform)

---

## Architecture

### High-Level Architecture

```
                        ┌──────────────────────────┐
                        │   Route 53 (DNS)         │
                        │   mcp.finops.company.com │
                        └────────────┬─────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────┐
                        │ Application Load Balancer│
                        │  - SSL/TLS termination   │
                        │  - Health checks         │
                        └────────────┬─────────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     ▼                               ▼
         ┌─────────────────────┐        ┌─────────────────────┐
         │ ECS Fargate Task 1  │        │ ECS Fargate Task 2  │
         │  - MCP Server       │        │  - MCP Server       │
         │  - Auto-scaled      │        │  - Auto-scaled      │
         └─────────┬───────────┘        └─────────┬───────────┘
                   │                              │
                   └──────────────┬───────────────┘
                                  │
               ┌──────────────────┼──────────────────┐
               ▼                  ▼                  ▼
    ┌──────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │ ElastiCache      │ │ RDS PostgreSQL  │ │ Secrets Manager │
    │ (Redis)          │ │ (Multi-AZ)      │ │ - OAuth keys    │
    │ - Violation cache│ │ - Audit logs    │ │ - API keys      │
    │ - Policy cache   │ │ - User sessions │ └─────────────────┘
    └──────────────────┘ └─────────────────┘
                                  │
                         ┌────────┴────────┐
                         ▼                 ▼
                 ┌─────────────┐  ┌──────────────┐
                 │ CloudWatch  │  │ CloudTrail   │
                 │ - Metrics   │  │ - Audit logs │
                 │ - Alarms    │  └──────────────┘
                 └─────────────┘
                         │
                         ▼
                    ┌─────────────────────┐
                    │   AWS Services      │
                    │  - EC2, RDS, S3...  │
                    └─────────────────────┘
```

### Infrastructure Components

| Component | Specification | Rationale |
|-----------|--------------|-----------|
| **ECS Service** | Fargate launch type, 2-10 tasks | Serverless containers, auto-scaling |
| **Task Definition** | 2 vCPU, 4GB RAM per task | Sufficient for production load |
| **Load Balancer** | Application Load Balancer | SSL/TLS, health checks, path routing |
| **ElastiCache** | cache.t4g.micro (0.5GB) | Managed Redis, Multi-AZ |
| **RDS PostgreSQL** | db.t4g.micro (20GB) | Managed database, Multi-AZ, automated backups |
| **VPC** | 3 subnets across 3 AZs | High availability |
| **Secrets Manager** | 3-5 secrets | OAuth keys, database credentials |
| **CloudWatch** | Logs + Metrics + Alarms | Observability |

---

## Agent Safety Enhancements

Phase 2 adds critical safety features to prevent "intent failure" - where agents execute based on underspecified requests, potentially wasting resources or misleading users.

### Key Safety Features

**1. Intent Disambiguation**
- Detects ambiguous requests (missing region, resource type, time period)
- Triggers clarification loops before execution
- Generates "intent commits" describing what will be executed
- Requires user confirmation for high-stakes operations

**2. Cost & Risk Thresholds**
- Enforces configurable limits (e.g., max 500 resources without approval)
- Estimates API costs before execution
- Requires explicit approval for expensive operations
- Supports progressive disclosure (sample first, expand if needed)

**3. Intent Belief Logging**
- Logs what the agent believed the user wanted
- Captures assumptions made and alternatives considered
- Enables debugging of "why did it do that?" issues
- Tracks whether outcomes matched stated intent

**4. Dry Run Mode**
- Preview operations without executing
- Shows estimated resource count, API calls, cost, and time
- Validates requests before committing
- Doesn't count against tool call budgets

**5. Regret Prediction**
- Identifies potentially regrettable scenarios
- Warns about common mistakes (wrong region, missing resources)
- Learns from user corrections to improve predictions
- Configurable per organization

### Example: Intent Disambiguation Flow

```
User: "Check my compliance"

MCP Server: {
  "clarification_needed": true,
  "ambiguities": [
    {
      "parameter": "resource_types",
      "question": "Which resource types should I check?",
      "options": [
        {"value": ["ec2:instance"], "estimated_resources": 42, "estimated_time": "2s"},
        {"value": ["ec2:instance", "rds:db"], "estimated_resources": 67, "estimated_time": "3s"},
        {"value": "all", "estimated_resources": 450, "estimated_time": "15s", "requires_approval": true}
      ]
    },
    {
      "parameter": "region",
      "question": "Which region(s)?",
      "options": [
        {"value": "us-east-1", "estimated_resources": 42},
        {"value": ["us-east-1", "us-west-2"], "estimated_resources": 89},
        {"value": "all", "estimated_resources": 450, "requires_approval": true}
      ]
    }
  ]
}

User clarifies: "EC2 instances in us-east-1"

MCP Server: {
  "intent_commit": {
    "operation": "check_tag_compliance",
    "parameters": {
      "resource_types": ["ec2:instance"],
      "region": "us-east-1"
    },
    "estimated_scope": {
      "resources": 42,
      "api_calls": 3,
      "estimated_cost": "$0.002",
      "estimated_time": "2s"
    },
    "potential_regrets": [
      "This will only check EC2 instances. RDS databases and S3 buckets will not be included."
    ]
  },
  "approval_required": false,
  "proceed": "Confirm to execute"
}

User: "Confirm"

MCP Server: Executes compliance check
```

For complete requirements and design, see [Agent Safety Enhancements Spec](../.kiro/specs/agent-safety-enhancements/requirements.md).

---

## Phase 2 Sub-Phases (Compressed Timeline)

Phase 2 is delivered in ~1.5 weeks (7 working days) using an AI-assisted development model.

| Sub-Phase | Schedule | Deliverables |
|-----------|----------|-------------|
| **2.1** Remediation Script Generation | Days 1-3 (parallel) | Tools 9-10: `generate_custodian_policy`, `generate_openops_workflow` |
| **2.2** Compliance Tools | Days 1-3 (parallel) | Tools 11-12: `schedule_compliance_audit`, `detect_tag_drift` |
| **2.3** Export & Policy Tools | Days 1-3 (parallel) | Tools 13-14: `export_violations_csv`, `import_aws_tag_policy` |
| **2.4** Auto-Policy + Daily Snapshots | Days 1-3 (parallel) | Automatic policy detection, daily compliance snapshots |
| **🧪 UAT 1** | Day 4 | Functional validation on EC2 — all 14 tools + regression |
| **2.5** ECS Fargate Production | Days 5-6 | ECS, ALB, ElastiCache, RDS, OAuth, CI/CD |
| **🧪 UAT 2** | Day 7 | Production validation on ECS Fargate |

> **⚡ Parallelization**: Phases 2.1-2.4 are developed in parallel since they are independent features touching different files. All are validated together in UAT 1.

---

## MCP Tools (14 Total)

### Existing Tools from Phase 1 (8)

1. `check_tag_compliance` - Validate resource tags
2. `find_untagged_resources` - Find untagged resources
3. `validate_resource_tags` - Check specific resources
4. `get_cost_attribution_gap` - Calculate financial impact
5. `suggest_tags` - ML-powered suggestions
6. `get_tagging_policy` - Retrieve policy
7. `generate_compliance_report` - Executive reports
8. `get_violation_history` - Trend tracking

**Phase 1 Bug Fixes & Enhancements**:
- ✅ Fix S3 bucket ARN support in `suggest_tags` tool (Phase 1 limitation)
- ✅ Add OpenSearch/Elasticsearch domain support to `find_untagged_resources`
- ✅ Improve ARN validation to handle all AWS resource types correctly

### New Tools in Phase 2 (6)

#### 9. generate_custodian_policy

**Purpose**: Generate Cloud Custodian YAML policies from compliance violations

**Sub-Phase**: 2.1 (Days 1-3, parallel)

**Parameters**:
```json
{
  "resource_types": ["ec2:instance", "rds:db"],
  "violation_types": ["missing_tag", "invalid_value"],
  "target_tags": ["Environment", "Owner", "CostCenter"],
  "dry_run": true
}
```

**Returns**:
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

**Features**:
- Generates valid Cloud Custodian policy YAML from violation data
- Supports: tag enforcement, tag normalization, missing tag remediation
- Dry-run mode: generates `notify` actions instead of `tag` actions
- Output is syntactically valid and directly executable with `custodian run`

#### 10. generate_openops_workflow

**Purpose**: Generate OpenOps-compatible automation workflows from compliance violations

**Sub-Phase**: 2.1 (Days 1-3, parallel)

**Parameters**:
```json
{
  "violations": ["compliance_score_below_threshold"],
  "remediation_strategy": "auto_tag",
  "resource_types": ["ec2:instance"],
  "threshold": 0.8
}
```

**Returns**:
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

**Features**:
- Generates OpenOps YAML workflow conforming to platform schema
- Supports: compliance score thresholds, resource type filters, scheduled execution
- Users can go from "check compliance" → "generate remediation" in one conversation

#### 11. schedule_compliance_audit

**Purpose**: Schedule recurring compliance audits

**Sub-Phase**: 2.2 (Days 1-3, parallel)

**Parameters**:
```json
{
  "schedule": "daily | weekly | monthly",
  "time": "09:00",
  "timezone": "America/New_York",
  "resource_types": ["ec2:instance", "rds:db"],
  "recipients": ["finops-team@company.com"],
  "format": "email | slack | both"
}
```

**Returns**:
```json
{
  "schedule_id": "audit-sched-789",
  "next_run": "2026-02-10T09:00:00-05:00",
  "status": "active"
}
```

**Features**:
- Configurable schedule (cron format)
- Full or filtered resource type coverage
- Results stored with "scheduled" flag in history
- CloudWatch metrics for scan success/failure

#### 12. detect_tag_drift

**Purpose**: Detect tags that have changed unexpectedly since last scan

**Sub-Phase**: 2.2 (Days 1-3, parallel)

**Parameters**:
```json
{
  "lookback_days": 7,
  "resource_types": ["ec2:instance"],
  "tag_keys": ["Environment", "Owner"],
  "threshold": 5
}
```

**Returns**:
```json
{
  "drift_detected": [
    {
      "resource_arn": "arn:aws:ec2:...",
      "tag": "Environment",
      "old_value": "production",
      "new_value": "prod",
      "changed_at": "2026-02-08T10:23:00Z",
      "changed_by": "arn:aws:iam::123456789012:user/john.doe",
      "severity": "critical"
    }
  ],
  "total_drifts": 12
}
```

**Features**:
- Compares current tags against last known state
- Reports: tags added, removed, or changed
- Filters by resource type, region, tag key
- Severity classification (required tag removed = critical)

#### 13. export_violations_csv

**Purpose**: Export violation data to CSV format for external analysis

**Sub-Phase**: 2.3 (Days 1-3, parallel)

**Parameters**:
```json
{
  "filters": {
    "severity": "errors_only",
    "resource_types": ["ec2:instance"]
  },
  "columns": ["resource_arn", "resource_type", "violation", "severity", "region"],
  "format": "csv"
}
```

**Returns**:
```json
{
  "data": "resource_arn,resource_type,violation,...\narn:aws:ec2:...,ec2:instance,...",
  "row_count": 450,
  "format": "csv"
}
```

**Features**:
- Configurable columns and filters
- Supports large datasets with pagination
- Download-ready format for spreadsheet analysis

#### 14. import_aws_tag_policy

**Purpose**: Fetch and convert AWS Organizations tag policies at runtime

**Sub-Phase**: 2.3 (Days 1-3, parallel)

**Parameters**:
```json
{
  "policy_id": "p-xxxxxxxx",
  "save_to_file": true,
  "output_path": "policies/tagging_policy.json"
}
```

**Returns**:
```json
{
  "status": "success",
  "policy": {
    "version": "1.0",
    "required_tags": [],
    "optional_tags": []
  },
  "saved_to": "policies/tagging_policy.json",
  "summary": {
    "required_tags_count": 5,
    "optional_tags_count": 2,
    "enforced_services": ["ec2", "rds", "s3"]
  }
}
```

**Features**:
- User-initiated import via Claude Desktop ("Import my AWS tag policy")
- Lists available policies if policy_id not provided
- Automatic conversion and file saving
- IAM permission guidance for insufficient access
- Requires: `organizations:DescribePolicy` and `organizations:ListPolicies`

---

## AWS Organizations Tag Policy Integration

Phase 2 adds seamless integration with AWS Organizations tag policies, making it easy for organizations to import their existing policies and keep them in sync.

### Problem Statement

Most AWS organizations already have tag policies defined in AWS Organizations. Requiring users to manually recreate these policies in our custom format creates friction and blocks adoption. Phase 2 solves this with three integration approaches:

1. **Manual Converter Script** (Phase 1 - Already Implemented)
2. **MCP Tool for Import** (Phase 2.1 - New Tool)
3. **Automatic Detection** (Phase 2.2 - Startup Behavior)

### Tool 14: import_aws_tag_policy

**Purpose**: Fetch and convert AWS Organizations tag policy to MCP format

**Parameters**:
```json
{
  "policy_id": "p-xxxxxxxx",
  "save_to_file": true,
  "output_path": "policies/tagging_policy.json"
}
```

**Returns**:
```json
{
  "status": "success",
  "policy": {
    "version": "1.0",
    "required_tags": [...],
    "optional_tags": [...]
  },
  "saved_to": "policies/tagging_policy.json",
  "summary": {
    "required_tags_count": 5,
    "optional_tags_count": 2,
    "enforced_services": ["ec2", "rds", "s3"]
  }
}
```

**Implementation**:
- Calls `organizations:DescribePolicy` API
- Parses AWS tag policy JSON format
- Converts to MCP server format
- Optionally saves to file
- Returns converted policy

**Error Handling**:
- If no policy_id provided: Lists available policies
- If policy not found: Returns error with available policies
- If insufficient permissions: Returns IAM policy needed

### Automatic Policy Detection (Startup)

On MCP server startup, if `policies/tagging_policy.json` doesn't exist:

1. **Check for AWS Organizations tag policy**
   - Call `organizations:ListPolicies` with filter `TAG_POLICY`
   - If multiple policies found: Use the one attached to the account's OU
   - If one policy found: Use it automatically

2. **Convert and save**
   - Convert AWS policy to MCP format
   - Save to `policies/tagging_policy.json`
   - Log conversion details

3. **Fall back to default**
   - If no AWS policy found: Create minimal default policy
   - Default policy includes: CostCenter, Owner, Environment

4. **Log and notify**
   - Log which policy source was used
   - Include in `/health` endpoint response

**Configuration**:
```yaml
# config.yaml
policy:
  auto_import_aws_policy: true  # Enable automatic import
  aws_policy_id: null  # Specific policy ID, or null for auto-detect
  fallback_to_default: true  # Create default if no AWS policy found
```

### Conversion Logic

**AWS Format → MCP Format Mapping**:

| AWS Field | MCP Field | Notes |
|-----------|-----------|-------|
| `tags.{key}.tag_key.@@assign` | `required_tags[].name` | Tag key with proper capitalization |
| `tags.{key}.tag_value.@@assign` | `required_tags[].allowed_values` | Array of allowed values |
| `tags.{key}.enforced_for.@@assign` | `required_tags[].applies_to` | Resource types |
| `tags.{key}` (no enforced_for) | `optional_tags[]` | Non-enforced tags become optional |

**Special Cases**:
- `ALL_SUPPORTED` wildcard → Expanded to known resource types for that service
- Wildcards in values (e.g., `"300*"`) → Removed (not supported in Phase 2)
- `@@operators` → Ignored (inheritance not applicable)

### Benefits

1. **Zero friction onboarding**: Organizations can start using the MCP server immediately
2. **Single source of truth**: AWS Organizations remains the authoritative policy
3. **Automatic sync**: Server can periodically re-import to stay in sync
4. **Audit trail**: Conversion logged for compliance

### Tool 14 vs Automatic Detection (Phase 2.4)

**Tool 14 `import_aws_tag_policy` (Phase 2.3)**:
- User-initiated import via Claude Desktop
- "Import my AWS tag policy"
- Gives user control over when/how to import

**Automatic Policy Detection (Phase 2.4)**:
- Zero-touch setup on server startup
- Server handles it automatically
- Best for production deployments

---

## Authentication & Authorization

### OAuth 2.0 + PKCE Implementation

Phase 2 replaces simple API keys with OAuth 2.0 for enterprise security.

#### OAuth Flow

```
1. User opens Claude Desktop
2. Claude Desktop initiates OAuth flow with MCP server
3. User redirected to company SSO (e.g., Okta, Azure AD)
4. User authenticates and consents to scopes
5. MCP server issues access token (1 hour expiry)
6. Claude Desktop uses access token for MCP requests
7. Token refresh after expiry
```

#### OAuth Scopes

| Scope | Description | Required For |
|-------|-------------|--------------|
| `tag:read` | Read tag data, compliance reports | All compliance tools (1-14) |
| `admin` | Full access, policy updates, scheduling | Admin operations, scheduled audits |

### Credential Management (AWS)

#### IAM Task Role (ECS Fargate)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TagComplianceReadAccess",
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*",
        "rds:Describe*",
        "rds:ListTagsForResource",
        "s3:GetBucketTagging",
        "s3:ListAllMyBuckets",
        "lambda:List*",
        "ecs:List*",
        "ecs:Describe*",
        "ce:GetCostAndUsage",
        "ce:GetTags",
        "tag:GetResources",
        "tag:GetTagKeys",
        "tag:GetTagValues"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:tagging-mcp/*"
    },
    {
      "Sid": "CloudWatchAccess",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*"
    }
  ]
}
```

**Task Role Name**: `FinOpsTagComplianceFargateTaskRole`

#### Secrets in AWS Secrets Manager

```bash
# OAuth client credentials
aws secretsmanager create-secret \
  --name finops/mcp/oauth-credentials \
  --secret-string '{
    "client_id": "tagging-mcp-prod",
    "client_secret": "...generated...",
    "issuer_url": "https://login.company.com"
  }'

# Database credentials
aws secretsmanager create-secret \
  --name finops/mcp/database-credentials \
  --secret-string '{
    "username": "mcp_admin",
    "password": "...generated...",
    "host": "tagging-mcp-db.xxxxx.us-east-1.rds.amazonaws.com",
    "port": 5432,
    "database": "finops_mcp"
  }'

# API encryption keys
aws secretsmanager create-secret \
  --name finops/mcp/encryption-keys \
  --secret-string '{
    "jwt_secret": "...generated...",
    "api_key_salt": "...generated..."
  }'
```

#### Loading Secrets in Code

```python
# mcp_server/config.py
import boto3
import json
from functools import lru_cache

secrets_client = boto3.client('secretsmanager')

@lru_cache(maxsize=10)
def get_secret(secret_name: str) -> dict:
    """Retrieve and cache secrets from AWS Secrets Manager"""
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

# Usage
oauth_config = get_secret('finops/mcp/oauth-credentials')
db_config = get_secret('finops/mcp/database-credentials')
```

---

## Infrastructure as Code (Terraform)

### Directory Structure

```
terraform/
├── main.tf              # Main configuration
├── variables.tf         # Input variables
├── outputs.tf           # Output values
├── modules/
│   ├── ecs/             # ECS Fargate module
│   ├── rds/             # RDS PostgreSQL module
│   ├── elasticache/     # ElastiCache Redis module
│   ├── alb/             # Application Load Balancer module
│   └── vpc/             # VPC networking module
└── environments/
    ├── dev.tfvars       # Development environment
    ├── staging.tfvars   # Staging environment
    └── prod.tfvars      # Production environment
```

### Example: ECS Fargate Configuration

```hcl
# terraform/modules/ecs/main.tf
resource "aws_ecs_cluster" "main" {
  name = "tagging-mcp-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "mcp_server" {
  family                   = "tagging-mcp-server"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "2048"  # 2 vCPU
  memory                   = "4096"  # 4GB
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn           = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name  = "mcp-server"
      image = "${var.ecr_repository_url}:latest"

      portMappings = [{
        containerPort = 8080
        protocol      = "tcp"
      }]

      environment = [
        {
          name  = "AWS_REGION"
          value = var.aws_region
        },
        {
          name  = "ENVIRONMENT"
          value = var.environment
        }
      ]

      secrets = [
        {
          name      = "OAUTH_CLIENT_ID"
          valueFrom = "${aws_secretsmanager_secret.oauth.arn}:client_id::"
        },
        {
          name      = "DATABASE_URL"
          valueFrom = "${aws_secretsmanager_secret.database.arn}:connection_string::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/tagging-mcp-server"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])
}

resource "aws_ecs_service" "mcp_server" {
  name            = "tagging-mcp-server"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.mcp_server.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = "mcp-server"
    container_port   = 8080
  }

  # Auto-scaling configuration
  depends_on = [aws_lb_listener.https]
}

# Auto-scaling
resource "aws_appautoscaling_target" "ecs_target" {
  max_capacity       = 10
  min_capacity       = 2
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.mcp_server.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "ecs_cpu_policy" {
  name               = "tagging-mcp-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.ecs_target.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_target.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 70.0
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}
```

### Deployment Commands

```bash
# Initialize Terraform
cd terraform
terraform init

# Plan deployment (staging)
terraform plan -var-file=environments/staging.tfvars

# Apply deployment
terraform apply -var-file=environments/staging.tfvars

# Deploy to production
terraform apply -var-file=environments/prod.tfvars
```

---

## Monitoring & Observability

### CloudWatch Dashboards

Create custom dashboard with these widgets:

1. **API Request Metrics**
   - Total requests per minute
   - Error rate (4xx, 5xx)
   - Average response time

2. **Resource Metrics**
   - ECS task count
   - CPU utilization
   - Memory utilization

3. **Database Metrics**
   - RDS connections
   - Query latency
   - Disk usage

4. **Cache Metrics**
   - Redis hit rate
   - Eviction count
   - Memory usage

### CloudWatch Alarms

```hcl
# terraform/modules/monitoring/alarms.tf

resource "aws_cloudwatch_metric_alarm" "high_error_rate" {
  alarm_name          = "tagging-mcp-high-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "5XXError"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "Alert when 5XX errors exceed 10 in 5 minutes"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "tagging-mcp-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 85
  alarm_description   = "Alert when CPU exceeds 85%"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "database_connections" {
  alarm_name          = "tagging-mcp-db-connections-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Alert when database connections exceed 80"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
```

### Structured Logging

```python
# mcp_server/logging_config.py
import structlog
import logging
from pythonjsonlogger import jsonlogger

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Usage in tools
logger.info(
    "tag_compliance_check_completed",
    user_id="user-123",
    compliance_score=0.72,
    resources_checked=450,
    duration_ms=1234
)
```

### X-Ray Tracing

```python
# mcp_server/main.py
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.ext.flask.middleware import XRayMiddleware

# Enable X-Ray tracing
xray_recorder.configure(service='tagging-mcp-server')
XRayMiddleware(app, xray_recorder)

# Trace tool invocations
@xray_recorder.capture('check_tag_compliance')
async def check_tag_compliance(params):
    # Tool implementation
    pass
```

---

## CI/CD Pipeline

### GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy to ECS

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests
        run: pytest tests/ --cov=mcp_server --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v3

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v1

      - name: Build and push Docker image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          ECR_REPOSITORY: finops-tag-compliance-mcp
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker tag $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG $ECR_REGISTRY/$ECR_REPOSITORY:latest
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest

      - name: Deploy to ECS
        run: |
          aws ecs update-service \
            --cluster tagging-mcp-cluster \
            --service tagging-mcp-server \
            --force-new-deployment
```

---

## Database Schema (PostgreSQL)

```sql
-- Audit log table
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    user_id VARCHAR(255) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    parameters JSONB,
    result_summary JSONB,
    duration_ms INTEGER,
    status VARCHAR(20),
    error_message TEXT,
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_tool_name ON audit_logs(tool_name);

-- OAuth sessions table
CREATE TABLE oauth_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    access_token_hash VARCHAR(64) NOT NULL,
    refresh_token_hash VARCHAR(64),
    scopes TEXT[] NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_oauth_sessions_user_id ON oauth_sessions(user_id);
CREATE INDEX idx_oauth_sessions_expires_at ON oauth_sessions(expires_at);

-- Scheduled audits table
CREATE TABLE scheduled_audits (
    id SERIAL PRIMARY KEY,
    schedule_id VARCHAR(50) UNIQUE NOT NULL,
    schedule_type VARCHAR(20) NOT NULL,  -- daily, weekly, monthly
    time TIME NOT NULL,
    timezone VARCHAR(50) NOT NULL,
    recipients TEXT[] NOT NULL,
    format VARCHAR(20) NOT NULL,  -- email, slack, both
    next_run TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) NOT NULL,  -- active, paused, deleted
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

---

## Cost Estimate (Phase 2)

| Component | Monthly Cost |
|-----------|--------------|
| **Compute** | |
| ECS Fargate (2 tasks, 2 vCPU, 4GB each) | $75 |
| **Database** | |
| RDS db.t4g.micro (Multi-AZ) | $30 |
| RDS storage 20GB | $5 |
| **Caching** | |
| ElastiCache cache.t4g.micro | $15 |
| **Networking** | |
| Application Load Balancer | $20 |
| Data transfer | $10 |
| **Secrets & Logs** | |
| Secrets Manager (5 secrets) | $2 |
| CloudWatch Logs (10GB) | $5 |
| CloudWatch Alarms (10 alarms) | $1 |
| **Total** | **~$163/month** |

**Annual**: ~$1,956

**Cost increase from Phase 1**: +$123/month (+308%)
**Value**: Production-grade reliability, auto-scaling, OAuth security

---

## Migration from Phase 1 to Phase 2

### Migration Steps (Compressed Timeline)

1. **Days 1-3**: Build all 6 new tools + server features in parallel
   - Phases 2.1-2.4 developed concurrently (independent features, no conflicts)
   - Regression test harness created before any new code
   - Automated test suite run after each sub-phase

2. **Day 4**: UAT 1 — Functional validation on EC2
   - Deploy updated code to EC2 (`git pull` + restart)
   - Test all 6 new tools (9-14) against real AWS account
   - Run full regression suite against Phase 1 tools
   - Go/no-go decision for production deployment

3. **Days 5-6**: ECS Fargate production deployment
   - Create ECS cluster, RDS, ElastiCache via CloudFormation/CDK
   - Deploy application with OAuth 2.0 authentication
   - Data migration: SQLite → PostgreSQL
   - Verify data integrity

4. **Day 7**: UAT 2 — Production validation
   - Re-run same tool queries from UAT 1 on production
   - Validate ElastiCache, RDS, OAuth all functioning
   - Keep Phase 1 EC2 running as rollback option
   - Update DNS to point to ALB after validation

### Blue/Green Deployment

```bash
# Deploy new ECS service (green)
terraform apply -var="deployment_color=green"

# Test green deployment
curl https://green.mcp.finops.company.com/health

# Switch traffic to green
aws route53 change-resource-record-sets \
  --hosted-zone-id Z123456 \
  --change-batch file://dns-change-to-green.json

# Monitor for 24 hours

# Decommission blue deployment
terraform destroy -target=module.ecs_blue
```

---

## Success Criteria for Phase 2

### Functional Requirements

✅ All 14 tools working in production
✅ OAuth 2.0 authentication functional
✅ Cloud Custodian policies generated from compliance violations
✅ OpenOps workflows generated from compliance data
✅ Daily compliance snapshots running automatically
✅ Automatic AWS policy detection working on startup
✅ Auto-scaling validated (scales from 2 to 10 tasks)

### Non-Functional Requirements

✅ 99.9% uptime over 30-day period
✅ <1 second response time for 95% of requests
✅ Zero security incidents
✅ Successful blue/green deployment
✅ All CloudWatch alarms tested

### Business Requirements

✅ 20+ active users
✅ 100+ compliance audits per month
✅ Generated remediation scripts (Custodian/OpenOps) are syntactically valid
✅ Measurable compliance improvement (5%+ increase)
✅ User satisfaction NPS > 50

---

## Next Steps After Phase 2

1. **Evaluate multi-cloud demand** - Do users need Azure/GCP support?
2. **Codebase modernization** - `src/` layout, `mcp_handler.py` decomposition (deferred to Phase 3)
3. **Multi-account AWS** - AssumeRole scanning across multiple accounts (deferred to Phase 3)
4. **Decide on Phase 3** - Go/no-go for multi-cloud + multi-account expansion

---

**Document Version**: 2.0
**Last Updated**: February 2026
**Ready for Development**: After Phase 1.9 completion
**Development Team**: Claude (AI Developer) + FinOps Engineer (UAT)
