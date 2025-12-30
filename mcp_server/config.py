"""Configuration management for FinOps Tag Compliance MCP Server.

This module handles loading and validating configuration from environment
variables with sensible defaults.

Requirements: 14.2
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


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
    )
    port: int = Field(
        default=8080,
        description="Port to run the server on",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    environment: str = Field(
        default="development",
        description="Environment name (development, staging, production)",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )
    
    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_password: Optional[str] = Field(
        default=None,
        description="Redis password (optional)",
    )
    redis_ttl: int = Field(
        default=3600,
        description="Default TTL for cached data in seconds",
    )
    
    # AWS Configuration
    aws_region: str = Field(
        default="us-east-1",
        description="Default AWS region",
    )
    
    # Policy Configuration
    policy_path: str = Field(
        default="policies/tagging_policy.json",
        description="Path to the tagging policy JSON file",
    )
    
    # Database Configuration
    audit_db_path: str = Field(
        default="audit_logs.db",
        description="Path to the audit logs SQLite database",
    )
    history_db_path: str = Field(
        default="compliance_history.db",
        description="Path to the compliance history SQLite database",
    )
    
    # CloudWatch Configuration
    cloudwatch_enabled: bool = Field(
        default=False,
        description="Enable CloudWatch logging",
    )
    cloudwatch_log_group: str = Field(
        default="/finops/mcp-server",
        description="CloudWatch log group name",
    )
    cloudwatch_log_stream: Optional[str] = Field(
        default=None,
        description="CloudWatch log stream name (auto-generated if not set)",
    )
    
    class Config:
        """Pydantic settings configuration."""
        env_prefix = ""  # No prefix for environment variables
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
        # Map environment variable names to field names
        fields = {
            "host": {"env": ["MCP_SERVER_HOST", "HOST"]},
            "port": {"env": ["MCP_SERVER_PORT", "PORT"]},
            "log_level": {"env": ["LOG_LEVEL"]},
            "environment": {"env": ["ENVIRONMENT", "ENV"]},
            "debug": {"env": ["DEBUG"]},
            "redis_url": {"env": ["REDIS_URL"]},
            "redis_password": {"env": ["REDIS_PASSWORD"]},
            "redis_ttl": {"env": ["REDIS_TTL"]},
            "aws_region": {"env": ["AWS_REGION", "AWS_DEFAULT_REGION"]},
            "policy_path": {"env": ["POLICY_PATH", "POLICY_FILE_PATH"]},
            "audit_db_path": {"env": ["AUDIT_DB_PATH"]},
            "history_db_path": {"env": ["HISTORY_DB_PATH", "DATABASE_PATH"]},
            "cloudwatch_enabled": {"env": ["CLOUDWATCH_ENABLED"]},
            "cloudwatch_log_group": {"env": ["CLOUDWATCH_LOG_GROUP"]},
            "cloudwatch_log_stream": {"env": ["CLOUDWATCH_LOG_STREAM"]},
        }


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
