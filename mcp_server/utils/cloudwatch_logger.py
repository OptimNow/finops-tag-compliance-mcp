# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""CloudWatch logging configuration and utilities.

Provides CloudWatch logging and metrics emission for the MCP server.
Includes custom metrics for security monitoring (authentication failures,
CORS violations) that trigger CloudWatch alarms.

Requirements: 23.2, 23.5
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from .correlation import get_correlation_id


class CorrelationIDFilter(logging.Filter):
    """
    Logging filter that adds correlation ID to all log records.

    This filter automatically injects the correlation ID from the
    current context into every log record, making it available for
    formatting and structured logging.

    Requirements: 15.1
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add correlation ID to the log record.

        Args:
            record: The log record to filter

        Returns:
            True to allow the record to be logged
        """
        # Get correlation ID from context
        correlation_id = get_correlation_id()

        # Add to record (will be empty string if not set)
        record.correlation_id = correlation_id if correlation_id else "-"

        return True


class CloudWatchHandler(logging.Handler):
    """Custom logging handler that sends logs to AWS CloudWatch."""

    def __init__(
        self,
        log_group: str,
        log_stream: str,
        region: str = "us-east-1",
    ):
        """
        Initialize CloudWatch logging handler.

        Args:
            log_group: CloudWatch log group name
            log_stream: CloudWatch log stream name
            region: AWS region for CloudWatch
        """
        super().__init__()
        self.log_group = log_group
        self.log_stream = log_stream
        self.region = region
        self.client = boto3.client("logs", region_name=region)
        self._ensure_log_group_and_stream()

    def _ensure_log_group_and_stream(self) -> None:
        """Create log group and stream if they don't exist."""
        try:
            # Try to create log group (will fail silently if it exists)
            try:
                self.client.create_log_group(logGroupName=self.log_group)
            except ClientError as e:
                if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                    raise

            # Try to create log stream (will fail silently if it exists)
            try:
                self.client.create_log_stream(
                    logGroupName=self.log_group,
                    logStreamName=self.log_stream,
                )
            except ClientError as e:
                if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                    raise
        except Exception as e:
            # Log to stderr if CloudWatch setup fails
            import sys

            print(f"Failed to setup CloudWatch logging: {e}", file=sys.stderr)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to CloudWatch with structured fields.

        Args:
            record: The log record to emit
        """
        try:
            # Format the message
            message = self.format(record)
            timestamp = int(record.created * 1000)

            # Get correlation ID from context
            correlation_id = get_correlation_id()

            # Create structured log entry with correlation ID
            # CloudWatch supports structured JSON in messages
            structured_message = {
                "message": message,
                "level": record.levelname,
                "logger": record.name,
                "timestamp": record.created,
            }

            # Add correlation ID if present
            if correlation_id:
                structured_message["correlation_id"] = correlation_id

            # Add any extra fields from the log record
            if hasattr(record, "correlation_id"):
                structured_message["correlation_id"] = record.correlation_id

            # Convert to JSON string for CloudWatch
            json_message = json.dumps(structured_message)

            self.client.put_log_events(
                logGroupName=self.log_group,
                logStreamName=self.log_stream,
                logEvents=[
                    {
                        "message": json_message,
                        "timestamp": timestamp,
                    }
                ],
            )
        except Exception as e:
            # Don't raise exceptions from logging handler
            # Instead, log to stderr
            import sys

            print(f"Failed to send log to CloudWatch: {e}", file=sys.stderr)


def configure_cloudwatch_logging(
    log_group: str | None = None,
    log_stream: str | None = None,
    region: str = "us-east-1",
    enable: bool = True,
) -> None:
    """
    Configure CloudWatch logging for the application.

    Adds a CloudWatch handler to the root logger if enabled.
    Can be disabled via environment variable or parameter.

    Args:
        log_group: CloudWatch log group name (default: /finops/mcp-server)
        log_stream: CloudWatch log stream name (default: application)
        region: AWS region for CloudWatch (default: us-east-1)
        enable: Whether to enable CloudWatch logging (default: True)

    Environment Variables:
        CLOUDWATCH_LOGGING_ENABLED: Set to "false" to disable CloudWatch logging
        CLOUDWATCH_LOG_GROUP: Override log group name
        CLOUDWATCH_LOG_STREAM: Override log stream name
        AWS_REGION: Override AWS region
    """
    # Check if CloudWatch logging is disabled via environment variable
    if not enable:
        return

    env_enabled = os.getenv("CLOUDWATCH_LOGGING_ENABLED", "true").lower()
    if env_enabled == "false":
        return

    # Get configuration from environment or use defaults
    log_group = os.getenv("CLOUDWATCH_LOG_GROUP", log_group or "/finops/mcp-server")
    log_stream = os.getenv("CLOUDWATCH_LOG_STREAM", log_stream or "application")
    region = os.getenv("AWS_REGION", region)

    try:
        # Create and configure CloudWatch handler
        handler = CloudWatchHandler(
            log_group=log_group,
            log_stream=log_stream,
            region=region,
        )

        # Use format that includes correlation ID
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] - %(message)s"
        )
        handler.setFormatter(formatter)

        # Add correlation ID filter to CloudWatch handler
        correlation_filter = CorrelationIDFilter()
        handler.addFilter(correlation_filter)

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        # Log that CloudWatch logging is configured
        logger = logging.getLogger(__name__)
        logger.info(f"CloudWatch logging configured: group={log_group}, stream={log_stream}")
    except Exception as e:
        # Log to stderr if CloudWatch setup fails
        import sys

        print(f"Failed to configure CloudWatch logging: {e}", file=sys.stderr)


# =============================================================================
# CloudWatch Metrics for Security Monitoring (Requirements: 23.2, 23.5)
# =============================================================================

# Global CloudWatch client for metrics (initialized lazily)
_cloudwatch_client = None
_metrics_enabled = None


def _get_cloudwatch_client():
    """Get or create CloudWatch client for metrics."""
    global _cloudwatch_client
    if _cloudwatch_client is None:
        region = os.getenv("AWS_REGION", "us-east-1")
        _cloudwatch_client = boto3.client("cloudwatch", region_name=region)
    return _cloudwatch_client


def _is_metrics_enabled() -> bool:
    """Check if CloudWatch metrics are enabled."""
    global _metrics_enabled
    if _metrics_enabled is None:
        env_value = os.getenv("CLOUDWATCH_METRICS_ENABLED", "true").lower()
        _metrics_enabled = env_value != "false"
    return _metrics_enabled


def get_metrics_namespace() -> str:
    """
    Get the CloudWatch namespace for custom metrics.

    Returns:
        Namespace string in format "project-name/environment"
    """
    project = os.getenv("PROJECT_NAME", "mcp-tagging")
    environment = os.getenv("ENVIRONMENT", "prod")
    return f"{project}/{environment}"


def emit_metric(
    metric_name: str,
    value: float = 1.0,
    unit: str = "Count",
    dimensions: dict[str, str] | None = None,
) -> None:
    """
    Emit a custom metric to CloudWatch.

    Args:
        metric_name: Name of the metric (e.g., "AuthenticationFailures")
        value: Metric value (default: 1.0)
        unit: Metric unit (default: "Count")
        dimensions: Optional dimension key-value pairs

    Requirements: 23.2, 23.5
    """
    if not _is_metrics_enabled():
        return

    try:
        client = _get_cloudwatch_client()
        namespace = get_metrics_namespace()
        environment = os.getenv("ENVIRONMENT", "prod")

        # Build metric data
        metric_data: dict[str, Any] = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Timestamp": datetime.utcnow(),
        }

        # Add default dimension for environment
        default_dimensions = [{"Name": "Environment", "Value": environment}]

        # Add custom dimensions if provided
        if dimensions:
            for name, dim_value in dimensions.items():
                default_dimensions.append({"Name": name, "Value": dim_value})

        metric_data["Dimensions"] = default_dimensions

        # Put metric data
        client.put_metric_data(
            Namespace=namespace,
            MetricData=[metric_data],
        )

        logger = logging.getLogger(__name__)
        logger.debug(f"Emitted CloudWatch metric: {metric_name}={value} ({unit})")

    except Exception as e:
        # Don't fail the request if metrics emission fails
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to emit CloudWatch metric {metric_name}: {e}")


def emit_auth_failure_metric(
    failure_type: str,
    client_ip: str | None = None,
) -> None:
    """
    Emit an authentication failure metric to CloudWatch.

    This metric is used to trigger the AuthFailureAlarm defined in
    the CloudFormation template.

    Args:
        failure_type: Type of auth failure (missing_header, invalid_format, etc.)
        client_ip: Optional client IP address

    Requirements: 23.2
    """
    dimensions = {"FailureType": failure_type}
    if client_ip:
        # Don't include full IP in dimensions (privacy), just track count
        pass

    emit_metric(
        metric_name="AuthenticationFailures",
        value=1.0,
        unit="Count",
        dimensions=dimensions,
    )


def emit_cors_violation_metric(
    origin: str,
    path: str | None = None,
) -> None:
    """
    Emit a CORS violation metric to CloudWatch.

    This metric is used to trigger the CORSViolationAlarm defined in
    the CloudFormation template.

    Args:
        origin: The rejected origin
        path: Optional request path

    Requirements: 23.5
    """
    # Sanitize origin for dimension (max 256 chars, limited charset)
    sanitized_origin = origin[:200].replace(",", "_") if origin else "unknown"

    emit_metric(
        metric_name="CORSViolations",
        value=1.0,
        unit="Count",
        dimensions={"Origin": sanitized_origin},
    )
