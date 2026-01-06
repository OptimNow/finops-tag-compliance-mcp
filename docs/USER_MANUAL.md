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

---

## Available Tools

The MCP server provides 8 tools for tag compliance management:

### 1. check_tag_compliance

Scan resources and get a compliance score.

**What it does**: Scans specified resource types, validates them against your tagging policy, and returns a compliance score with detailed violations.

**Example prompts**:
- "Check tag compliance for my EC2 instances"
- "What's the compliance score for all my S3 buckets?"
- "Scan my Lambda functions for tag violations"

**Resource types**: `ec2:instance`, `rds:db`, `s3:bucket`, `lambda:function`, `ecs:service`, `opensearch:domain`

---

### 2. find_untagged_resources

Find resources missing required tags.

**What it does**: Identifies resources with no tags or missing required tags, includes cost estimates and resource age to help prioritize remediation.

**Example prompts**:
- "Find all untagged S3 buckets"
- "Which EC2 instances are missing the CostCenter tag?"
- "Show me untagged resources costing more than $50/month"

---

### 3. validate_resource_tags

Validate specific resources by ARN.

**What it does**: Validates one or more specific resources against the tagging policy, returns detailed violation information.

**Example prompts**:
- "Validate the tags on arn:aws:ec2:us-east-1:123456789:instance/i-abc123"
- "Check if this S3 bucket has valid tags: arn:aws:s3:::my-bucket"

---

### 4. get_cost_attribution_gap

Calculate the financial impact of tagging gaps.

**What it does**: Shows how much cloud spend cannot be allocated to teams/projects due to missing or invalid tags.

**Example prompts**:
- "What's my cost attribution gap?"
- "How much money can't be attributed due to missing tags?"
- "Show me the cost impact of untagged resources by region"

---

### 5. suggest_tags

Get tag suggestions for a resource.

**What it does**: Analyzes patterns like VPC naming, IAM roles, and similar resources to recommend tag values with confidence scores.

**Example prompts**:
- "Suggest tags for arn:aws:ec2:us-east-1:123456789:instance/i-abc123"
- "What tags should I add to this S3 bucket?"

---

### 6. get_tagging_policy

View the current tagging policy.

**What it does**: Returns the complete policy configuration including required tags, optional tags, and validation rules.

**Example prompts**:
- "What tagging policy is configured?"
- "Show me the required tags"
- "What are the allowed values for the Environment tag?"

---

### 7. generate_compliance_report

Generate a comprehensive compliance report.

**What it does**: Creates a detailed report with compliance summary, top violations ranked by count and cost, and actionable recommendations.

**Example prompts**:
- "Generate a compliance report for all my resources"
- "Create a markdown report of tag violations"
- "Give me a summary report with recommendations"

**Output formats**: JSON, CSV, Markdown

---

### 8. get_violation_history

View historical compliance data.

**What it does**: Shows how compliance has changed over time to track progress and measure remediation effectiveness.

**Example prompts**:
- "Show me compliance history for the last 30 days"
- "How has our tag compliance improved this month?"
- "What's the trend in tag violations?"

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
| EC2 | "Check tag compliance for EC2 instances" |
| S3 | "Find S3 buckets missing the DataClassification tag" |
| RDS | "Which RDS databases are missing required tags?" |
| Lambda | "Scan Lambda functions for tag violations" |
| ECS | "Check compliance for ECS services" |
| OpenSearch | "Find untagged OpenSearch domains" |

### Advanced Queries

| Scenario | Example prompt |
|----------|----------------|
| Filter by region | "Check compliance for EC2 instances in us-east-1" |
| Filter by severity | "Show only critical tag violations" |
| Cost threshold | "Find untagged resources costing more than $50/month" |
| Time-based | "Show compliance history for the last 30 days" |
| Specific resource | "Validate tags on arn:aws:s3:::my-bucket" |

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


---

## Appendix: Tool Logic Reference

This appendix documents the internal logic used by each of the 8 MCP tools. Understanding how these tools work can help you interpret results and troubleshoot unexpected behavior.

---

### 1. check_tag_compliance

**Purpose**: Scan resources and calculate a compliance score.

**Logic Flow**:
1. **Caching**: Generates a cache key from query parameters (resource types, filters, severity). Returns cached results if available (1-hour TTL by default). Use `force_refresh=True` to bypass cache.
2. **Resource Scanning**: Fetches resources from AWS for each specified resource type.
3. **Filtering**: Applies region and account filters to narrow results.
4. **Policy Validation**: For each resource, validates tags against the tagging policy:
   - Checks for missing required tags
   - Validates tag values against allowed value lists
   - Validates tag values against regex patterns
