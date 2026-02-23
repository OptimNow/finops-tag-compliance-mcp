# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""Configuration management for FinOps Tag Compliance MCP Server.

This module handles loading and validating configuration from environment
variables with sensible defaults.

``CoreSettings`` contains protocol-agnostic settings needed by the core
library (AWS, Redis, policy, databases, CloudWatch, budget, loop detection,
security, timeouts). Usable by CLI, Lambda, stdio MCP, or any entry point.

HTTP-specific settings (host, port, request sanitization, rate limiting) live
in ``http_config.py`` as ``ServerSettings``.  Backward-compatible re-exports
(``ServerSettings``, ``Settings``, ``get_settings``) are provided at the
bottom of this file so existing imports continue to work.

Requirements: 14.2
"""


from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """
    Protocol-agnostic settings for the core FinOps tag compliance library.

    These settings are used by services, clients, and tools regardless
    of whether the entry point is HTTP, stdio MCP, CLI, or Lambda.

    Requirements: 14.2
    """

    # General Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
        validation_alias="LOG_LEVEL",
    )
    environment: str = Field(
        default="development",
        description="Environment name (development, staging, production)",
        validation_alias=AliasChoices("ENVIRONMENT", "ENV"),
    )
    debug: bool = Field(default=False, description="Enable debug mode", validation_alias="DEBUG")

    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
        validation_alias="REDIS_URL",
    )
    redis_password: str | None = Field(
        default=None, description="Redis password (optional)", validation_alias="REDIS_PASSWORD"
    )
    redis_ttl: int = Field(
        default=3600,
        description="Default TTL for cached data in seconds",
        validation_alias="REDIS_TTL",
    )

    # AWS Configuration
    aws_region: str = Field(
        default="us-east-1",
        description="Default AWS region",
        validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION"),
    )

    # Policy Configuration
    policy_path: str = Field(
        default="policies/tagging_policy.json",
        description="Path to the tagging policy JSON file",
        validation_alias=AliasChoices("POLICY_PATH", "POLICY_FILE_PATH"),
    )

    # Database Configuration
    audit_db_path: str = Field(
        default="audit_logs.db",
        description="Path to the audit logs SQLite database",
        validation_alias="AUDIT_DB_PATH",
    )
    history_db_path: str = Field(
        default="compliance_history.db",
        description="Path to the compliance history SQLite database",
        validation_alias=AliasChoices("HISTORY_DB_PATH", "DATABASE_PATH"),
    )

    # CloudWatch Configuration
    cloudwatch_enabled: bool = Field(
        default=False,
        description="Enable CloudWatch logging",
        validation_alias="CLOUDWATCH_ENABLED",
    )
    cloudwatch_log_group: str = Field(
        default="/finops/mcp-server",
        description="CloudWatch log group name",
        validation_alias="CLOUDWATCH_LOG_GROUP",
    )
    cloudwatch_log_stream: str | None = Field(
        default=None,
        description="CloudWatch log stream name (auto-generated if not set)",
        validation_alias="CLOUDWATCH_LOG_STREAM",
    )
    security_log_stream: str = Field(
        default="security",
        description="CloudWatch log stream name for security events",
        validation_alias="SECURITY_LOG_STREAM",
    )

    # Budget Tracking Configuration (Requirements: 15.3)
    max_tool_calls_per_session: int = Field(
        default=100,
        description="Maximum tool calls allowed per session",
        validation_alias="MAX_TOOL_CALLS_PER_SESSION",
    )
    session_budget_ttl_seconds: int = Field(
        default=3600,
        description="TTL for session budget tracking in seconds",
        validation_alias="SESSION_BUDGET_TTL_SECONDS",
    )
    budget_tracking_enabled: bool = Field(
        default=True,
        description="Enable tool-call budget tracking",
        validation_alias="BUDGET_TRACKING_ENABLED",
    )

    # Loop Detection Configuration (Requirements: 15.4)
    max_identical_calls: int = Field(
        default=3,
        description="Maximum identical calls allowed before blocking",
        validation_alias="MAX_IDENTICAL_CALLS",
    )
    loop_detection_window_seconds: int = Field(
        default=300,
        description="Time window for tracking identical calls in seconds",
        validation_alias="LOOP_DETECTION_WINDOW_SECONDS",
    )
    loop_detection_enabled: bool = Field(
        default=True,
        description="Enable loop detection for repeated tool calls",
        validation_alias="LOOP_DETECTION_ENABLED",
    )

    # Security Service Configuration (Requirements: 16.4)
    max_unknown_tool_attempts: int = Field(
        default=5,
        description="Maximum unknown tool attempts allowed per session before rate limiting",
        validation_alias="MAX_UNKNOWN_TOOL_ATTEMPTS",
    )
    security_event_window_seconds: int = Field(
        default=300,
        description="Time window for tracking security events in seconds",
        validation_alias="SECURITY_EVENT_WINDOW_SECONDS",
    )
    security_monitoring_enabled: bool = Field(
        default=True,
        description="Enable security event monitoring and rate limiting",
        validation_alias="SECURITY_MONITORING_ENABLED",
    )

    # Multi-Region Scanning Configuration
    # Multi-region scanning is ALWAYS enabled. Use allowed_regions to restrict.
    allowed_regions: list[str] | None = Field(
        default=None,
        description=(
            "Restrict scanning to specific AWS regions (comma-separated). "
            "If not set, all enabled regions in the account are scanned. "
            "Example: ALLOWED_REGIONS=us-east-1,us-west-2,eu-west-1"
        ),
        validation_alias="ALLOWED_REGIONS",
    )
    max_concurrent_regions: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum regions to scan in parallel",
        validation_alias="MAX_CONCURRENT_REGIONS",
    )
    region_scan_timeout_seconds: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Timeout for scanning a single region",
        validation_alias="REGION_SCAN_TIMEOUT_SECONDS",
    )
    region_cache_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="TTL for caching enabled regions list",
        validation_alias="REGION_CACHE_TTL_SECONDS",
    )
    compliance_cache_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="TTL for caching compliance scan results in seconds (default: 1 hour, max: 24 hours)",
        validation_alias="COMPLIANCE_CACHE_TTL_SECONDS",
    )

    # Timeout Configuration (Requirements: 16.1, 16.2)
    tool_execution_timeout_seconds: int = Field(
        default=30,
        description="Maximum time allowed for a single tool execution in seconds",
        validation_alias="TOOL_EXECUTION_TIMEOUT_SECONDS",
    )
    aws_api_timeout_seconds: int = Field(
        default=10,
        description="Timeout for AWS API calls in seconds",
        validation_alias="AWS_API_TIMEOUT_SECONDS",
    )
    redis_timeout_seconds: int = Field(
        default=5,
        description="Timeout for Redis operations in seconds",
        validation_alias="REDIS_TIMEOUT_SECONDS",
    )

    # Authentication Configuration (Requirements: 19.1, 19.4)
    auth_enabled: bool = Field(
        default=False,
        description="Enable API key authentication",
        validation_alias="AUTH_ENABLED",
    )
    api_keys: str = Field(
        default="",
        description="Comma-separated list of valid API keys",
        validation_alias="API_KEYS",
    )
    auth_realm: str = Field(
        default="mcp-server",
        description="Authentication realm for WWW-Authenticate header",
        validation_alias="AUTH_REALM",
    )

    # CORS Configuration (Requirements: 20.1, 20.4)
    cors_allowed_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins (use * for all in dev)",
        validation_alias="CORS_ALLOWED_ORIGINS",
    )

    # TLS Configuration (Requirements: 18.5)
    tls_enabled: bool = Field(
        default=False,
        description="Enable TLS mode (reject plaintext HTTP on MCP endpoints)",
        validation_alias="TLS_ENABLED",
    )

    # --- Phase 2.4: Auto-Policy Detection ---
    auto_import_aws_policy: bool = Field(
        default=True,
        description=(
            "On startup, if no policy file exists, attempt to import "
            "a tag policy from AWS Organizations."
        ),
        validation_alias="AUTO_IMPORT_AWS_POLICY",
    )
    auto_import_policy_id: str | None = Field(
        default=None,
        description=(
            "Specific AWS Organizations policy ID to import (e.g., 'p-abc12345'). "
            "If not set, the first available tag policy is used."
        ),
        validation_alias="AUTO_IMPORT_POLICY_ID",
    )
    fallback_to_default_policy: bool = Field(
        default=True,
        description=(
            "If no policy file exists and AWS import fails/disabled, "
            "create a default policy with Owner/Environment/Application tags."
        ),
        validation_alias="FALLBACK_TO_DEFAULT_POLICY",
    )

    # --- Phase 2.4: Scheduled Compliance Snapshots ---
    scheduler_enabled: bool = Field(
        default=False,
        description="Enable daily compliance snapshot scheduler",
        validation_alias="SCHEDULER_ENABLED",
    )
    snapshot_schedule_hour: int = Field(
        default=2,
        ge=0,
        le=23,
        description="Hour to run the daily compliance snapshot (0-23, default: 2 = 02:00)",
        validation_alias="SNAPSHOT_SCHEDULE_HOUR",
    )
    snapshot_schedule_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        description="Minute to run the daily compliance snapshot (0-59, default: 0)",
        validation_alias="SNAPSHOT_SCHEDULE_MINUTE",
    )
    snapshot_schedule_timezone: str = Field(
        default="UTC",
        description="Timezone for the snapshot schedule (default: UTC)",
        validation_alias="SNAPSHOT_SCHEDULE_TIMEZONE",
    )

    model_config = SettingsConfigDict(
        env_prefix="",  # No prefix for environment variables
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore HTTP-specific settings when using CoreSettings
    )

    @field_validator("allowed_regions", mode="before")
    @classmethod
    def parse_allowed_regions(cls, v):
        """Parse comma-separated region list from environment variable."""
        if v is None or v == "":
            return None
        if isinstance(v, str):
            # Parse comma-separated string: "us-east-1,us-west-2,eu-west-1"
            regions = [r.strip() for r in v.split(",") if r.strip()]
            return regions if regions else None
        return v


# Global core settings instance (lazy loaded)
_core_settings: CoreSettings | None = None


def settings() -> CoreSettings:
    """
    Get the global settings instance.

    Returns ``CoreSettings`` for protocol-agnostic consumers (container,
    stdio_server).  HTTP entry points should import ``settings`` from
    ``http_config`` instead to get ``ServerSettings``.
    """
    global _core_settings
    if _core_settings is None:
        _core_settings = CoreSettings()
    return _core_settings
