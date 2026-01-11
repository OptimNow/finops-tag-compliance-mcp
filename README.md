# FinOps Tag Compliance MCP Server

**Status**: ✅ Phase 1 MVP Complete (January 2026)
**Deployment**: Local (stdio) or Remote (HTTP) - **Remote recommended for production**
**Target Audience**: FinOps Practitioners, Solution Architects, DevOps Engineers

---

## Quick Start

### Option A: Local Development (Docker)

```bash
# Clone and start locally
git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp
docker-compose up -d
```

Server URL: `http://localhost:8000`

### Option B: Remote Deployment (Recommended)

Deploy to AWS EC2, Google Cloud Run, or any container platform. See the [Deployment Guide](./docs/DEPLOYMENT.md) for instructions.

For production use, we **strongly recommend remote deployment** because:
- Centralized credential management (IAM roles, service accounts)
- Better security (no credentials on desktop)
- Shared caching for multiple users
- Centralized audit logging
- High availability options

### Configure Claude Desktop

**Local (stdio) Mode:**
```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "docker",
      "args": ["run", "-i", "--rm",
               "-v", "~/.aws:/root/.aws:ro",
               "finops-tag-compliance-mcp"]
    }
  }
}
```

**Remote (HTTP) Mode (Recommended):**

**Prerequisites:** Python 3.11+ with `requests` library:
```bash
pip install requests
```

1. Download the bridge script: [scripts/mcp_bridge.py](scripts/mcp_bridge.py)
2. Save it locally (e.g., `~/tools/mcp_bridge.py`)
3. Edit Claude Desktop config:

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python",
      "args": ["/path/to/mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://your-server:8000"
      }
    }
  }
}
```

4. Restart Claude Desktop
5. Test with: *"Show me our tagging policy"*

### AWS Credentials Setup

The server needs AWS credentials with specific IAM permissions to scan your resources. See the [IAM Permissions Guide](./docs/IAM_PERMISSIONS.md) for detailed setup.

**Local Development:**
- Mounts your `~/.aws` credentials folder
- Requires `aws configure` to be set up
- Your IAM user needs read-only permissions

**Remote Deployment (Recommended):**
- Uses IAM Instance Profile (EC2) or Service Account (GCP/Azure)
- No credentials to manage manually
- More secure and easier to maintain

**Troubleshooting:** See the [IAM Permissions Guide](./docs/IAM_PERMISSIONS.md)

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

This MCP server supports **both local (stdio) and remote (HTTP) deployment modes**.

**Local Mode (Development):**
- Claude Desktop connects directly to local Docker container
- Uses stdio protocol for communication
- Good for development and testing
- Simple setup with `docker-compose up`

**Remote Mode (Production - Recommended):**
- MCP server deployed to cloud infrastructure
- Claude Desktop connects via HTTP through bridge script
- Centralized authentication and audit logging
- Better security, caching, and availability
- Multiple users can share the same server

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
