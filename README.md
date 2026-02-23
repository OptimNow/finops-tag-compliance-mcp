# FinOps Tag Compliance MCP Server

> **Turn Claude into your AWS tagging compliance assistant** — Ask in plain English, get real-time insights on your cloud costs and compliance.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)

---

## Quick Start

```bash
# Install
pip install finops-tag-compliance-mcp

# Run
finops-tag-compliance
```

Add to your Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "finops-tag-compliance": {
      "command": "finops-tag-compliance",
      "env": {
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

That's it. Now ask Claude: *"Which of my EC2 instances are missing required tags?"*

> **Want multi-account support, scheduled reports, and a dashboard?**
> Connect your AWS account at [mcp.optimnow.io](https://mcp.optimnow.io) — no setup required.

---

## What Is This?

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that gives Claude real-time access to your AWS tagging compliance data. Instead of writing boto3 scripts or clicking through the AWS Console, just ask Claude in natural language:

- *"Run a compliance check on all my EC2 and RDS instances"*
- *"How much of our EC2 spend is unattributable due to missing tags?"*
- *"Suggest tags for this EC2 instance based on its name and similar resources"*
- *"Generate a markdown compliance report for our Q1 review"*

Behind the scenes, this MCP server queries your AWS environment, validates resources against your tagging policy, calculates cost impacts, and returns structured insights that Claude translates into natural language.

---

## Features

### 14 Tools

| Tool | Description |
|------|-------------|
| `check_tag_compliance` | Scan resources and calculate compliance score |
| `find_untagged_resources` | Find resources missing required tags with cost impact |
| `validate_resource_tags` | Validate specific resources by ARN |
| `get_cost_attribution_gap` | Calculate financial impact of tagging gaps |
| `suggest_tags` | ML-powered tag recommendations with confidence scores |
| `get_tagging_policy` | View current policy configuration |
| `generate_compliance_report` | Generate reports in JSON, CSV, or Markdown |
| `get_violation_history` | Track compliance trends over time |
| `detect_tag_drift` | Find unexpected tag changes since last scan |
| `generate_custodian_policy` | Create Cloud Custodian enforcement YAML |
| `generate_openops_workflow` | Build automated remediation workflows |
| `schedule_compliance_audit` | Configure recurring audit schedules |
| `export_violations_csv` | Export violations for spreadsheet analysis |
| `import_aws_tag_policy` | Import policies from AWS Organizations |

### Multi-Region Scanning

Scans all enabled AWS regions in parallel. Global resources (S3, IAM) are always included regardless of region filters.

### 40+ AWS Resource Types

EC2, S3, RDS, Lambda, ECS, DynamoDB, ElastiCache, EBS, EFS, Bedrock, OpenSearch, and many more. Use `"all"` to scan everything.

### Cost Attribution

Links tagging violations to actual dollar amounts using AWS Cost Explorer. State-aware cost attribution correctly assigns $0 to stopped EC2 instances.

### Customizable Policy

Define required and optional tags in a simple JSON file (`policies/tagging_policy.json`) with allowed values, regex validation, and per-resource-type rules.

---

## Installation

### Prerequisites

- Python 3.11+
- AWS credentials configured (`~/.aws/credentials` or environment variables)
- [Claude Desktop](https://claude.ai/download) or any MCP-compatible client

### Install from PyPI

```bash
pip install finops-tag-compliance-mcp
```

### Install from Source

```bash
git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp
pip install -e .
```

### AWS Permissions

The server needs read-only AWS permissions. See [IAM Permissions Guide](./docs/security/IAM_PERMISSIONS.md) for the full policy, but the key permissions are:

- `ec2:Describe*`, `rds:Describe*`, `s3:List*`, `lambda:List*`
- `tag:GetResources` (Resource Groups Tagging API)
- `ce:GetCostAndUsage` (Cost Explorer — optional, for cost attribution)

No write permissions are needed.

---

## Configuration

### Claude Desktop

Add to your `claude_desktop_config.json`:

**Minimal** (uses default region and auto-discovers AWS credentials):
```json
{
  "mcpServers": {
    "finops-tag-compliance": {
      "command": "finops-tag-compliance"
    }
  }
}
```

**With options**:
```json
{
  "mcpServers": {
    "finops-tag-compliance": {
      "command": "finops-tag-compliance",
      "env": {
        "AWS_REGION": "us-east-1",
        "AWS_PROFILE": "my-profile",
        "ALLOWED_REGIONS": "us-east-1,us-west-2,eu-west-1",
        "POLICY_PATH": "/path/to/my/tagging_policy.json"
      }
    }
  }
}
```

**Config file location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | Default AWS region |
| `AWS_PROFILE` | (default) | AWS credentials profile |
| `ALLOWED_REGIONS` | (all enabled) | Comma-separated list of regions to scan |
| `MAX_CONCURRENT_REGIONS` | `5` | Max parallel region scans (1-20) |
| `POLICY_PATH` | `policies/tagging_policy.json` | Path to tagging policy |
| `RESOURCE_TYPES_CONFIG_PATH` | `config/resource_types.json` | Resource types configuration |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL (optional, for caching) |
| `COMPLIANCE_CACHE_TTL_SECONDS` | `3600` | Cache TTL for compliance results |

Redis is optional. Without it, results are not cached between invocations.

### Tagging Policy

Define your organization's tagging rules in `policies/tagging_policy.json`:

```json
{
  "required_tags": [
    {
      "name": "Environment",
      "description": "Deployment environment",
      "allowed_values": ["production", "staging", "development"],
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket"]
    },
    {
      "name": "CostCenter",
      "description": "Cost center for billing",
      "validation_regex": "^CC-\\d{4}$",
      "applies_to": []
    }
  ],
  "optional_tags": [
    {
      "name": "Project",
      "description": "Project name"
    }
  ]
}
```

- `allowed_values`: Tag value must be in this list (case-sensitive)
- `validation_regex`: Tag value must match this pattern
- `applies_to`: Resource types this tag applies to (empty = all types)

See [Tagging Policy Guide](./docs/TAGGING_POLICY_GUIDE.md) for full documentation.

---

## Testing with MCP Inspector

The [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) lets you test the server interactively in your browser:

```bash
npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server
```

This opens a UI where you can list tools, execute them with custom arguments, and inspect results.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   MCP Protocol Layer (stdio)                     │
│  stdio_server.py → FastMCP with 14 registered tools              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Tools Layer (Adapters)                        │
│  Thin wrappers: MCP tool calls → service method calls            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               Services Layer (Core Library)                      │
│  ComplianceService, CostService, PolicyService, etc.             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  Protocol-agnostic — no MCP knowledge                            │
│  Reusable: from mcp_server.services import ComplianceService     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Clients Layer                                  │
│  AWSClient (boto3 + rate limiting), RedisCache, SQLite           │
└─────────────────────────────────────────────────────────────────┘
```

The services layer has zero knowledge of MCP. You can import `ComplianceService` directly into a CLI tool, webhook handler, or any other Python application.

---

## Project Structure

```
finops-tag-compliance-mcp/
├── mcp_server/
│   ├── stdio_server.py      # MCP entry point (Claude Desktop)
│   ├── container.py          # Service container (dependency injection)
│   ├── config.py             # Configuration settings
│   ├── services/             # Core business logic (12 services)
│   ├── tools/                # MCP tool adapters (14 tools)
│   ├── models/               # Pydantic data models (17 files)
│   ├── clients/              # AWS, Redis, database clients
│   └── utils/                # Correlation IDs, validation, error handling
├── policies/                 # Tagging policy (JSON)
├── config/                   # Resource types configuration
├── examples/                 # Claude Desktop config examples
├── tests/                    # Unit + property-based tests
├── docs/                     # Documentation
├── pyproject.toml            # Package configuration
└── LICENSE                   # Apache 2.0
```

---

## Development

```bash
# Clone and install with dev dependencies
git clone https://github.com/OptimNow/finops-tag-compliance-mcp.git
cd finops-tag-compliance-mcp
pip install -e ".[dev]"

# Run tests
pytest tests/unit tests/property --ignore=tests/unit/test_aws_client.py

# Format
black mcp_server/ tests/

# Lint
ruff check mcp_server/ tests/

# Type check
mypy mcp_server/
```

### Testing Strategy

- **Unit tests** (`tests/unit/`): Fast, isolated, mock all AWS calls
- **Property tests** (`tests/property/`): Hypothesis-based generative testing for invariants
- **Integration tests** (`tests/integration/`): End-to-end with real AWS (requires credentials)

---

## Documentation

| Guide | Description |
|-------|-------------|
| [User Manual](./docs/USER_MANUAL.md) | Practical guide for FinOps practitioners |
| [Tagging Policy Guide](./docs/TAGGING_POLICY_GUIDE.md) | Define your organization's tagging rules |
| [Resource Type Configuration](./docs/RESOURCE_TYPE_CONFIGURATION.md) | Manage which AWS resource types to scan |
| [Tool Logic Reference](./docs/TOOL_LOGIC_REFERENCE.md) | Detailed logic for each of the 14 tools |
| [Tool Search Configuration](./docs/TOOL_SEARCH_CONFIGURATION.md) | Reduce token costs with on-demand tool loading |
| [IAM Permissions](./docs/security/IAM_PERMISSIONS.md) | Required AWS permissions |
| [MCP Security Best Practices](./docs/security/MCP_SECURITY_BEST_PRACTICES.md) | Security guidance |
| [Testing Quick Start](./docs/TESTING_QUICK_START.md) | Getting started with the test suite |

---

## Contributing

We welcome contributions! Bug reports, feature requests, documentation improvements, and code contributions are all appreciated.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Run tests (`pytest tests/unit tests/property`)
4. Commit your changes
5. Open a Pull Request

See [GitHub Issues](https://github.com/OptimNow/finops-tag-compliance-mcp/issues) for current work.

---

## License

Apache 2.0 — see [LICENSE](./LICENSE) for details.

---

**Built for the FinOps community by [OptimNow](https://optimnow.io)**
