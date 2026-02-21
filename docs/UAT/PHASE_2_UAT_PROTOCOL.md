# Phase 2 UAT Protocol — FinOps Tag Compliance MCP Server

**Version**: 2.1
**Date**: February 20, 2026
**Target**: Production ECS Fargate at `https://mcp.optimnow.io`
**Scope**: All 14 MCP tools + ECS infrastructure + Phase 2.5 migration validation

---

## How to Use This Protocol

This protocol is designed for **two actors**:

| Actor | Role |
|-------|------|
| **Human (Jean)** | Asks Claude natural language questions via Claude Desktop. Signs off on acceptance criteria. |
| **Claude** | Interprets questions, calls the right MCP tools, and reports results. Also runs automated HTTP tests. |

**Two testing modes:**

1. **Natural Language UAT (Section NL)** — Jean asks Claude plain English questions via Claude Desktop. Claude picks the right tool, calls it, and reports back. This validates the full end-to-end experience as a real user would use it.
2. **Automated API Tests (Sections A-F)** — Claude runs structured HTTP tests against production for schema validation, math consistency, and edge cases.

**Workflow:**
1. Jean runs through the Natural Language prompts (Section NL) via Claude Desktop
2. Claude runs automated tests (Sections A-F) via HTTP API calls
3. Both sign off on the Go/No-Go checklist (Section G)

---

## Test Environment

| Setting | Value |
|---------|-------|
| Server URL | `https://mcp.optimnow.io` |
| API Key | `TSvlygVknr1XhJ4UUEz6VEW5lrvjgDY6` |
| Transport | HTTP POST to `/mcp/tools/call` |
| Auth Header | `Authorization: Bearer <API_KEY>` |
| AWS Account | 382598791951 |
| Infrastructure | ECS Fargate (Phase 2.5) |

**HTTP call format (for Claude):**
```bash
python -c "
import requests, json
r = requests.post('https://mcp.optimnow.io/mcp/tools/call',
    headers={'Content-Type':'application/json','Authorization':'Bearer API_KEY'},
    json={'name':'TOOL_NAME','arguments':{...}}, timeout=120)
print(json.dumps(r.json(), indent=2))
"
```

---

## NL. Natural Language UAT (30 prompts)

These are the prompts Jean asks Claude via Claude Desktop. Claude picks the right MCP tool(s), calls them, and reports back. Jean validates the answer makes sense.

**How to run**: Open Claude Desktop connected to `tagging-mcp-prod`. Ask each prompt below. Check the "Accept" column when the response is sensible, correct, and uses the right tool.

### Compliance Scanning (Tools 1, 7, 8)

| ID | Prompt to Ask Claude | Expected Tool(s) | Accept Criteria |
|----|---------------------|-------------------|-----------------|
| NL.1 | "What's my overall tag compliance score?" | `check_tag_compliance` | Returns a score (0-100%), resource count, and violation summary |
| NL.2 | "How compliant are my EC2 instances and S3 buckets with our tagging policy?" | `check_tag_compliance` | Scans both types, shows per-type breakdown |
| NL.3 | "Show me only the critical tagging errors, not warnings" | `check_tag_compliance` (severity: errors_only) | Only error-severity violations returned |
| NL.4 | "Check compliance across all my AWS resources" | `check_tag_compliance` (all) | Scans all resource types, total_resources matches sum of individual types |
| NL.5 | "Generate a compliance report in markdown format for my EC2 instances" | `generate_compliance_report` | Returns markdown with headings, tables, score |
| NL.6 | "Has my compliance improved over the last 30 days?" | `get_violation_history` | Returns trend data with timestamps and scores |

### Finding Problems (Tools 2, 3, 12)

| ID | Prompt to Ask Claude | Expected Tool(s) | Accept Criteria |
|----|---------------------|-------------------|-----------------|
| NL.7 | "Which resources are missing required tags?" | `find_untagged_resources` | Returns list with resource IDs, types, and missing tags |
| NL.8 | "Find untagged EC2 instances and tell me how much they cost" | `find_untagged_resources` (include_costs: true) | Includes cost estimates per resource |
| NL.9 | "Check the tags on my S3 bucket finops-mcp-config-prod" | `validate_resource_tags` | Validates that specific bucket, shows compliant/non-compliant and tag details |
| NL.10 | "Have any of my resource tags changed unexpectedly in the last 2 weeks?" | `detect_tag_drift` | Returns drift analysis with lookback_days=14, shows added/removed/changed |
| NL.11 | "Detect tag drift on my EC2 instances over the past month" | `detect_tag_drift` | Filters to ec2:instance, 30-day lookback |

