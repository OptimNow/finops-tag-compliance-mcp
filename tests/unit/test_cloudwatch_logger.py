"""Unit tests for CloudWatch logging integration."""

import logging
import os
from unittest.mock import MagicMock, patch, call

import pytest

from mcp_server.utils.cloudwatch_logger import (
    CloudWatchHandler,
    configure_cloudwatch_logging,
)


class TestCloudWatchHandler:
    """Tests for CloudWatchHandler class."""

    @patch("mcp_server.utils.cloudwatch_logger.boto3.client")
    def test_handler_initialization(self, mock_boto_client):
        """Test CloudWatchHandler initialization."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        handler = CloudWatchHandler(
            log_group="/test/group",
            log_stream="test-stream",
            region="us-east-1",
        )

        assert handler.log_group == "/test/group"
        assert handler.log_stream == "test-stream"
        assert handler.region == "us-east-1"
        mock_boto_client.assert_called_once_with("logs", region_name="us-east-1")

    @patch("mcp_server.utils.cloudwatch_logger.boto3.client")
    def test_handler_creates_log_group_and_stream(self, mock_boto_client):
        """Test that handler creates log group and stream on initialization."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        handler = CloudWatchHandler(
            log_group="/test/group",
            log_stream="test-stream",
        )

        # Verify create_log_group was called
        mock_client.create_log_group.assert_called_once_with(logGroupName="/test/group")

        # Verify create_log_stream was called
        mock_client.create_log_stream.assert_called_once_with(
            logGroupName="/test/group",
            logStreamName="test-stream",
        )

    @patch("mcp_server.utils.cloudwatch_logger.boto3.client")
    def test_handler_handles_existing_log_group(self, mock_boto_client):
        """Test that handler handles existing log group gracefully."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Simulate log group already exists
        error_response = {"Error": {"Code": "ResourceAlreadyExistsException"}}
        mock_client.create_log_group.side_effect = ClientError(error_response, "CreateLogGroup")

        # Should not raise exception
        handler = CloudWatchHandler(
            log_group="/test/group",
            log_stream="test-stream",
        )

        assert handler is not None

    @patch("mcp_server.utils.cloudwatch_logger.boto3.client")
    def test_handler_emits_log_record(self, mock_boto_client):
        """Test that handler emits log records to CloudWatch."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        handler = CloudWatchHandler(
            log_group="/test/group",
            log_stream="test-stream",
        )

        # Create a log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Emit the record
        handler.emit(record)

        # Verify put_log_events was called
        mock_client.put_log_events.assert_called_once()
        call_args = mock_client.put_log_events.call_args

        assert call_args[1]["logGroupName"] == "/test/group"
        assert call_args[1]["logStreamName"] == "test-stream"
        assert len(call_args[1]["logEvents"]) == 1
        assert "Test message" in call_args[1]["logEvents"][0]["message"]

    @patch("mcp_server.utils.cloudwatch_logger.boto3.client")
    def test_handler_handles_emit_errors(self, mock_boto_client):
        """Test that handler handles errors during emit gracefully."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Simulate put_log_events failure
        mock_client.put_log_events.side_effect = Exception("CloudWatch error")

        handler = CloudWatchHandler(
            log_group="/test/group",
            log_stream="test-stream",
        )

        # Create a log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        # Should not raise exception
        handler.emit(record)


class TestConfigureCloudWatchLogging:
    """Tests for configure_cloudwatch_logging function."""

    @patch("mcp_server.utils.cloudwatch_logger.CloudWatchHandler")
    @patch.dict(os.environ, {}, clear=True)
    def test_configure_with_defaults(self, mock_handler_class):
        """Test configure_cloudwatch_logging with default parameters."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        configure_cloudwatch_logging()

        # Verify handler was created with defaults
        mock_handler_class.assert_called_once_with(
            log_group="/finops/mcp-server",
            log_stream="application",
            region="us-east-1",
        )

    @patch("mcp_server.utils.cloudwatch_logger.CloudWatchHandler")
    @patch.dict(os.environ, {}, clear=True)
    def test_configure_with_custom_parameters(self, mock_handler_class):
        """Test configure_cloudwatch_logging with custom parameters."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        configure_cloudwatch_logging(
            log_group="/custom/group",
            log_stream="custom-stream",
            region="eu-west-1",
        )

        # Verify handler was created with custom parameters
        mock_handler_class.assert_called_once_with(
            log_group="/custom/group",
            log_stream="custom-stream",
            region="eu-west-1",
        )

    @patch("mcp_server.utils.cloudwatch_logger.CloudWatchHandler")
    @patch.dict(
        os.environ,
        {
            "CLOUDWATCH_LOG_GROUP": "/env/group",
            "CLOUDWATCH_LOG_STREAM": "env-stream",
            "AWS_REGION": "ap-southeast-1",
        },
    )
    def test_configure_with_environment_variables(self, mock_handler_class):
        """Test configure_cloudwatch_logging respects environment variables."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        configure_cloudwatch_logging()

        # Verify handler was created with environment variable values
        mock_handler_class.assert_called_once_with(
            log_group="/env/group",
            log_stream="env-stream",
            region="ap-southeast-1",
        )

    @patch("mcp_server.utils.cloudwatch_logger.CloudWatchHandler")
    @patch.dict(os.environ, {"CLOUDWATCH_LOGGING_ENABLED": "false"})
    def test_configure_disabled_via_environment(self, mock_handler_class):
        """Test that CloudWatch logging can be disabled via environment variable."""
        configure_cloudwatch_logging()

        # Verify handler was not created
        mock_handler_class.assert_not_called()

    @patch("mcp_server.utils.cloudwatch_logger.CloudWatchHandler")
    @patch.dict(os.environ, {}, clear=True)
    def test_configure_disabled_via_parameter(self, mock_handler_class):
        """Test that CloudWatch logging can be disabled via parameter."""
        configure_cloudwatch_logging(enable=False)

        # Verify handler was not created
        mock_handler_class.assert_not_called()

    @patch("mcp_server.utils.cloudwatch_logger.CloudWatchHandler")
    @patch.dict(os.environ, {}, clear=True)
    def test_configure_adds_handler_to_root_logger(self, mock_handler_class):
        """Test that handler is added to root logger."""
        mock_handler = MagicMock()
        mock_handler_class.return_value = mock_handler

        # Get root logger before configuration
        root_logger = logging.getLogger()
        initial_handler_count = len(root_logger.handlers)

        configure_cloudwatch_logging()

        # Verify handler was added to root logger
        assert len(root_logger.handlers) > initial_handler_count

    @patch("mcp_server.utils.cloudwatch_logger.CloudWatchHandler")
    @patch.dict(os.environ, {}, clear=True)
    def test_configure_handles_initialization_errors(self, mock_handler_class):
        """Test that configure_cloudwatch_logging handles initialization errors."""
        # Simulate handler initialization failure
        mock_handler_class.side_effect = Exception("CloudWatch setup failed")

        # Should not raise exception
        configure_cloudwatch_logging()