5. **Score Calculation**: `Compliance Score = Compliant Resources ÷ Total Resources`
6. **Severity Filtering**: Filters violations by severity if requested (`errors_only`, `warnings_only`, or `all`).

**Key Details**:
- Cache key is a SHA256 hash of normalized query parameters
- Resources without violations are counted as compliant
- Cost attribution gap is the sum of cost impacts from all violations

---

### 2. find_untagged_resources

**Purpose**: Find resources with no tags or missing required tags.

**Logic Flow**:
1. **Resource Fetching**: Fetches all resources of specified types from AWS.
2. **Required Tag Detection**: For each resource, determines which required tags apply based on the `applies_to` field in the policy.
3. **Missing Tag Check**: 
   - If resource has no tags → all required tags are missing
   - If resource has some tags → checks which required tags are absent
4. **Cost Estimation** (only when `include_costs=True`):
   - **EC2/RDS**: Uses actual per-resource costs from AWS Cost Explorer
   - **S3/Lambda/ECS**: Uses service average (service total ÷ resource count) since AWS doesn't provide per-resource granularity
5. **Cost Threshold Filtering**: If `min_cost_threshold` is set, excludes resources below that cost.
6. **Age Calculation**: Calculates resource age in days from creation date.

**Cost Source Types**:
- `actual`: Per-resource cost from Cost Explorer (EC2, RDS)
- `service_average`: Service total divided by resource count (S3, Lambda, ECS)
- `estimated`: Fallback when cost data unavailable

---

### 3. validate_resource_tags

**Purpose**: Validate specific resources by ARN against the tagging policy.

**Logic Flow**:
1. **ARN Parsing**: Extracts service, region, account, and resource ID from each ARN.
   - Format: `arn:aws:service:region:account:resource`
   - S3 buckets have empty region/account fields
2. **Resource Type Mapping**: Maps AWS service to internal resource type:
   - `ec2` + `instance/` → `ec2:instance`
   - `rds` + `db:` → `rds:db`
   - `s3` → `s3:bucket`
   - `lambda` + `function:` → `lambda:function`
   - `ecs` + `service/` → `ecs:service`
3. **Tag Fetching**: Retrieves current tags from AWS for each resource.
4. **Policy Validation**: Validates tags against policy rules:
   - **Missing Required Tag** (Severity: Error)
   - **Invalid Value** - not in allowed values list (Severity: Error)
   - **Invalid Format** - doesn't match regex pattern (Severity: Error)

**Validation Rules Applied**:
- Only required tags that apply to the resource type are checked
- Allowed values are case-sensitive
- Regex patterns use Python's `re.match()` (anchored at start)

---

### 4. get_cost_attribution_gap

**Purpose**: Calculate the financial impact of tagging gaps.

**Logic Flow**:
1. **Resource Fetching**: Fetches all resources of specified types.
2. **Cost Data Retrieval**: Gets costs from AWS Cost Explorer:
   - Per-resource costs (where available)
   - Service-level totals
3. **Cost Mapping**:
   - **EC2/RDS**: Uses actual per-resource costs from Cost Explorer
   - **S3/Lambda/ECS**: Distributes service total evenly among resources (estimate)
4. **Compliance Check**: For each resource, validates tags against policy.
5. **Attribution Calculation**:
   - **Attributable Spend**: Sum of costs for compliant resources
   - **Non-Attributable Spend**: Sum of costs for non-compliant resources
   - **Gap**: Total Spend - Attributable Spend
   - **Gap Percentage**: (Gap ÷ Total Spend) × 100
6. **Breakdown Generation**: Groups results by dimension (resource_type, region, or account).

**Notes for $0 Spend Cases**:
- "No resources found for this type"
- "X resource(s) found but $0 cost reported - may need Cost Allocation Tags or resources are in free tier"
- "All X resource(s) are properly tagged"

---

### 5. suggest_tags

**Purpose**: Suggest tag values for a resource based on patterns and context.

**Three Suggestion Strategies**:

**Strategy 1: Pattern Matching**
Scans resource name, VPC name, IAM role, and ARN for keywords:

| Tag | Patterns Detected |
|-----|-------------------|
| Environment | `prod`, `prd`, `production`, `live`, `main` → production |
|             | `stag`, `stg`, `staging`, `preprod`, `uat` → staging |
|             | `dev`, `develop`, `sandbox` → development |
|             | `test`, `tst`, `qa` → test |
| CostCenter | `eng`, `engineering`, `tech`, `platform`, `devops` → Engineering |
|            | `mkt`, `marketing`, `campaign`, `analytics` → Marketing |
|            | `sales`, `crm`, `revenue` → Sales |
|            | `ops`, `operations`, `support` → Operations |
|            | `fin`, `finance`, `billing`, `payment` → Finance |
| DataClassification | `public`, `cdn`, `static`, `assets` → public |
|                    | `internal`, `private`, `corp` → internal |
|                    | `confidential`, `sensitive`, `pii` → confidential |
|                    | `restricted`, `secret`, `hipaa`, `pci` → restricted |

