# Security Configuration Guide

This document describes all security-related configuration options for the FinOps Tag Compliance MCP Server.

**Requirements: 16.1, 16.2, 16.5, 18.x, 19.x, 20.x, 21.x, 22.x, 23.x**

## Overview

The MCP server provides multiple layers of security configuration to protect against prompt injection, tool misuse, and data exposure:

1. **API Key Authentication** - Bearer token authentication for API access (NEW)
2. **CORS Restriction** - Configurable origin allowlist (NEW)
3. **TLS/HTTPS** - Transport layer security via ALB (NEW)
4. **Request Sanitization** - Validates and limits incoming requests
5. **Tool Budget Enforcement** - Prevents runaway tool consumption
6. **Loop Detection** - Blocks repeated identical tool calls
7. **Security Monitoring** - Tracks and rate-limits suspicious activity
8. **CloudWatch Alerting** - Alarms for authentication and CORS violations (NEW)
9. **Error Sanitization** - Prevents sensitive information leakage

## Configuration Options

All security settings are configured via environment variables. See `.env.example` for a complete template.

---

## Production Security (NEW)

These settings enable production-grade security for remote deployments.

### API Key Authentication (Requirements: 19.1, 19.2, 19.3, 19.4, 19.5)

API key authentication protects MCP endpoints from unauthorized access.

#### `AUTH_ENABLED`
- **Type**: Boolean
- **Default**: `false`
- **Description**: Enable/disable API key authentication
- **Environment Variable**: `AUTH_ENABLED`
- **Example**: `AUTH_ENABLED=true`
- **Notes**:
  - When enabled, all requests except `/health`, `/`, `/docs` require authentication
  - Requires at least one API key in `API_KEYS`

#### `API_KEYS`
- **Type**: String (comma-separated)
- **Default**: `` (empty)
- **Description**: Comma-separated list of valid API keys
- **Environment Variable**: `API_KEYS`
- **Example**: `API_KEYS=key1,key2,key3`
- **Notes**:
  - Generate secure keys: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
  - Rotate keys every 90 days
  - Store production keys in AWS Secrets Manager

#### `AUTH_REALM`
- **Type**: String
- **Default**: `mcp-server`
- **Description**: Authentication realm for WWW-Authenticate header
- **Environment Variable**: `AUTH_REALM`
- **Example**: `AUTH_REALM=finops-mcp`
- **Notes**:
  - Included in 401 responses per RFC 6750
  - Helps clients identify the authentication scope

### CORS Configuration (Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6)

CORS restriction limits which web origins can access the API.

#### `CORS_ALLOWED_ORIGINS`
- **Type**: String (comma-separated)
- **Default**: `*`
- **Description**: Comma-separated list of allowed CORS origins, or `*` for all
- **Environment Variable**: `CORS_ALLOWED_ORIGINS`
- **Example**: `CORS_ALLOWED_ORIGINS=https://claude.ai,https://your-app.example.com`
- **Notes**:
  - Use `*` only for development
  - For production, specify exact origins
  - Empty string blocks all cross-origin requests

**Production CORS Behavior**:
When specific origins are configured (not `*`):
- Methods restricted to `POST`, `OPTIONS` only
- Headers restricted to `Content-Type`, `Authorization`, `X-Correlation-ID`
- CORS violations are logged and emit CloudWatch metrics

### TLS Configuration (Requirement: 18.5)

TLS ensures encrypted transport between clients and server.

#### `TLS_ENABLED`
- **Type**: Boolean
- **Default**: `false`
- **Description**: Flag indicating TLS termination is handled externally
- **Environment Variable**: `TLS_ENABLED`
- **Example**: `TLS_ENABLED=true`
- **Notes**:
  - In production, TLS is terminated at ALB level
  - Set to `true` when deploying behind HTTPS ALB
  - Application serves HTTP on port 8080 internally

### CloudWatch Metrics (Requirements: 23.2, 23.5)

CloudWatch metrics enable alerting for security events.

#### `CLOUDWATCH_METRICS_ENABLED`
- **Type**: Boolean
- **Default**: `false`
- **Description**: Enable/disable CloudWatch custom metrics for security alerting
- **Environment Variable**: `CLOUDWATCH_METRICS_ENABLED`
- **Example**: `CLOUDWATCH_METRICS_ENABLED=true`
- **Notes**:
  - When enabled, authentication failures emit `AuthenticationFailures` metric
  - CORS violations emit `CORSViolations` metric
  - Metrics trigger CloudWatch alarms defined in CloudFormation

