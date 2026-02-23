# Copyright (c) 2025 OptimNow - Jean Latiere. All Rights Reserved.
# Licensed under the Proprietary Software License.
# See LICENSE file in the project root for full license information.

"""HTTP-specific configuration for the FastAPI server.

Extends ``CoreSettings`` with host/port, request sanitization,
rate limiting, and other HTTP-specific settings.

This module is only needed by the HTTP entry point (``main.py``,
``run_server.py``). The stdio MCP server and core library use
``CoreSettings`` from ``config.py`` directly.

Requirements: 14.2
"""

from pydantic import AliasChoices, Field

from .config import CoreSettings


class ServerSettings(CoreSettings):
    """
    HTTP server settings extending CoreSettings.

    Adds host/port binding, request sanitization, and rate limiting
    configuration used only by the FastAPI HTTP server.

    Requirements: 14.2
    """

    # Server Bind Configuration
    host: str = Field(
        default="0.0.0.0",
        description="Host to bind the server to",
        validation_alias=AliasChoices("MCP_SERVER_HOST", "HOST"),
    )
    port: int = Field(
        default=8080,
        description="Port to run the server on",
        validation_alias=AliasChoices("MCP_SERVER_PORT", "PORT"),
    )

    # Request Sanitization Configuration (Requirements: 16.2, 16.5)
    max_request_size_bytes: int = Field(
        default=10 * 1024 * 1024,  # 10 MB
        description="Maximum request body size in bytes",
        validation_alias="MAX_REQUEST_SIZE_BYTES",
    )
    max_header_size_bytes: int = Field(
        default=8 * 1024,  # 8 KB
        description="Maximum total header size in bytes",
        validation_alias="MAX_HEADER_SIZE_BYTES",
    )
    max_header_count: int = Field(
        default=50,
        description="Maximum number of headers allowed",
        validation_alias="MAX_HEADER_COUNT",
    )
    max_query_string_length: int = Field(
        default=4096,
        description="Maximum query string length",
        validation_alias="MAX_QUERY_STRING_LENGTH",
    )
    max_path_length: int = Field(
        default=2048, description="Maximum URL path length", validation_alias="MAX_PATH_LENGTH"
    )
    request_sanitization_enabled: bool = Field(
        default=True,
        description="Enable request sanitization middleware",
        validation_alias="REQUEST_SANITIZATION_ENABLED",
    )

    # HTTP Timeout Configuration (Requirements: 16.2)
    http_request_timeout_seconds: int = Field(
        default=30,
        description="Timeout for HTTP requests in seconds",
        validation_alias="HTTP_REQUEST_TIMEOUT_SECONDS",
    )

    # Rate Limiting Configuration (Requirements: 16.2)
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting for API requests",
        validation_alias="RATE_LIMIT_ENABLED",
    )
    rate_limit_requests_per_minute: int = Field(
        default=60,
        description="Maximum requests allowed per minute per IP",
        validation_alias="RATE_LIMIT_REQUESTS_PER_MINUTE",
    )
    rate_limit_burst_size: int = Field(
        default=10,
        description="Burst size for rate limiting (requests allowed in quick succession)",
        validation_alias="RATE_LIMIT_BURST_SIZE",
    )


# Backwards-compatible alias
Settings = ServerSettings


def get_settings() -> Settings:
    """
    Get HTTP server settings.

    Loads settings from environment variables and .env file.

    Returns:
        Settings instance with all configuration values
    """
    return Settings()


# Global settings instance (lazy loaded)
_settings: Settings | None = None


def settings() -> Settings:
    """
    Get the global HTTP server settings instance.

    Creates the settings instance on first call and caches it.

    Returns:
        Global Settings instance
    """
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings
