# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""Configuration management for FinOps Tag Compliance MCP Server.

This module handles loading and validating configuration from environment
variables with sensible defaults.

Requirements: 14.2
"""

from typing import Optional
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings have sensible defaults for local development.
    In production, these should be set via environment variables
    or a .env file.
    
    Requirements: 14.2
    """
    
    # Server Configuration
    host: str = Field(
        default="0.0.0.0",
        description="Host to bind the server to",
        validation_alias=AliasChoices("MCP_SERVER_HOST", "HOST")
    )
    port: int = Field(
        default=8080,
        description="Port to run the server on",
        validation_alias=AliasChoices("MCP_SERVER_PORT", "PORT")
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
        validation_alias="LOG_LEVEL"
    )
    environment: str = Field(
        default="development",
        description="Environment name (development, staging, production)",
        validation_alias=AliasChoices("ENVIRONMENT", "ENV")
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
        validation_alias="DEBUG"
    )
    
    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
        validation_alias="REDIS_URL"
    )
    redis_password: Optional[str] = Field(
        default=None,
        description="Redis password (optional)",
        validation_alias="REDIS_PASSWORD"
    )
    redis_ttl: int = Field(
        default=3600,
        description="Default TTL for cached data in seconds",
        validation_alias="REDIS_TTL"
    )
    
    # AWS Configuration
    aws_region: str = Field(
        default="us-east-1",
        description="Default AWS region",
        validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION")
    )
    
    # Policy Configuration
    policy_path: str = Field(
        default="policies/tagging_policy.json",
        description="Path to the tagging policy JSON file",
        validation_alias=AliasChoices("POLICY_PATH", "POLICY_FILE_PATH")
    )
    
    # Database Configuration
    audit_db_path: str = Field(
        default="audit_logs.db",
        description="Path to the audit logs SQLite database",
        validation_alias="AUDIT_DB_PATH"
    )
    history_db_path: str = Field(
        default="compliance_history.db",
        description="Path to the compliance history SQLite database",
        validation_alias=AliasChoices("HISTORY_DB_PATH", "DATABASE_PATH")
    )
    
    # CloudWatch Configuration
    cloudwatch_enabled: bool = Field(
        default=False,
        description="Enable CloudWatch logging",
        validation_alias="CLOUDWATCH_ENABLED"
    )
    cloudwatch_log_group: str = Field(
        default="/finops/mcp-server",
        description="CloudWatch log group name",
        validation_alias="CLOUDWATCH_LOG_GROUP"
    )
    cloudwatch_log_stream: Optional[str] = Field(
        default=None,
        description="CloudWatch log stream name (auto-generated if not set)",
        validation_alias="CLOUDWATCH_LOG_STREAM"
    )
    security_log_stream: str = Field(
        default="security",
        description="CloudWatch log stream name for security events",
        validation_alias="SECURITY_LOG_STREAM"
    )
    
    # Budget Tracking Configuration (Requirements: 15.3)
    max_tool_calls_per_session: int = Field(
        default=100,
        description="Maximum tool calls allowed per session",
        validation_alias="MAX_TOOL_CALLS_PER_SESSION"
    )
    session_budget_ttl_seconds: int = Field(
        default=3600,
        description="TTL for session budget tracking in seconds",
        validation_alias="SESSION_BUDGET_TTL_SECONDS"
    )
    budget_tracking_enabled: bool = Field(
        default=True,
        description="Enable tool-call budget tracking",
        validation_alias="BUDGET_TRACKING_ENABLED"
    )
    
    # Loop Detection Configuration (Requirements: 15.4)
    max_identical_calls: int = Field(
        default=3,
        description="Maximum identical calls allowed before blocking",
        validation_alias="MAX_IDENTICAL_CALLS"
    )
    loop_detection_window_seconds: int = Field(
        default=300,
        description="Time window for tracking identical calls in seconds",
        validation_alias="LOOP_DETECTION_WINDOW_SECONDS"
    )
    loop_detection_enabled: bool = Field(
        default=True,
        description="Enable loop detection for repeated tool calls",
        validation_alias="LOOP_DETECTION_ENABLED"
    )
    
    # Security Service Configuration (Requirements: 16.4)
    max_unknown_tool_attempts: int = Field(
        default=5,
        description="Maximum unknown tool attempts allowed per session before rate limiting",
        validation_alias="MAX_UNKNOWN_TOOL_ATTEMPTS"
    )
    security_event_window_seconds: int = Field(
        default=300,
        description="Time window for tracking security events in seconds",
        validation_alias="SECURITY_EVENT_WINDOW_SECONDS"
    )
    security_monitoring_enabled: bool = Field(
        default=True,
        description="Enable security event monitoring and rate limiting",
        validation_alias="SECURITY_MONITORING_ENABLED"
    )
    
    # Request Sanitization Configuration (Requirements: 16.2, 16.5)
    max_request_size_bytes: int = Field(
        default=10 * 1024 * 1024,  # 10 MB
        description="Maximum request body size in bytes",
        validation_alias="MAX_REQUEST_SIZE_BYTES"
    )
    max_header_size_bytes: int = Field(
        default=8 * 1024,  # 8 KB
        description="Maximum total header size in bytes",
        validation_alias="MAX_HEADER_SIZE_BYTES"
    )
    max_header_count: int = Field(
        default=50,
        description="Maximum number of headers allowed",
        validation_alias="MAX_HEADER_COUNT"
    )
    max_query_string_length: int = Field(
        default=4096,
        description="Maximum query string length",
        validation_alias="MAX_QUERY_STRING_LENGTH"
    )
    max_path_length: int = Field(
        default=2048,
        description="Maximum URL path length",
        validation_alias="MAX_PATH_LENGTH"
    )
    request_sanitization_enabled: bool = Field(
        default=True,
        description="Enable request sanitization middleware",
        validation_alias="REQUEST_SANITIZATION_ENABLED"
    )
    
    # Timeout Configuration (Requirements: 16.1, 16.2)
    tool_execution_timeout_seconds: int = Field(
        default=30,
        description="Maximum time allowed for a single tool execution in seconds",
        validation_alias="TOOL_EXECUTION_TIMEOUT_SECONDS"
    )
    aws_api_timeout_seconds: int = Field(
        default=10,
        description="Timeout for AWS API calls in seconds",
        validation_alias="AWS_API_TIMEOUT_SECONDS"
    )
    redis_timeout_seconds: int = Field(
        default=5,
        description="Timeout for Redis operations in seconds",
        validation_alias="REDIS_TIMEOUT_SECONDS"
    )
    http_request_timeout_seconds: int = Field(
        default=30,
        description="Timeout for HTTP requests in seconds",
        validation_alias="HTTP_REQUEST_TIMEOUT_SECONDS"
    )
    
    # Rate Limiting Configuration (Requirements: 16.2)
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting for API requests",
        validation_alias="RATE_LIMIT_ENABLED"
    )
    rate_limit_requests_per_minute: int = Field(
        default=60,
        description="Maximum requests allowed per minute per IP",
        validation_alias="RATE_LIMIT_REQUESTS_PER_MINUTE"
    )
    rate_limit_burst_size: int = Field(
        default=10,
        description="Burst size for rate limiting (requests allowed in quick succession)",
        validation_alias="RATE_LIMIT_BURST_SIZE"
    )
    
    model_config = SettingsConfigDict(
        env_prefix="",  # No prefix for environment variables
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


def get_settings() -> Settings:
    """
    Get application settings.
    
    Loads settings from environment variables and .env file.
    
    Returns:
        Settings instance with all configuration values
    """
    return Settings()


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None


def settings() -> Settings:
    """
    Get the global settings instance.
    
    Creates the settings instance on first call and caches it.
    
    Returns:
        Global Settings instance
    """
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings
