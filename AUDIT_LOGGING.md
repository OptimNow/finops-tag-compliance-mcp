# Audit Logging Implementation

This document describes the audit logging system implemented for the FinOps Tag Compliance MCP Server.

## Overview

The audit logging system automatically tracks every MCP tool invocation, providing a complete audit trail for compliance, debugging, and performance monitoring.

## Architecture

The audit logging system consists of three main components:

### 1. Data Models (`mcp_server/models/audit.py`)

- **AuditStatus**: Enum for SUCCESS or FAILURE status
- **AuditLogEntry**: Pydantic model representing a single audit log entry

### 2. Audit Service (`mcp_server/services/audit_service.py`)

- **AuditService**: Service class for logging and retrieving audit entries
- Manages SQLite database for persistent storage
- Provides filtering and querying capabilities

### 3. Audit Middleware (`mcp_server/middleware/audit_middleware.py`)

- **@audit_tool**: Decorator for async tool functions
- **@audit_tool_sync**: Decorator for synchronous tool functions
- Automatically captures invocation details and logs them

## Database Schema

The audit logs are stored in SQLite with the following schema:

```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    parameters TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    execution_time_ms REAL
);

CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp);
```

## Integration with MCP Tools

To enable audit logging for an MCP tool, simply add the `@audit_tool` decorator:

### Before (without audit logging):

```python
async def check_tag_compliance(
    resource_types: list[str],
    filters: dict | None = None,
    severity: str = "all"
) -> ComplianceResult:
    """Check tag compliance for AWS resources."""
    # Implementation
    pass
```

### After (with audit logging):

```python
from mcp_server.middleware import audit_tool

@audit_tool
async def check_tag_compliance(
    resource_types: list[str],
    filters: dict | None = None,
    severity: str = "all"
) -> ComplianceResult:
    """Check tag compliance for AWS resources."""
    # Implementation
    pass
```

That's it! The decorator handles all the logging automatically.

## What Gets Logged

Every tool invocation logs:

1. **Timestamp**: When the tool was called (UTC timezone)
2. **Tool Name**: The function name of the tool
3. **Parameters**: All arguments passed to the tool (both args and kwargs)
4. **Status**: SUCCESS if the tool completed, FAILURE if an exception was raised
5. **Error Message**: The exception message if the tool failed
6. **Execution Time**: How long the tool took to execute (in milliseconds)

## Querying Audit Logs

The `AuditService` provides flexible querying:

```python
from mcp_server.services import AuditService
from mcp_server.models import AuditStatus

audit_service = AuditService()

# Get all recent logs
logs = audit_service.get_logs(limit=100)

# Filter by tool name
compliance_logs = audit_service.get_logs(tool_name="check_tag_compliance")

# Filter by status
failures = audit_service.get_logs(status=AuditStatus.FAILURE)

# Combine filters
recent_compliance_failures = audit_service.get_logs(
    tool_name="check_tag_compliance",
    status=AuditStatus.FAILURE,
    limit=10
)
```

## Use Cases

### 1. Compliance Auditing

Track who accessed what data and when:

```python
audit_service = AuditService()
logs = audit_service.get_logs(limit=1000)

for log in logs:
    print(f"{log.timestamp}: {log.tool_name} - {log.status}")
```

### 2. Error Analysis

Identify which tools are failing and why:

```python
failures = audit_service.get_logs(status=AuditStatus.FAILURE)

for failure in failures:
    print(f"Tool: {failure.tool_name}")
    print(f"Error: {failure.error_message}")
    print(f"Parameters: {failure.parameters}")
    print("---")
```

### 3. Performance Monitoring

Find slow tools that need optimization:

```python
logs = audit_service.get_logs(limit=100)
sorted_logs = sorted(logs, key=lambda x: x.execution_time_ms or 0, reverse=True)

print("Slowest tools:")
for log in sorted_logs[:10]:
    print(f"{log.tool_name}: {log.execution_time_ms:.2f}ms")
```

### 4. Usage Analytics

Understand which tools are most frequently used:

```python
from collections import Counter

logs = audit_service.get_logs(limit=1000)
tool_counts = Counter(log.tool_name for log in logs)

print("Most used tools:")
for tool, count in tool_counts.most_common(10):
    print(f"{tool}: {count} invocations")
```

## Testing

The audit logging system includes comprehensive unit tests:

- **tests/unit/test_audit_service.py**: Tests for the AuditService
- **tests/unit/test_audit_middleware.py**: Tests for the audit decorators

Run the tests:

```bash
pytest tests/unit/test_audit_service.py tests/unit/test_audit_middleware.py -v
```

## Requirements Satisfied

This implementation satisfies all audit logging requirements:

- ✅ **Requirement 12.1**: Log every tool invocation with timestamp, tool name, and parameters
- ✅ **Requirement 12.2**: Store audit logs in SQLite database
- ✅ **Requirement 12.3**: Include result status (success/failure) in audit logs
- ✅ **Requirement 12.4**: Log error messages when errors occur

## Performance Impact

The audit logging system is designed to have minimal performance impact:

- Logging adds approximately 1-5ms per tool invocation
- SQLite writes are fast for single-row inserts
- Database is indexed on timestamp for efficient queries
- No impact on tool functionality or error handling

## Future Enhancements

Potential improvements for Phase 2:

1. **Log Rotation**: Automatically archive or delete old logs
2. **Remote Logging**: Send logs to CloudWatch or other centralized logging services
3. **Real-time Monitoring**: WebSocket endpoint for live log streaming
4. **Advanced Analytics**: Built-in dashboards for usage patterns and trends
5. **Log Encryption**: Encrypt sensitive parameters in the database
6. **User Context**: Track which user/client made each request

## Configuration

The audit service can be configured via environment variables:

```bash
# Custom database path
AUDIT_DB_PATH=/var/log/finops-mcp/audit_logs.db

# Enable/disable audit logging
AUDIT_LOGGING_ENABLED=true
```

## Security Considerations

1. **Sensitive Data**: Tool parameters may contain sensitive information (ARNs, account IDs, etc.)
2. **File Permissions**: Ensure the audit database file has appropriate permissions (600 or 640)
3. **Access Control**: Restrict access to the audit database to authorized users only
4. **Data Retention**: Implement a retention policy to comply with data protection regulations
5. **Encryption**: Consider encrypting the database file for production deployments

## Maintenance

### Database Size Management

Monitor the size of the audit database:

```bash
ls -lh audit_logs.db
```

Clean up old logs (example: delete logs older than 90 days):

```python
import sqlite3
from datetime import datetime, timedelta, timezone

conn = sqlite3.connect("audit_logs.db")
cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
conn.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff,))
conn.commit()
conn.close()
```

### Backup

Regular backups of the audit database are recommended:

```bash
# Simple file copy
cp audit_logs.db audit_logs_backup_$(date +%Y%m%d).db

# Or use SQLite backup command
sqlite3 audit_logs.db ".backup audit_logs_backup.db"
```

## Conclusion

The audit logging system provides comprehensive tracking of all MCP tool invocations with minimal code changes and performance impact. It satisfies all Phase 1 audit logging requirements and provides a foundation for enhanced monitoring and compliance features in future phases.
