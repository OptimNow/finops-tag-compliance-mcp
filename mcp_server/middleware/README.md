# Audit Middleware

The audit middleware provides automatic logging of all MCP tool invocations for compliance and debugging purposes.

## Features

- **Automatic Logging**: Every tool invocation is logged with timestamp, parameters, and result status
- **Error Tracking**: Failed invocations are logged with error messages
- **Performance Monitoring**: Execution time is tracked for each invocation
- **SQLite Storage**: All audit logs are stored in a local SQLite database
- **Query Support**: Retrieve logs with filtering by tool name, status, and time range

## Usage

### Decorating Async Tools

For async tools (most MCP tools), use the `@audit_tool` decorator:

```python
from mcp_server.middleware import audit_tool
from mcp_server.models import ComplianceResult

@audit_tool
async def check_tag_compliance(
    resource_types: list[str],
    filters: dict | None = None,
    severity: str = "all"
) -> ComplianceResult:
    """Check tag compliance for AWS resources."""
    # Tool implementation
    pass
```

### Decorating Sync Tools

For synchronous tools, use the `@audit_tool_sync` decorator:

```python
from mcp_server.middleware import audit_tool_sync

@audit_tool_sync
def get_policy_config() -> dict:
    """Get policy configuration."""
    # Tool implementation
    pass
```

## What Gets Logged

Each audit log entry contains:

- **timestamp**: When the tool was invoked (UTC)
- **tool_name**: Name of the tool function
- **parameters**: All arguments passed to the tool (args and kwargs)
- **status**: SUCCESS or FAILURE
- **error_message**: Error message if the tool failed (None otherwise)
- **execution_time_ms**: How long the tool took to execute in milliseconds

## Retrieving Audit Logs

Use the `AuditService` to query audit logs:

```python
from mcp_server.services import AuditService
from mcp_server.models import AuditStatus

# Initialize the service
audit_service = AuditService()

# Get all logs (most recent first)
all_logs = audit_service.get_logs()

# Get logs for a specific tool
compliance_logs = audit_service.get_logs(tool_name="check_tag_compliance")

# Get only failed invocations
failed_logs = audit_service.get_logs(status=AuditStatus.FAILURE)

# Limit the number of results
recent_logs = audit_service.get_logs(limit=10)

# Combine filters
recent_failures = audit_service.get_logs(
    tool_name="check_tag_compliance",
    status=AuditStatus.FAILURE,
    limit=5
)
```

## Database Location

By default, audit logs are stored in `audit_logs.db` in the current working directory. You can specify a custom location:

```python
audit_service = AuditService(db_path="/path/to/custom/audit_logs.db")
```

## Example: Analyzing Tool Usage

```python
from mcp_server.services import AuditService

audit_service = AuditService()

# Get all logs
logs = audit_service.get_logs(limit=100)

# Calculate success rate
total = len(logs)
successful = sum(1 for log in logs if log.status == "success")
success_rate = (successful / total * 100) if total > 0 else 0

print(f"Success rate: {success_rate:.1f}%")

# Find slowest tools
sorted_by_time = sorted(logs, key=lambda x: x.execution_time_ms or 0, reverse=True)
print(f"Slowest tool: {sorted_by_time[0].tool_name} ({sorted_by_time[0].execution_time_ms:.2f}ms)")

# Count invocations by tool
from collections import Counter
tool_counts = Counter(log.tool_name for log in logs)
print(f"Most used tool: {tool_counts.most_common(1)[0]}")
```

## Requirements Satisfied

This middleware implementation satisfies the following requirements:

- **12.1**: Logs every tool invocation with timestamp, tool name, and parameters
- **12.2**: Stores audit logs in SQLite database
- **12.3**: Includes result status (success/failure) in audit logs
- **12.4**: Logs error messages when errors occur

## Performance Considerations

- Audit logging adds minimal overhead (typically < 5ms per invocation)
- SQLite writes are synchronous but fast for single-row inserts
- The database is indexed on timestamp for efficient queries
- Consider periodic cleanup of old logs to manage database size

## Security Notes

- Audit logs may contain sensitive information from tool parameters
- Ensure the audit database file has appropriate file permissions
- Consider encrypting the database file for production deployments
- Implement log rotation or archival for long-term storage
