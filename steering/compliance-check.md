# Compliance Check Workflow

Use this workflow when the user wants to assess tag compliance, scan resources, find violations, or generate reports.

## Step 1: Read the tagging policy

Always start by calling `get_tagging_policy`. This returns:
- Required and optional tags with their validation rules
- `all_applicable_resource_types` — a deduplicated list of every resource type in scope

Use this list for all subsequent scanning calls. Never guess resource types.

## Step 2: Scan in batches

Call `check_tag_compliance` with batches of 4-6 resource types from the policy:

```
Batch 1: ["ec2:instance", "s3:bucket", "rds:db", "lambda:function"]
Batch 2: ["ecs:service", "dynamodb:table", "opensearch:domain", "sns:topic"]
Batch 3: ... (remaining types from policy)
```

After each batch completes, aggregate the results. Present the combined compliance score.

## Step 3: Check data quality

Every response has a `data_quality` field:
- `"complete"` — all regions scanned, safe to present as account-wide
- `"partial"` — some regions failed; you MUST tell the user which regions are missing and that numbers are incomplete

Never present partial results as if they are complete.

## Step 4: Present results

Summarize for the user:
- Overall compliance score (percentage)
- Total resources scanned vs compliant
- Top violations by count
- Cost attribution gap (if available)
- Any data quality warnings

## Finding untagged resources

When the user asks specifically about untagged or missing-tag resources, use `find_untagged_resources` instead of `check_tag_compliance`:

- Pass resource types from `get_tagging_policy` (in batches of 4-6)
- Set `include_costs=true` only when the user asks about cost impact
- Use `min_cost_threshold` to filter by monthly cost when requested

## Validating specific resources

When the user provides specific ARNs, use `validate_resource_tags`:

- Accepts up to 100 ARNs per call
- Returns per-resource violation details
- No need to call `get_tagging_policy` first (the tool loads it internally)

## Generating reports

Use `generate_compliance_report` when the user wants a formatted report:

- Supports `"json"`, `"csv"`, and `"markdown"` formats
- Follows the same batch scanning rules
- Includes recommendations when `include_recommendations=true` (default)

## Exporting violations

Use `export_violations_csv` for spreadsheet-ready output:

- Default columns: resource_id, resource_type, region, violation_type, tag_name, severity
- Can include additional columns: current_value, allowed_values, cost_impact, arn

## Viewing history

Use `get_violation_history` for trend analysis:

- `days_back`: 1-90 (default 30)
- `group_by`: "day", "week", or "month"
- Requires previous scans stored with `store_snapshot=true`

## Detecting drift

Use `detect_tag_drift` when the user asks about unexpected changes:

- Compares current tags against policy expectations
- Classifies by severity: critical (required tag removed), warning (value changed), info (optional change)
- `lookback_days`: 1-90 (default 7)
