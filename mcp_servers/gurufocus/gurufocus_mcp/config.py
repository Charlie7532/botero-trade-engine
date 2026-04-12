"""Configuration for the GuruFocus MCP server."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerSettings(BaseSettings):
    """Settings for the GuruFocus MCP server.

    Configuration can be set via environment variables with the
    GURUFOCUS_ prefix.

    Example:
        # Environment variables
        export GURUFOCUS_API_TOKEN="your-api-token"
        export GURUFOCUS_CACHE_ENABLED=true
        export GURUFOCUS_LOG_LEVEL=DEBUG
    """

    model_config = SettingsConfigDict(
        env_prefix="GURUFOCUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Configuration
    api_token: str = Field(
        default="",
        description="GuruFocus API token for authentication",
    )
    api_base_url: str = Field(
        default="https://api.gurufocus.com/public/user",
        description="Base URL for the GuruFocus API",
    )
    api_timeout: float = Field(
        default=30.0,
        description="Request timeout in seconds",
    )
    api_max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts",
    )

    # Cache Configuration
    cache_enabled: bool = Field(
        default=True,
        description="Enable response caching",
    )
    cache_dir: str = Field(
        default=".cache/gurufocus-mcp",
        description="Directory for cache storage",
    )

    # Rate Limiting
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting",
    )
    rate_limit_rpm: float = Field(
        default=30.0,
        description="Maximum requests per minute",
    )
    rate_limit_daily: int = Field(
        default=0,
        description="Maximum requests per day (0 = unlimited)",
    )

    # Logging (aligned with gurufocus-api)
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    log_format: Literal["json", "console"] = Field(
        default="console",
        description="Log output format: 'json' for production, 'console' for development",
    )

    # Output Format
    default_output_format: Literal["toon", "json"] = Field(
        default="toon",
        description="Default output format for tool responses: 'toon' for token-efficient, 'json' for standard",
    )

    # Server Info
    server_name: str = Field(
        default="gurufocus-mcp",
        description="MCP server name",
    )
    server_version: str = Field(
        default="0.1.0",
        description="MCP server version",
    )

    def validate_api_token(self) -> bool:
        """Check if a valid API token is configured.

        Returns:
            True if an API token is set
        """
        return bool(self.api_token and self.api_token.strip())


def get_settings() -> MCPServerSettings:
    """Get the server settings.

    Returns:
        MCPServerSettings instance loaded from environment
    """
    return MCPServerSettings()
