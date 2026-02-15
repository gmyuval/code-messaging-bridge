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
    old_debug = os.environ.get("CMB_DEBUG")
    old_port = os.environ.get("CMB_PORT")
    os.environ["CMB_DEBUG"] = "true"
    os.environ["CMB_PORT"] = "9000"
    try:
        settings = Settings(
            _env_file=None,
        )
        assert settings.debug is True
        assert settings.port == 9000
    finally:
        if old_debug is None:
            os.environ.pop("CMB_DEBUG", None)
        else:
            os.environ["CMB_DEBUG"] = old_debug
        if old_port is None:
            os.environ.pop("CMB_PORT", None)
        else:
            os.environ["CMB_PORT"] = old_port
