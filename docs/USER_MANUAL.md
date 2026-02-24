# User manual

A practical guide for FinOps practitioners to use the FinOps Tag Compliance MCP Server with Claude.

## Table of contents

1. [Getting started](#getting-started)
2. [Available tools](#available-tools)
3. [Common workflows](#common-workflows)
4. [Example prompts](#example-prompts)
5. [Understanding results](#understanding-results)
6. [Troubleshooting](#troubleshooting)
7. [Tips for FinOps practitioners](#tips-for-finops-practitioners)
8. [Customizing output formatting](#customizing-output-formatting)

---

## Getting started

### Prerequisites

1. MCP server installed (see the [README](../README.md) for quick start instructions)
2. Claude Desktop (or any MCP-compatible client) configured to connect to the server
3. AWS credentials with read access to your resources (see [IAM permissions guide](security/IAM_PERMISSIONS.md))

### Quick test

After setup, try asking Claude:

> "What tagging policy is configured?"

You should see a response listing your required and optional tags.

---

## Available tools

The MCP server provides 14 tools for tag compliance management:

### 1. check_tag_compliance

Scan resources and get a compliance score.

**What it does**: Scans specified resource types, validates them against your tagging policy, and returns a compliance score with detailed violations.

**Example prompts**:
```
Check tag compliance for my EC2 instances
```
```
What's the compliance score for all my S3 buckets?
```
```
Scan my Lambda functions for tag violations
```

**Resource types**:
- Specific types: `ec2:instance`, `rds:db`, `s3:bucket`, `lambda:function`, `ecs:service`, `opensearch:domain`
- Use `all` to scan ALL taggable resources (50+ types including Bedrock, DynamoDB, SNS, SQS, etc.)

**Note**: The `all` option uses AWS Resource Groups Tagging API which only returns resources that have at least one tag. For completely untagged resources, use specific resource types.

---

### 2. find_untagged_resources

Find resources missing required tags.

**What it does**: Identifies resources with no tags or missing required tags, includes cost estimates and resource age to help prioritize remediation.

**Example prompts**:
```
Find all untagged S3 buckets
```
```
Which EC2 instances are missing the CostCenter tag?
```
```
Show me untagged resources costing more than $50/month
```

---

### 3. validate_resource_tags

Validate specific resources by ARN.

**What it does**: Validates one or more specific resources against the tagging policy, returns detailed violation information.

**Example prompts**:
```
Validate the tags on arn:aws:ec2:us-east-1:123456789:instance/i-abc123
```
```
Check if this S3 bucket has valid tags: arn:aws:s3:::my-bucket
```

---

### 4. get_cost_attribution_gap

Calculate the financial impact of tagging gaps.

**What it does**: Shows how much cloud spend cannot be allocated to teams/projects due to missing or invalid tags.

**Example prompts**:
```
What's my cost attribution gap?
```
```
How much money can't be attributed due to missing tags?
```
```
Show me the cost impact of untagged resources by region
```

---

### 5. suggest_tags

Get tag suggestions for a resource.

**What it does**: Analyzes patterns like VPC naming, IAM roles, and similar resources to recommend tag values with confidence scores.

**Example prompts**:
```
Suggest tags for arn:aws:ec2:us-east-1:123456789:instance/i-abc123
```
```
What tags should I add to this EC2 instance?
```

---

### 6. get_tagging_policy

View the current tagging policy.

**What it does**: Returns the complete policy configuration including required tags, optional tags, and validation rules.

**Example prompts**:
```
What tagging policy is configured?
```
```
Show me the required tags
```
```
What are the allowed values for the Environment tag?
```

---

### 7. generate_compliance_report

Generate a comprehensive compliance report.

**What it does**: Creates a detailed report with compliance summary, top violations ranked by count and cost, and actionable recommendations.

**Example prompts**:
```
Generate a compliance report for all my resources
```
```
Create a markdown report of tag violations
```
```
Give me a summary report with recommendations
```

**Output formats**: JSON, CSV, Markdown

---

### 8. get_violation_history

View historical compliance data.

**What it does**: Shows how compliance has changed over time to track progress and measure remediation effectiveness.

**Example prompts**:
```
Show me compliance history for the last 30 days
```
```
How has our tag compliance improved this month?
```
```
What's the trend in tag violations?
```

---

### 9. generate_custodian_policy

Generate Cloud Custodian YAML policies from your tagging policy.

**What it does**: Creates enforceable Cloud Custodian policies based on your current tagging policy. Use `dry_run=True` (default) for notify-only policies, or `False` for auto-remediation.

**Example prompts**:
```
Generate Cloud Custodian policies for my tagging rules
```
```
Create enforcement policies for missing Environment and Owner tags
```
```
Generate auto-remediation policies for EC2 instances
```

---

### 10. generate_openops_workflow

Generate an OpenOps automation workflow for tag remediation.

**What it does**: Creates an OpenOps-compatible YAML workflow that automates tag compliance enforcement with notification, auto-tagging, or reporting strategies.

**Example prompts**:
```
Create an OpenOps workflow to notify when compliance drops below 80%
```
```
Generate a daily auto-tagging workflow for EC2 instances
```
```
Build a weekly tag compliance reporting workflow
```

---

### 11. schedule_compliance_audit

Create a compliance audit schedule configuration.

**What it does**: Generates a schedule configuration for recurring compliance audits, including cron expressions and next estimated run time. The configuration can be used with external schedulers.

**Example prompts**:
```
Schedule a daily compliance audit at 9am UTC
```
```
Set up a weekly audit with email notifications
```
```
Create a monthly compliance check schedule for EC2 and RDS
```

---

### 12. detect_tag_drift

Detect unexpected tag changes since the last compliance scan.

**What it does**: Compares current resource tags against expected state from the tagging policy to identify missing required tags and invalid tag values. Classifies drift by severity: critical, warning, or info.

**Example prompts**:
```
Detect tag drift on my EC2 instances
```
```
Have any tags changed unexpectedly in the last 7 days?
```
```
Check for tag drift on the Environment and Owner tags
```

---

### 13. export_violations_csv

Export compliance violations as CSV data.

**What it does**: Runs a compliance scan and exports violations in CSV format for spreadsheet analysis, reporting, or integration with other tools.

**Example prompts**:
```
Export all tag violations as CSV
```
```
Give me a CSV of critical violations for EC2 and RDS
```
```
Export violations with resource ARN and cost impact columns
```

---

### 14. import_aws_tag_policy

Import and convert an AWS Organizations tag policy to MCP format.

**What it does**: Connects to AWS Organizations to retrieve tag policies and converts them to the MCP server's tagging policy format. If no policy ID is provided, lists all available tag policies.

**Example prompts**:
```
List my AWS Organizations tag policies
```
```
Import the tag policy p-abc12345 from AWS Organizations
```
```
Convert my AWS Organizations tagging rules to MCP format
```

---

## Common workflows

### Workflow 1: Initial assessment

Start with a broad compliance check to understand your current state:

1. **Check overall compliance**:
   > "Check tag compliance for all resource types"

2. **Identify biggest gaps**:
   > "Find untagged resources sorted by cost"

3. **Understand the financial impact**:
   > "What's my cost attribution gap?"

4. **Generate a report for stakeholders**:
   > "Generate a compliance report in markdown format"

---

### Workflow 2: Remediation planning

Focus on fixing the most impactful violations:

1. **Find high-cost untagged resources**:
   > "Find untagged EC2 instances costing more than $100/month"

2. **Get tag suggestions**:
   > "Suggest tags for [resource ARN]"

3. **Validate after tagging**:
   > "Validate the tags on [resource ARN]"

4. **Generate enforcement policies**:
   > "Generate Cloud Custodian policies for EC2 tag enforcement"

---

### Workflow 3: Ongoing monitoring

Track compliance over time:

1. **Weekly compliance check**:
   > "Check tag compliance for EC2 and RDS"

2. **Review trends**:
   > "Show me compliance history for the last 7 days"

3. **Detect drift**:
   > "Have any tags changed unexpectedly this week?"

4. **Export for reporting**:
   > "Export violations as CSV for the team"

---

### Workflow 4: Team accountability

Identify ownership gaps:

1. **Find resources without owners**:
   > "Find resources missing the Owner tag"

2. **Check by cost center**:
   > "Check compliance for resources tagged with CostCenter=Engineering"

3. **Generate team report**:
   > "Generate a compliance report grouped by CostCenter"

---

## Example prompts

### Basic queries

| What you want | Example prompt |
|---------------|----------------|
| Overall compliance | "What's my tag compliance score?" |
| View policy | "Show me the tagging policy" |
| Find violations | "Which resources have tag violations?" |
| Cost impact | "How much is untagged spend costing me?" |

### Resource-specific queries

| Resource type | Example prompt |
|---------------|----------------|
| All resources | "Check tag compliance for all resource types" |
| EC2 | "Check tag compliance for EC2 instances" |
| S3 | "Find S3 buckets missing the DataClassification tag" |
| RDS | "Which RDS databases are missing required tags?" |
| Lambda | "Scan Lambda functions for tag violations" |
| ECS | "Check compliance for ECS services" |
| OpenSearch | "Find untagged OpenSearch domains" |
| Bedrock | "Check compliance for my Bedrock agents and knowledge bases" |
| DynamoDB | "Find untagged DynamoDB tables" |

### Advanced queries

| Scenario | Example prompt |
|----------|----------------|
| All resources | "Check tag compliance for all resource types" |
| Filter by region | "Check compliance for EC2 instances in us-east-1" |
| Filter by severity | "Show only critical tag violations" |
| Cost threshold | "Find untagged resources costing more than $50/month" |
| Time-based | "Show compliance history for the last 30 days" |
| Specific resource | "Validate tags on arn:aws:s3:::my-bucket" |
| AI/ML resources | "Find all untagged Bedrock and SageMaker resources" |
| Enforcement | "Generate Cloud Custodian policies for my tagging rules" |
| Drift detection | "Check for tag drift in the last 7 days" |
| Export | "Export all violations as CSV" |

---

## Understanding results

### Compliance score

The compliance score is calculated as:

```
Score = (Compliant Resources / Total Resources) × 100
```

- **90-100%**: Excellent - Minor cleanup needed
- **70-89%**: Good - Some attention required
- **50-69%**: Fair - Significant gaps exist
- **Below 50%**: Poor - Immediate action needed

### Violation types

| Type | Description | Severity |
|------|-------------|----------|
| `missing_required_tag` | A required tag is not present | Error |
| `invalid_value` | Tag value not in allowed list | Error |
| `invalid_format` | Tag value doesn't match regex pattern | Warning |

### Cost attribution gap

The cost attribution gap shows:

- **Total Spend**: All cloud costs in the period
- **Attributable Spend**: Costs that can be allocated (properly tagged)
- **Gap**: Costs that cannot be allocated (missing/invalid tags)
- **Gap Percentage**: Gap as percentage of total spend

---

## Troubleshooting

### "No resources found"

- Check that your AWS credentials have read access
- Verify the resource type is correct (e.g., `ec2:instance` not just `ec2`)
- Ensure resources exist in the specified region

### "Policy file not found"

- The tagging policy file may be missing or misconfigured
- Check `policies/tagging_policy.json` exists
- Verify the `POLICY_FILE_PATH` environment variable

### "Access denied" errors

- Your AWS credentials may lack required permissions
- See [IAM permissions guide](security/IAM_PERMISSIONS.md) for required policies

### Slow responses

- Large accounts may take longer to scan
- Try filtering by resource type or region
- Results are cached for 1 hour by default

### Claude doesn't see the tools

- Check that `python -m mcp_server.stdio_server` runs without errors
- Check Claude Desktop config file syntax (use a JSON validator)
- Restart Claude Desktop after config changes
- Test with MCP Inspector: `npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server`

---

## Tips for FinOps practitioners

### Start small
Begin with one resource type (like EC2) before scanning everything. This helps you understand the results and plan remediation.

### Focus on cost impact
Use the cost attribution gap tool to prioritize. A $500/month untagged instance matters more than a $5/month Lambda function.

### Automate reporting
Set up a weekly routine to generate compliance reports. Track trends over time to show improvement.

### Customize your policy
The default policy is a starting point. Customize `policies/tagging_policy.json` to match your organization's actual requirements.

### Tag at creation
The best time to tag is when resources are created. Use this tool to catch what slips through and establish better processes.

---

## Customizing output formatting

The MCP server returns structured data, and Claude decides how to present it (bullet points, tables, charts, etc.). You can customize this by instructing Claude on your preferred format.

### One-time formatting request

Add formatting instructions to your prompt:

```
Check tag compliance for my EC2 instances. Display the results in a table format.
```

```
Find untagged resources and show them in a markdown table with columns for Resource ID, Type, Region, and Missing Tags.
```

```
Show me the cost attribution gap with a bar chart visualization.
```

### Persistent formatting preferences

To make Claude always use your preferred format, start your conversation with a formatting instruction:

```
For all tag compliance results in this conversation, please:
- Display violations and resources in markdown tables (not bullet points)
- Include a summary section at the top
- Sort by cost impact (highest first)
- Use charts/graphs when showing trends or comparisons
```

### Example formatting prompts

| Format | Example prompt |
|--------|----------------|
| Tables | "Show untagged resources in a table with Resource ID, Type, Cost, and Missing Tags columns" |
| Charts | "Display the compliance score trend as a bar chart" |
| CSV-ready | "List violations in CSV format I can paste into Excel" |
| Executive summary | "Give me a brief executive summary with key metrics, then detailed tables" |
| Grouped | "Show violations grouped by resource type in separate tables" |

### Claude Desktop system prompt (advanced)

For organization-wide formatting preferences, you can add instructions to Claude Desktop's system prompt. Edit your Claude Desktop config to include formatting preferences that apply to all conversations.

---

## Getting help

- **Installation & setup**: See the [README](../README.md)
- **Policy configuration**: See [Tagging policy guide](TAGGING_POLICY_GUIDE.md)
- **IAM permissions**: See [IAM permissions guide](security/IAM_PERMISSIONS.md)
- **Tool logic details**: See [Tool logic reference](TOOL_LOGIC_REFERENCE.md)
- **Bug reports**: Open an issue on [GitHub](https://github.com/OptimNow/finops-tag-compliance-mcp/issues)