#### `PROJECT_NAME`
- **Type**: String
- **Default**: `mcp-tagging`
- **Description**: Project name for CloudWatch namespace
- **Environment Variable**: `PROJECT_NAME`
- **Example**: `PROJECT_NAME=mcp-tagging`
- **Notes**:
  - CloudWatch namespace: `{PROJECT_NAME}/{ENVIRONMENT}`
  - Must match CloudFormation alarm configuration

---

### Request Sanitization (Requirements: 16.2, 16.5)

Request sanitization middleware validates incoming requests to prevent injection attacks and resource exhaustion.

#### `REQUEST_SANITIZATION_ENABLED`
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable/disable request sanitization middleware
- **Environment Variable**: `REQUEST_SANITIZATION_ENABLED`
- **Example**: `REQUEST_SANITIZATION_ENABLED=true`

#### `MAX_REQUEST_SIZE_BYTES`
- **Type**: Integer
- **Default**: `10485760` (10 MB)
- **Description**: Maximum request body size in bytes
- **Environment Variable**: `MAX_REQUEST_SIZE_BYTES`
- **Example**: `MAX_REQUEST_SIZE_BYTES=10485760`
- **Notes**: 
  - Prevents large payload attacks
  - Typical MCP requests are < 1 KB
  - Set to 0 to disable size checking

#### `MAX_HEADER_SIZE_BYTES`
- **Type**: Integer
- **Default**: `8192` (8 KB)
- **Description**: Maximum total header size in bytes
- **Environment Variable**: `MAX_HEADER_SIZE_BYTES`
- **Example**: `MAX_HEADER_SIZE_BYTES=8192`
- **Notes**:
  - Prevents header injection attacks
  - Standard HTTP limit is 8 KB
  - Set to 0 to disable header size checking

#### `MAX_HEADER_COUNT`
- **Type**: Integer
- **Default**: `50`
- **Description**: Maximum number of headers allowed per request
- **Environment Variable**: `MAX_HEADER_COUNT`
- **Example**: `MAX_HEADER_COUNT=50`
- **Notes**:
  - Prevents header flooding attacks
  - Typical requests have < 20 headers
  - Set to 0 to disable header count checking

#### `MAX_QUERY_STRING_LENGTH`
- **Type**: Integer
- **Default**: `4096`
- **Description**: Maximum query string length in characters
- **Environment Variable**: `MAX_QUERY_STRING_LENGTH`
- **Example**: `MAX_QUERY_STRING_LENGTH=4096`
- **Notes**:
  - Prevents query string injection attacks
  - Typical queries are < 1000 characters
  - Set to 0 to disable query string length checking

#### `MAX_PATH_LENGTH`
- **Type**: Integer
- **Default**: `2048`
- **Description**: Maximum URL path length in characters
- **Environment Variable**: `MAX_PATH_LENGTH`
- **Example**: `MAX_PATH_LENGTH=2048`
- **Notes**:
  - Prevents path traversal attacks
  - Typical paths are < 256 characters
  - Set to 0 to disable path length checking

### Tool-Call Budget Enforcement (Requirements: 15.3)

Budget enforcement prevents agents from making excessive tool calls, protecting against runaway behavior and cost overruns.

#### `BUDGET_TRACKING_ENABLED`
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable/disable tool-call budget tracking per session
- **Environment Variable**: `BUDGET_TRACKING_ENABLED`
- **Example**: `BUDGET_TRACKING_ENABLED=true`
- **Notes**:
  - When disabled, no budget limits are enforced
  - Recommended to keep enabled in production

#### `MAX_TOOL_CALLS_PER_SESSION`
- **Type**: Integer
- **Default**: `100`
- **Description**: Maximum tool calls allowed per session
- **Environment Variable**: `MAX_TOOL_CALLS_PER_SESSION`
- **Example**: `MAX_TOOL_CALLS_PER_SESSION=100`
- **Notes**:
  - Typical user sessions use 5-20 tool calls
  - Set higher for complex multi-step workflows
  - Set lower for cost-sensitive environments
  - Recommended range: 50-500

#### `SESSION_BUDGET_TTL_SECONDS`
- **Type**: Integer
- **Default**: `3600` (1 hour)
- **Description**: TTL for session budget tracking in seconds
- **Environment Variable**: `SESSION_BUDGET_TTL_SECONDS`
- **Example**: `SESSION_BUDGET_TTL_SECONDS=3600`
- **Notes**:
  - Budget counter resets after this duration
  - Typical sessions last 5-30 minutes
  - Set to match your expected session duration
  - Recommended range: 300-7200 seconds

