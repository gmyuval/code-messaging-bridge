"""Tests for application configuration."""

from __future__ import annotations

import os

import pytest

from code_messaging_bridge.config import Settings


def test_settings_default_values() -> None:
    """Settings should have sensible defaults when debug mode is on."""
    settings = Settings(
        _env_file=None,
        debug=True,
    )
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000
    assert settings.debug is True
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


def test_settings_rejects_empty_secrets_in_production() -> None:
    """Non-debug mode should fail if Meta API credentials are empty."""
    with pytest.raises(ValueError, match="Required Meta WhatsApp credentials not set"):
        Settings(
            _env_file=None,
            debug=False,
            meta_phone_number_id="",
            meta_access_token="",
            meta_app_secret="",
        )


def test_settings_accepts_secrets_in_production() -> None:
    """Non-debug mode should accept non-empty Meta API credentials."""
    settings = Settings(
        _env_file=None,
        debug=False,
        meta_phone_number_id="123456",
        meta_access_token="test_token",  # noqa: S106
        meta_app_secret="test_secret",  # noqa: S106
    )
    assert settings.meta_phone_number_id == "123456"


def test_settings_skips_validation_in_debug() -> None:
    """Debug mode should not require Meta API credentials."""
    settings = Settings(
        _env_file=None,
        debug=True,
        meta_phone_number_id="",
        meta_access_token="",
        meta_app_secret="",
    )
    assert settings.debug is True


def test_settings_rejects_path_traversal() -> None:
    """Working directory must not contain '..' components."""
    with pytest.raises(ValueError, match="must not contain"):
        Settings(
            _env_file=None,
            debug=True,
            claude_working_directory="../../../etc",
        )


def test_settings_rejects_non_directory(tmp_path: object) -> None:
    """Working directory must be a directory if it exists."""
    from pathlib import Path

    file_path = Path(str(tmp_path)) / "not_a_dir.txt"
    file_path.write_text("test")
    with pytest.raises(ValueError, match="not a directory"):
        Settings(
            _env_file=None,
            debug=True,
            claude_working_directory=str(file_path),
        )


def test_settings_resolves_working_directory(tmp_path: object) -> None:
    """Working directory should be resolved to absolute path."""
    settings = Settings(
        _env_file=None,
        debug=True,
        claude_working_directory=str(tmp_path),
    )
    from pathlib import Path

    assert Path(settings.claude_working_directory).is_absolute()
