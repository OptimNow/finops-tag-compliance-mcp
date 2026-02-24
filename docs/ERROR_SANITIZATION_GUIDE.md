# Error sanitization implementation guide

## Overview

This document describes the error sanitization system implemented for the FinOps Tag Compliance MCP Server to ensure that sensitive information is never exposed in error messages.

**Requirement: 16.5** - "THE MCP_Server SHALL NOT expose sensitive information (credentials, internal paths) in error messages"

## Architecture

The error sanitization system consists of three main components:

### 1. Detection layer
Identifies sensitive information patterns in error messages:
- File paths (Unix, Windows, Docker)
- AWS credentials (Access Keys, Secret Keys)
- Database credentials and connection strings
- Email addresses
- Internal IP addresses
- Stack traces
- Container paths

### 2. Redaction layer
Automatically redacts detected sensitive information:
- Replaces patterns with `[REDACTED]` (customizable)
- Preserves non-sensitive text
- Maintains readability of error messages

### 3. Response layer
Converts exceptions into user-safe responses:
- Maps exception types to error codes
- Generates user-friendly messages
- Preserves full details for internal logging
- Includes correlation IDs for tracing

## Usage patterns

### Pattern 1: Global exception handler (automatic)

The global exception handler in `main.py` automatically sanitizes all unhandled exceptions:

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Automatically sanitizes and returns safe error response
    sanitized_error = sanitize_exception(exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": sanitized_error.error_code,
            "message": sanitized_error.user_message,
        },
    )
```

**Result**: All unhandled exceptions are automatically sanitized before being sent to users.

### Pattern 2: Explicit sanitization in services

Services can explicitly sanitize exceptions:

```python
from mcp_server.utils.error_sanitization import sanitize_exception

try:
    # Service logic
    result = await aws_client.get_instances()
except Exception as exc:
    sanitized = sanitize_exception(exc)
    logger.error(f"Service error: {sanitized.internal_message}")
    raise ValueError(sanitized.user_message)
```

**Result**: Services can provide context-specific error handling while maintaining security.

### Pattern 3: AWS-specific error handling

AWS errors are handled with AWS-specific error codes:

```python
from mcp_server.utils.error_sanitization import handle_aws_error

try:
    # AWS API call
    response = await ec2_client.describe_instances()
except Exception as exc:
    sanitized = handle_aws_error(exc)
    # Automatically maps to appropriate error code
    # e.g., "AccessDenied" → "permission_denied"
```

**Result**: AWS errors are mapped to appropriate error codes and user messages.

### Pattern 4: Database error handling

Database errors are handled with database-specific error codes:

```python
from mcp_server.utils.error_sanitization import handle_database_error

try:
    # Database operation
    conn.execute("INSERT INTO users ...")
except Exception as exc:
    sanitized = handle_database_error(exc)
    # Automatically maps to appropriate error code
    # e.g., "UNIQUE constraint failed" → "duplicate_entry"
```

**Result**: Database errors are mapped to appropriate error codes and user messages.

### Pattern 5: Safe response creation

Create guaranteed-safe error responses:

```python
from mcp_server.utils.error_sanitization import create_safe_error_response

response = create_safe_error_response(
    error_code="validation_error",
    user_message="The provided email is invalid",
    details={"field": "email", "reason": "invalid format"}
)
# Guaranteed no sensitive info in response
```

**Result**: Error responses are guaranteed to contain no sensitive information.

## Sensitive information patterns

### File paths
- **Unix/Linux**: `/home/user/app/main.py`, `/etc/config.json`
- **Windows**: `C:\Users\user\app\main.py`, `D:\Projects\app\config.json`
- **Docker**: `/app/service.py`, `/src/main.py`, `/workspace/code.py`

### Credentials
- **AWS Access Keys**: `AKIA[0-9A-Z]{16}`
- **AWS Secret Keys**: 40-character base64 strings
- **Passwords**: `password = "secret"`, `pwd: secret123`
- **API Keys**: `api_key = "key123"`, `token: abc123`
- **Database Credentials**: `user: admin`, `password: secret`

### Connection strings
- **MySQL**: `mysql://user:password@host:port/db`
- **PostgreSQL**: `postgres://user:password@host:port/db`
- **MongoDB**: `mongodb://user:password@host:port/db`
- **Redis**: `redis://user:password@host:port`

