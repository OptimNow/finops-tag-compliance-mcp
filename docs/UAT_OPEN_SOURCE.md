# UAT protocol — open-source stdio MCP server

## FinOps Tag Compliance MCP Server

**Version:** 0.2.0
**Transport:** stdio (JSON-RPC over stdin/stdout)
**Date:** _______________

---

## Overview

This UAT validates the open-source release of the FinOps Tag Compliance MCP Server.
Tests are split into two tiers:

| Tier | Scope | AWS Required? | Automated? |
|------|-------|---------------|------------|
| **Tier 1** | Installation, startup, protocol, schemas, validation, config | No | Yes |
| **Tier 2** | Live compliance scanning via Claude Desktop prompts | Yes | No (manual) |

**Pass criteria:**
- Tier 1: 100% pass (all automated, no AWS needed)
- Tier 2: ≥90% pass rate across 3 runs

---

## Prerequisites

### 1. Python environment

- **Python 3.10+** required
- Verify: `python --version`

### 2. Install the package (editable mode)

```bash
cd /path/to/finops-tag-compliance-mcp
pip install -e .
```

### 3. AWS credentials (Tier 2 only)

- AWS credentials configured (`aws configure` or env vars)
- IAM role with read-only permissions (see `docs/security/IAM_PERMISSIONS.md`)
- Some tagged and untagged EC2/RDS/S3/Lambda resources in your account

### 4. Claude Desktop configuration (Tier 2 only)

Edit your Claude Desktop config:
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "finops-tagging": {
      "command": "python",
      "args": ["-m", "mcp_server.stdio_server"],
      "cwd": "/path/to/finops-tag-compliance-mcp",
      "env": {
        "AWS_REGION": "us-east-1"
      }
    }
  }
}
```

Restart Claude Desktop after saving. You should see the hammer icon with 14 tools.

**Quick verification:** Ask Claude "Show me our tagging policy" — you should get a response with policy details.

---

## Tier 1 — offline tests (no AWS required)

### T1.01: package installs from source

```bash
pip install -e .
```

**Expected:** Installs without errors. Entry point `finops-tag-compliance` is available.
**Pass:** [ ]

---

### T1.02: server module imports cleanly

```python
python -c "from mcp_server.stdio_server import mcp; print('OK')"
```

**Expected:** Prints "OK", no import errors.
**Pass:** [ ]

---

### T1.03: server starts and responds to MCP initialize

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' | python -m mcp_server.stdio_server
```

**Expected:** JSON-RPC response with `serverInfo` containing name "FinOps Tag Compliance".
**Pass:** [ ]

---

### T1.04: all 14 tools are registered

```bash
# After initialize + initialized notification, send tools/list
```

**Expected:** `tools/list` response contains exactly 14 tools:
1. `check_tag_compliance`
2. `find_untagged_resources`
3. `validate_resource_tags`
4. `get_cost_attribution_gap`
5. `suggest_tags`
6. `get_tagging_policy`
7. `generate_compliance_report`
8. `get_violation_history`
9. `detect_tag_drift`
10. `generate_custodian_policy`
11. `generate_openops_workflow`
12. `schedule_compliance_audit`
13. `export_violations_csv`
14. `import_aws_tag_policy`

**Pass:** [ ]

---

### T1.05: tool schemas have required parameters and descriptions

**Expected:** Every tool has:
- A non-empty `description`
- An `inputSchema` with `type: "object"`
- Correct required parameters per tool specification

**Pass:** [ ]

---

### T1.06: `get_tagging_policy` returns policy without AWS

```bash
# Call tools/call with method get_tagging_policy
```

**Expected:** Returns the tagging policy from `policies/tagging_policy.json` with required and optional tags listed.
**Pass:** [ ]

---

### T1.07: `generate_custodian_policy` works offline

**Expected:** Returns valid Cloud Custodian YAML policies without needing AWS access.
**Pass:** [ ]

---

### T1.08: `schedule_compliance_audit` works offline

**Expected:** Returns cron expression and schedule configuration without needing AWS.
**Pass:** [ ]

---

### T1.09: input validation rejects invalid ARNs

```python
# Call validate_resource_tags with resource_arns=["not-an-arn"]
```

**Expected:** Returns validation error, does not crash.
**Pass:** [ ]

---

### T1.10: input validation rejects oversized lists

```python
# Call check_tag_compliance with resource_types containing 200 items
```

**Expected:** Returns validation error about max list size (100).
**Pass:** [ ]

---

### T1.11: unit tests pass (1000+)

```bash
pytest tests/unit --ignore=tests/unit/test_aws_client.py -q
```

