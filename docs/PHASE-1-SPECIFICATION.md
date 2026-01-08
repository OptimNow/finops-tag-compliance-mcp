# Phase 1 Specification: AWS-Only MVP

**Version**: 2.0  
**Status**: ✅ Complete  
**Timeline**: Months 1-2 (Completed January 2026)  
**Deployment**: EC2 instance at `100.50.91.35:8080`

---

## Overview

Phase 1 delivers a minimum viable product (MVP) focused exclusively on AWS tag compliance. The goal was to prove the concept, gather user feedback, and validate the value proposition before investing in production infrastructure or multi-cloud support.

**What's Included**:
- ✅ 8 core MCP tools for tag compliance
- ✅ 50+ AWS resource types via Resource Groups Tagging API
- ✅ Docker containerization with Redis caching
- ✅ SQLite for audit logs and compliance history
- ✅ EC2 deployment with IAM instance profile
- ✅ Agent safety features (loop detection, budget enforcement)

---

## Architecture

```
┌─────────────────────────────────────────────┐
│ EC2 Instance (t3.small)                     │
│ Amazon Linux 2023                           │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │ Docker Containers                    │  │
│  │                                      │  │
│  │  ┌────────────────────────────────┐ │  │
│  │  │ MCP Server (Python 3.11)       │ │  │
│  │  │  - FastAPI (HTTP server)       │ │  │
│  │  │  - MCP SDK                     │ │  │
│  │  │  - boto3 (AWS SDK)             │ │  │
│  │  │  - Tag validation engine       │ │  │
│  │  └────────────────────────────────┘ │  │
│  │                                      │  │
│  │  ┌────────────────────────────────┐ │  │
│  │  │ Redis (cache)                  │ │  │
│  │  │  - Violation cache             │ │  │
│  │  │  - Policy cache                │ │  │
│  │  └────────────────────────────────┘ │  │
│  │                                      │  │
│  │  SQLite Databases:                  │  │
│  │  - /app/data/audit_logs.db          │  │
│  │  - /app/data/compliance_history.db  │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  IAM Instance Profile:                     │
│  "tagging-mcp-server-role-dev"              │
└─────────────────┬───────────────────────────┘
                  │
                  │ AWS API Calls
                  ▼
         ┌──────────────────┐
         │   AWS Services   │
         │  - EC2, RDS, S3  │
         │  - Lambda, ECS   │
         │  - DynamoDB      │
         │  - OpenSearch    │
         │  - Cost Explorer │
         └──────────────────┘
```

### Infrastructure Specifications

| Component | Specification | Notes |
|-----------|--------------|-------|
| EC2 Instance | t3.small (2 vCPU, 2GB RAM) | ~$15/month |
| Elastic IP | 100.50.91.35 | Stable endpoint |
| Storage | 20GB gp3 EBS | Logs, databases |
| Security Group | Port 8080 (HTTP) | MCP endpoint |
| IAM Role | tagging-mcp-server-role-dev | Read-only AWS access |

---

## MCP Tools (8 Core Tools)

### 1. check_tag_compliance

**Purpose**: Validate resource tags against organizational policy

**Parameters**:
```json
{
  "resource_types": ["ec2:instance", "rds:db", "s3:bucket"],
  "filters": {
    "region": "us-east-1"
  },
  "severity": "all",
  "store_snapshot": false
}
```

**Returns**:
```json
{
  "compliance_score": 0.72,
  "total_resources": 450,
  "compliant_resources": 324,
  "violations": [...],
  "cost_attribution_gap": 26250.00
}
```

### 2. find_untagged_resources

**Purpose**: Find all resources with no tags or missing critical tags

**Parameters**:
```json
{
  "resource_types": ["ec2:instance", "rds:db", "s3:bucket"],
  "regions": ["us-east-1", "us-west-2"],
  "min_cost_threshold": 10.00
}
```

**Returns**:
```json
{
  "untagged_resources": [...],
  "total_cost_impact": 4250.00
}
```

### 3. validate_resource_tags

**Purpose**: Check if specific resource(s) comply with tagging policy

**Parameters**:
```json
{
  "resource_arns": [
    "arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123"
  ]
}
```

**Returns**:
```json
{
  "results": [
    {
      "resource_arn": "...",
      "compliant": false,
      "violations": [...]
    }
  ]
}
```

### 4. get_cost_attribution_gap

**Purpose**: Calculate financial impact of untagged/incorrectly tagged resources

**Parameters**:
```json
{
  "time_period": {
    "start": "2024-12-01",
    "end": "2024-12-31"
  },
  "grouping": "by_resource_type"
}
```

