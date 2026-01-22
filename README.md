# FinOps Tag Compliance MCP Server

> **Turn Claude into your AWS tagging compliance assistant** — Ask in plain English, get real-time insights on your cloud costs and compliance.

**Status**: ✅ Phase 1 MVP Complete (January 2026) | **For**: FinOps Practitioners, Solution Architects, DevOps Engineers

---

## What's This About?

Ever wished you could just ask Claude "Hey, which of my AWS resources are missing cost center tags?" and get an instant, intelligent answer? That's exactly what this MCP server does. 

**MCP (Model Context Protocol)** is like giving Claude a phone line to your infrastructure. Instead of Claude being limited to just chatting, it can now actively query your AWS environment, validate your tagging policies, calculate cost impacts, and even suggest fixes—all through natural conversation.

Think of it as teaching Claude to be your FinOps analyst. You talk to Claude normally, and behind the scenes, this MCP server translates your questions into AWS API calls, validates data against your organization's policies, and brings back actionable insights.

### 🎬 See It In Action

Watch a 2-minute demo where Claude analyzes AWS resources, identifies untagged instances, calculates their cost impact, and suggests intelligent tag values:

[![Watch Demo](https://cdn.loom.com/sessions/thumbnails/ccdf1e1aed4c4236bfa9e81367176376-with-play.gif)](https://www.loom.com/share/ccdf1e1aed4c4236bfa9e81367176376)

**[▶️ Watch the demo](https://www.loom.com/share/ccdf1e1aed4c4236bfa9e81367176376)**

Ready to try it yourself? Head to the **[Deployment Guide](./docs/DEPLOYMENT.md)** for setup instructions.

---

## Why This Matters

Here's a sobering stat: According to the FinOps Foundation's 2025 report, **43% of cloud costs lack proper tagging**. For large enterprises, that's a $2.3B annual "attribution gap"—money being spent with no idea which team, project, or cost center is responsible.

The official AWS MCP can read your resource tags, but that's like having a librarian who can only tell you which books exist—not whether they're organized correctly, which ones are missing ISBN numbers, or how much money you're losing from the chaos.

This MCP server goes deeper. It validates tags against your organization's policies, links violations to actual dollar amounts, tracks compliance trends over time, and even uses ML to suggest corrections based on naming patterns and resource metadata.

### Beyond Simple Tag Reading

Here's what sets this apart from the standard AWS MCP:

The official tool reads tags from your resources. This one **validates** them against your organization's schema, **quantifies** the financial impact when they're wrong or missing, **suggests** intelligent corrections using ML, and **tracks** compliance trends so you can see if things are getting better or worse over time. It's the difference between a read-only view and an active compliance assistant.

See the detailed [comparison with AWS Native MCP](./docs/DIFFERENTIATION-FROM-AWS-NATIVE.md) for technical specifics.

---

## What Can You Ask Claude?

Instead of wrestling with AWS Console filters or writing boto3 scripts, just ask Claude naturally:

**"Run a compliance check on all my EC2 and RDS instances"**
Get a comprehensive score, see which resources fail policy checks, and understand why.

**"How much of our EC2 spend is unattributable due to missing tags?"**
Links violations directly to dollars. Maybe those 47 untagged instances represent $12K/month—now you know where to focus.

**"Suggest tags for this EC2 instance based on its name and similar resources"**
ML analyzes naming patterns, resource metadata, and sibling resources to recommend tag values with confidence scores.

**"Show me the tagging compliance trend for the last 30 days"**
Every compliance scan is automatically stored in SQLite. See if your compliance is improving, declining, or stuck.

**"Generate a markdown report for our Q1 compliance review"**
Beautiful, formatted reports ready for stakeholders. JSON and CSV options too.

Behind the scenes, this MCP server is running sophisticated validation logic, cost calculations, and trend analysis. But you just talk to Claude like you're talking to a colleague.

---

## How It Works

This MCP server runs as a lightweight HTTP service (either on your laptop or in the cloud). When you ask Claude a question about AWS tagging, Claude calls the appropriate "tool" from this server, which:

1. **Queries your AWS environment** using IAM credentials (no hardcoded keys)
2. **Validates resources** against your tagging policy (defined in a simple JSON file)
3. **Calculates compliance scores** and identifies violations
4. **Estimates financial impact** using AWS Cost Explorer data
5. **Stores results** in SQLite for historical trend tracking
6. **Returns insights** to Claude in a structured format

Claude then translates those technical results into natural language you can understand and act on.

### 8 Core Tools Claude Can Use

When you're chatting with Claude, it automatically picks the right tool for your question:

**check_tag_compliance** scans resources against your policy and calculates a compliance score. **find_untagged_resources** identifies resources missing required tags with cost impact. **validate_resource_tags** validates specific resources by ARN (great for CI/CD pipelines). **get_cost_attribution_gap** calculates how much spend is unattributable. **suggest_tags** provides ML-powered recommendations with confidence scores. **get_tagging_policy** shows your current policy configuration. **generate_compliance_report** creates formatted reports in JSON, CSV, or Markdown. **get_violation_history** shows compliance trends over time.

You don't need to memorize these—Claude figures out which tools to use based on what you're asking. But if you're curious about the implementation details, check out the [Tool Logic Reference](./docs/TOOL_LOGIC_REFERENCE.md).

---

## For MCP Beginners

If you're new to Model Context Protocol, here's the mental model:

**Without MCP**: Claude is like a very smart person locked in a room with no phone or internet. It can only work with what you paste into the chat.

**With MCP**: Claude now has a phone line to specific services. When you ask about AWS tagging, Claude can "call" this MCP server to get real-time data from your infrastructure.

**Key concept**: MCP servers expose "tools" that Claude can invoke. Think of tools as functions. When you ask "Which S3 buckets are untagged?", Claude recognizes it needs the `find_untagged_resources` tool, calls it with the right parameters (`resource_types=["s3:bucket"]`), gets structured data back, and translates that into a natural language answer for you.

**Two deployment modes:**

For local testing, you run the MCP server on your laptop (just `docker-compose up`). Claude Desktop connects to `localhost:8080` via a small Python bridge script. It uses your local AWS credentials from `~/.aws`.

For production use, you deploy the server to AWS EC2 or similar. Multiple team members can connect their Claude Desktop to the same server URL. It uses IAM roles instead of local credentials, provides centralized audit logging, and enables shared caching for faster responses.

Same configuration approach for both—just change the URL from `localhost:8080` to your server address. See the [Deployment Guide](./docs/DEPLOYMENT.md) for step-by-step setup.

---

## Smart Performance: Tool Search

**New in January 2026**: Claude now supports "Tool Search"—a way to load tool definitions on-demand instead of upfront.

Here's why this matters: Imagine Claude needs to load a manual for 8 different tools at the start of every conversation, even if you only use 2 of them. That wastes tokens (and your money).

With Tool Search enabled, Claude loads only your most commonly used tools immediately (like `check_tag_compliance` and `find_untagged_resources`). The other tools? Claude discovers them only when needed. This cuts token costs by **85%** for tool definitions.

Bonus: Studies show this improves Claude Opus 4.5 accuracy from 79.5% to 88.1% on tool-use tasks, because it's not overwhelmed by irrelevant tool definitions.

Setup is simple: add one config flag to your Claude Desktop settings and mark which tools to defer. Check out the [Tool Search Configuration Guide](./docs/TOOL_SEARCH_CONFIGURATION.md) for copy-paste examples.

---

## Real-World Use Cases

**Monthly compliance audits**: Your CFO wants a quarterly report on tagging compliance. Instead of exporting CSV files from AWS and building spreadsheets, ask Claude: *"Generate a markdown report showing tagging compliance trends for Q1 2026."* Done. Formatted, with charts, ready to present.

**Pre-deployment validation**: Before launching 50 new EC2 instances via Terraform, validate their tags: *"Validate these 10 resource ARNs against our policy."* Catch violations before they hit production. Integrates beautifully with CI/CD pipelines.

**Cost attribution gap analysis**: Your finance team is frustrated because 40% of AWS costs can't be allocated to teams. Ask Claude: *"How much EC2 spend is unattributable due to missing CostCenter tags?"* Get a dollar amount, a list of offending resources, and remediation suggestions.

**Intelligent tagging suggestions**: You have 200 EC2 instances with inconsistent tagging. Instead of manually fixing them, let ML do the heavy lifting: *"Suggest tags for instance i-0abc123 based on its name and VPC."* Get recommendations with confidence scores and reasoning.

---

## What's Supported

This server currently focuses on AWS, with support for over 50 resource types including EC2, S3, RDS, Lambda, ECS, DynamoDB, ElastiCache, EBS, EFS, and various AI/ML services like Bedrock. You can scan specific types or use `"all"` to check everything.

Authentication uses IAM roles (no hardcoded credentials). The server integrates with AWS Organizations tag policies, stores compliance history in SQLite, caches results in Redis for fast repeat queries, and provides comprehensive audit logging.

Security features include input validation, budget enforcement to prevent runaway queries, loop detection to catch infinite calls, and error sanitization to ensure no secrets leak into logs. See the [Security Configuration Guide](./docs/SECURITY_CONFIGURATION.md) for details.

---

## Roadmap

**Phase 1 (Complete)**: AWS support with 8 tools, compliance history tracking, cost attribution, ML tag suggestions, Docker deployment on EC2.

**Phase 2 (Months 3-4)**: Production scale on ECS Fargate with 16 total tools, high availability, ElastiCache Redis, RDS PostgreSQL, OAuth 2.0 authentication.

**Phase 3 (Months 5-6)**: Multi-cloud support for Azure and GCP with unified tagging policies and cross-cloud consistency checking.

**Phase 4 (Months 7-8)**: Automation integration—generate remediation scripts (Terraform, CloudFormation, Ansible), integrate with OpenOps and wiv.ai for automated workflows.

See the [full Roadmap](./docs/ROADMAP.md) for timelines and decision points.

---

## Documentation

**Start here**: [User Manual](./docs/USER_MANUAL.md) — Practical guide for FinOps practitioners
**Deploy**: [Deployment Guide](./docs/DEPLOYMENT.md) — Local and remote setup instructions
**Configure**: [Tagging Policy Guide](./docs/TAGGING_POLICY_GUIDE.md) — Define your organization's rules | [Resource Type Configuration](./docs/RESOURCE_TYPE_CONFIGURATION.md) — Manage AWS resource types
**Optimize**: [Tool Search Configuration](./docs/TOOL_SEARCH_CONFIGURATION.md) — Reduce token costs by 85%
**Security**: [IAM Permissions Guide](./docs/IAM_PERMISSIONS.md) — Required AWS permissions

For architecture deep dives, check out the [System Diagrams](./docs/diagrams/README.md). For testing and development, see [Testing Quick Start](./docs/TESTING_QUICK_START.md). Full technical specs are in [SPECIFICATION.md](./docs/SPECIFICATION.md).

---

## Contributing

This project is actively developed and we welcome contributions: bug reports, feature requests, documentation improvements, use case examples, and feedback on the MCP tool design.

See [Development Journal](./docs/DEVELOPMENT_JOURNAL.md) for build history and [GitHub Issues](https://github.com/OptimNow/finops-tag-compliance-mcp/issues) for current work.

---

## Architecture

This project follows a **layered service-oriented architecture** with clear separation between the MCP protocol layer and reusable business logic:

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Protocol Layer                          │
│  main.py (FastAPI) → mcp_handler.py (Protocol handling)         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Tools Layer (Adapters)                     │
│  check_tag_compliance.py, find_untagged_resources.py, etc.      │
│  Thin wrappers that translate MCP calls to service methods      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Services Layer (Core Library)                   │
│  ComplianceService, CostService, PolicyService, AuditService    │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  ✓ Protocol-agnostic (no MCP knowledge)                         │
│  ✓ Reusable in CLI, REST API, webhooks, etc.                    │
│  ✓ All business logic lives here                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Models Layer (Pydantic)                    │
│  17 model files with strict validation, type safety, schemas    │
│  ComplianceResult, Violation, Resource, TagPolicy, etc.         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Clients Layer                              │
│  AWSClient (boto3 wrapper), RedisCache, SQLite databases        │
└─────────────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- **Services are reusable**: The `mcp_server/services/` layer has zero knowledge of MCP. You could import `ComplianceService` into a CLI tool or webhook handler today.
- **Pydantic everywhere**: All data structures use Pydantic models with validation, constraints, and automatic JSON schema generation for LLM compatibility.
- **Thin tool adapters**: Each MCP tool in `mcp_server/tools/` is a lightweight wrapper that calls the corresponding service method.

---

## Project Structure

```
finops-tag-compliance-mcp/
├── mcp_server/
│   ├── main.py           # FastAPI app, MCP endpoints
│   ├── mcp_handler.py    # MCP protocol handling
│   ├── services/         # Core business logic (protocol-agnostic)
│   ├── tools/            # MCP tool adapters
│   ├── models/           # Pydantic data models (17 files)
│   ├── clients/          # AWS, Redis, database clients
│   └── middleware/       # Budget, security, sanitization
├── policies/             # Your tagging policy (JSON)
├── scripts/              # Utilities (mcp_bridge.py, converter)
├── tests/                # Comprehensive test suite
├── docs/                 # Documentation & diagrams
├── docker-compose.yml    # Local development setup
└── Dockerfile            # Container image
```

---

**License**: Apache 2.0
**Support**: [GitHub Discussions](https://github.com/OptimNow/finops-tag-compliance-mcp/discussions)
**Built with ❤️ for the FinOps community**