### Loop Detection (Requirements: 15.4)

Loop detection prevents agents from repeatedly calling the same tool with identical parameters, which indicates a stuck or confused agent.

#### `LOOP_DETECTION_ENABLED`
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable/disable loop detection for repeated identical tool calls
- **Environment Variable**: `LOOP_DETECTION_ENABLED`
- **Example**: `LOOP_DETECTION_ENABLED=true`
- **Notes**:
  - When disabled, no loop detection is performed
  - Recommended to keep enabled in production

#### `MAX_IDENTICAL_CALLS`
- **Type**: Integer
- **Default**: `3`
- **Description**: Maximum identical calls allowed before blocking
- **Environment Variable**: `MAX_IDENTICAL_CALLS`
- **Example**: `MAX_IDENTICAL_CALLS=3`
- **Notes**:
  - Identical = same tool + same parameters
  - Legitimate retries are typically 1-2 times
  - Set to 2-5 depending on retry tolerance
  - Recommended: 3

#### `LOOP_DETECTION_WINDOW_SECONDS`
- **Type**: Integer
- **Default**: `300` (5 minutes)
- **Description**: Time window for tracking identical calls in seconds
- **Environment Variable**: `LOOP_DETECTION_WINDOW_SECONDS`
- **Example**: `LOOP_DETECTION_WINDOW_SECONDS=300`
- **Notes**:
  - Identical calls outside this window are not counted
  - Typical sessions last 5-30 minutes
  - Set to match your expected session duration
  - Recommended range: 60-600 seconds

### Security Monitoring (Requirements: 16.4)

Security monitoring tracks suspicious activity like unknown tool invocations and applies rate limiting.

#### `SECURITY_MONITORING_ENABLED`
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable/disable security event monitoring and rate limiting
- **Environment Variable**: `SECURITY_MONITORING_ENABLED`
- **Example**: `SECURITY_MONITORING_ENABLED=true`
- **Notes**:
  - When disabled, no security monitoring is performed
  - Recommended to keep enabled in production

#### `MAX_UNKNOWN_TOOL_ATTEMPTS`
- **Type**: Integer
- **Default**: `5`
- **Description**: Maximum unknown tool attempts allowed per session before rate limiting
- **Environment Variable**: `MAX_UNKNOWN_TOOL_ATTEMPTS`
- **Example**: `MAX_UNKNOWN_TOOL_ATTEMPTS=5`
- **Notes**:
  - Unknown tool = tool not registered in MCP server
  - Legitimate attempts are typically 0-1
  - Set to 3-10 depending on tolerance
  - Recommended: 5

#### `SECURITY_EVENT_WINDOW_SECONDS`
- **Type**: Integer
- **Default**: `300` (5 minutes)
- **Description**: Time window for tracking security events in seconds
- **Environment Variable**: `SECURITY_EVENT_WINDOW_SECONDS`
- **Example**: `SECURITY_EVENT_WINDOW_SECONDS=300`
- **Notes**:
  - Security event counters reset after this duration
  - Typical sessions last 5-30 minutes
  - Set to match your expected session duration
  - Recommended range: 60-600 seconds

### Timeout Configuration (Requirements: 16.1, 16.2)

Timeouts prevent tools from hanging indefinitely and consuming resources.

#### `TOOL_EXECUTION_TIMEOUT_SECONDS`
- **Type**: Integer
- **Default**: `30`
- **Description**: Maximum time allowed for a single tool execution in seconds
- **Environment Variable**: `TOOL_EXECUTION_TIMEOUT_SECONDS`
- **Example**: `TOOL_EXECUTION_TIMEOUT_SECONDS=30`
- **Notes**:
  - Prevents tools from hanging indefinitely
  - Typical tool execution: 1-10 seconds
  - Set based on your AWS API response times
  - Recommended range: 15-60 seconds

#### `AWS_API_TIMEOUT_SECONDS`
- **Type**: Integer
- **Default**: `10`
- **Description**: Timeout for AWS API calls in seconds
- **Environment Variable**: `AWS_API_TIMEOUT_SECONDS`
- **Example**: `AWS_API_TIMEOUT_SECONDS=10`
- **Notes**:
  - Prevents AWS API calls from hanging
  - Typical AWS API response: 1-5 seconds
  - Set based on your network latency
  - Recommended range: 5-30 seconds

