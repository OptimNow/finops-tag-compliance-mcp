# Cost Attribution Workflow

Use this workflow when the user asks about the financial impact of tagging gaps, unattributable spend, or cost allocation.

## What is the cost attribution gap?

The cost attribution gap is the dollar amount of cloud spend that cannot be allocated to teams, projects, or cost centers because resources are missing required tags. This directly impacts FinOps showback/chargeback processes.

## Step 1: Read the tagging policy

Call `get_tagging_policy` to identify which resource types are in scope. Focus on cost-generating resource types for this workflow.

## Step 2: Scan in small batches

`get_cost_attribution_gap` is the **slowest tool** (3-5 minutes for many types). Always scan in batches of **3-4 cost-generating resource types**:

```
Batch 1: ["ec2:instance", "rds:db", "lambda:function"]
Batch 2: ["ecs:service", "opensearch:domain", "dynamodb:table"]
Batch 3: ... (remaining cost-generating types)
```

Never use `["all"]` for cost attribution — it will almost certainly timeout.

## Step 3: Interpret results

Each response includes:
- `total_spend` — total cloud spend for the scanned resources
- `attributable_spend` — spend on resources with valid required tags
- `attribution_gap` — the dollar gap (total minus attributable)
- `attribution_gap_percentage` — the gap as a percentage
- `breakdown` — optional grouping by resource_type, region, or account

## Step 4: Report accurately

- If `data_quality.status` is `"partial"`, clearly state which regions or resource types are missing
- Never fabricate dollar amounts for failed regions
- Present the gap as a range if data is incomplete (e.g., "at least $X based on Y of Z regions")

## Optional parameters

- `time_period`: `{"Start": "2026-01-01", "End": "2026-02-01"}` — defaults to last 30 days
- `group_by`: `"resource_type"`, `"region"`, or `"account"` — adds breakdown by dimension
- `filters`: `{"region": "us-east-1"}` — restrict to specific region or account

## Combining with compliance data

For a complete picture, pair cost attribution with compliance checking:

1. `get_cost_attribution_gap` — how much spend is unattributable
2. `find_untagged_resources` with `include_costs=true` — which specific resources are causing the gap
3. `suggest_tags` on the highest-cost untagged resources — get tag recommendations

This gives the user both the aggregate financial impact and actionable per-resource remediation steps.
