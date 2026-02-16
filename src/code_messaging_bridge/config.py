"""Application configuration using pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables with CMB_ prefix."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CMB_",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://cmb:cmb@localhost:5432/cmb"
    database_url_sync: str = "postgresql+psycopg2://cmb:cmb@localhost:5432/cmb"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Meta WhatsApp Business API
    meta_phone_number_id: str = ""
    meta_access_token: str = ""
    meta_verify_token: str = ""
    meta_app_secret: str = ""

    # Claude Code
    claude_cli_path: str = "claude"
    claude_working_directory: str = "."
    claude_max_turns: int = 10

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    webhook_base_url: str = ""

    # Security
    allowed_phone_numbers: list[str] = []


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
