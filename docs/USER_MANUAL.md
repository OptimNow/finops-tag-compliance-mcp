# User Manual: Tag Compliance MCP Server

A practical guide for FinOps practitioners to use the Tag Compliance MCP Server with Claude Desktop.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Available Tools](#available-tools)
3. [Common Workflows](#common-workflows)
4. [Example Prompts](#example-prompts)
5. [Understanding Results](#understanding-results)
6. [Troubleshooting](#troubleshooting)
7. [Tips for FinOps Practitioners](#tips-for-finops-practitioners)
8. [Customizing Output Formatting](#customizing-output-formatting)

---

## Getting Started

### What is this tool?

The Tag Compliance MCP Server helps you manage AWS resource tagging through natural conversation with Claude. Instead of writing scripts or navigating the AWS console, you can simply ask Claude questions like:

- "Which of my EC2 instances are missing required tags?"
- "What's my overall tag compliance score?"
- "How much money am I losing due to untagged resources?"

### Prerequisites

1. MCP server deployed (see [Deployment Guide](DEPLOYMENT.md))
2. Claude Desktop configured to connect to the server
3. AWS credentials with read access to your resources

### Quick Test

After setup, try asking Claude:

> "What tagging policy is configured?"

You should see a response listing your required and optional tags.

### Tool Search Optimization (Optional)

**NEW: January 2026** - Reduce your token costs by 85% with Claude's Tool Search feature!

Instead of loading all 8 tool definitions upfront, Claude can discover tools on-demand. This optimization:
- **Saves costs**: Reduces token usage from ~15K to ~3K per conversation
- **Improves performance**: Faster response times and better tool selection accuracy
- **No functionality changes**: All tools still work exactly the same

**To enable:**
1. See [examples/](../examples/) for ready-to-use configuration files
2. Read the [Tool Search Configuration Guide](./TOOL_SEARCH_CONFIGURATION.md) for detailed setup

This is **completely optional** - your MCP server works perfectly without it. But if you're doing many conversations, the cost savings add up quickly!

---

## Available Tools

The MCP server provides 8 tools for tag compliance management:

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
What tags should I add to this S3 bucket?
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

## Common Workflows

### Workflow 1: Initial Assessment

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

### Workflow 2: Remediation Planning

Focus on fixing the most impactful violations:

1. **Find high-cost untagged resources**:
   > "Find untagged EC2 instances costing more than $100/month"

2. **Get tag suggestions**:
   > "Suggest tags for [resource ARN]"

3. **Validate after tagging**:
   > "Validate the tags on [resource ARN]"

---

### Workflow 3: Ongoing Monitoring

Track compliance over time:

1. **Weekly compliance check**:
   > "Check tag compliance for EC2 and RDS"

2. **Review trends**:
   > "Show me compliance history for the last 7 days"

3. **Identify new violations**:
   > "Find resources created in the last week that are missing tags"

---

### Workflow 4: Team Accountability

Identify ownership gaps:

1. **Find resources without owners**:
   > "Find resources missing the Owner tag"

2. **Check by cost center**:
   > "Check compliance for resources tagged with CostCenter=Engineering"

3. **Generate team report**:
   > "Generate a compliance report grouped by CostCenter"

---

## Example Prompts

### Basic Queries

| What you want | Example prompt |
|---------------|----------------|
| Overall compliance | "What's my tag compliance score?" |
| View policy | "Show me the tagging policy" |
| Find violations | "Which resources have tag violations?" |
| Cost impact | "How much is untagged spend costing me?" |

### Resource-Specific Queries

| Resource Type | Example prompt |
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

### Advanced Queries

| Scenario | Example prompt |
|----------|----------------|
| All resources | "Check tag compliance for all resource types" |
| Filter by region | "Check compliance for EC2 instances in us-east-1" |
| Filter by severity | "Show only critical tag violations" |
| Cost threshold | "Find untagged resources costing more than $50/month" |
| Time-based | "Show compliance history for the last 30 days" |
| Specific resource | "Validate tags on arn:aws:s3:::my-bucket" |
| AI/ML resources | "Find all untagged Bedrock and SageMaker resources" |

---

## Understanding Results

### Compliance Score

The compliance score is calculated as:

```
Score = (Compliant Resources / Total Resources) × 100
```

- **90-100%**: Excellent - Minor cleanup needed
- **70-89%**: Good - Some attention required
- **50-69%**: Fair - Significant gaps exist
- **Below 50%**: Poor - Immediate action needed

### Violation Types

| Type | Description | Severity |
|------|-------------|----------|
| `missing_required_tag` | A required tag is not present | Error |
| `invalid_value` | Tag value not in allowed list | Error |
| `invalid_format` | Tag value doesn't match regex pattern | Warning |

### Cost Attribution Gap

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
- See [IAM Permissions Guide](IAM_PERMISSIONS.md) for required policies

### Slow responses

- Large accounts may take longer to scan
- Try filtering by resource type or region
- Results are cached for 1 hour by default

### Claude doesn't see the tools

- Verify the MCP server is running: `curl http://SERVER:8080/health`
- Check Claude Desktop config file syntax
- Restart Claude Desktop after config changes

---

## Tips for FinOps Practitioners

### Start Small
Begin with one resource type (like EC2) before scanning everything. This helps you understand the results and plan remediation.

### Focus on Cost Impact
Use the cost attribution gap tool to prioritize. A $500/month untagged instance matters more than a $5/month Lambda function.

### Automate Reporting
Set up a weekly routine to generate compliance reports. Track trends over time to show improvement.

### Customize Your Policy
The default policy is a starting point. Customize `policies/tagging_policy.json` to match your organization's actual requirements.

### Tag at Creation
The best time to tag is when resources are created. Use this tool to catch what slips through and establish better processes.

---

## Customizing Output Formatting

The MCP server returns structured data, and Claude decides how to present it (bullet points, tables, charts, etc.). You can customize this by instructing Claude on your preferred format.

### One-Time Formatting Request

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

### Persistent Formatting Preferences

To make Claude always use your preferred format, start your conversation with a formatting instruction:

```
For all tag compliance results in this conversation, please:
- Display violations and resources in markdown tables (not bullet points)
- Include a summary section at the top
- Sort by cost impact (highest first)
- Use charts/graphs when showing trends or comparisons
```

### Example Formatting Prompts

| Format | Example Prompt |
|--------|----------------|
| Tables | "Show untagged resources in a table with Resource ID, Type, Cost, and Missing Tags columns" |
| Charts | "Display the compliance score trend as a bar chart" |
| CSV-ready | "List violations in CSV format I can paste into Excel" |
| Executive summary | "Give me a brief executive summary with key metrics, then detailed tables" |
| Grouped | "Show violations grouped by resource type in separate tables" |

### Claude Desktop System Prompt (Advanced)

For organization-wide formatting preferences, you can add instructions to Claude Desktop's system prompt. Edit your Claude Desktop config to include formatting preferences that apply to all conversations.

---

## Getting Help

- **Deployment issues**: See [Deployment Guide](DEPLOYMENT.md)
- **Policy configuration**: See [Tagging Policy Guide](TAGGING_POLICY_GUIDE.md)
- **IAM permissions**: See [IAM Permissions Guide](IAM_PERMISSIONS.md)
- **Bug reports**: Open an issue on GitHub
- **Tool logic details**: See [Tool Logic Reference](TOOL_LOGIC_REFERENCE.md)