**Strategy 2: Similar Resource Analysis**
- Finds resources in the same VPC or of the same type
- Counts tag value occurrences
- Suggests the most common value
- Confidence based on consistency ratio and sample size

**Strategy 3: Context Inference**
- **Application**: Extracts from resource name (e.g., `app-name-prod` → `app-name`)
- **Owner**: Infers team from IAM role name (e.g., `platform-team-role` → `platform-team@example.com`)

**Confidence Scores**:
| Source | Confidence |
|--------|------------|
| VPC name | 0.85 |
| IAM role | 0.80 |
| Resource name | 0.75 |
| Resource ARN | 0.65 |
| Similar resources | 0.10-0.95 (varies) |
| Application inference | 0.60 |
| Owner inference | 0.45 |

---

### 6. get_tagging_policy

**Purpose**: Return the current tagging policy configuration.

**Logic Flow**:
1. **Policy Loading**: Reads policy from `policies/tagging_policy.json`.
2. **Validation**: Validates structure using Pydantic models.
3. **Caching**: Policy is cached in memory after first load.

**Policy Structure**:
```json
{
  "required_tags": [
    {
      "name": "Environment",
      "description": "Deployment environment",
      "allowed_values": ["production", "staging", "development"],
      "validation_regex": null,
      "applies_to": ["ec2:instance", "rds:db", "s3:bucket"]
    }
  ],
  "optional_tags": [
    {
      "name": "Project",
      "description": "Project identifier"
    }
  ]
}
```

**Key Fields**:
- `allowed_values`: If set, tag value must be in this list
- `validation_regex`: If set, tag value must match this pattern
- `applies_to`: Resource types this tag applies to (empty = all types)

---

### 7. generate_compliance_report

**Purpose**: Generate a comprehensive compliance report with rankings and recommendations.

**Logic Flow**:
1. **Summary Calculation**: Computes total resources, compliant count, violation count.
2. **Violation Ranking by Count**: Groups violations by tag name, counts occurrences, sorts descending.
3. **Violation Ranking by Cost**: Groups violations by tag name, sums cost impacts, sorts descending.
4. **Recommendation Generation**: Analyzes patterns and generates prioritized recommendations.

**Recommendation Rules**:
| Condition | Priority | Recommendation |
|-----------|----------|----------------|
| Top cost violation > $1,000/month | High | Address missing '[tag]' tags |
| Top count violation > 10 resources | High | Fix widespread '[tag]' violations |
| Compliance score < 50% | High | Implement automated tagging policies |
| Resource type with most violations > 5 | Medium | Focus tagging efforts on [type] resources |
| Cost attribution gap > $5,000/month | High | Reduce cost attribution gap |
| Cost attribution gap > $1,000/month | Medium | Improve cost attribution |
| Compliance score ≥ 90% | Low | Maintain excellent compliance |

**Output Formats**:
- **JSON**: Full structured data
- **CSV**: Multiple sections (summary, violations by count, violations by cost, recommendations)
- **Markdown**: Formatted document with tables and sections

---

### 8. get_violation_history

**Purpose**: Show how compliance has changed over time.

**Logic Flow**:
1. **Data Storage**: Compliance scan results are stored in SQLite database (`compliance_history.db`).
2. **Query Execution**: Retrieves historical data based on `days_back` parameter (1-90 days).
3. **Grouping**: Aggregates data by period:
   - **Day**: `DATE(timestamp)`
   - **Week**: `DATE(timestamp, 'weekday 0', '-6 days')` (week starting Monday)
   - **Month**: `DATE(timestamp, 'start of month')`
4. **Aggregation**: For each period, calculates:
   - Average compliance score
   - Sum of total resources
   - Sum of compliant resources
   - Sum of violation count
5. **Trend Analysis**: Compares earliest and latest scores:
   - `latest > earliest` → Improving
   - `latest < earliest` → Declining
   - `latest = earliest` → Stable

**Database Schema**:
```sql
CREATE TABLE compliance_scans (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    compliance_score REAL NOT NULL,
    total_resources INTEGER NOT NULL,
    compliant_resources INTEGER NOT NULL,
    violation_count INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
```

**Note**: History is populated automatically when compliance scans are run. If no scans have been stored, history will be empty.

---

