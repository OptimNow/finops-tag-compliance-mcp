# FinOps Tag Compliance MCP Server

**Status**: Phase 1 MVP Complete  
**Type**: Remote MCP Server  
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

Server URL: `http://localhost:8080`

### Option B: Remote Server (EC2)

If someone has deployed the server to EC2 for you, get the server URL (e.g., `http://ec2-xx-xx-xx-xx.compute.amazonaws.com:8080`).

### Configure Claude Desktop

**Prerequisites:** Python 3.11+ with `requests` library installed:
```bash
pip install requests
```

1. Download the bridge script: [mcp_bridge.py](scripts/mcp_bridge.py)
2. Save it somewhere on your machine (e.g., `C:\tools\mcp_bridge.py`)
3. Edit Claude Desktop config:

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`  
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "finops-tag-compliance": {
      "command": "python",
      "args": ["C:\\tools\\mcp_bridge.py"],
      "env": {
        "MCP_SERVER_URL": "http://localhost:8080"
      }
    }
  }
}
```

Replace `MCP_SERVER_URL` with your server's address (local or remote EC2).

4. Restart Claude Desktop
5. Test with: "Show me our tagging policy"

---

## Overview

The FinOps Tag Compliance MCP Server is a multi-cloud tag governance solution that goes beyond basic tag reading to provide intelligent schema validation, cost attribution analysis, and automated bulk tagging workflows across AWS, Azure, and GCP.

### Key Differentiation from Official Cloud MCPs

| Capability | Official AWS/Azure/GCP MCP | FinOps Tag Compliance MCP |
|------------|---------------------------|---------------------------|
| **Tag Data Access** | ✅ Read tags via API | ✅ Read tags via API |
| **Schema Validation** | ❌ No | ✅ Validates against org policy |
| **Cross-Cloud Consistency** | ❌ Single cloud only | ✅ AWS + Azure + GCP unified |
| **Cost Attribution** | ❌ No | ✅ Links violations to $ impact |
| **Tag Suggestions** | ❌ No | ✅ ML-powered recommendations |
| **Bulk Tagging Workflows** | ❌ No | ✅ Step-up auth + approval |

---

## What Problem Does This Solve?

**The Cost Attribution Gap**: According to the FinOps Foundation's State of FinOps 2025 report, 43% of cloud costs lack proper tagging, creating a $2.3B annual attribution gap for enterprises. This MCP server addresses that gap by:

1. **Enforcing tag compliance** across all cloud resources
2. **Quantifying the financial impact** of missing or incorrect tags
3. **Automating bulk remediation** with approval workflows
4. **Providing ML-powered suggestions** based on resource patterns
5. **Unifying governance** across multi-cloud environments

---

## Documentation

- [Full Specification](./SPECIFICATION.md) - Complete technical specification with 15 tools, 5 resources, and detailed use cases
- Implementation guide (coming soon)
- API reference (coming soon)

---

## Use Cases

### 1. Monthly Tag Compliance Audit
Run comprehensive audits across all clouds to identify violations and quantify cost impact.

### 2. Real-Time Tag Validation (Pre-Deployment)
Validate IaC templates before deployment to catch tag policy violations in CI/CD.

### 3. Intelligent Bulk Tagging with Approval
Use ML suggestions to tag resources in bulk with step-up authorization workflows.

### 4. Cross-Cloud Tag Consistency Enforcement
Ensure consistent tagging standards across AWS, Azure, and GCP.

### 5. Cost Attribution Gap Analysis
Link tagging violations directly to unattributable cloud spend.

---

## Architecture

This is a **remote MCP server** designed for enterprise deployments:

- **Authentication**: OAuth 2.0 + PKCE (MCP spec 2025-11-25)
- **Authorization**: Step-up auth for write operations
- **Multi-Cloud**: Unified interface for AWS, Azure, GCP
- **Deployment**: Cloud-hosted (AWS ECS/Lambda, Azure Container Apps, GCP Cloud Run)
- **Security**: Centralized secrets management, comprehensive audit logging

---

## Status & Roadmap

**Current Status**: Specification complete, ready for implementation

**Roadmap**:
- **Phase 1 (Months 1-3)**: Core compliance engine + AWS support
- **Phase 2 (Months 4-6)**: Azure + GCP support + ML suggestions
- **Phase 3 (Months 7-9)**: Bulk tagging workflows + step-up auth
- **Phase 4 (Months 10-12)**: Enterprise features (multi-tenancy, advanced analytics)

---

## Contributing

This project is in the specification phase. Feedback, suggestions, and contributions are welcome!

---

## License

Apache 2.0 License