#### `REDIS_TIMEOUT_SECONDS`
- **Type**: Integer
- **Default**: `5`
- **Description**: Timeout for Redis operations in seconds
- **Environment Variable**: `REDIS_TIMEOUT_SECONDS`
- **Example**: `REDIS_TIMEOUT_SECONDS=5`
- **Notes**:
  - Prevents Redis operations from hanging
  - Typical Redis operation: < 1 second
  - Set based on your Redis latency
  - Recommended range: 2-10 seconds

#### `HTTP_REQUEST_TIMEOUT_SECONDS`
- **Type**: Integer
- **Default**: `30`
- **Description**: Timeout for HTTP requests in seconds
- **Environment Variable**: `HTTP_REQUEST_TIMEOUT_SECONDS`
- **Example**: `HTTP_REQUEST_TIMEOUT_SECONDS=30`
- **Notes**:
  - Prevents HTTP requests from hanging
  - Typical HTTP request: 1-10 seconds
  - Set based on your network conditions
  - Recommended range: 15-60 seconds

### Rate Limiting Configuration (Requirements: 16.2)

Rate limiting prevents abuse and resource exhaustion by limiting request frequency.

#### `RATE_LIMIT_ENABLED`
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable/disable rate limiting for API requests
- **Environment Variable**: `RATE_LIMIT_ENABLED`
- **Example**: `RATE_LIMIT_ENABLED=true`
- **Notes**:
  - When disabled, no rate limiting is performed
  - Recommended to keep enabled in production

#### `RATE_LIMIT_REQUESTS_PER_MINUTE`
- **Type**: Integer
- **Default**: `60`
- **Description**: Maximum requests allowed per minute per IP
- **Environment Variable**: `RATE_LIMIT_REQUESTS_PER_MINUTE`
- **Example**: `RATE_LIMIT_REQUESTS_PER_MINUTE=60`
- **Notes**:
  - Typical user: 1-5 requests per minute
  - Set to 60 for normal usage
  - Set to 10-20 for strict rate limiting
  - Set to 100+ for high-volume usage
  - Recommended range: 10-200

#### `RATE_LIMIT_BURST_SIZE`
- **Type**: Integer
- **Default**: `10`
- **Description**: Burst size for rate limiting (requests allowed in quick succession)
- **Environment Variable**: `RATE_LIMIT_BURST_SIZE`
- **Example**: `RATE_LIMIT_BURST_SIZE=10`
- **Notes**:
  - Allows temporary spikes in request rate
  - Typical burst: 5-20 requests
  - Set to 10 for normal usage
  - Set to 5 for strict rate limiting
  - Recommended range: 5-50

## Configuration Profiles

### Development Profile

For local development with relaxed security:

```bash
REQUEST_SANITIZATION_ENABLED=false
BUDGET_TRACKING_ENABLED=false
LOOP_DETECTION_ENABLED=false
SECURITY_MONITORING_ENABLED=false
RATE_LIMIT_ENABLED=false

TOOL_EXECUTION_TIMEOUT_SECONDS=60
AWS_API_TIMEOUT_SECONDS=30
REDIS_TIMEOUT_SECONDS=10
HTTP_REQUEST_TIMEOUT_SECONDS=60
```

### Staging Profile

For staging environments with moderate security:

```bash
REQUEST_SANITIZATION_ENABLED=true
MAX_REQUEST_SIZE_BYTES=10485760
MAX_HEADER_SIZE_BYTES=8192
MAX_HEADER_COUNT=50

BUDGET_TRACKING_ENABLED=true
MAX_TOOL_CALLS_PER_SESSION=200
SESSION_BUDGET_TTL_SECONDS=3600

LOOP_DETECTION_ENABLED=true
MAX_IDENTICAL_CALLS=3
LOOP_DETECTION_WINDOW_SECONDS=300

SECURITY_MONITORING_ENABLED=true
MAX_UNKNOWN_TOOL_ATTEMPTS=5
SECURITY_EVENT_WINDOW_SECONDS=300

RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
RATE_LIMIT_BURST_SIZE=10

TOOL_EXECUTION_TIMEOUT_SECONDS=30
AWS_API_TIMEOUT_SECONDS=10
REDIS_TIMEOUT_SECONDS=5
HTTP_REQUEST_TIMEOUT_SECONDS=30
```

### Production Profile

For production environments with strict security:

