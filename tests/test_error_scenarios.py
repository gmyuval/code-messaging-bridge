"""Tests for error scenarios and edge cases."""

from __future__ import annotations

import subprocess
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_messaging_bridge.rate_limiter import RateLimiter
from code_messaging_bridge.services.claude.runner import ClaudeCodeRunner

# --- Rate limiter tests ---


def test_rate_limiter_allows_within_limit() -> None:
    """Should allow requests within the rate limit."""
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert limiter.is_allowed("user1") is True
    assert limiter.is_allowed("user1") is True
    assert limiter.is_allowed("user1") is True


def test_rate_limiter_blocks_over_limit() -> None:
    """Should block requests exceeding the rate limit."""
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.is_allowed("user1") is True
    assert limiter.is_allowed("user1") is True
    assert limiter.is_allowed("user1") is False


def test_rate_limiter_independent_keys() -> None:
    """Different keys should have independent limits."""
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.is_allowed("user1") is True
    assert limiter.is_allowed("user2") is True
    assert limiter.is_allowed("user1") is False
    assert limiter.is_allowed("user2") is False


def test_rate_limiter_window_expires() -> None:
    """Requests should be allowed again after the window expires."""
    limiter = RateLimiter(max_requests=1, window_seconds=0.1)
    assert limiter.is_allowed("user1") is True
    assert limiter.is_allowed("user1") is False
    time.sleep(0.15)
    assert limiter.is_allowed("user1") is True


# --- Claude retry tests ---


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
@patch("code_messaging_bridge.services.claude.runner.time.sleep")
def test_retry_succeeds_on_second_attempt(
    mock_sleep: MagicMock,
    mock_run: MagicMock,
) -> None:
    """Should retry and succeed when first attempt fails."""
    from code_messaging_bridge.services.claude.schemas import ClaudeInvocation

    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Transient error"),
        subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"result":"ok","is_error":false}', stderr=""
        ),
    ]

    settings = MagicMock()
    settings.claude_cli_path = "claude"
    runner = ClaudeCodeRunner(settings)
    result = runner.invoke_with_retry(ClaudeInvocation(prompt="test"))

    assert result.success is True
    assert result.output == "ok"
    assert mock_run.call_count == 2
    mock_sleep.assert_called_once()


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_retry_does_not_retry_on_timeout(mock_run: MagicMock) -> None:
    """Should NOT retry when Claude CLI times out (would take too long)."""
    from code_messaging_bridge.services.claude.schemas import ClaudeInvocation

    mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=600)

    settings = MagicMock()
    settings.claude_cli_path = "claude"
    runner = ClaudeCodeRunner(settings)
    result = runner.invoke_with_retry(ClaudeInvocation(prompt="test"))

    assert result.success is False
    assert "timed out" in (result.error_message or "")
    assert mock_run.call_count == 1  # No retry


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_retry_does_not_retry_on_file_not_found(mock_run: MagicMock) -> None:
    """Should NOT retry when Claude CLI binary is missing."""
    from code_messaging_bridge.services.claude.schemas import ClaudeInvocation

    mock_run.side_effect = FileNotFoundError()

    settings = MagicMock()
    settings.claude_cli_path = "claude"
    runner = ClaudeCodeRunner(settings)
    result = runner.invoke_with_retry(ClaudeInvocation(prompt="test"))

    assert result.success is False
    assert "not found" in (result.error_message or "")
    assert mock_run.call_count == 1  # No retry


@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
@patch("code_messaging_bridge.services.claude.runner.time.sleep")
def test_retry_exhausted(mock_sleep: MagicMock, mock_run: MagicMock) -> None:
    """Should return failure after all retries are exhausted."""
    from code_messaging_bridge.services.claude.schemas import ClaudeInvocation

    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="Persistent error"
    )

    settings = MagicMock()
    settings.claude_cli_path = "claude"
    runner = ClaudeCodeRunner(settings)
    result = runner.invoke_with_retry(ClaudeInvocation(prompt="test"))

    assert result.success is False
    assert mock_run.call_count == 3  # 1 initial + 2 retries


# --- Webhook error scenario tests ---


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.webhooks.process_whatsapp_message")
async def test_webhook_rejects_non_whitelisted_number(
    mock_task: MagicMock,
    client: Any,
    app: Any,
    async_session: Any,
) -> None:
    """Should reject messages from numbers not in the whitelist."""
    from datetime import UTC, datetime

    from code_messaging_bridge.api.dependencies import get_whatsapp_provider
    from code_messaging_bridge.config import get_settings
    from code_messaging_bridge.services.messaging.schemas import (
        InboundMessage,
        Platform,
        WebhookValidationResult,
    )

    provider = MagicMock()
    provider.validate_webhook = AsyncMock(return_value=WebhookValidationResult(is_valid=True))
    provider.parse_inbound = AsyncMock(
        return_value=InboundMessage(
            platform=Platform.WHATSAPP,
            platform_user_id="+9999999999",
            platform_message_id="wamid.BAD",
            content="Hello",
            timestamp=datetime.now(UTC),
            raw_payload={},
        )
    )
    app.dependency_overrides[get_whatsapp_provider] = lambda: provider

    # Set whitelist that doesn't include the sender
    settings = get_settings()
    original = settings.allowed_phone_numbers
    settings.allowed_phone_numbers = ["+1111111111"]

    try:
        response = await client.post(
            "/api/webhooks/whatsapp",
            content=b'{}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 403
        mock_task.delay.assert_not_called()
    finally:
        settings.allowed_phone_numbers = original
        app.dependency_overrides.pop(get_whatsapp_provider, None)


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.webhooks.process_whatsapp_message")
@patch("code_messaging_bridge.api.webhooks._rate_limiter")
async def test_webhook_rate_limits(
    mock_limiter: MagicMock,
    mock_task: MagicMock,
    client: Any,
    app: Any,
    async_session: Any,
) -> None:
    """Should return 429 when rate limit is exceeded."""
    from datetime import UTC, datetime

    from code_messaging_bridge.api.dependencies import get_whatsapp_provider
    from code_messaging_bridge.services.messaging.schemas import (
        InboundMessage,
        Platform,
        WebhookValidationResult,
    )

    provider = MagicMock()
    provider.validate_webhook = AsyncMock(return_value=WebhookValidationResult(is_valid=True))
    provider.parse_inbound = AsyncMock(
        return_value=InboundMessage(
            platform=Platform.WHATSAPP,
            platform_user_id="+1234567890",
            platform_message_id="wamid.RL",
            content="Hello",
            timestamp=datetime.now(UTC),
            raw_payload={},
        )
    )
    app.dependency_overrides[get_whatsapp_provider] = lambda: provider

    mock_limiter.is_allowed.return_value = False

    try:
        response = await client.post(
            "/api/webhooks/whatsapp",
            content=b'{}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 429
        mock_task.delay.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_whatsapp_provider, None)
