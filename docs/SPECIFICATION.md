# Tagging MCP Server - Specification Overview

**Version**: 3.0  
**Last Updated**: January 2026  
**Status**: Phase 1 Complete, Phase 2 Planned  
**Repository**: https://github.com/OptimNow/tagging-mcp-server

---

## What This Is

The Tagging MCP Server is a purpose-built remote MCP server that solves the cloud tagging problem. While generic cloud MCP servers provide raw tag data access, this server adds intelligence: policy validation, cost attribution analysis, violation tracking, and tag suggestions.

**The Problem**: 30-50% of cloud resources are untagged or incorrectly tagged in typical enterprises, making cost allocation impossible and compliance reporting a nightmare.

**The Solution**: An MCP server that validates tags against your organization's policies, connects tag violations to dollar impact, suggests remediation, and tracks compliance over time.

---

## Implementation Phases

This project follows a phased approach to deliver value incrementally:

| Phase | Status | Timeline | Focus |
|-------|--------|----------|-------|
| **[Phase 1](./PHASE-1-SPECIFICATION.md)** | ✅ Complete | Months 1-2 | AWS-Only MVP on EC2 |
| **[Phase 2](./PHASE-2-SPECIFICATION.md)** | 📋 Planned | Months 3-4 | Production ECS Fargate + OAuth |
| **[Phase 3](./PHASE-3-SPECIFICATION.md)** | 📋 Planned | Months 5-6 | Multi-Cloud (Azure + GCP) |

See **[ROADMAP.md](./ROADMAP.md)** for the complete implementation timeline.

---

## Current Capabilities (Phase 1)

### 8 MCP Tools

| Tool | Purpose |
|------|---------|
| `check_tag_compliance` | Scan resources and return compliance score |
| `find_untagged_resources` | Find resources missing required tags |
| `validate_resource_tags` | Validate specific resources by ARN |
| `get_cost_attribution_gap` | Calculate financial impact of tagging gaps |
| `suggest_tags` | Suggest tag values based on patterns |
| `get_tagging_policy` | Return the policy configuration |
| `generate_compliance_report` | Generate formatted compliance reports |
| `get_violation_history` | Return historical compliance data with trends |

### Supported AWS Resource Types

- EC2 instances, volumes, snapshots
- RDS databases and clusters
- S3 buckets
- Lambda functions
- ECS services
- DynamoDB tables
- OpenSearch/Elasticsearch domains
- And 40+ more via Resource Groups Tagging API

### Key Features

- **Tagging Policy Validation**: JSON-based policy with required tags, allowed values, regex patterns
- **Cost Attribution**: Integration with AWS Cost Explorer to show financial impact
- **Compliance History**: SQLite-based tracking for trend analysis
- **Caching**: Redis caching to minimize AWS API calls
- **Audit Logging**: Every tool invocation logged for compliance
- **Agent Safety**: Loop detection, budget enforcement, correlation IDs

---

## Architecture

### Phase 1 (Current)

```
┌─────────────────────────────────────────────┐
│ EC2 Instance (t3.small)                     │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │ Docker Container: MCP Server         │  │
│  │  - FastAPI + MCP SDK                 │  │
│  │  - boto3 (AWS SDK)                   │  │
│  │  - Redis (caching)                   │  │
│  │  - SQLite (audit + history)          │  │
│  └──────────────────────────────────────┘  │
│                                             │
│  IAM Instance Profile (read-only)          │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
         ┌──────────────────┐
         │   AWS Services   │
         │  - EC2, RDS, S3  │
         │  - Cost Explorer │
         └──────────────────┘
```

### Phase 2 (Planned)

- ECS Fargate (serverless containers)
- Application Load Balancer with SSL
- ElastiCache (managed Redis)
- RDS PostgreSQL (managed database)
- OAuth 2.0 + PKCE authentication
- Auto-scaling based on load

### Phase 3 (Planned)

- Azure SDK integration
- GCP SDK integration
- Cross-cloud consistency checking
- Unified multi-cloud reporting

---

## Differentiation from Official Cloud MCP Servers

| Capability | Official AWS MCP | FinOps Tag Compliance MCP |
|------------|------------------|---------------------------|
| Tag Data Access | ✅ Read tags via API | ✅ Read tags via API |
| Schema Validation | ❌ No | ✅ Validates against org policy |
| Cost Attribution | ❌ No | ✅ Links violations to $ impact |
| Tag Suggestions | ❌ No | ✅ Pattern-based recommendations |
| Compliance Reporting | ❌ No | ✅ Formatted reports with trends |
| Violation Tracking | ❌ No | ✅ Historical trend analysis |
| Agent Safety | ❌ No | ✅ Loop detection, budgets |

See **[DIFFERENTIATION-FROM-AWS-NATIVE.md](./DIFFERENTIATION-FROM-AWS-NATIVE.md)** for a detailed comparison.

---

## Quick Start

### Local Development

```bash
# Clone and start
git clone https://github.com/OptimNow/tagging-mcp-server.git
cd tagging-mcp-server
docker-compose up -d

# Test health
curl http://localhost:8080/health
```

### Claude Desktop Configuration

```json
{
  "mcpServers": {
    "tagging-mcp": {
      "command": "python",
      "args": ["C:\\path\\to\\repo\\scripts\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://localhost:8080"
      }
    }
  }
}
```

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for complete setup instructions.

---

## Documentation

### For Users
- **[USER_MANUAL.md](./USER_MANUAL.md)** - How to use the MCP tools with Claude
- **[TAGGING_POLICY_GUIDE.md](./TAGGING_POLICY_GUIDE.md)** - How to configure tagging policies

### For Operators
- **[DEPLOYMENT.md](./DEPLOYMENT.md)** - Local and AWS deployment guide
- **[IAM_PERMISSIONS.md](./IAM_PERMISSIONS.md)** - Required AWS permissions
- **[SECURITY_CONFIGURATION.md](./SECURITY_CONFIGURATION.md)** - Security settings

### For Developers
- **[Phase 1 Specification](./PHASE-1-SPECIFICATION.md)** - Current implementation details
- **[Phase 2 Specification](./PHASE-2-SPECIFICATION.md)** - Production infrastructure plans
- **[Phase 3 Specification](./PHASE-3-SPECIFICATION.md)** - Multi-cloud plans
- **[ROADMAP.md](./ROADMAP.md)** - Implementation timeline

---

## Success Metrics

### Phase 1 (Achieved)
- ✅ 8 MCP tools working and tested
- ✅ <2 second response time for compliance checks
- ✅ Docker container runs stable
- ✅ IAM role authentication (no credentials in code)
- ✅ Deployed to EC2 with Elastic IP

### Phase 2 (Target)
- 99.9% uptime SLA
- <1 second response time
- OAuth 2.0 authentication
- Auto-scaling 2-10 tasks
- Bulk tagging with approval workflows

### Phase 3 (Target)
- AWS + Azure + GCP support
- Cross-cloud consistency checking
- Unified compliance reporting

---

## Cost Estimate

| Phase | Monthly Cost | Notes |
|-------|--------------|-------|
| Phase 1 (EC2) | ~$40 | Single t3.small instance |
| Phase 2 (Fargate) | ~$150-200 | ECS + RDS + ElastiCache |
| Phase 3 (Multi-Cloud) | ~$180-250 | + Azure/GCP API costs |

---

## License

Apache 2.0

---

## Contributors

- Jean Latiere (FinOps Foundation, OptimNow)
- Built with Kiro AI Assistant

---

**For development teams**: Start with **[Phase 1 Specification](./PHASE-1-SPECIFICATION.md)** for current implementation details.
