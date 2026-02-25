---
name: "finops-tag-compliance"
displayName: "FinOps Tag Compliance"
description: "AWS resource tagging validation, compliance scoring, cost attribution gap analysis, and remediation policy generation"
keywords:
  - "tagging"
  - "tag compliance"
  - "finops"
  - "untagged resources"
  - "cost attribution"
  - "tag policy"
  - "tag drift"
  - "compliance score"
  - "missing tags"
  - "cloud custodian"
  - "tag remediation"
  - "aws tags"
---

# FinOps Tag Compliance Power

You have access to the **FinOps Tag Compliance** MCP server, which provides 14 tools for AWS resource tagging validation and compliance checking.

## Onboarding

Before using this power, verify the following:

1. **Python 3.10+** is installed (`python --version`)
2. **AWS credentials** are configured with read-only access to EC2, RDS, S3, Lambda, ECS, Cost Explorer, and Resource Groups Tagging API. See the [IAM Permissions Guide](docs/security/IAM_PERMISSIONS.md) for the least-privilege policy.
3. The MCP server package is installed (`pip install finops-tag-compliance-mcp`)
4. A tagging policy exists at `policies/tagging_policy.json` defining required and optional tags

No write permissions are needed. The server is entirely read-only.

## Critical Rules

Follow these rules for EVERY interaction with the tagging tools:

### 1. Never guess resource types

ALWAYS call `get_tagging_policy` first and use the `all_applicable_resource_types` field from the response. The policy may include Bedrock, DynamoDB, ECS, EKS, SageMaker, and others that you would miss by guessing.

### 2. Scan in batches to avoid timeouts

MCP clients may have a 60-second response timeout. Scan in batches of **4-6 resource types** per call. Never pass `["all"]` unless explicitly requested and you've warned about potential timeouts.

### 3. Report data quality honestly

Every scan response includes a `data_quality` field. If `data_quality.status` is `"partial"`, some regions failed. You MUST disclose this to the user. Never estimate, extrapolate, or fabricate values for regions that failed.

### 4. Cost attribution gap is the slowest tool

`get_cost_attribution_gap` can take 3-5 minutes with many resource types. Always use batches of 3-4 cost-generating types per call.

## Available Tools

| Tool | Purpose |
|------|---------|
| `get_tagging_policy` | View configured tagging policy (START HERE) |
| `check_tag_compliance` | Scan resources and get compliance score |
| `find_untagged_resources` | Find resources missing required tags |
| `validate_resource_tags` | Validate specific resources by ARN |
| `get_cost_attribution_gap` | Calculate financial impact of tagging gaps |
| `suggest_tags` | Get ML-powered tag suggestions for a resource |
| `generate_compliance_report` | Generate JSON/CSV/Markdown reports |
| `get_violation_history` | View historical compliance trends |
| `detect_tag_drift` | Find unexpected tag changes |
| `generate_custodian_policy` | Create Cloud Custodian enforcement YAML |
| `generate_openops_workflow` | Build remediation automation workflows |
| `schedule_compliance_audit` | Configure recurring audit schedules |
| `export_violations_csv` | Export violations for spreadsheets |
| `import_aws_tag_policy` | Import from AWS Organizations |

## Workflows

For detailed step-by-step workflows, see the steering files:

- **[Compliance Check](steering/compliance-check.md)** — Initial assessment, scanning, and reporting
- **[Cost Attribution](steering/cost-attribution.md)** — Analyzing the financial impact of tagging gaps
- **[Remediation](steering/remediation.md)** — Generating enforcement policies and automation
- **[Policy Import](steering/policy-import.md)** — Importing and managing tagging policies