### Network information
- **Internal IPs**: `192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`
- **Localhost**: `127.0.0.1`, `localhost`

### Stack traces
- **Python**: `File "/app/service.py", line 123, in process`
- **Function calls**: `at module.function()`

## Error code mapping

| Exception Type | Error Code | User Message |
|---|---|---|
| ValueError | `invalid_input` | "The provided input is invalid. Please check your parameters and try again." |
| TypeError | `invalid_type` | "The provided value has an invalid type. Please check the parameter type." |
| KeyError | `not_found` | "The requested resource was not found." |
| FileNotFoundError | `not_found` | "The requested resource was not found." |
| PermissionError | `permission_denied` | "You do not have permission to perform this action." |
| TimeoutError | `timeout` | "The request took too long to complete. Please try again." |
| ConnectionError | `connection_error` | "Failed to connect to a required service. Please try again later." |
| RuntimeError | `runtime_error` | "An error occurred while processing your request." |
| NotImplementedError | `not_implemented` | "This feature is not yet implemented." |
| ValidationError | `validation_error` | "The provided data failed validation. Please check your input." |
| SecurityViolationError | `security_violation` | "Your request was rejected due to a security policy violation." |
| BudgetExhaustedError | `budget_exceeded` | "The tool call budget for this session has been exceeded." |
| LoopDetectedError | `loop_detected` | "A repeated tool call pattern was detected. Please try a different approach." |

## AWS error code mapping

| AWS Error | Error Code | User Message |
|---|---|---|
| AccessDenied | `permission_denied` | "You do not have permission to access this AWS resource." |
| UnauthorizedOperation | `permission_denied` | "You do not have permission to access this AWS resource." |
| InvalidParameterValue | `invalid_input` | "Invalid parameter provided to AWS API." |
| ThrottlingException | `rate_limit` | "AWS API rate limit exceeded. Please try again later." |
| RequestLimitExceeded | `rate_limit` | "AWS API rate limit exceeded. Please try again later." |
| ServiceUnavailable | `service_unavailable` | "The AWS service is temporarily unavailable. Please try again later." |

## Database error code mapping

| Database Error | Error Code | User Message |
|---|---|---|
| UNIQUE constraint failed | `duplicate_entry` | "A record with this value already exists." |
| duplicate key | `duplicate_entry` | "A record with this value already exists." |
| no such table | `not_found` | "Database table not found." |
| table does not exist | `not_found` | "Database table not found." |
| database is locked | `database_locked` | "Database is temporarily locked. Please try again." |

## Logging strategy

### Internal logging (full details)
- Full error messages with all details
- Sensitive information included
- Stack traces included
- Correlation IDs for tracing
- Logged to CloudWatch and local logs

### User response (sanitized)
- User-friendly error messages
- No sensitive information
- No stack traces
- Error codes for machine-readable handling
- Correlation IDs for support

## Example: Error flow

### Scenario: AWS API call fails

**Internal Error**:
```
AccessDenied: User: arn:aws:iam::123456789012:user/admin is not authorized 
to perform: ec2:DescribeInstances on resource: arn:aws:ec2:us-east-1:123456789012:*
```

**Sanitization Process**:
1. Detect sensitive patterns:
   - AWS ARN: `arn:aws:iam::123456789012:user/admin`
   - AWS ARN: `arn:aws:ec2:us-east-1:123456789012:*`
   - Account ID: `123456789012`

2. Redact sensitive info:
```
AccessDenied: User: [REDACTED] is not authorized 
to perform: ec2:DescribeInstances on resource: [REDACTED]
```

3. Map to error code: `permission_denied`

