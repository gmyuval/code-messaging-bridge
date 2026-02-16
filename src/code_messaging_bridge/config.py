"""Application configuration using pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
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

    @field_validator("claude_working_directory")
    @classmethod
    def validate_working_directory(cls, v: str) -> str:
        """Validate that the working directory is safe and exists."""
        resolved = Path(v).resolve()
        if ".." in Path(v).parts:
            msg = f"claude_working_directory must not contain '..': {v}"
            raise ValueError(msg)
        if resolved.exists() and not resolved.is_dir():
            msg = f"claude_working_directory is not a directory: {resolved}"
            raise ValueError(msg)
        return str(resolved)

    @model_validator(mode="after")
    def validate_required_secrets(self) -> Settings:
        """Ensure required Meta API credentials are set in non-debug mode."""
        if self.debug:
            return self
        required = {
            "meta_phone_number_id": self.meta_phone_number_id,
            "meta_access_token": self.meta_access_token,
            "meta_app_secret": self.meta_app_secret,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            msg = (
                f"Required Meta WhatsApp credentials not set: {', '.join(missing)}. "
                f"Set CMB_DEBUG=true to skip this check during development."
            )
            raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
