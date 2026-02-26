# Security & Anti-Hallucination Design

This document describes the security measures and LLM anti-hallucination patterns
built into the FinOps Tag Compliance MCP Server. It is intended for stakeholders
evaluating the server's suitability for production use with AI assistants.

---

## Table of Contents

1. [Security Overview](#security-overview)
2. [Input Validation & Injection Prevention](#1-input-validation--injection-prevention)
3. [Error Sanitization — Zero Information Leakage](#2-error-sanitization--zero-information-leakage)
4. [AWS Credential Security](#3-aws-credential-security)
5. [Rate Limiting & Backoff](#4-rate-limiting--backoff)
6. [Session Abuse Prevention](#5-session-abuse-prevention)
7. [Audit Trail](#6-audit-trail)
8. [Anti-Hallucination Overview](#anti-hallucination-overview)
9. [Mandatory Workflow Directives](#7-mandatory-workflow-directives)
10. [Authoritative Resource Type List](#8-authoritative-resource-type-list)
11. [Data Quality Metadata](#9-data-quality-metadata)
12. [Cost Data Transparency](#10-cost-data-transparency)
13. [Timeout & Batch Guidance](#11-timeout--batch-guidance)
14. [Parameter Name Tolerance](#12-parameter-name-tolerance)
15. [Enum-Based Validation](#13-enum-based-validation)

---

## Security Overview

The server enforces a **defense-in-depth** strategy across six layers:

| Layer | Mechanism | Key File |
|-------|-----------|----------|
| Input | Injection detection, size limits, ARN validation | `utils/input_validation.py` |
| AWS | No hardcoded creds, IAM read-only, rate limiting | `clients/aws_client.py` |
| Output | Sensitive data redaction, safe error codes | `utils/error_sanitization.py` |
| Session | Budget tracker (100 calls/session), loop detector | `utils/budget_tracker.py`, `utils/loop_detection.py` |
| Audit | SQLite logging with correlation IDs | `services/audit_service.py` |
| IAM | Read-only permissions, zero write access | `docs/security/IAM_PERMISSIONS.md` |

---

### 1. Input Validation & Injection Prevention

**File:** `mcp_server/utils/input_validation.py`

Every parameter from the AI agent passes through `InputValidator` before reaching
business logic. The validator enforces:

**Injection detection** — 14+ compiled regex patterns catch:
- Cross-site scripting (`<script>`, `javascript:`, `onerror=`)
- Template injection (`{{`, `${`, `<%`)
- Path traversal (`../`, `..\\`)
- Shell access (`; rm`, `| cat`, backticks)
- SQL injection (`UNION SELECT`, `DROP TABLE`, `OR 1=1`)
- Null byte injection (`\x00`)
- Control characters (ASCII 0–31 except whitespace)

**Size limits** — prevent denial-of-service via oversized payloads:

| Parameter | Max |
|-----------|-----|
| Resource types per call | 10 |
| Resource ARNs per call | 100 |
| Regions per call | 20 |
| String length | 1,024 characters |
| Array length | 1,000 items |
| Dict keys | 50 |
| Nesting depth | 5 levels |

**ARN format validation** — regex validates AWS ARN structure including partition
(`aws`, `aws-cn`, `aws-us-gov`), service name, region, account ID (12 digits),
and resource identifier.

Any violation raises a `SecurityViolationError` with a typed code (e.g.,
`injection_attempt`, `control_characters`) that maps to a safe user-facing message.

---

### 2. Error Sanitization — Zero Information Leakage

**File:** `mcp_server/utils/error_sanitization.py`

All errors are sanitized before reaching the AI agent or end user. The module
detects and redacts **8 categories** of sensitive data:

| Category | Examples redacted |
|----------|-------------------|
| File paths | `/home/user/app/config.py`, `C:\secrets\key.json` |
| AWS credentials | `AKIA...` access keys, secret keys, tokens |
| Connection strings | `postgres://user:pass@host`, `redis://...` |
| Email addresses | Internal team addresses in error messages |
| Internal IPs | `10.x.x.x`, `192.168.x.x`, `172.16.x.x`, `127.0.0.1` |
| Stack traces | Python tracebacks, file/line references |
| Container paths | `/app/`, `/src/`, `/workspace/` |
| Database credentials | Username, host, server fields in connection errors |

**Two-tier logging:**

- **Internal logs** — full exception details, stack traces, correlation IDs
  (written to server logs, never exposed)
- **User responses** — generic error codes (`access_denied`, `timeout`,
  `invalid_input`) with safe, actionable messages

Exception types are mapped to error codes deterministically:

| Exception | Error Code | User Message |
|-----------|-----------|--------------|
| `ValueError` | `invalid_input` | "Invalid input parameters" |
| `PermissionError` | `permission_denied` | "You do not have permission" |
| `TimeoutError` | `timeout` | "Operation timed out" |
| `SecurityViolationError` | `security_violation` | "Input rejected for security reasons" |
| `BudgetExhaustedError` | `budget_exceeded` | "Session tool-call budget exhausted" |

---

### 3. AWS Credential Security

**File:** `mcp_server/clients/aws_client.py`

- **No hardcoded credentials.** The server uses the standard boto3 credential
  chain: environment variables, AWS profiles, EC2/ECS instance profiles.
  Credentials rotate automatically via IAM.
- **Read-only IAM policy.** Phase 1 requires zero write permissions. The server
  can describe, list, and read tags — it cannot create, modify, or delete any
  AWS resource. See `docs/security/IAM_PERMISSIONS.md` for the full policy.
- **Cost Explorer isolation.** The Cost Explorer client is always created in
  `us-east-1` regardless of the scan region, matching AWS's global endpoint.

---

### 4. Rate Limiting & Backoff

**File:** `mcp_server/clients/aws_client.py`

- **Per-service rate limiting:** 100 ms minimum interval between calls to the
  same AWS service, enforced with async locks.
- **Exponential backoff:** Up to 5 retries with `delay = 1s * 2^attempt`.
  Only throttling errors (`Throttling`, `RequestLimitExceeded`) are retried;
  permission or validation errors fail immediately.
- **Concurrency control:** A semaphore caps concurrent API calls at 5 per batch
  operation, preventing runaway parallelism.

---

### 5. Session Abuse Prevention

Two mechanisms prevent an AI agent from making excessive or repetitive calls:

#### Budget Tracker (`mcp_server/utils/budget_tracker.py`)

- **Default limit:** 100 tool calls per session
- **Session TTL:** 1 hour (auto-expires)
- **Storage:** Redis with atomic `INCR` (falls back to in-memory if Redis is
  unavailable)
- **Race-condition safe:** Double-checks count after increment; raises
  `BudgetExhaustedError` if exceeded

#### Loop Detector (`mcp_server/utils/loop_detection.py`)

- **Signature:** SHA-256 hash of tool name + parameters
- **Window:** 5-minute sliding window
- **Threshold:** 3 identical calls max — then `LoopDetectedError`
- **Storage:** Redis with TTL (falls back to in-memory)

Both are feature-flagged (`BUDGET_TRACKING_ENABLED`, `LOOP_DETECTION_ENABLED`)
and default to enabled.

---

### 6. Audit Trail

**File:** `mcp_server/services/audit_service.py`

Every tool invocation is logged to SQLite:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 UTC |
| `tool_name` | Which tool was called |
| `parameters` | JSON-serialized input (for safe storage) |
| `status` | `success` or `failure` |
| `error_message` | Sanitized error (if any) |
| `execution_time_ms` | Duration in milliseconds |
| `correlation_id` | UUID linking all logs for one request |

Indexed by timestamp and correlation ID for fast retrieval.

---

## Anti-Hallucination Overview

AI agents (LLMs) connected via MCP can hallucinate in several ways:

- **Guessing resource types** instead of reading the policy
- **Presenting partial data as complete** when some regions fail
- **Fabricating cost figures** or precision levels
- **Sending invalid parameter names** and silently getting defaults

This server addresses each with structured metadata and explicit directives
embedded in tool docstrings and response payloads.

| Defense | Mechanism | Where Applied |
|---------|-----------|---------------|
| "Do NOT guess" workflow | Tool docstrings | 6 scanning tools |
| Authoritative type list | `all_applicable_resource_types` field | `get_tagging_policy` response |
| Data quality metadata | `data_quality.status` = `complete` or `partial` | Every scan response |
| Cost source labels | `cost_source` field per resource | `find_untagged_resources` |
| Batch size guidance | "Scan 4–6 types per call" | 6 scanning tools |
| Parameter tolerance | Alternate names accepted | `schedule_compliance_audit` |
| Enum validation | Whitelist of valid values | `InputValidator` |

---

### 7. Mandatory Workflow Directives

**File:** `mcp_server/stdio_server.py` — tool docstrings

Six scanning tools include this instruction block:

```
REQUIRED WORKFLOW — do NOT guess resource types:
1. FIRST call get_tagging_policy to retrieve the policy and extract ALL
   resource types from the "applies_to" fields across all required tags.
2. THEN call this tool with those resource types — either in one call or
   in batches of 4-6 types to avoid timeouts.
Do NOT pick resource types from memory (e.g., "EC2, S3, Lambda"). The
policy may include Bedrock, DynamoDB, ECS, EKS, SageMaker, and others
that you would miss. Always read the policy first.
```

**Why this matters:** Without this directive, LLMs default to well-known services
(EC2, S3, Lambda) and silently miss services like Bedrock, OpenSearch, or EKS
that may be in the organization's tagging policy.

Each scanning tool also includes a `CRITICAL — data accuracy` block:

```
CRITICAL — data accuracy: Always check the "data_quality" field in the
response. If data_quality.status is "partial", some regions failed to scan
and the results are INCOMPLETE. You MUST disclose this to the user — do NOT
present partial data as if it were a complete account-wide picture. Never
estimate, extrapolate, or fabricate values for regions that failed.
```

---

### 8. Authoritative Resource Type List

**File:** `mcp_server/stdio_server.py` — `get_tagging_policy` tool

The `get_tagging_policy` response includes a computed
`all_applicable_resource_types` field — a deduplicated, sorted list of every
resource type referenced across all required and optional tags in the policy.

```python
response["all_applicable_resource_types"] = sorted(all_types)
```

The LLM receives the exact list it needs. It does not have to parse `applies_to`
arrays or construct a list from memory. The docstring reinforces this:

```
The response includes an "all_applicable_resource_types" field — a
deduplicated list of every resource type referenced in the policy.
Use that list (in batches of 4-6) as the resource_types parameter
for scanning tools. NEVER guess or pick resource types from memory.
```

---

### 9. Data Quality Metadata

**File:** `mcp_server/stdio_server.py` — `_build_data_quality()`

Every scan response includes a `data_quality` block:

```json
{
  "status": "partial",
  "warning": "3 of 12 regions failed to scan. Results are incomplete and DO NOT cover: ap-southeast-1, eu-north-1, sa-east-1. Do not present these numbers as account-wide totals.",
  "failed_regions": ["ap-southeast-1", "eu-north-1", "sa-east-1"]
}
```

Or, when everything succeeds:

```json
{
  "status": "complete",
  "note": "All 12 regions scanned successfully."
}
```

The warning text is phrased as a **directive to the LLM** — "Do not present
these numbers as account-wide totals" — not just informational metadata. This
embeds the ground truth directly in the response payload so the LLM cannot
ignore it.

---

### 10. Cost Data Transparency

**File:** `mcp_server/models/untagged.py`

Every resource with cost data includes a `cost_source` field:

| Value | Meaning |
|-------|---------|
| `actual` | Per-resource data from Cost Explorer (EC2, RDS) |
| `service_average` | Service total divided by resource count (rough estimate) |
| `estimated` | Placeholder when Cost Explorer is unavailable |
| `stopped` | Instance is stopped; compute cost is $0 |

The field description is embedded in the Pydantic model so it appears in the
JSON schema the LLM receives. This prevents the LLM from presenting a rough
`service_average` estimate as a precise figure.

---

### 11. Timeout & Batch Guidance

Every scanning tool docstring includes explicit batch-size advice:

```
TIMEOUT WARNING: MCP clients (e.g., Claude Desktop) may have a 60-second
response timeout. Scanning many resource types across all regions can
take 2-5 minutes and will silently timeout on the client side. To avoid
this, scan in batches of 4-6 resource types per call and aggregate the
results yourself. Only use ["all"] if the client supports long timeouts.
```

When a timeout does occur, the server returns an actionable error instead of
a raw exception:

```json
{
  "error": "timeout",
  "message": "Scan timed out after 180 seconds for 15 resource types across 12 regions.",
  "suggestion": "Try scanning specific resource types instead of 'all'. Example: ['ec2:instance', 's3:bucket', 'lambda:function', 'rds:db']"
}
```

This prevents the LLM from retrying the same failing call in a loop.

---

### 12. Parameter Name Tolerance

**File:** `mcp_server/stdio_server.py` — `schedule_compliance_audit`

LLMs sometimes guess parameter names instead of reading the schema exactly.
This tool accepts alternate names as fallbacks:

| Canonical Name | Also Accepts |
|----------------|-------------|
| `schedule` | `schedule_type` |
| `time` | `time_of_day` |
| `timezone_str` | `timezone` |

The implementation picks the alternate only when the canonical parameter holds
its default value, avoiding conflicts.

---

### 13. Enum-Based Validation

**File:** `mcp_server/utils/input_validation.py`

All categorical parameters are validated against explicit whitelists:

- **Resource types:** 40+ valid types (e.g., `ec2:instance`, `bedrock:agent`)
- **Severity levels:** `all`, `errors_only`, `warnings_only`
- **Report formats:** `json`, `csv`, `markdown`
- **Group-by options:** `resource_type`, `region`, `account`, `service`

Invalid values are rejected immediately with a descriptive error, rather than
silently producing wrong results.

---

## Summary

The server uses two complementary strategies:

1. **Security** — validates inputs, sanitizes outputs, limits session scope, and
   maintains a full audit trail. The AWS integration is read-only with no
   hardcoded credentials.

2. **Anti-hallucination** — instead of trusting the LLM to reason correctly, the
   server embeds ground truth in structured metadata (`data_quality`,
   `cost_source`, `all_applicable_resource_types`) and uses imperative
   directives in tool docstrings to constrain LLM behavior. Every response
   tells the LLM exactly what it can and cannot claim.
