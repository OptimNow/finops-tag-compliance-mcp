# CloudWatch Logging Integration

## Overview

The FinOps Tag Compliance MCP Server includes integrated CloudWatch logging support for operational monitoring and troubleshooting. All application logs are automatically sent to AWS CloudWatch Logs when the feature is enabled.

## Features

- **Structured Logging**: All logs include timestamp, logger name, log level, and message
- **Automatic Log Group/Stream Creation**: Creates CloudWatch log group and stream if they don't exist
- **Graceful Degradation**: Application continues to function even if CloudWatch is unavailable
- **Environment-Based Configuration**: Configure via environment variables
- **IAM Instance Profile Support**: Uses IAM instance profile for authentication (no hardcoded credentials)

## Configuration

### Environment Variables

CloudWatch logging is configured via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOUDWATCH_LOGGING_ENABLED` | `true` | Set to `false` to disable CloudWatch logging |
| `CLOUDWATCH_LOG_GROUP` | `/finops/mcp-server` | CloudWatch log group name |
| `CLOUDWATCH_LOG_STREAM` | `application` | CloudWatch log stream name |
| `AWS_REGION` | `us-east-1` | AWS region for CloudWatch |

### Example Configuration

```bash
# Enable CloudWatch logging with custom log group
export CLOUDWATCH_LOGGING_ENABLED=true
export CLOUDWATCH_LOG_GROUP=/production/tagging-mcp
export CLOUDWATCH_LOG_STREAM=mcp-server-01
export AWS_REGION=us-east-1
```

### Disabling CloudWatch Logging

To disable CloudWatch logging (useful for local development):

```bash
export CLOUDWATCH_LOGGING_ENABLED=false
```

Or pass `enable=False` when calling `configure_cloudwatch_logging()`:

```python
from mcp_server.utils.cloudwatch_logging import configure_cloudwatch_logging

configure_cloudwatch_logging(enable=False)
```

## How It Works

### Initialization

When the MCP server starts, it automatically configures CloudWatch logging:

1. Reads configuration from environment variables
2. Creates a CloudWatch handler with the specified log group and stream
3. Adds the handler to the root logger
4. All subsequent log messages are sent to CloudWatch

### Log Group and Stream Creation

The CloudWatch handler automatically creates the log group and stream if they don't exist:

- **Log Group**: Created with default settings
- **Log Stream**: Created within the log group

If the log group or stream already exists, the handler uses the existing one.

### Error Handling

If CloudWatch is unavailable or misconfigured:

- Errors are logged to stderr
- Application continues to function normally
- Console logging remains active
- No exceptions are raised

## Usage

### In Application Code

All standard Python logging calls automatically send logs to CloudWatch:

```python
import logging

logger = logging.getLogger(__name__)

# These logs are automatically sent to CloudWatch
logger.info("Application started")
logger.warning("Cache miss for resource")
logger.error("Failed to fetch AWS resources")
```

### Viewing Logs in CloudWatch

1. Open AWS CloudWatch Console
2. Navigate to Logs → Log Groups
3. Find your log group (default: `/finops/mcp-server`)
4. Click on the log stream (default: `application`)
5. View log events

### Querying Logs

Use CloudWatch Insights to query logs:

```
fields @timestamp, @message, @logStream
| filter @message like /ERROR/
| stats count() by @logStream
```

## IAM Permissions

The EC2 instance running the MCP server needs the following IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/finops/*"
    }
  ]
}
```

## Performance Considerations

- **Asynchronous Logging**: Log events are sent to CloudWatch asynchronously
- **Batching**: Multiple log events can be batched in a single API call
- **Rate Limiting**: CloudWatch has rate limits; the handler implements exponential backoff
- **Network Overhead**: Minimal impact on application performance

## Troubleshooting

### Logs Not Appearing in CloudWatch

1. **Check IAM Permissions**: Verify the EC2 instance has CloudWatch permissions
2. **Check Configuration**: Verify environment variables are set correctly
3. **Check Log Group/Stream**: Verify the log group and stream exist in CloudWatch
4. **Check Network**: Verify the EC2 instance can reach CloudWatch API
5. **Check Logs**: Look for errors in stderr or application logs

### CloudWatch API Errors

If you see errors like "ResourceAlreadyExistsException":

- This is normal and expected if the log group/stream already exists
- The handler gracefully handles these errors
- Logs will continue to be sent to the existing log group/stream

### High CloudWatch Costs

If CloudWatch logging is generating high costs:

1. Reduce log level: Set `logging.basicConfig(level=logging.WARNING)`
2. Disable CloudWatch logging: Set `CLOUDWATCH_LOGGING_ENABLED=false`
3. Use log retention policies: Set CloudWatch log retention to 7-30 days
4. Filter logs: Use CloudWatch Insights to identify high-volume log sources

## Best Practices

1. **Use Structured Logging**: Include relevant context in log messages
2. **Set Appropriate Log Levels**: Use INFO for important events, DEBUG for detailed diagnostics
3. **Monitor Log Costs**: Set CloudWatch log retention policies
4. **Use Log Insights**: Query logs to identify issues and trends
5. **Archive Old Logs**: Use CloudWatch log export to S3 for long-term storage

## Related Documentation

- [AWS CloudWatch Logs Documentation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/)
- [CloudWatch Logs Insights Query Syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html)
- [IAM Permissions for CloudWatch Logs](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/permissions-reference-cwl.html)