### Cost Impact (Tool 4)

| ID | Prompt to Ask Claude | Expected Tool(s) | Accept Criteria |
|----|---------------------|-------------------|-----------------|
| NL.12 | "How much of my cloud spend can't be attributed to a team because of missing tags?" | `get_cost_attribution_gap` | Returns total spend, attributable spend, gap amount and percentage |
| NL.13 | "What's the cost attribution gap broken down by resource type?" | `get_cost_attribution_gap` (group_by: resource_type) | Shows per-type gap breakdown |

### Tag Suggestions (Tool 5)

| ID | Prompt to Ask Claude | Expected Tool(s) | Accept Criteria |
|----|---------------------|-------------------|-----------------|
| NL.14 | "What tags should I add to my S3 bucket finops-mcp-config-prod?" | `suggest_tags` | Returns suggestions with tag keys, values, and confidence scores |
| NL.15 | "Suggest tags for one of my non-compliant EC2 instances" | `suggest_tags` (may call find_untagged first) | Provides concrete tag suggestions for a real instance |

### Policy Management (Tools 6, 14)

| ID | Prompt to Ask Claude | Expected Tool(s) | Accept Criteria |
|----|---------------------|-------------------|-----------------|
| NL.16 | "What's our current tagging policy? What tags are required?" | `get_tagging_policy` | Lists required tags (CostCenter, Owner, Environment) with allowed values |
| NL.17 | "Import our AWS Organizations tag policy" | `import_aws_tag_policy` | Lists available policies or imports from AWS Orgs |
| NL.18 | "Refresh the tagging policy from AWS Organizations policy p-95ouootqj0" | `import_aws_tag_policy` (policy_id) | Imports specific policy, shows required tags from AWS Orgs |

### Remediation & Automation (Tools 9, 10, 11)

| ID | Prompt to Ask Claude | Expected Tool(s) | Accept Criteria |
|----|---------------------|-------------------|-----------------|
| NL.19 | "Generate a Cloud Custodian policy to enforce tags on my EC2 instances" | `generate_custodian_policy` | Returns valid YAML with Custodian policy for EC2 |
| NL.20 | "Create a Custodian dry-run policy for EC2 and S3 so I can preview what would be flagged" | `generate_custodian_policy` (dry_run: true) | All policies use notify action, not tag action |
| NL.21 | "Generate an OpenOps workflow to auto-tag non-compliant resources" | `generate_openops_workflow` (auto_tag) | Returns workflow YAML with auto-tag remediation steps |
| NL.22 | "Create an OpenOps notification workflow for non-compliant EC2 instances" | `generate_openops_workflow` (notify) | Returns workflow with notify strategy |
| NL.23 | "Set up a daily compliance audit at 9 AM" | `schedule_compliance_audit` | Returns schedule ID, cron expression, next run time |
| NL.24 | "Schedule a weekly compliance check for Monday at 2:30 PM Eastern time" | `schedule_compliance_audit` (weekly, US/Eastern) | Shows weekly schedule with correct timezone |

### Export (Tool 13)

| ID | Prompt to Ask Claude | Expected Tool(s) | Accept Criteria |
|----|---------------------|-------------------|-----------------|
| NL.25 | "Export all my tagging violations as a CSV" | `export_violations_csv` | Returns CSV data with headers, row count, column count |
| NL.26 | "Give me a CSV of EC2 instance tagging violations" | `export_violations_csv` (ec2:instance) | CSV filtered to EC2 only |

### Multi-Step / Conversational

| ID | Prompt to Ask Claude | Expected Tool(s) | Accept Criteria |
|----|---------------------|-------------------|-----------------|
| NL.27 | "How bad is our tagging situation? Give me the full picture." | Multiple: `check_tag_compliance`, `get_cost_attribution_gap`, `find_untagged_resources` | Combines compliance score, cost gap, and untagged resource count into a coherent summary |
| NL.28 | "Find my worst-tagged resources and suggest how to fix them" | `find_untagged_resources` then `suggest_tags` | Identifies non-compliant resources, then provides tag suggestions for them |
| NL.29 | "Save a compliance snapshot and then show me the trend" | `check_tag_compliance` (store_snapshot: true) then `get_violation_history` | Stores result, then shows history including the new data point |
| NL.30 | "Generate a remediation plan: find what's wrong, create Custodian policies, and export violations" | `check_tag_compliance`, `generate_custodian_policy`, `export_violations_csv` | Orchestrates multiple tools into a coherent remediation workflow |