**Returns**:
```json
{
  "total_cloud_spend": 125000.00,
  "attributable_spend": 98750.00,
  "attribution_gap": 26250.00,
  "attribution_gap_percentage": 21.0
}
```

### 5. suggest_tags

**Purpose**: Pattern-based tag suggestions for untagged resources

**Parameters**:
```json
{
  "resource_arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-0abc123"
}
```

**Returns**:
```json
{
  "suggestions": [
    {
      "tag_key": "CostCenter",
      "suggested_value": "Engineering",
      "confidence": 0.87,
      "reasoning": "Similar EC2 instances in same VPC tagged Engineering"
    }
  ]
}
```

### 6. get_tagging_policy

**Purpose**: Retrieve current organizational tagging policy

**Returns**:
```json
{
  "version": "1.0",
  "required_tags": [...],
  "optional_tags": [...],
  "tag_naming_rules": {...}
}
```

### 7. generate_compliance_report

**Purpose**: Generate comprehensive compliance report

**Parameters**:
```json
{
  "format": "json | csv | markdown",
  "include_recommendations": true
}
```

**Returns**:
```json
{
  "report_date": "2024-12-15",
  "overall_compliance": 0.68,
  "summary": {...},
  "top_violations": [...],
  "recommendations": [...]
}
```

### 8. get_violation_history

**Purpose**: Track compliance trends over time

**Parameters**:
```json
{
  "days_back": 90,
  "group_by": "day | week | month"
}
```

**Returns**:
```json
{
  "history": [...],
  "trend": "improving | declining | stable",
  "improvement_rate": 0.03
}
```

---

## Supported AWS Resource Types (50+)

Phase 1 uses the AWS Resource Groups Tagging API for comprehensive resource coverage. The tagging policy applies to ALL resource types by default (wildcard).

### Compute
- `ec2:instance` - EC2 instances
- `ec2:volume` - EBS volumes
- `ec2:snapshot` - EBS snapshots
- `ec2:image` - AMIs
- `lambda:function` - Lambda functions
- `ecs:service` - ECS services
- `ecs:cluster` - ECS clusters

### Storage
- `s3:bucket` - S3 buckets
- `elasticfilesystem:file-system` - EFS file systems

### Database
- `rds:db` - RDS databases
- `rds:cluster` - RDS clusters
- `dynamodb:table` - DynamoDB tables
- `elasticache:cluster` - ElastiCache clusters
- `es:domain` - OpenSearch/Elasticsearch domains

### AI/ML (Bedrock, SageMaker)
- `bedrock:agent` - Bedrock agents
- `bedrock:agent-alias` - Bedrock agent aliases
- `bedrock:knowledge-base` - Bedrock knowledge bases
- `bedrock:guardrail` - Bedrock guardrails
- `bedrock:custom-model` - Bedrock custom models
- `sagemaker:endpoint` - SageMaker endpoints
- `sagemaker:notebook-instance` - SageMaker notebooks

### Networking
- `ec2:vpc` - VPCs
- `ec2:subnet` - Subnets
- `ec2:security-group` - Security groups
- `elasticloadbalancing:loadbalancer` - Load balancers

### Messaging
- `sns:topic` - SNS topics
- `sqs:queue` - SQS queues
- `kinesis:stream` - Kinesis streams

### Other
- `secretsmanager:secret` - Secrets Manager secrets
- `kms:key` - KMS keys
- `cloudwatch:alarm` - CloudWatch alarms
- `states:stateMachine` - Step Functions state machines

### Using "all" Resource Types

To scan ALL taggable resources at once:
```json
{
  "resource_types": ["all"]
}
```

**Important**: The Resource Groups Tagging API only returns resources that have at least one tag. Resources with zero tags won't appear in "all" scans. For completely untagged resources, use specific resource types (ec2:instance, s3:bucket, etc.).

---

## Tagging Policy Schema

```json
{
  "version": "1.0",
  "required_tags": [
    {
      "name": "CostCenter",
      "description": "Department for cost allocation",
      "allowed_values": ["Engineering", "Marketing", "Sales", "Operations"],
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket"]
    },
    {
      "name": "Owner",
      "description": "Email of resource owner",
      "validation_regex": "^[a-z0-9._%+-]+@[a-z0-9.-]+\\.[a-z]{2,}$"
    },
    {
      "name": "Environment",
      "description": "Deployment environment",
      "allowed_values": ["production", "staging", "development"]
    },
    {
      "name": "Project",
      "description": "Project or application name"
    },
    {
      "name": "Application",
      "description": "Application identifier"
    }
  ],
  "optional_tags": [
    {
      "name": "Compliance",
      "allowed_values": ["PCI-DSS", "HIPAA", "SOC2", "None"]
    }
  ],
  "tag_naming_rules": {
    "case_sensitivity": false,
    "max_key_length": 128,
    "max_value_length": 256
  }
}
```

