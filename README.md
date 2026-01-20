# FinOps Tag Compliance MCP Server

**Status**: ✅ Phase 1 MVP Complete (January 2026)
**Deployment**: Local or Remote via HTTP - **Remote recommended for production**
**Target Audience**: FinOps Practitioners, Solution Architects, DevOps Engineers

---

## Getting Started

See the **[Deployment Guide](./docs/DEPLOYMENT.md)** for installation and setup instructions.

### 📺 Video Demo

Watch a 2-minute demo of the MCP server in action with Claude Desktop:

[![Watch Demo](https://cdn.loom.com/sessions/thumbnails/ccdf1e1aed4c4236bfa9e81367176376-with-play.gif)](https://www.loom.com/share/ccdf1e1aed4c4236bfa9e81367176376)

**[▶️ Watch the demo](https://www.loom.com/share/ccdf1e1aed4c4236bfa9e81367176376)** - See how to check tag compliance, get cost impact, and receive ML-powered tag suggestions.

---

## Overview

The FinOps Tag Compliance MCP Server is an intelligent AWS tag governance solution that provides schema validation, cost attribution analysis, ML-powered tag suggestions, and compliance trend tracking.

### What Makes This Different?

Unlike the official AWS MCP that simply reads tags, this server:

| Capability | Official AWS MCP | FinOps Tag Compliance MCP |
|------------|------------------|---------------------------|
| **Tag Data Access** | ✅ Read tags via API | ✅ Read tags via API |
| **Schema Validation** | ❌ No | ✅ Validates against org policy |
| **Cost Attribution** | ❌ No | ✅ Links violations to $ impact |
| **Tag Suggestions** | ❌ No | ✅ ML-powered recommendations |
| **Compliance Trends** | ❌ No | ✅ Historical tracking with SQLite |
| **50+ Resource Types** | ❌ Limited | ✅ Comprehensive coverage |

See [Differentiation from AWS Native MCP](./docs/DIFFERENTIATION-FROM-AWS-NATIVE.md) for detailed comparison.

### The Problem We Solve

**The Cost Attribution Gap**: According to the FinOps Foundation's State of FinOps 2025 report, 43% of cloud costs lack proper tagging, creating a $2.3B annual attribution gap for enterprises.

This MCP server addresses that gap by:
1. **Enforcing tag compliance** across 50+ AWS resource types
2. **Quantifying financial impact** of missing or incorrect tags
3. **Providing ML-powered suggestions** based on resource patterns
4. **Tracking compliance trends** over time with automatic snapshots
5. **Integrating with AWS Organizations** tag policies

---

## Key Features

### 🎯 8 Core MCP Tools

1. **check_tag_compliance** - Scan resources against policy, get compliance score
2. **find_untagged_resources** - Identify resources missing required tags
3. **validate_resource_tags** - Validate specific resources by ARN
4. **get_cost_attribution_gap** - Calculate financial impact of tagging gaps
5. **suggest_tags** - Get ML-powered tag recommendations
6. **get_tagging_policy** - Retrieve current policy configuration
7. **generate_compliance_report** - Create formatted reports (JSON/CSV/Markdown)
8. **get_violation_history** - View compliance trends over time

### ⚡ Tool Search Optimization (Advanced Tool Use)

**NEW: January 2026** - Reduce token usage by 85% with Claude's Tool Search feature!

Instead of loading all 8 tool definitions upfront, Claude can discover tools on-demand. This feature:
- **Reduces costs**: Load only the tools needed for each conversation
- **Improves performance**: Claude Opus 4.5 accuracy improved from 79.5% to 88.1%
- **Scales better**: As we add more tools in Phase 2+, you won't pay for unused tools
- **No code changes**: Pure client-side optimization - your server works with both old and new clients

**How to enable**:
1. Add beta header: `"anthropic-beta": "mcp-client-2025-11-20"` to your API calls
2. Configure `defer_loading: true` for less-frequently used tools
3. Keep your 3-5 most-used tools always loaded

See [Tool Search Configuration Guide](./docs/TOOL_SEARCH_CONFIGURATION.md) for detailed setup instructions and recommended configuration.

### 📊 Automatic Compliance History

Every compliance scan is automatically stored in SQLite for trend analysis:
- **Automatic snapshots** with configurable storage
- **Trend detection** (improving, declining, stable)
- **Time-based grouping** (daily, weekly, monthly)
- **Persistent storage** with Docker volume mounts

### 🔄 AWS Organizations Integration

- **Import existing policies** with converter script
- **Zero-friction onboarding** for AWS customers
- **Policy validation** to ensure compatibility
- See [Tagging Policy Guide](./docs/TAGGING_POLICY_GUIDE.md)

### 🌐 Comprehensive Resource Coverage

Supports 50+ AWS resource types including:
- Compute: EC2, Lambda, ECS, Batch
- Storage: S3, EBS, EFS
- Database: RDS, DynamoDB, ElastiCache
- AI/ML: Bedrock agents, knowledge bases, guardrails
- And many more...

Use **"all"** to scan everything, or specify individual types.

### 🔒 Enterprise-Grade Security

- IAM role-based authentication (no hardcoded credentials)
- Input validation and sanitization
- Budget enforcement (prevent runaway queries)
- Loop detection (prevent infinite calls)
- Comprehensive audit logging
- Error sanitization (no secrets in logs)

See [Security Configuration Guide](./docs/SECURITY_CONFIGURATION.md)

---

## Documentation

### 📚 Essential Reading

- **[User Manual](./docs/USER_MANUAL.md)** - **Start here!** Practical guide for FinOps practitioners
- **[Deployment Guide](./docs/DEPLOYMENT.md)** - Local and remote deployment instructions
- **[Tool Search Configuration Guide](./docs/TOOL_SEARCH_CONFIGURATION.md)** - **NEW!** Optimize token usage with Tool Search (85% cost reduction)
- **[Tagging Policy Guide](./docs/TAGGING_POLICY_GUIDE.md)** - Configure your tagging policy
- **[IAM Permissions Guide](./docs/IAM_PERMISSIONS.md)** - Required AWS permissions

### 🏗️ Architecture & Design

- **[System Diagrams](./docs/diagrams/README.md)** - Visual architecture documentation
  - [System Architecture](./docs/diagrams/01-system-architecture.md)
  - [State Machine Diagrams](./docs/diagrams/02-state-machine-diagrams.md)
  - [Sequence Diagrams](./docs/diagrams/03-sequence-diagrams.md)
  - [Component Diagram](./docs/diagrams/04-component-diagram.md)
  - [Deployment Architecture](./docs/diagrams/05-deployment-architecture.md)
  - [Diagram Best Practices](./docs/diagrams/00-diagram-best-practices.md) - Fun guide to system diagrams!

### 🔧 Technical Reference

- **[Full Specification](./docs/SPECIFICATION.md)** - Complete technical specification
- **[Tool Logic Reference](./docs/TOOL_LOGIC_REFERENCE.md)** - Detailed tool behavior
- **[Phase 1 Specification](./docs/PHASE-1-SPECIFICATION.md)** - MVP implementation details
- **[Security Configuration](./docs/SECURITY_CONFIGURATION.md)** - Security features
- **[Error Sanitization Guide](./docs/ERROR_SANITIZATION_GUIDE.md)** - Error handling
- **[Audit Logging](./docs/AUDIT_LOGGING.md)** - Audit trail documentation
- **[CloudWatch Logging](./docs/CLOUDWATCH_LOGGING.md)** - CloudWatch integration

### 🧪 Development & Testing

- **[Testing Quick Start](./docs/TESTING_QUICK_START.md)** - How to run tests
- **[UAT Protocol](./docs/UAT_PROTOCOL.md)** - User acceptance testing procedures
- **[GenAI Testing Guidelines](./docs/GENAI_AND_AGENTS_TESTING_GUIDELINES.md)** - Testing AI systems
- **[Development Journal](./docs/DEVELOPMENT_JOURNAL.md)** - Build history and decisions

### 🗺️ Planning & Roadmap

- **[Roadmap](./docs/ROADMAP.md)** - Future phases and timeline
- **[Phase 2 Specification](./docs/PHASE-2-SPECIFICATION.md)** - Production scale (ECS Fargate)
- **[Phase 3 Specification](./docs/PHASE-3-SPECIFICATION.md)** - Multi-cloud support (Azure, GCP)

---

## Use Cases

### 1. Monthly Tag Compliance Audit
*"Run a full compliance check on all EC2 and RDS resources and show me the trend over the last 30 days"*

Get comprehensive compliance scores, identify violations, and track improvements over time.

### 2. Cost Attribution Gap Analysis
*"How much of our EC2 spend is unattributable due to missing tags?"*

Link tagging violations directly to dollars, prioritize remediation by financial impact.

### 3. Pre-Deployment Validation
*"Validate these 10 resource ARNs before we launch to production"*

Catch tag policy violations in CI/CD pipelines before resources go live.

### 4. Intelligent Tag Recommendations
*"Suggest tags for this EC2 instance based on naming patterns and similar resources"*

ML-powered suggestions with confidence scores and reasoning.

### 5. Executive Compliance Reports
*"Generate a markdown report showing our tagging compliance for Q1 2026"*

Beautiful, formatted reports for stakeholders with trends and actionable insights.

---

## Status & Roadmap

### ✅ Phase 1: MVP - AWS Support (Complete)

**Completed: January 2026**

- 8 core MCP tools working
- AWS SDK integration (50+ resource types)
- Compliance history tracking with SQLite
- Cost attribution gap analysis
- ML-powered tag suggestions
- Docker deployment on EC2
- AWS Organizations policy converter
- Comprehensive documentation

**Success Metrics Achieved:**
- ✅ Server running with <2s response times
- ✅ 50+ AWS resource types supported
- ✅ Historical trend analysis working
- ✅ IAM role-based authentication
- ✅ Complete test coverage

### 🚀 Phase 2: Production Scale (Planned: Months 3-4)

**Goal:** Enterprise-grade deployment on ECS Fargate

- Enhanced MCP server (16 total tools)
- High availability with Application Load Balancer
- ElastiCache Redis for distributed caching
- RDS PostgreSQL for audit logs at scale
- OAuth 2.0 + PKCE authentication
- Step-up authorization for write operations
- Automated daily compliance snapshots
- Enhanced security and monitoring

See [Phase 2 Specification](./docs/PHASE-2-SPECIFICATION.md)

### 🌐 Phase 3: Multi-Cloud (Planned: Months 5-6)

**Goal:** Extend to Azure and GCP

- Azure and GCP SDK integration
- Unified multi-cloud tagging policy
- Cross-cloud consistency checking
- Centralized credential management
- Multi-cloud cost attribution

See [Phase 3 Specification](./docs/PHASE-3-SPECIFICATION.md)

### 🤖 Phase 4: Automation Integration (Planned: Months 7-8)

**Goal:** Script generation and automation platform integration

- Generate remediation scripts (AWS CLI, Terraform, CloudFormation)
- OpenOps and wiv.ai integration
- Ansible playbook generation
- Automated remediation workflows

See [Roadmap](./docs/ROADMAP.md) for complete timeline and decision points.

---

## Architecture

This MCP server supports **local and remote deployment** with Claude Desktop connecting via HTTP bridge script.

**Local Deployment (Development):**
- MCP server runs locally in Docker (`localhost:8080`)
- Claude Desktop connects via Python bridge to `http://localhost:8080`
- Simple setup with `docker-compose up`
- Good for development and testing
- Uses your local AWS credentials

**Remote Deployment (Production - Recommended):**
- MCP server deployed to cloud infrastructure (AWS EC2, GCP, etc.)
- Claude Desktop connects via Python bridge to `http://your-server:8080`
- Centralized authentication with IAM roles/service accounts
- Better security, caching, and availability
- Multiple users can share the same server
- Centralized audit logging

**Both modes use the same configuration approach** - just change the `MCP_SERVER_URL` from `localhost` to your server address.

### Key Architecture Features

- **Authentication**: IAM roles (AWS), Service Accounts (GCP), or Service Principals (Azure)
- **Caching**: Redis for performance optimization (1-hour TTL)
- **Persistence**: SQLite for audit logs and compliance history
- **Security**: Comprehensive input validation, error sanitization, budget enforcement
- **Observability**: CloudWatch logging, Prometheus metrics, audit trails

See [System Architecture Diagram](./docs/diagrams/01-system-architecture.md) for visual overview.

---

## Contributing

This project is actively developed. We welcome:
- Bug reports and feature requests (open an issue)
- Documentation improvements (PRs welcome)
- Use case examples and success stories
- Feedback on the MCP tool design

See [Development Journal](./docs/DEVELOPMENT_JOURNAL.md) for build history.

---

## Project Structure

```
finops-tag-compliance-mcp/
├── mcp_server/              # Main application code
│   ├── clients/             # AWS, Redis client wrappers
│   ├── models/              # Pydantic data models
│   ├── services/            # Business logic layer
│   ├── tools/               # 8 MCP tool implementations
│   ├── middleware/          # Security, validation, audit
│   └── utils/               # Helper functions
├── policies/                # Tagging policy configuration
├── scripts/                 # Utility scripts (converter, bridge)
├── tests/                   # Test suite
├── docs/                    # Documentation
│   └── diagrams/            # System architecture diagrams
├── docker-compose.yml       # Local development setup
└── Dockerfile               # Container image
```

---

## License

Apache 2.0 License

---

## Support & Resources

- **Documentation**: [docs/](./docs/)
- **Issues**: [GitHub Issues](https://github.com/OptimNow/finops-tag-compliance-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/OptimNow/finops-tag-compliance-mcp/discussions)
- **FinOps Foundation**: [State of FinOps Report](https://www.finops.org/)

---

**Built with ❤️ for the FinOps community**