```bash
# Production Security (NEW)
AUTH_ENABLED=true
API_KEYS=your-secure-key-here  # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
AUTH_REALM=mcp-server
CORS_ALLOWED_ORIGINS=https://claude.ai
TLS_ENABLED=true
CLOUDWATCH_METRICS_ENABLED=true
PROJECT_NAME=mcp-tagging

# Request Sanitization
REQUEST_SANITIZATION_ENABLED=true
MAX_REQUEST_SIZE_BYTES=5242880  # 5 MB
MAX_HEADER_SIZE_BYTES=4096      # 4 KB
MAX_HEADER_COUNT=30

# Budget Tracking
BUDGET_TRACKING_ENABLED=true
MAX_TOOL_CALLS_PER_SESSION=50
SESSION_BUDGET_TTL_SECONDS=1800  # 30 minutes

# Loop Detection
LOOP_DETECTION_ENABLED=true
MAX_IDENTICAL_CALLS=2
LOOP_DETECTION_WINDOW_SECONDS=300

# Security Monitoring
SECURITY_MONITORING_ENABLED=true
MAX_UNKNOWN_TOOL_ATTEMPTS=3
SECURITY_EVENT_WINDOW_SECONDS=300

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=30
RATE_LIMIT_BURST_SIZE=5

# Timeouts
TOOL_EXECUTION_TIMEOUT_SECONDS=30
AWS_API_TIMEOUT_SECONDS=10
REDIS_TIMEOUT_SECONDS=5
HTTP_REQUEST_TIMEOUT_SECONDS=30
```

### High-Security Profile

For highly sensitive environments:

```bash
REQUEST_SANITIZATION_ENABLED=true
MAX_REQUEST_SIZE_BYTES=1048576  # 1 MB
MAX_HEADER_SIZE_BYTES=2048      # 2 KB
MAX_HEADER_COUNT=20

BUDGET_TRACKING_ENABLED=true
MAX_TOOL_CALLS_PER_SESSION=25
SESSION_BUDGET_TTL_SECONDS=900   # 15 minutes

LOOP_DETECTION_ENABLED=true
MAX_IDENTICAL_CALLS=1
LOOP_DETECTION_WINDOW_SECONDS=300

SECURITY_MONITORING_ENABLED=true
MAX_UNKNOWN_TOOL_ATTEMPTS=1
SECURITY_EVENT_WINDOW_SECONDS=300

RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=10
RATE_LIMIT_BURST_SIZE=2

TOOL_EXECUTION_TIMEOUT_SECONDS=20
AWS_API_TIMEOUT_SECONDS=8
REDIS_TIMEOUT_SECONDS=3
HTTP_REQUEST_TIMEOUT_SECONDS=20
```

## Security Layers

### Layer 1: Request Validation

The request sanitization middleware validates all incoming requests:

1. **Size Limits**: Rejects requests exceeding `MAX_REQUEST_SIZE_BYTES`
2. **Header Validation**: 
   - Rejects requests with > `MAX_HEADER_COUNT` headers
   - Rejects requests with header size > `MAX_HEADER_SIZE_BYTES`
3. **Query String Validation**: Rejects query strings > `MAX_QUERY_STRING_LENGTH`
4. **Path Validation**: Rejects paths > `MAX_PATH_LENGTH`

**Response on Validation Failure**:
```json
{
  "error": "request_validation_failed",
  "message": "Request validation failed: [reason]"
}
```

### Layer 2: Tool Invocation Validation

Before executing any tool:

1. **Tool Registration Check**: Verify tool is registered in MCP server
2. **Schema Validation**: Validate parameters against tool schema
3. **Budget Check**: Verify session hasn't exceeded tool call budget
4. **Loop Detection**: Check for repeated identical calls

**Response on Validation Failure**:
```json
{
  "error": "tool_validation_failed",
  "message": "[specific reason]"
}
```

### Layer 3: Execution Monitoring

During tool execution:

1. **Timeout Enforcement**: Tools must complete within configured timeout
2. **Error Sanitization**: All errors are sanitized before returning to user
3. **Audit Logging**: All invocations are logged with correlation IDs

### Layer 4: Response Sanitization

All responses are sanitized to prevent information leakage:

1. **Credential Redaction**: AWS keys, passwords, tokens are redacted
2. **Path Redaction**: File paths, Docker paths are redacted
3. **Stack Trace Removal**: Internal stack traces are never exposed
4. **Error Code Mapping**: Generic error codes instead of raw exceptions

## Monitoring and Alerting

### Health Endpoint