**Policy Location**: `policies/tagging_policy.json`

---

## Agent Safety Features

### Loop Detection
- Detects repeated identical tool calls
- Blocks after N occurrences (default: 3)
- Prevents runaway agent behavior

### Budget Enforcement
- Configurable max tool calls per session
- Graceful degradation when budget exceeded
- Logged for analysis

### Correlation IDs
- Every request gets a unique correlation ID
- End-to-end tracing across tool calls
- Included in all log entries

### Input Validation
- All tool inputs validated against schemas
- Rejects malformed requests
- Prevents injection attacks

### Error Sanitization
- Internal paths and credentials never exposed
- User-friendly error messages
- Detailed errors logged server-side only

---

## IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TagComplianceReadAccess",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeTags",
        "ec2:DescribeVolumes",
        "rds:DescribeDBInstances",
        "rds:ListTagsForResource",
        "s3:GetBucketTagging",
        "s3:ListAllMyBuckets",
        "lambda:ListFunctions",
        "lambda:ListTags",
        "ecs:ListClusters",
        "ecs:ListServices",
        "dynamodb:ListTables",
        "dynamodb:ListTagsOfResource",
        "es:ListDomainNames",
        "es:ListTags",
        "tag:GetResources",
        "tag:GetTagKeys",
        "tag:GetTagValues",
        "ce:GetCostAndUsage",
        "ce:GetTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/tagging-mcp-server/*"
    }
  ]
}
```

---

## Deployment

### Local Development

```bash
# Clone repository
git clone https://github.com/OptimNow/tagging-mcp-server.git
cd tagging-mcp-server

# Start with Docker Compose
docker-compose up -d

# Test health
curl http://localhost:8080/health
```

### AWS Deployment

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for complete instructions including:
- CloudFormation stack deployment
- EC2 instance configuration
- Docker container setup
- Claude Desktop configuration

### Current Production Deployment

- **Elastic IP**: 100.50.91.35
- **MCP Endpoint**: http://100.50.91.35:8080
- **CloudWatch Logs**: /tagging-mcp-server/dev
- **Stack Name**: tagging-mcp-server

---

## Testing Results

### API Testing (January 5, 2026)

| Tool | Status | Result |
|------|--------|--------|
| `get_tagging_policy` | ✅ Pass | Returns 5 required tags |
| `check_tag_compliance` | ✅ Pass | 4 EC2 instances, 50% compliance |
| `find_untagged_resources` | ✅ Pass | 17 S3 buckets, ~$95/month impact |

### Test Suite

- 137 unit tests passing
- 38 integration tests passing
- 33 property-based tests passing
- 11 history service tests passing

---

## Known Limitations

| Limitation | Workaround | Fixed In |
|------------|------------|----------|
| No high availability | Manual restart if EC2 fails | Phase 2 |
| No auto-scaling | Fixed capacity | Phase 2 |
| No bulk tagging | Read-only operations | Phase 2 |
| No multi-cloud | AWS only | Phase 3 |
| Simple API auth | API key only | Phase 2 (OAuth) |

---

## Success Criteria (Achieved)

✅ All 8 core tools working and tested  
✅ MCP server responds in <2 seconds  
✅ Docker container runs stable  
✅ IAM role authentication (no credentials in code)  
✅ Compliance reports match manual audits  
✅ Deployed to EC2 with stable endpoint  
✅ Claude Desktop integration working  

---

## Cost

| Component | Monthly Cost |
|-----------|--------------|
| EC2 t3.small (24/7) | $15 |
| EBS 20GB gp3 | $2 |
| Elastic IP | $0 (attached) |
| Data transfer | $5 |
| CloudWatch Logs | $3 |
| **Total** | **~$25/month** |

---

## Next Steps

Phase 1 is complete. See **[Phase 2 Specification](./PHASE-2-SPECIFICATION.md)** for:
- ECS Fargate deployment
- OAuth 2.0 authentication
- Bulk tagging with approval workflows
- Auto-scaling
- Agent safety enhancements

---

**Document Version**: 2.0  
**Last Updated**: January 2026  
**Status**: ✅ Complete