### NL Sign-Off

| Criteria | Pass/Fail |
|----------|-----------|
| Claude correctly identified the right tool for 25+ of 30 prompts | |
| Responses were factually correct (scores, counts, resources match reality) | |
| Multi-step prompts produced coherent, combined answers | |
| No crashes, timeouts, or garbled responses | |

---

## A. Infrastructure Health (4 tests)

Validates ECS Fargate deployment is healthy before running tool tests.

| ID | Test | Method | Pass Criteria |
|----|------|--------|---------------|
| A.1 | Health endpoint | `GET /health` | HTTP 200, `status=healthy`, `redis_connected=true`, `sqlite_connected=true` |
| A.2 | Server version | `GET /health` | Response includes server metadata (tool count, uptime) |
| A.3 | ECS task running | `aws ecs describe-services` | `runningCount >= 1`, `desiredCount >= 1` |
| A.4 | Target group healthy | `aws elbv2 describe-target-health` | At least 1 target in `healthy` state |

---

## B. Phase 1 Tools — Regression (8 tools, 24 tests)

Ensures all original tools still work correctly after Phase 2 changes and ECS migration.

### Tool 1: check_tag_compliance

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| B1.1 | Basic scan | `resource_types: ["ec2:instance", "s3:bucket"]` | `compliance_score` is 0.0-1.0, `total_resources >= 0`, `violations` is array, `scan_timestamp` exists |
| B1.2 | Region metadata | `resource_types: ["ec2:instance"]` | `region_metadata.total_regions > 0`, `successful_regions` is array |
| B1.3 | Severity filter | `resource_types: ["ec2:instance"], severity: "errors_only"` | All violations have `severity == "error"` |
| B1.4 | Math consistency | Same as B1.1 | `compliant_resources + non_compliant == total_resources` (when non_compliant is present) |
| B1.5 | Stored in history | `resource_types: ["s3:bucket"], store_snapshot: true` | Subsequent `get_violation_history` shows new data point |

### Tool 2: find_untagged_resources

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| B2.1 | Basic scan | `resource_types: ["ec2:instance", "s3:bucket"]` | `total_untagged >= 0`, `resources` is array, `scan_timestamp` exists |
| B2.2 | With costs | `resource_types: ["ec2:instance"], include_costs: true` | `total_monthly_cost` is number >= 0 |
| B2.3 | Resource structure | From B2.1 results | Each resource has: `resource_id`, `resource_type`, `region`, `arn`, `current_tags` (object), `missing_required_tags` (array) |

### Tool 3: validate_resource_tags

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| B3.1 | Valid ARN | `resource_arns: ["arn:aws:s3:::finops-mcp-config-prod"]` | `total_resources >= 1`, `results` is array, `validation_timestamp` exists |
| B3.2 | Result structure | From B3.1 | Each result has: `resource_arn`, `resource_type`, `is_compliant` (bool), `violations` (array), `current_tags` (object) |
| B3.3 | Math consistency | From B3.1 | `total_resources == compliant_resources + non_compliant_resources` |

### Tool 4: get_cost_attribution_gap

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| B4.1 | Basic gap | `resource_types: ["ec2:instance", "s3:bucket"]` | `total_spend >= 0`, `attributable_spend >= 0`, `attribution_gap >= 0`, `attribution_gap_percentage` 0-100 |
| B4.2 | Math consistency | From B4.1 | `abs(attribution_gap - (total_spend - attributable_spend)) < 0.01` |
| B4.3 | Group by | `resource_types: ["ec2:instance", "s3:bucket"], group_by: "resource_type"` | `breakdown` is object (if present) |

### Tool 5: suggest_tags

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| B5.1 | S3 bucket | `resource_arn: "arn:aws:s3:::finops-mcp-config-prod"` | `resource_arn` and `resource_type` exist, `suggestions` is array, `current_tags` is object |
| B5.2 | Suggestion structure | From B5.1 | Each suggestion has: `tag_key`, `suggested_value`, `confidence` (0.0-1.0) |

### Tool 6: get_tagging_policy

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| B6.1 | Returns policy | `{}` (no args) | `required_tags` is non-empty array, `optional_tags` is array |
| B6.2 | Known tags | From B6.1 | Required tag names include `Environment`, `Owner`, `CostCenter` (from AWS Organizations policy) |
| B6.3 | Tag structure | From B6.1 | Each tag has `name` and `description` fields |

