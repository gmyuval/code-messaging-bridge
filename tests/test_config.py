"""Tests for application configuration."""

from __future__ import annotations

import os

from code_messaging_bridge.config import Settings


def test_settings_default_values() -> None:
    """Settings should have sensible defaults."""
    settings = Settings(
        _env_file=None,
    )
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.debug is False
    assert settings.claude_max_turns == 10
    assert settings.allowed_phone_numbers == []


def test_settings_from_env_vars() -> None:
    """Settings should load from CMB_ prefixed environment variables."""
    os.environ["CMB_DEBUG"] = "true"
    os.environ["CMB_PORT"] = "9000"
    try:
        settings = Settings(
            _env_file=None,
        )
        assert settings.debug is True
        assert settings.port == 9000
    finally:
        del os.environ["CMB_DEBUG"]
        del os.environ["CMB_PORT"]
