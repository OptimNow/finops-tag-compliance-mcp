"""Health check data models."""

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    """Health status response for the MCP server."""

    status: str = Field(
        ...,
        description="Overall health status: 'healthy' or 'degraded'",
        examples=["healthy"]
    )
    version: str = Field(
        ...,
        description="Version of the MCP server",
        examples=["0.1.0"]
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when health check was performed"
    )
    cloud_providers: list[str] = Field(
        default=["aws"],
        description="List of supported cloud providers"
    )
    redis_connected: bool = Field(
        ...,
        description="Whether Redis cache is connected"
    )
    sqlite_connected: bool = Field(
        ...,
        description="Whether SQLite database is accessible"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}