**Expected:** ≥1000 tests pass. One pre-existing failure (`test_cache_failure_does_not_break_multi_region_scan`) may occur due to MagicMock logging.
**Pass:** [ ]

---

### T1.12: property tests collect without import errors

```bash
pytest tests/property --collect-only -q
```

**Expected:** 314+ tests collected, zero errors.
**Pass:** [ ]

---

### T1.13: no private infrastructure references in codebase

```bash
grep -r "mcp_handler\|http_config\|middleware/auth\|deploy_ecs\|mcp_bridge\|382598" mcp_server/ tests/ --include="*.py"
```

**Expected:** Zero matches. No leaked references to HTTP server, deployment scripts, or AWS account IDs.
**Pass:** [ ]

---

### T1.14: no secrets in codebase

```bash
grep -ri "api_key.*=\|password.*=\|secret.*=\|token.*=" mcp_server/ --include="*.py" | grep -v "def \|#\|test\|example\|param\|Optional"
```

**Expected:** Zero real secrets. Only parameter names and documentation references.
**Pass:** [ ]

---

### T1.15: LICENSE is Apache-2.0

**Expected:** LICENSE file contains "Apache License, Version 2.0".
**Pass:** [ ]

---

### T1.16: README has correct quick start

**Expected:** README.md contains:
- `pip install finops-tag-compliance-mcp` instruction
- Claude Desktop JSON config snippet
- No references to Docker, ECS, HTTP, or mcp_bridge.py
**Pass:** [ ]

---

### T1.17: error sanitization hides internal paths

**Expected:** When a tool returns an error, the error message contains a user-friendly code (e.g., `internal_error`) but no file paths, stack traces, or sensitive details.
**Pass:** [ ]

---

### T1.18: pyproject.toml metadata is correct for PyPI

**Expected:**
- `name = "finops-tag-compliance-mcp"`
- `requires-python = ">=3.10"`
- `license` = Apache-2.0
- No `fastapi` or `uvicorn` in core dependencies
- Entry point `finops-tag-compliance` defined
**Pass:** [ ]

---

## Tier 2 — live tests (AWS required)

> **Prerequisites:** Complete steps 2-4 in the Prerequisites section above.

### T2.01: check tag compliance for EC2

**Prompt:** `Check tag compliance for my EC2 instances`
**Expected:** Compliance score, violation list, resource details.

---

### T2.02: find untagged resources

**Prompt:** `Find all untagged resources`
**Expected:** List of resources missing required tags with resource type and region.

---

### T2.03: cost attribution gap

**Prompt:** `What's our cost attribution gap?`
**Expected:** Total spend, attributable amount, gap amount and percentage.

---

### T2.04: view tagging policy

**Prompt:** `Show me our tagging policy`
**Expected:** Full policy with required tags, allowed values, and applicable resource types.

---

### T2.05: validate specific resource

**Prompt:** `Validate tags for arn:aws:ec2:us-east-1:<ACCOUNT>:instance/<ID>`
**Expected:** Detailed per-tag validation results (compliant/missing/invalid).

---

### T2.06: suggest tags

**Prompt:** `Suggest tags for arn:aws:ec2:us-east-1:<ACCOUNT>:instance/<ID>`
**Expected:** Tag suggestions with confidence scores and reasoning.

---

### T2.07: generate compliance report

**Prompt:** `Generate a compliance report for EC2 and S3`
**Expected:** Summary with scores, violation counts, and recommendations.

---

### T2.08: multi-region scanning

**Prompt:** `Check compliance for EC2 instances across all regions`
**Expected:** Results from multiple regions, regional breakdown shown.

---

### T2.09: compliance history

**Prompt:** `Show me compliance trends for the last 30 days`
**Expected:** Historical data or "no history yet" for first run.

---

### T2.10: export violations

**Prompt:** `Export compliance violations as CSV`
**Expected:** CSV-formatted output with resource IDs, violation types, severity.

---

### T2.11: filter by severity

**Prompt:** `Show me only critical tagging errors for EC2`
**Expected:** Only ERROR-severity violations returned.

---

### T2.12: generate remediation workflow

**Prompt:** `Generate an OpenOps workflow to fix tagging issues`
**Expected:** Valid workflow configuration with remediation steps.

---

## Results summary

| Tier | Total | Passed | Failed | Pass Rate |
|------|-------|--------|--------|-----------|
| Tier 1 (Offline) | 18 | | | |
| Tier 2 (Live) | 12 | | | |
| **Total** | **30** | | | |

**Overall verdict:** [ ] PASS / [ ] FAIL

**Notes:**