### Tool 7: generate_compliance_report

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| B7.1 | JSON format | `resource_types: ["ec2:instance"], format: "json"` | `format == "json"`, `formatted_output` exists |
| B7.2 | Markdown format | `resource_types: ["ec2:instance"], format: "markdown"` | `format == "markdown"`, `formatted_output` contains markdown syntax |
| B7.3 | CSV format | `resource_types: ["ec2:instance"], format: "csv"` | `format == "csv"`, `formatted_output` exists |

### Tool 8: get_violation_history

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| B8.1 | Basic history | `days_back: 30, group_by: "day"` | `days_back` is number, `history` is array |
| B8.2 | Data point structure | From B8.1 (if data exists) | Each point has `timestamp` and `compliance_score` (0.0-1.0) |

---

## C. Phase 2 Tools — New Functionality (6 tools, 28 tests)

### Tool 9: generate_custodian_policy

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| C9.1 | Basic generation | `resource_types: ["ec2:instance", "s3:bucket"]` | `total_policies >= 1`, `policies` is array, `combined_yaml` is string, `resource_types_covered` is array, `target_tags` is array |
| C9.2 | Policy structure | From C9.1 | Each policy has: `name`, `resource_type`, `yaml_content`, `description`, `filter_count` (number), `action_type` |
| C9.3 | Dry run = true | `resource_types: ["ec2:instance"], dry_run: true` | `dry_run == true`, all policies have `action_type == "notify"` |
| C9.4 | Dry run = false | `resource_types: ["ec2:instance"], dry_run: false` | `dry_run == false`, policies have `action_type != "notify"` (e.g., "tag") |
| C9.5 | Consistency | From C9.1 | `total_policies == len(policies)` |
| C9.6 | YAML validity | From C9.1 | `combined_yaml` parses as valid YAML |

### Tool 10: generate_openops_workflow

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| C10.1 | Notify strategy | `resource_types: ["ec2:instance"], remediation_strategy: "notify"` | `workflow_name` is non-empty string, `yaml_content` is non-empty string, `remediation_strategy == "notify"` |
| C10.2 | Report strategy | `resource_types: ["ec2:instance"], remediation_strategy: "report"` | `remediation_strategy == "report"` |
| C10.3 | Auto-tag strategy | `resource_types: ["ec2:instance", "s3:bucket"], remediation_strategy: "auto_tag"` | `remediation_strategy == "auto_tag"`, `resource_types` in response |
| C10.4 | Step structure | From C10.1 | `steps` is array, `step_count` is number, each step has `name` and `action` |
| C10.5 | Consistency | From C10.1 | `step_count == len(steps)` |

### Tool 11: schedule_compliance_audit

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| C11.1 | Daily schedule | `schedule: "daily", time: "09:00"` | `schedule_id` starts with `audit-sched-`, `status == "created"`, `schedule_type == "daily"`, `time == "09:00"` |
| C11.2 | Weekly schedule | `schedule: "weekly", time: "14:30", timezone_str: "US/Eastern"` | `schedule_type == "weekly"`, `timezone == "US/Eastern"`, `cron_expression` is non-empty string |
| C11.3 | Monthly schedule | `schedule: "monthly", time: "08:00"` | `schedule_type == "monthly"`, `cron_expression` contains `1 *` (day 1) |
| C11.4 | Next run | From C11.1 | `next_run` is non-empty ISO 8601 string |
| C11.5 | Message | From C11.1 | `message` is non-empty human-readable string |

### Tool 12: detect_tag_drift

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| C12.1 | Basic detection | `{}` (defaults) | `drift_detected` is array, `total_drifts >= 0`, `resources_analyzed >= 0`, `lookback_days` is 1-90 |
| C12.2 | With resource filter | `resource_types: ["ec2:instance"], lookback_days: 14` | `lookback_days == 14`, `scan_timestamp` exists |
| C12.3 | Summary structure | From C12.1 | `summary` object has `added`, `removed`, `changed` (all numbers) |
| C12.4 | Consistency | From C12.1 | `total_drifts == len(drift_detected)` |
| C12.5 | Drift entry structure | From C12.1 (if drifts exist) | Each drift has: `resource_arn`, `resource_id`, `resource_type`, `tag_key`, `drift_type` (in: added/removed/changed), `severity` (in: critical/warning/info) |

