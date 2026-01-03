# Phase 2 Specification: Production-Grade ECS Fargate Deployment

**Version**: 1.0
**Timeline**: Months 3-4 (8 weeks)
**Status**: Ready for Development (after Phase 1 completion)
**Prerequisites**: Phase 1 successfully deployed and validated

---

## Overview

Phase 2 transforms the Phase 1 MVP into a production-grade service with high availability, auto-scaling, and enterprise features. The functionality remains AWS-only, but the infrastructure is designed for reliability, security, and scale.

**Key Improvements from Phase 1**:
- ✅ ECS Fargate (serverless containers) instead of single EC2
- ✅ Application Load Balancer with SSL/TLS
- ✅ Managed Redis (ElastiCache) and PostgreSQL (RDS)
- ✅ OAuth 2.0 + PKCE authentication (replaces simple API keys)
- ✅ Step-up authorization for write operations
- ✅ 7 additional tools (15 total) including bulk tagging
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

## MCP Tools (15 Total)

### Existing Tools from Phase 1 (8)

1. `check_tag_compliance` - Validate resource tags
2. `find_untagged_resources` - Find untagged resources
3. `validate_resource_tags` - Check specific resources
4. `get_cost_attribution_gap` - Calculate financial impact
5. `suggest_tags` - ML-powered suggestions
6. `get_tagging_policy` - Retrieve policy
7. `generate_compliance_report` - Executive reports
8. `get_violation_history` - Trend tracking

### New Tools in Phase 2 (7)

#### 9. bulk_tag_resources (Write Operation - Step-Up Auth Required)

**Purpose**: Apply tags to multiple resources with approval workflow

**Authentication**: Requires step-up authorization (OAuth 2.0 with elevated scope)

**Parameters**:
```json
{
  "resource_arns": [
    "arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123",
    "arn:aws:ec2:us-east-1:123456789012:instance/i-0def456"
  ],
  "tags": {
    "CostCenter": "Engineering",
    "Owner": "platform-team@company.com"
  },
  "dry_run": false,
  "approval_required": true
}
```

**Returns**:
```json
{
  "request_id": "bulk-tag-req-12345",
  "status": "pending_approval",
  "resources_affected": 2,
  "estimated_compliance_improvement": 0.04,
  "approval_url": "https://mcp.finops.company.com/approvals/12345",
  "approvers": ["john.doe@company.com", "jane.smith@company.com"]
}
```

**Step-Up Flow**:
1. User requests bulk tagging
2. MCP server checks if user has `tag:write` scope
3. If NO: Returns 403 with step-up auth URL
4. User re-authenticates with elevated scope
5. Request creates approval ticket
6. Approver reviews and approves/denies
7. If approved: Tags applied, audit logged

#### 10. preview_bulk_tagging

**Purpose**: Preview impact of bulk tagging before execution

**Parameters**:
```json
{
  "resource_arns": ["arn:aws:ec2:..."],
  "tags": {"CostCenter": "Engineering"}
}
```

**Returns**:
```json
{
  "preview": {
    "resources_affected": 42,
    "current_compliance": 0.68,
    "projected_compliance": 0.72,
    "compliance_improvement": 0.04,
    "cost_attribution_gap_reduction": 5200.00,
    "resources": [
      {
        "arn": "arn:aws:ec2:...",
        "current_tags": {"Environment": "production"},
        "new_tags": {"Environment": "production", "CostCenter": "Engineering"},
        "tags_added": ["CostCenter"],
        "tags_changed": []
      }
    ]
  }
}
```

#### 11. approve_bulk_tagging_request

**Purpose**: Approve or deny pending bulk tagging requests

**Authorization**: Requires `tag:approve` role

**Parameters**:
```json
{
  "request_id": "bulk-tag-req-12345",
  "action": "approve | deny",
  "comment": "Approved - Engineering team resources"
}
```

**Returns**:
```json
{
  "request_id": "bulk-tag-req-12345",
  "status": "approved",
  "executed": true,
  "resources_tagged": 42,
  "execution_time": "2024-12-15T14:32:00Z"
}
```

#### 12. schedule_compliance_audit

**Purpose**: Schedule recurring compliance audits

**Parameters**:
```json
{
  "schedule": "daily | weekly | monthly",
  "time": "09:00",
  "timezone": "America/New_York",
  "recipients": ["finops-team@company.com"],
  "format": "email | slack | both"
}
```

**Returns**:
```json
{
  "schedule_id": "audit-sched-789",
  "next_run": "2024-12-16T09:00:00-05:00",
  "status": "active"
}
```

#### 13. detect_tag_drift

**Purpose**: Detect tags that have changed unexpectedly

**Parameters**:
```json
{
  "lookback_days": 7,
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
      "changed_at": "2024-12-14T10:23:00Z",
      "changed_by": "arn:aws:iam::123456789012:user/john.doe"
    }
  ],
  "total_drifts": 12
}
```

#### 14. cross_account_compliance_check

**Purpose**: Check compliance across multiple AWS accounts

**Parameters**:
```json
{
  "account_ids": ["123456789012", "234567890123"],
  "assume_role": "arn:aws:iam::*:role/OrganizationAccountAccessRole"
}
```

