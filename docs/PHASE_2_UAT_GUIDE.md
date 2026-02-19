# Phase 2 UAT Guide -- FinOps Tag Compliance MCP Server

**Version**: 1.0
**Date**: February 2026
**Owner**: Jean Latiere (FinOps Engineer)
**Status**: Ready for UAT 1

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [UAT Round 1: Functional Validation](#3-uat-round-1-functional-validation)
   - [Phase 1 Regression Checks (Tools 1-8)](#31-phase-1-regression-checks-tools-1-8)
   - [Phase 2.1: Remediation Script Generation (Tools 9-10)](#32-phase-21-remediation-script-generation-tools-9-10)
   - [Phase 2.2: Compliance Tools (Tools 11-12)](#33-phase-22-compliance-tools-tools-11-12)
   - [Phase 2.3: Export and Import (Tools 13-14)](#34-phase-23-export-and-import-tools-13-14)
   - [Phase 2.4: Auto-Policy and Scheduler](#35-phase-24-auto-policy-and-scheduler)
4. [UAT Round 2: Non-Regression Testing with promptfoo](#4-uat-round-2-non-regression-testing-with-promptfoo)
5. [Acceptance Criteria](#5-acceptance-criteria)
6. [Known Limitations](#6-known-limitations)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Overview

Phase 2 adds **6 new MCP tools** (bringing the total from 8 to 14), plus server-side automation features:

| # | Tool Name | Sub-Phase | Purpose |
|---|-----------|-----------|---------|
| 9 | `generate_custodian_policy` | 2.1 | Generate Cloud Custodian YAML policies from the tagging policy |
| 10 | `generate_openops_workflow` | 2.1 | Generate OpenOps automation workflows for tag remediation |
| 11 | `schedule_compliance_audit` | 2.2 | Create recurring compliance audit schedule configurations |
| 12 | `detect_tag_drift` | 2.2 | Detect unexpected tag changes across resources |
| 13 | `export_violations_csv` | 2.3 | Export compliance violations as CSV data |
| 14 | `import_aws_tag_policy` | 2.3 | Import AWS Organizations tag policies at runtime |

**Server-side features** (Phase 2.4):
- Automatic policy detection on startup (no policy file needed)
- Daily compliance snapshot scheduler (APScheduler)

**What this UAT validates:**
- All 6 new tools return correct results against real AWS resources
- All 8 Phase 1 tools continue to work (no regressions)
- Server-side features (auto-policy, scheduler) function correctly
- Automated regression test suite passes 100%

---

## 2. Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.10+ | MCP server runtime |
| Node.js | 18+ | promptfoo regression tests |
| Git | Any recent | Pull latest code |
| AWS CLI | v2 | AWS credential configuration |

### AWS Configuration

1. **AWS credentials must be configured** with the correct profile:
   ```bash
   aws sts get-caller-identity
   ```
   This should return the AWS account you want to scan.

2. **Required IAM permissions** (read-only):
   - `ec2:DescribeInstances`, `ec2:DescribeTags`, `ec2:DescribeRegions`
   - `rds:DescribeDBInstances`, `rds:ListTagsForResource`
   - `s3:ListAllMyBuckets`, `s3:GetBucketTagging`
   - `lambda:ListFunctions`, `lambda:ListTags`
   - `ecs:ListServices`, `ecs:ListTagsForResource`
   - `ce:GetCostAndUsage` (Cost Explorer)
   - `tag:GetResources`, `tag:GetTagKeys`, `tag:GetTagValues`

3. **For Tool 14 (import_aws_tag_policy)** -- additional permissions:
   - `organizations:ListPolicies`
   - `organizations:DescribePolicy`
   - These are only needed if your account has AWS Organizations tag policies.

### Environment Setup

1. **Pull the latest code:**
   ```bash
   cd C:\Users\jlati\Documents\GitHub\finops-tag-compliance-mcp
   git checkout phase-2
   git pull
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify the `.env` file** exists and contains at minimum:
   ```
   AWS_REGION=us-east-1
   POLICY_PATH=policies/tagging_policy.json
   ```

4. **Verify the tagging policy file** exists:
   ```bash
   python -c "import json; print(json.load(open('policies/tagging_policy.json'))['required_tags'][0]['name'])"
   ```
   Expected output: `Environment` (or the first required tag in your policy).

### Choose Your Testing Transport

You can test via **either** transport. The stdio transport is recommended for UAT 1.

**Option A -- stdio (MCP Inspector):**
```bash
npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server
```
This opens a web UI at `http://localhost:5173` where you can invoke tools directly.

**Option B -- HTTP (run_server.py):**
```bash
python run_server.py
```
Then send POST requests to `http://localhost:8080/mcp/tools/call`.

**Option C -- Claude Desktop:**
Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "tagging-mcp-local": {
      "command": "python",
      "args": ["-m", "mcp_server.stdio_server"],
      "cwd": "C:\\Users\\jlati\\Documents\\GitHub\\finops-tag-compliance-mcp"
    }
  }
}
```
Then ask Claude to call each tool naturally.

---

## 3. UAT Round 1: Functional Validation

This section is organized by sub-phase. For each tool, you will find:
- **What to test** -- a brief description of the test
- **How to test** -- exact JSON to send via MCP Inspector or curl
- **Expected result** -- what success looks like
- **Edge cases** -- error scenarios to try

### How to Send Tool Calls

**MCP Inspector**: Paste the JSON into the "Arguments" field and click "Call Tool".

**curl (HTTP transport)**:
```bash
curl -s -X POST http://localhost:8080/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "TOOL_NAME", "arguments": { ... }}' | python -m json.tool
```

---

### 3.1 Phase 1 Regression Checks (Tools 1-8)

Before testing new tools, verify that all Phase 1 tools still work. Run each of these and confirm the output structure matches expectations.

**Tool 1: check_tag_compliance**
```json
{"name": "check_tag_compliance", "arguments": {"resource_types": ["ec2:instance", "s3:bucket"], "severity": "all"}}
```
Expected: JSON with `compliance_score` (0-1), `total_resources` (>= 0), `violations` array, `scan_timestamp`.

**Tool 2: find_untagged_resources**
```json
{"name": "find_untagged_resources", "arguments": {"resource_types": ["ec2:instance"]}}
```
Expected: JSON with `total_untagged`, `resources` array, `scan_timestamp`.

**Tool 3: validate_resource_tags**
```json
{"name": "validate_resource_tags", "arguments": {"resource_arns": ["arn:aws:s3:::YOUR-BUCKET-NAME"]}}
```
Replace `YOUR-BUCKET-NAME` with an actual S3 bucket in your account.
Expected: JSON with `total_resources`, `compliant_resources`, `non_compliant_resources`, `results` array.

**Tool 4: get_cost_attribution_gap**
```json
{"name": "get_cost_attribution_gap", "arguments": {"resource_types": ["ec2:instance", "s3:bucket"]}}
```
Expected: JSON with `total_spend`, `attributable_spend`, `attribution_gap`, `attribution_gap_percentage` (0-100).

**Tool 5: suggest_tags**
```json
{"name": "suggest_tags", "arguments": {"resource_arn": "arn:aws:s3:::YOUR-BUCKET-NAME"}}
```
Expected: JSON with `resource_arn`, `resource_type`, `suggestions` array, `current_tags`.

**Tool 6: get_tagging_policy**
```json
{"name": "get_tagging_policy", "arguments": {}}
```
Expected: JSON with `required_tags` array (containing at least Environment, Owner, Application), `optional_tags` array.

**Tool 7: generate_compliance_report**
```json
{"name": "generate_compliance_report", "arguments": {"resource_types": ["ec2:instance"], "format": "markdown"}}
```
Expected: JSON with `format` = "markdown", `report_data` containing markdown text.

**Tool 8: get_violation_history**
```json
{"name": "get_violation_history", "arguments": {"days_back": 30, "group_by": "day"}}
```
Expected: JSON with `period_days`, `data_points` array. Empty `data_points` is acceptable if no scans have been stored yet.

**Pass criteria**: All 8 tools return valid JSON with the expected fields. No errors or exceptions.

---

### 3.2 Phase 2.1: Remediation Script Generation (Tools 9-10)

#### Tool 9: generate_custodian_policy

**What to test**: Generates valid Cloud Custodian YAML policies based on your tagging policy. The YAML should be syntactically valid and target the correct resource types and tags.

**Test 9a -- Default (all resource types, dry-run mode)**
```json
{"name": "generate_custodian_policy", "arguments": {}}
```
Expected result:
- `policy_count` >= 1
- `yaml_content` contains valid YAML with `policies:` key
- `dry_run` is `true`
- YAML contains `notify` actions (not `tag` actions) because dry_run defaults to true
- `resource_types` lists the resource types targeted

Validation: Copy the `yaml_content` value and verify it parses as valid YAML:
```python
import yaml; yaml.safe_load(PASTE_YAML_HERE)
```

**Test 9b -- Specific resource types and tags**
```json
{"name": "generate_custodian_policy", "arguments": {"resource_types": ["ec2:instance", "rds:db"], "target_tags": ["Environment", "Owner"], "dry_run": false}}
```
Expected result:
- `yaml_content` contains policies for EC2 and RDS only
- YAML contains `tag` actions (not `notify`) because `dry_run` is false
- Policies filter for `Environment` and `Owner` tags being absent

**Test 9c -- Violation type filter**
```json
{"name": "generate_custodian_policy", "arguments": {"violation_types": ["missing_tag"], "resource_types": ["s3:bucket"]}}
```
Expected result:
- YAML policies only target missing tags (not invalid values)
- Resource type is S3 (`s3` in Cloud Custodian format)

**Edge cases to try:**
- Empty `resource_types` array: `{"resource_types": []}` -- should generate policies for all types
- Invalid resource type: `{"resource_types": ["invalid:type"]}` -- should handle gracefully (skip or warn)
- Empty `target_tags`: `{"target_tags": []}` -- should use all required tags from policy

---

#### Tool 10: generate_openops_workflow

**What to test**: Generates an OpenOps-compatible YAML workflow for tag compliance remediation.

**Test 10a -- Notify strategy (default)**
```json
{"name": "generate_openops_workflow", "arguments": {"resource_types": ["ec2:instance"]}}
```
Expected result:
- `workflow_name` is a descriptive string
- `yaml_content` contains valid YAML with workflow steps
- `remediation_strategy` is `"notify"`
- `step_count` >= 1
- `steps` array contains at least one step with `name` and `action` fields

**Test 10b -- Auto-tag strategy with threshold**
```json
{"name": "generate_openops_workflow", "arguments": {"resource_types": ["ec2:instance", "s3:bucket"], "remediation_strategy": "auto_tag", "threshold": 0.8, "target_tags": ["Environment"]}}
```
Expected result:
- YAML content includes auto-tagging steps
- Workflow references the 0.8 compliance threshold
- Only targets the `Environment` tag

**Test 10c -- Report strategy with weekly schedule**
```json
{"name": "generate_openops_workflow", "arguments": {"remediation_strategy": "report", "schedule": "weekly"}}
```
Expected result:
- `remediation_strategy` is `"report"`
- YAML contains reporting steps (not tagging actions)

**Edge cases to try:**
- Invalid strategy: `{"remediation_strategy": "delete_everything"}` -- should reject or fall back to "notify"
- Threshold out of range: `{"threshold": 5.0}` -- should validate (0.0-1.0 range)
- No resource types: `{"resource_types": null}` -- should default to all types from policy

---

### 3.3 Phase 2.2: Compliance Tools (Tools 11-12)

#### Tool 11: schedule_compliance_audit

**What to test**: Creates a compliance audit schedule configuration with cron expression and next run time. Note: this tool generates the configuration -- it does not start an actual scheduler process.

**Test 11a -- Daily schedule**
```json
{"name": "schedule_compliance_audit", "arguments": {"schedule": "daily", "time": "09:00", "timezone_str": "America/New_York"}}
```
Expected result:
- `schedule_id` starts with `audit-sched-` and contains a UUID
- `status` is `"created"` or `"active"`
- `schedule_type` is `"daily"`
- `time` is `"09:00"`
- `timezone` is `"America/New_York"`
- `next_run` is a valid ISO 8601 datetime string
- `cron_expression` is a valid cron expression (e.g., `0 9 * * *`)
- `message` contains a human-readable confirmation

**Test 11b -- Weekly schedule with recipients**
```json
{"name": "schedule_compliance_audit", "arguments": {"schedule": "weekly", "time": "14:00", "timezone_str": "UTC", "resource_types": ["ec2:instance", "rds:db"], "recipients": ["finops@company.com"], "notification_format": "csv"}}
```
Expected result:
- `schedule_type` is `"weekly"`
- `resource_types` contains `["ec2:instance", "rds:db"]`
- `recipients` contains the email address
- `notification_format` is `"csv"`
- `cron_expression` reflects weekly (e.g., `0 14 * * 1`)

**Test 11c -- Monthly schedule**
```json
{"name": "schedule_compliance_audit", "arguments": {"schedule": "monthly", "time": "02:00"}}
```
Expected result:
- `schedule_type` is `"monthly"`
- `cron_expression` reflects monthly (e.g., `0 2 1 * *`)

**Edge cases to try:**
- Invalid schedule: `{"schedule": "hourly"}` -- should reject with error
- Invalid time format: `{"time": "25:99"}` -- should reject with validation error
- Invalid timezone: `{"timezone_str": "Mars/Olympus"}` -- should handle gracefully

---

#### Tool 12: detect_tag_drift

**What to test**: Compares current resource tags against the tagging policy to identify resources with missing or invalid tags. Reports each deviation as a "drift" with severity classification.

**Test 12a -- Default drift detection**
```json
{"name": "detect_tag_drift", "arguments": {}}
```
Expected result:
- `drift_detected` is an array (may be empty if all resources are compliant)
- `total_drifts` is a non-negative integer
- `resources_analyzed` is a non-negative integer
- `lookback_days` is `7` (default)
- `scan_timestamp` is a valid ISO 8601 string
- If drifts are found, each entry has: `resource_arn`, `resource_id`, `resource_type`, `tag_key`, `drift_type` (one of "added", "removed", "changed"), `severity` (one of "critical", "warning", "info")

**Test 12b -- Specific resource types and tag keys**
```json
{"name": "detect_tag_drift", "arguments": {"resource_types": ["ec2:instance"], "tag_keys": ["Environment", "Owner"], "lookback_days": 30}}
```
Expected result:
- Only EC2 instances are analyzed
- Only `Environment` and `Owner` tags are reported
- `lookback_days` is `30`

**Test 12c -- Short lookback**
```json
{"name": "detect_tag_drift", "arguments": {"lookback_days": 1}}
```
Expected result:
- Same structure as Test 12a, but with a 1-day lookback window

**Edge cases to try:**
- Lookback out of range: `{"lookback_days": 0}` or `{"lookback_days": 365}` -- should validate (1-90 range)
- Non-existent tag key: `{"tag_keys": ["NonExistentTag"]}` -- should return empty or handle gracefully

---

### 3.4 Phase 2.3: Export and Import (Tools 13-14)

#### Tool 13: export_violations_csv

**What to test**: Runs a compliance scan and exports violations as CSV-formatted text. The CSV should be valid and parseable by any spreadsheet tool.

**Test 13a -- Default export**
```json
{"name": "export_violations_csv", "arguments": {"resource_types": ["ec2:instance", "s3:bucket"]}}
```
Expected result:
- `csv_data` contains comma-separated data with a header row
- `row_count` is a non-negative integer (matches number of data rows, excluding header)
- `column_count` matches the number of columns in the header
- `columns` is an array listing the column names
- `format` is `"csv"`
- Default columns should include: `resource_arn`, `resource_type`, `violation_type`, `tag_name`, `severity`, `region`

Validation: Parse the CSV data:
```python
import csv, io
reader = csv.reader(io.StringIO(PASTE_CSV_DATA_HERE))
header = next(reader)
rows = list(reader)
print(f"Header: {header}")
print(f"Rows: {len(rows)}")
```

**Test 13b -- Custom columns and severity filter**
```json
{"name": "export_violations_csv", "arguments": {"resource_types": ["ec2:instance"], "severity": "errors_only", "columns": ["resource_arn", "tag_name", "severity", "current_value"]}}
```
Expected result:
- CSV header contains exactly the 4 requested columns
- All rows have severity "error" (since `errors_only` filter is applied)
- `filters_applied` shows the severity filter

**Test 13c -- All resource types**
```json
{"name": "export_violations_csv", "arguments": {"resource_types": ["all"]}}
```
Expected result:
- CSV contains violations from all scanned resource types
- `row_count` may be large (depends on environment)

**Edge cases to try:**
- Invalid column name: `{"columns": ["nonexistent_column"]}` -- should handle gracefully (skip invalid columns or return error)
- No violations found: If your account is fully compliant for a given type, `row_count` should be 0 and `csv_data` should contain only the header row

---

#### Tool 14: import_aws_tag_policy

**What to test**: Connects to AWS Organizations to list or import tag policies. This tool requires AWS Organizations with tag policies configured.

**Test 14a -- List available policies (no policy_id)**
```json
{"name": "import_aws_tag_policy", "arguments": {}}
```
Expected result (if AWS Organizations is configured):
- `status` is `"available_policies"` or `"success"`
- `available_policies` array with each entry containing `policy_id`, `policy_name`

Expected result (if no AWS Organizations access):
- `status` is `"error"`
- `message` explains the permission issue
- `required_permissions` lists the IAM actions needed

**Test 14b -- Import a specific policy**

First, get a policy ID from Test 14a, then:
```json
{"name": "import_aws_tag_policy", "arguments": {"policy_id": "p-XXXXXXXX", "save_to_file": false}}
```
Expected result:
- `status` is `"success"`
- `policy` contains `required_tags` and `optional_tags` arrays
- `summary` shows `required_tags_count`, `optional_tags_count`, `enforced_services`
- Since `save_to_file` is `false`, no file is written

**Test 14c -- Import and save to file**
```json
{"name": "import_aws_tag_policy", "arguments": {"policy_id": "p-XXXXXXXX", "save_to_file": true, "output_path": "policies/imported_policy.json"}}
```
Expected result:
- `status` is `"success"`
- `saved_to` shows the file path
- Verify the file exists: `type policies\imported_policy.json` (Windows) or `cat policies/imported_policy.json` (Linux)
- File contains valid JSON matching the MCP tagging policy format

**Edge cases to try:**
- Invalid policy ID: `{"policy_id": "p-invalid"}` -- should return error with guidance
- Save to read-only path: `{"output_path": "/root/readonly.json"}` -- should return file write error
- Account without Organizations: Should return clear error about missing permissions

**Note**: If your AWS account does not use AWS Organizations or does not have tag policies configured, Tests 14a-14c will return permission errors. This is expected behavior. Verify that the error messages are clear and actionable.

---

### 3.5 Phase 2.4: Auto-Policy and Scheduler

These are server-side features, not MCP tools. They require manual verification.

#### Auto-Policy Detection

**What to test**: When the MCP server starts without a `policies/tagging_policy.json` file, it should attempt to detect and import an AWS Organizations tag policy automatically.

**Test procedure:**

1. **Back up your current policy:**
   ```bash
   copy policies\tagging_policy.json policies\tagging_policy.json.bak
   ```

2. **Delete the policy file:**
   ```bash
   del policies\tagging_policy.json
   ```

3. **Start the MCP server and watch the logs:**
   ```bash
   python -m mcp_server.stdio_server 2>server_logs.txt
   ```
   Or for HTTP:
   ```bash
   python run_server.py
   ```

4. **Check the logs for auto-detection messages.** Look for one of:
   - `"Auto-detected AWS Organizations tag policy"` -- policy was found and imported
   - `"No AWS Organizations tag policy found, using default policy"` -- fallback to default
   - `"Failed to check AWS Organizations: ..."` -- permission error (expected if no Organizations access)

5. **Verify a policy file was created:**
   ```bash
   type policies\tagging_policy.json
   ```
   It should contain either the imported AWS policy or a default policy with at least `Environment`, `Owner`, and `CostCenter` tags.

6. **Test that the server works with the auto-detected policy:**
   ```json
   {"name": "get_tagging_policy", "arguments": {}}
   ```
   Should return the auto-detected or default policy.

7. **Restore your original policy:**
   ```bash
   copy policies\tagging_policy.json.bak policies\tagging_policy.json
   ```

**Pass criteria:**
- Server starts successfully without a pre-existing policy file
- Policy is either imported from AWS Organizations or a sensible default is created
- Server logs clearly indicate which policy source was used
- All tools work normally with the auto-detected policy

---

#### Daily Compliance Snapshot Scheduler

**What to test**: The server can be configured to run automated compliance scans at a scheduled time, storing results in the compliance history database.

**Note**: The scheduler feature is configured via environment variables. It may not yet be fully implemented in the current build. If the scheduler is not active, verify the configuration mechanism and log messages.

**Test procedure:**

1. **Configure the scheduler in `.env`:**
   ```
   SCHEDULER_ENABLED=true
   SNAPSHOT_SCHEDULE_HOUR=*
   ```
   Setting the hour to `*` means "run every hour" for testing purposes. In production, this would be a specific hour like `2` (for 2:00 AM UTC).

2. **Start the HTTP server:**
   ```bash
   python run_server.py
   ```

3. **Check the logs for scheduler startup:**
   Look for messages like:
   - `"Compliance snapshot scheduler started"` or `"Scheduler initialized"`
   - `"Next scheduled scan: ..."`

4. **Check the health endpoint** (HTTP transport only):
   ```bash
   curl http://localhost:8080/health
   ```
   The response may include scheduler status fields such as:
   - `last_scheduled_scan`
   - `next_scheduled_scan`
   - `scheduler_enabled`

5. **Wait for a scheduled scan to execute** (if hour is `*`, should trigger within the hour), then check compliance history:
   ```json
   {"name": "get_violation_history", "arguments": {"days_back": 1}}
   ```
   Should show a new data point from the scheduled scan.

**Pass criteria:**
- Scheduler configuration is accepted without errors
- Server logs confirm scheduler initialization
- Scheduled scans execute and store results in history
- Ad-hoc user scans with `store_snapshot=false` do not pollute the history

**If the scheduler is not yet implemented**: This is an acceptable finding for UAT 1. Document that the scheduler feature is pending and proceed with other tests.

---

## 4. UAT Round 2: Non-Regression Testing with promptfoo

The project includes an automated regression test suite using [promptfoo](https://promptfoo.dev/) that validates all 8 Phase 1 tools against the HTTP transport.

### Setup

1. **Install promptfoo** (if not already installed):
   ```bash
   npm install -g promptfoo@latest
   ```
   Or use without installing:
   ```bash
   npx promptfoo@latest eval
   ```

2. **Start the HTTP server** in a separate terminal:
   ```bash
   python run_server.py
   ```
   Wait for the banner showing all 14 tools are registered.

3. **Set environment variables** (optional, if auth is enabled):
   ```bash
   set MCP_SERVER_URL=http://localhost:8080
   set MCP_API_KEY=your-api-key
   set MCP_TIMEOUT=120
   ```

### Running the Tests

```bash
cd tests\regression
npx promptfoo@latest eval
```

This runs **34 test cases** covering all 8 Phase 1 tools:

| Tool | Tests | What They Validate |
|------|-------|--------------------|
| `check_tag_compliance` | 4 | Score range (0-1), violation structure, region metadata, severity filter |
| `find_untagged_resources` | 4 | Resource structure, cost estimates, region filter, total count |
| `validate_resource_tags` | 3 | Result structure, compliant/non-compliant counts, math consistency |
| `get_cost_attribution_gap` | 3 | Cost math (gap = total - attributable), percentage range, grouping |
| `suggest_tags` | 2 | Suggestion structure, confidence scores (0-1) |
| `get_tagging_policy` | 4 | Required tags present, tag structure, known tags (Environment/Owner/Application), idempotency |
| `generate_compliance_report` | 4 | JSON format, Markdown format, CSV format, recommendations |
| `get_violation_history` | 4 | Data point structure, daily/weekly/monthly grouping |
| Error handling | 4 | Invalid tool name, invalid severity, empty inputs, invalid ARN |
| Performance | 2 | Policy retrieval < 5s, history retrieval < 5s |

### Viewing Results

```bash
npx promptfoo@latest view
```
This opens a browser UI showing pass/fail for each test case.

### Expected Results

- **All 34 tests should pass.** If any Phase 1 test fails, it indicates a regression introduced by Phase 2 changes.
- Pay special attention to:
  - `check_tag_compliance` tests (most complex tool, most likely to regress)
  - Cost attribution gap math consistency tests
  - Violation structure tests (field names/types must not change)

### New Tests for Phase 2 Tools (9-14)

Regression tests for the 6 new tools will be added to `tests/regression/promptfooconfig.yaml` as a follow-up. The test cases will validate:

| Tool | Planned Assertions |
|------|--------------------|
| `generate_custodian_policy` | Valid YAML, policy count > 0, dry_run flag respected, correct resource mapping |
| `generate_openops_workflow` | Valid YAML, step count > 0, strategy reflected in output, workflow name present |
| `schedule_compliance_audit` | Schedule ID generated, cron expression valid, next_run in future, time/timezone preserved |
| `detect_tag_drift` | Total drifts >= 0, severity in valid set, lookback_days preserved, scan_timestamp present |
| `export_violations_csv` | Valid CSV format, row_count matches data, columns match header, filter applied correctly |
| `import_aws_tag_policy` | Status field present, policy structure valid, permission error handled gracefully |

---

## 5. Acceptance Criteria

### Go/No-Go Checklist for Phase 2.5 (Production Deployment)

Each item must be marked PASS before proceeding to ECS Fargate deployment.

#### New Tools (Phase 2.1-2.3)

| # | Tool | Criteria | PASS/FAIL |
|---|------|----------|-----------|
| 9 | `generate_custodian_policy` | Returns valid YAML; dry_run mode generates notify actions; non-dry-run generates tag actions | |
| 10 | `generate_openops_workflow` | Returns valid YAML; all 3 strategies work (notify, auto_tag, report); threshold filter works | |
| 11 | `schedule_compliance_audit` | Returns valid schedule config; cron expression matches frequency; next_run is in the future | |
| 12 | `detect_tag_drift` | Returns drift list; severity classification is correct; resource/tag filters work | |
| 13 | `export_violations_csv` | Returns valid CSV; row_count matches data; column filtering works; severity filtering works | |
| 14 | `import_aws_tag_policy` | Lists policies when no ID given; imports and converts policy correctly; handles permission errors gracefully | |

#### Server Features (Phase 2.4)

| Feature | Criteria | PASS/FAIL |
|---------|----------|-----------|
| Auto-policy detection | Server starts without policy file; creates valid policy from AWS or default | |
| Daily scheduler | Scheduler starts; health endpoint shows status; scheduled scan stores in history | |

#### Phase 1 Regression

| Criteria | PASS/FAIL |
|----------|-----------|
| All 8 Phase 1 tools return valid results with unchanged schemas | |
| promptfoo regression suite passes 34/34 tests | |
| `python run_tests.py --unit` passes all unit tests | |

#### Overall

| Criteria | PASS/FAIL |
|----------|-----------|
| No blocking errors or exceptions in server logs | |
| All 14 tools callable via MCP Inspector without errors | |
| Response times are reasonable (< 30s for full scans, < 5s for local-only tools) | |

**Decision**: If ALL items are PASS, proceed to Phase 2.5 (ECS Fargate). If any FAIL, document the issue and fix before proceeding.

---

## 6. Known Limitations

### Tool-Specific Limitations

1. **Tool 9 (generate_custodian_policy)**:
   - Generated policies are based on the tagging policy, not on live violation data. The policy tells Cloud Custodian what tags to enforce, not which resources currently violate.
   - Not all AWS resource types have Cloud Custodian equivalents. Unknown types are skipped.

2. **Tool 10 (generate_openops_workflow)**:
   - OpenOps platform schema may evolve. Generated workflows are based on the current schema version.
   - The `auto_tag` strategy generates AWS CLI commands but does not execute them.

3. **Tool 11 (schedule_compliance_audit)**:
   - This tool generates a schedule configuration. It does not start an actual background scheduler process. Integration with APScheduler or cron is a separate server-side concern.

4. **Tool 12 (detect_tag_drift)**:
   - Drift detection compares current tags against the policy (expected state), not against a historical tag snapshot. True "temporal drift" (comparing tags at time A vs time B) requires tag state storage, which is not yet implemented.
   - The `lookback_days` parameter controls how far back to look for baseline scans but the primary comparison is policy-based.

5. **Tool 13 (export_violations_csv)**:
   - CSV output is returned as a string in the JSON response. For very large datasets (10,000+ violations), the response may be large. Consider using resource type filters to limit output size.

6. **Tool 14 (import_aws_tag_policy)**:
   - Requires AWS Organizations access. Accounts without Organizations will get a clear error.
   - Wildcard values in AWS tag policies (e.g., `"300*"`) are not supported and are stripped during conversion.
   - The `@@operators` inheritance directives are ignored (not applicable to a single-server deployment).

### General Limitations

- **Scheduler**: The daily compliance snapshot scheduler may not be fully operational in the current build. Configuration acceptance and startup logging are the primary validation targets for UAT 1.
- **OAuth 2.0**: Not implemented until Phase 2.5 (ECS Fargate). UAT 1 uses API key auth or no auth.
- **PostgreSQL**: Not available until Phase 2.5. UAT 1 uses SQLite for audit and history data.
- **Cost data in CSV export**: The `cost_impact_monthly` column may show `$0.00` for all violations when using the Resource Groups Tagging API, which does not provide per-resource cost data. This is expected.

---

## 7. Troubleshooting

### Server Won't Start

**Problem**: `ValidationError: Extra inputs are not permitted`
```
pydantic_core._pydantic_core.ValidationError: 12 validation errors for CoreSettings
mcp_server_host
  Extra inputs are not permitted
```
**Solution**: The `.env` file contains HTTP-specific settings that `CoreSettings` does not recognize. Ensure `extra="ignore"` is set in `CoreSettings.model_config` in `mcp_server/config.py`. This should already be fixed, but verify if you encounter it.

**Problem**: `RuntimeError: ServiceContainer not initialized`
**Solution**: The container failed to initialize, likely due to missing AWS credentials. Run `aws sts get-caller-identity` to verify your credentials are configured.

**Problem**: `FileNotFoundError: policies/tagging_policy.json`
**Solution**: Either create the file manually or enable auto-policy detection. For quick testing, copy the example:
```bash
copy policies\tagging_policy_example.json policies\tagging_policy.json
```

### Tool Returns Error

**Problem**: Tool returns `{"error": "timeout", "message": "Scan timed out"}`
**Solution**: You are likely scanning too many resources. Use specific resource types instead of `["all"]`:
```json
{"resource_types": ["ec2:instance", "s3:bucket"]}
```

**Problem**: Tool returns `{"error": "scan_failed", "message": "..."}`
**Solution**: Check the error message for details. Common causes:
- Insufficient IAM permissions (check `docs/IAM_PERMISSIONS.md`)
- AWS API rate limiting (wait a few seconds and retry)
- Network connectivity to AWS (verify with `aws ec2 describe-instances`)

**Problem**: `import_aws_tag_policy` returns permission error
**Solution**: This tool requires `organizations:ListPolicies` and `organizations:DescribePolicy` permissions. If your account does not use AWS Organizations, this is expected. The tool should return a clear error message explaining what permissions are needed.

### promptfoo Tests Fail

**Problem**: All tests fail with connection error
**Solution**: The HTTP server is not running. Start it first:
```bash
python run_server.py
```
Wait for the startup banner before running tests.

**Problem**: Tests fail with 401 Unauthorized
**Solution**: Auth is enabled but no API key is configured. Either:
- Set `AUTH_ENABLED=false` in `.env` for local testing, or
- Set the `MCP_API_KEY` environment variable before running promptfoo

**Problem**: Specific test fails but tool works manually
**Solution**: The test may have outdated assertions. Compare the actual tool output against the expected assertions in `tests/regression/promptfooconfig.yaml`. If the schema has changed intentionally, update the assertions.

### MCP Inspector Issues

**Problem**: MCP Inspector shows "Connection failed"
**Solution**: Ensure you are running the stdio transport command exactly:
```bash
npx @modelcontextprotocol/inspector python -m mcp_server.stdio_server
```
The working directory must be the project root where `policies/` and `.env` are located.

**Problem**: Tool list is empty in MCP Inspector
**Solution**: The server failed to initialize. Check the terminal (stderr) for error messages. Common cause: missing dependencies. Run `pip install -r requirements.txt`.

### Windows-Specific Issues

**Problem**: `UnicodeDecodeError` when reading policy file
**Solution**: Ensure policy files are saved as UTF-8 without BOM. Open in a text editor and re-save with UTF-8 encoding.

**Problem**: Path issues with backslashes
**Solution**: Python handles both `/` and `\` on Windows. If you see path errors, try using forward slashes in `.env` values:
```
POLICY_PATH=policies/tagging_policy.json
```

---

**End of UAT Guide**

**Next Steps After UAT 1:**
1. Fix any FAIL items identified during testing
2. Re-run failed tests to confirm fixes
3. Add promptfoo regression tests for Tools 9-14
4. Proceed to Phase 2.5 (ECS Fargate deployment)
5. Conduct UAT 2 on production infrastructure