### Tool 13: export_violations_csv

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| C13.1 | Basic export | `resource_types: ["ec2:instance"]` | `csv_data` is string, `row_count >= 0`, `column_count > 0` |
| C13.2 | Metadata | From C13.1 | `columns` is non-empty array, `format == "csv"`, `filters_applied` is object, `export_timestamp` exists |
| C13.3 | Header matches | From C13.1 | First line of `csv_data` contains all values in `columns` array |
| C13.4 | Consistency | From C13.1 | `column_count == len(columns)` |

### Tool 14: import_aws_tag_policy

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| C14.1 | List policies | `{}` (no args) | `status` is string (either "listed" or "error"), `message` is non-empty string |
| C14.2 | Timestamp | From C14.1 | `conversion_timestamp` exists |
| C14.3 | Structure on list | From C14.1 | If `status == "listed"`: `available_policies` is array containing `p-95ouootqj0`. If `status == "error"`: `message` explains the issue. |
| C14.4 | Invalid policy ID | `policy_id: "p-invalid-does-not-exist"` | Returns JSON (does not crash), has `error` or `status` field |
| C14.5 | Import by ID | `policy_id: "p-95ouootqj0", save_to_file: true` | `status == "saved"`, `policy` has `required_tags` array |
| C14.6 | Imported tags match AWS Orgs | From C14.5 | `policy.required_tags` names include `CostCenter`, `Owner`, `Environment` (matching the AWS Orgs policy) |
| C14.7 | Policy refresh workflow | After C14.5: call `get_tagging_policy` | Returned policy reflects AWS Orgs tags (CostCenter, Owner, Environment) |
| C14.8 | Auto-import on startup | Delete `/mnt/efs/tagging_policy.json` via ECS Exec, restart task, check logs | Container logs show auto-policy detection, policy file recreated on EFS |

---

## D. Error Handling & Edge Cases (10 tests)

| ID | Test | Input | Pass Criteria |
|----|------|-------|---------------|
| D.1 | Invalid tool name | `name: "nonexistent_tool"` | Returns JSON error, does not crash |
| D.2 | Invalid severity | `check_tag_compliance` with `severity: "INVALID"` | Returns JSON (handles gracefully) |
| D.3 | Empty resource_types | `check_tag_compliance` with `resource_types: []` | Returns JSON (handles gracefully) |
| D.4 | Invalid ARN format | `validate_resource_tags` with `resource_arns: ["not-an-arn"]` | Returns JSON (validation error or empty results) |
| D.5 | Empty Custodian types | `generate_custodian_policy` with `resource_types: []` | Returns JSON (handles gracefully) |
| D.6 | Invalid lookback | `detect_tag_drift` with `lookback_days: 999` | Returns JSON (validation error or clamps to valid range) |
| D.7 | Invalid schedule | `schedule_compliance_audit` with `schedule: "hourly"` | Returns JSON (validation error) |
| D.8 | Invalid time format | `schedule_compliance_audit` with `time: "25:99"` | Returns JSON (validation error) |
| D.9 | Very large scan | `check_tag_compliance` with `resource_types: ["all"]` | Completes within 120s, returns valid JSON |
| D.10 | Concurrent requests | Two simultaneous `get_tagging_policy` calls | Both return identical valid results |

---

## E. Performance (6 tests)

| ID | Test | Tool | Pass Criteria |
|----|------|------|---------------|
| E.1 | Policy retrieval | `get_tagging_policy` | < 3 seconds (no AWS calls) |
| E.2 | History retrieval | `get_violation_history` | < 3 seconds (local DB only) |
| E.3 | Schedule creation | `schedule_compliance_audit` | < 3 seconds (no AWS calls) |
| E.4 | Custodian generation | `generate_custodian_policy` | < 5 seconds (policy-based only) |
| E.5 | Single-type scan | `check_tag_compliance` with 1 type | < 30 seconds |
| E.6 | Multi-type scan | `check_tag_compliance` with 3 types | < 60 seconds |

---

## F. ECS Fargate Infrastructure (5 tests)

Validates the Phase 2.5 ECS migration is stable.