The `/health` endpoint includes security metrics:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "security": {
    "request_sanitization_enabled": true,
    "budget_tracking_enabled": true,
    "loop_detection_enabled": true,
    "security_monitoring_enabled": true,
    "active_sessions": 5,
    "budget_exhausted_count": 0,
    "loop_detected_count": 0,
    "security_events_count": 2
  }
}
```

### CloudWatch Logs

Security events are logged to CloudWatch with correlation IDs:

```
[2024-01-15 10:30:45] SECURITY [correlation-id-123] Unknown tool invocation: tool_name=invalid_tool
[2024-01-15 10:31:12] SECURITY [correlation-id-124] Budget exhausted: session_id=sess-456, calls=100
[2024-01-15 10:32:00] SECURITY [correlation-id-125] Loop detected: tool=check_tag_compliance, count=3
```

## Best Practices

### 1. Start Conservative, Relax as Needed

Begin with strict limits and relax them based on actual usage patterns:

```bash
# Start with strict limits
MAX_TOOL_CALLS_PER_SESSION=25
MAX_IDENTICAL_CALLS=1

# Monitor for 1 week
# If no issues, gradually increase
MAX_TOOL_CALLS_PER_SESSION=50
MAX_IDENTICAL_CALLS=2
```

### 2. Monitor Security Events

Regularly review security logs for patterns:

```bash
# Check for budget exhaustion
grep "budget_exhausted" /var/log/mcp-server.log | wc -l

# Check for loop detection
grep "loop_detected" /var/log/mcp-server.log | wc -l

# Check for unknown tool attempts
grep "unknown_tool" /var/log/mcp-server.log | wc -l
```

### 3. Adjust Based on Usage Patterns

Analyze actual usage to set appropriate limits:

```bash
# Find max tool calls in a session
grep "tool_invocation" /var/log/mcp-server.log | \
  awk '{print $NF}' | sort | uniq -c | sort -rn | head -1

# Find max identical calls
grep "identical_call" /var/log/mcp-server.log | \
  awk '{print $NF}' | sort | uniq -c | sort -rn | head -1
```

### 4. Use Correlation IDs for Tracing

All security events include correlation IDs for end-to-end tracing:

```bash
# Trace all events for a specific session
grep "correlation-id-123" /var/log/mcp-server.log
```

### 5. Document Your Configuration

Keep a record of why each limit was set:

```markdown
# Security Configuration Rationale

## MAX_TOOL_CALLS_PER_SESSION=100
- Typical user sessions use 5-20 calls
- Set to 100 to allow for complex workflows
- Monitored for 2 weeks with no issues
- Increased from 50 on 2024-01-15

## MAX_IDENTICAL_CALLS=3
- Legitimate retries are typically 1-2 times
- Set to 3 to allow for transient failures
- No false positives observed
```

## Troubleshooting

### Budget Exhausted Errors

**Symptom**: Users getting "budget_exceeded" errors

**Solution**:
1. Check actual usage: `grep "tool_invocation" logs | wc -l`
2. Increase `MAX_TOOL_CALLS_PER_SESSION` if legitimate
3. Investigate if agent is stuck in a loop

### Loop Detection False Positives

**Symptom**: Legitimate retries being blocked

**Solution**:
1. Increase `MAX_IDENTICAL_CALLS` from 3 to 4-5
2. Increase `LOOP_DETECTION_WINDOW_SECONDS` if retries span longer
3. Check if agent is actually stuck or just retrying

### Request Validation Failures

**Symptom**: Valid requests being rejected

**Solution**:
1. Check which limit is being exceeded: `grep "request_validation_failed" logs`
2. Increase the appropriate limit:
   - Large payloads: increase `MAX_REQUEST_SIZE_BYTES`
   - Many headers: increase `MAX_HEADER_COUNT`
   - Long paths: increase `MAX_PATH_LENGTH`

## Compliance

This configuration satisfies the following requirements:

- **Requirement 16.1**: Only registered tools are executed
- **Requirement 16.2**: Request sanitization prevents injection attacks
- **Requirement 16.5**: Error messages never expose sensitive information
- **Requirement 15.3**: Tool-call budgets prevent runaway behavior
- **Requirement 15.4**: Loop detection prevents stuck agents

## Related Documentation

- [ERROR_SANITIZATION_GUIDE.md](ERROR_SANITIZATION_GUIDE.md) - Error message sanitization
- [AUDIT_LOGGING.md](AUDIT_LOGGING.md) - Audit logging configuration
- [CLOUDWATCH_LOGGING.md](CLOUDWATCH_LOGGING.md) - CloudWatch integration
- [.env.example](.env.example) - Environment variable template