**Returns**:
```json
{
  "results": [
    {
      "account_id": "123456789012",
      "compliance_score": 0.72,
      "violations": 127
    },
    {
      "account_id": "234567890123",
      "compliance_score": 0.65,
      "violations": 203
    }
  ],
  "overall_compliance": 0.68
}
```

#### 15. export_violations_csv

**Purpose**: Export violations to CSV for external analysis

**Parameters**:
```json
{
  "filters": {
    "severity": "errors_only",
    "resource_types": ["ec2:instance"]
  },
  "format": "csv | xlsx | json"
}
```

**Returns**:
```json
{
  "export_url": "https://s3.amazonaws.com/finops-exports/violations-2024-12-15.csv",
  "expires_at": "2024-12-16T00:00:00Z",
  "row_count": 450
}
```

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
| `tag:read` | Read tag data, compliance reports | All read tools |
| `tag:write` | Apply tags to resources | `bulk_tag_resources` |
| `tag:approve` | Approve bulk tagging requests | `approve_bulk_tagging_request` |
| `admin` | Full access, policy updates | Admin operations |

#### Step-Up Authorization

For sensitive operations (bulk tagging), users must re-authenticate with elevated scope:

```
User: "Bulk tag 100 EC2 instances with CostCenter=Engineering"

MCP Server: {
  "error": "insufficient_scope",
  "required_scope": "tag:write",
  "step_up_url": "https://mcp.finops.company.com/oauth/authorize?scope=tag:write"
}

User re-authenticates with tag:write scope

MCP Server: Creates approval request, returns request_id

Approver reviews and approves

MCP Server: Executes bulk tagging
```

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
      "Sid": "TagWriteAccess",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateTags",
        "rds:AddTagsToResource",
        "s3:PutBucketTagging",
        "lambda:TagResource",
        "ecs:TagResource"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "aws:RequestedRegion": ["us-east-1", "us-west-2"]
        }
      }
    },
    {
      "Sid": "SecretsManagerAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:finops/mcp/*"
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
    "client_id": "finops-mcp-prod",
    "client_secret": "...generated...",
    "issuer_url": "https://login.company.com"
  }'

# Database credentials
aws secretsmanager create-secret \
  --name finops/mcp/database-credentials \
  --secret-string '{
    "username": "mcp_admin",
    "password": "...generated...",
    "host": "finops-mcp-db.xxxxx.us-east-1.rds.amazonaws.com",
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
  name = "finops-mcp-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "mcp_server" {
  family                   = "finops-mcp-server"
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
          "awslogs-group"         = "/ecs/finops-mcp-server"
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
  name            = "finops-mcp-server"
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
  name               = "finops-mcp-cpu-scaling"
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
  alarm_name          = "finops-mcp-high-error-rate"
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
  alarm_name          = "finops-mcp-high-cpu"
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
  alarm_name          = "finops-mcp-db-connections-high"
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
xray_recorder.configure(service='finops-mcp-server')
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
            --cluster finops-mcp-cluster \
            --service finops-mcp-server \
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

-- Bulk tagging requests table
CREATE TABLE bulk_tagging_requests (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255) NOT NULL,
    resource_arns TEXT[] NOT NULL,
    tags JSONB NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pending, approved, denied, executed
    approved_by VARCHAR(255),
    approved_at TIMESTAMP WITH TIME ZONE,
    executed_at TIMESTAMP WITH TIME ZONE,
    comment TEXT
);

CREATE INDEX idx_bulk_requests_status ON bulk_tagging_requests(status);
CREATE INDEX idx_bulk_requests_created_by ON bulk_tagging_requests(created_by);

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

### Migration Steps

1. **Week 1**: Deploy Phase 2 infrastructure in parallel
   - Create ECS cluster, RDS, ElastiCache
   - Deploy same code as Phase 1
   - Test with staging users

2. **Week 2**: Add new Phase 2 features
   - Implement OAuth 2.0 authentication
   - Add 7 new tools
   - Test step-up authorization

3. **Week 3**: Data migration
   - Export SQLite audit logs from Phase 1
   - Import to PostgreSQL
   - Verify data integrity

4. **Week 4**: Cutover
   - Update DNS to point to ALB
   - Monitor for issues
   - Keep Phase 1 EC2 running for 1 week (rollback option)
   - Decommission Phase 1 EC2

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

✅ All 15 tools working in production
✅ OAuth 2.0 authentication functional
✅ Step-up authorization working for write operations
✅ Bulk tagging with approval workflows tested
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
✅ At least 5 bulk tagging operations approved and executed
✅ Measurable compliance improvement (5%+ increase)
✅ User satisfaction NPS > 50

---

## Next Steps After Phase 2

1. **Evaluate multi-cloud demand** - Do users need Azure/GCP support?
2. **Collect feature requests** - What additional tools would add value?
3. **Performance optimization** - Any bottlenecks at scale?
4. **Decide on Phase 3** - Go/no-go for multi-cloud expansion

---

**Document Version**: 1.0
**Last Updated**: December 2024
**Ready for Development**: After Phase 1 completion
**Assigned to**: Kiro (post-Phase 1)