| ID | Test | Method | Pass Criteria |
|----|------|--------|---------------|
| F.1 | Redis sidecar | Health endpoint | `redis_connected == true` |
| F.2 | EFS persistence | Stop/start task, check history | `get_violation_history` returns data from before restart (requires stored snapshot) |
| F.3 | ALB routing | HTTPS request | Response comes from Fargate target group (not EC2) |
| F.4 | TLS certificate | `curl -v https://mcp.optimnow.io` | Valid TLS certificate, no warnings |
| F.5 | EC2 removed | `aws cloudformation describe-stack-resources` | No `MCPServerInstance` resource in stack (removed in Phase 2.5 cleanup) |

---

## G. Go/No-Go Checklist

### Natural Language UAT

| Criteria | Pass/Fail |
|----------|-----------|
| Claude picks the right tool for 25+ of 30 prompts | |
| Responses are factually correct (match actual AWS data) | |
| Multi-step prompts produce coherent combined answers | |
| No crashes, timeouts, or garbled output | |

### Phase 1 Regression

| Criteria | Pass/Fail |
|----------|-----------|
| All 8 Phase 1 tools return valid JSON with expected schemas | |
| Math consistency checks pass (compliance counts, cost gap arithmetic) | |
| Multi-region metadata present in compliance results | |
| No field name or type changes from Phase 1 schemas | |

### Phase 2 New Tools

| Tool | Criteria | Pass/Fail |
|------|----------|-----------|
| generate_custodian_policy | Valid YAML; dry_run flag respected; total_policies consistent | |
| generate_openops_workflow | All 3 strategies work; step_count consistent; YAML present | |
| schedule_compliance_audit | Schedule ID generated; cron valid; next_run in future | |
| detect_tag_drift | Drifts detected or empty; summary structure valid; total consistent | |
| export_violations_csv | Valid CSV; header matches columns; column_count consistent | |
| import_aws_tag_policy | Imports from AWS Orgs; tags match source; refresh workflow works; auto-import on startup | |

### Infrastructure (Phase 2.5)

| Criteria | Pass/Fail |
|----------|-----------|
| ECS Fargate task running and healthy | |
| Redis sidecar connected | |
| EFS persistence verified | |
| TLS/HTTPS working | |
| EC2 instance removed from stack | |

### Error Handling & Performance

| Criteria | Pass/Fail |
|----------|-----------|
| All error/edge case tests return JSON (no crashes) | |
| Local-only tools complete in < 5s | |
| AWS-calling tools complete in < 60s | |

### Overall Verdict

| | |
|---|---|
| **Total tests** | 107 (30 NL + 77 automated) |
| **Passed** | ___ / 107 |
| **Failed** | ___ / 107 |
| **Skipped** | ___ / 107 |
| **Decision** | ACCEPT / REJECT |
| **Signed off by** | |
| **Date** | |

---

## H. Promptfoo Automated Regression (Addendum)

In addition to the above protocol, run the promptfoo regression suite which validates 55 test cases (34 Phase 1 + 21 Phase 2) with structural assertions:

```bash
cd tests/regression
# Set env vars for production target
export MCP_SERVER_URL=https://mcp.optimnow.io
export MCP_API_KEY=TSvlygVknr1XhJ4UUEz6VEW5lrvjgDY6
export MCP_TIMEOUT=120

npx promptfoo@latest eval
npx promptfoo@latest view  # Open results in browser
```

**Pass criteria**: 55/55 tests pass (100%).

---

## I. Tests Previously Run

For reference, here is what was tested **before this protocol was created**:

| When | What | Result |
|------|------|--------|
| Phase 2.5 migration (Feb 19) | `GET /health` on ECS | 200 OK, redis=true, sqlite=true |
| Phase 2.5 migration (Feb 19) | `get_tagging_policy` on ECS | 200 OK, 3 required tags |
| Phase 2.5 migration (Feb 19) | `check_tag_compliance` for s3:bucket on ECS | 200 OK, score 4.8%, 1/21 compliant |
| Phase 2.5 migration (Feb 19) | `detect_tag_drift` on ECS | 200 OK |
| Phase 2 UAT Round 1 (Feb 9) | Tools 9-14 basic smoke tests | All returned valid JSON; 3 bugs found and fixed (tools 10, 11, 14) |
| Phase 1 regression (ongoing) | 34 promptfoo test cases | Last known: all passing |
| Unit tests (local) | `python run_tests.py --unit` | 1224 collected, 1 import error (moto not installed) |

**What has NOT been tested yet:**
- Full 73-test protocol against production ECS
- Performance under load
- EFS persistence across task restarts
- Math consistency assertions on live data
- Error handling edge cases on production
- Phase 2 tools regression via promptfoo (21 new tests exist but not run against prod)