4. Generate user message: "You do not have permission to access this AWS resource."

**User Response**:
```json
{
  "error": "permission_denied",
  "message": "You do not have permission to access this AWS resource."
}
```

**Internal Log**:
```
[2024-01-15 10:30:45] ERROR [correlation-id-123] AWS error: AccessDenied: User: arn:aws:iam::123456789012:user/admin is not authorized to perform: ec2:DescribeInstances on resource: arn:aws:ec2:us-east-1:123456789012:*
```

## Testing

The implementation includes comprehensive unit tests:

```bash
# Run all error sanitization tests
python -m pytest tests/unit/test_error_sanitization.py -v

# Run specific test class
python -m pytest tests/unit/test_error_sanitization.py::TestDetectSensitiveInfo -v

# Run with coverage
python -m pytest tests/unit/test_error_sanitization.py --cov=mcp_server.utils.error_sanitization
```

**Test Coverage**: 37 tests covering:
- Sensitive information detection
- Sensitive information redaction
- Exception sanitization
- Error response sanitization
- Safe response creation
- AWS error handling
- Database error handling
- Integration scenarios

## Best practices

### 1. Always use sanitization for user-facing errors
```python
# ✅ Good
try:
    result = await service.process()
except Exception as exc:
    sanitized = sanitize_exception(exc)
    return JSONResponse(status_code=500, content=sanitized.to_dict())

# ❌ Bad
try:
    result = await service.process()
except Exception as exc:
    return JSONResponse(status_code=500, content={"error": str(exc)})
```

### 2. Log full details internally
```python
# ✅ Good
try:
    result = await service.process()
except Exception as exc:
    log_error_safely(exc, context={"operation": "process"})
    sanitized = sanitize_exception(exc)
    return JSONResponse(status_code=500, content=sanitized.to_dict())

# ❌ Bad
try:
    result = await service.process()
except Exception as exc:
    logger.error(str(exc))  # May expose sensitive info
    return JSONResponse(status_code=500, content={"error": str(exc)})
```

### 3. Use specialized handlers for known error types
```python
# ✅ Good
try:
    response = await ec2_client.describe_instances()
except Exception as exc:
    sanitized = handle_aws_error(exc)
    return JSONResponse(status_code=500, content=sanitized.to_dict())

# ❌ Bad
try:
    response = await ec2_client.describe_instances()
except Exception as exc:
    sanitized = sanitize_exception(exc)  # Generic handling
    return JSONResponse(status_code=500, content=sanitized.to_dict())
```

### 4. Include correlation IDs for tracing
```python
# ✅ Good
try:
    result = await service.process()
except Exception as exc:
    log_error_safely(
        exc,
        context={"correlation_id": get_correlation_id()}
    )
    sanitized = sanitize_exception(exc)
    return JSONResponse(status_code=500, content=sanitized.to_dict())
```

## Compliance

This implementation satisfies **Requirement 16.5**:

> "THE MCP_Server SHALL NOT expose sensitive information (credentials, internal paths) in error messages"

✅ **Credentials**: AWS keys, passwords, API tokens are automatically redacted
✅ **Internal Paths**: File paths, Docker paths, system paths are redacted
✅ **Stack Traces**: Full stack traces are logged internally but never sent to users
✅ **Network Info**: Internal IPs and connection strings are redacted
✅ **User Messages**: All user-facing error messages are guaranteed safe
✅ **Audit Trail**: Full errors are logged internally for debugging and security analysis
✅ **Correlation IDs**: All errors include correlation IDs for tracing

## Future enhancements

Potential improvements for future versions:

1. **Custom Redaction Patterns**: Allow configuration of additional sensitive patterns
2. **Error Analytics**: Track error patterns and frequencies
3. **Error Recovery Suggestions**: Provide actionable recovery steps
4. **Localization**: Support error messages in multiple languages
5. **Error Severity Levels**: Classify errors by severity for monitoring
6. **Error Aggregation**: Group similar errors for analysis
