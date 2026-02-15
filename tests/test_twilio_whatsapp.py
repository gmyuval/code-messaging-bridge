"""Tests for Twilio WhatsApp messaging provider."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from code_messaging_bridge.services.messaging.schemas import (
    OutboundMessage,
    Platform,
)
from code_messaging_bridge.services.messaging.twilio_whatsapp import (
    TwilioWhatsAppProvider,
)


def _make_provider(
    auth_token: str = "test_token",
) -> TwilioWhatsAppProvider:
    """Create a TwilioWhatsAppProvider with mocked Twilio client."""
    with patch("code_messaging_bridge.services.messaging.twilio_whatsapp.TwilioClient"):
        return TwilioWhatsAppProvider(
            account_sid="test_sid",
            auth_token=auth_token,
            whatsapp_number="whatsapp:+14155238886",
            webhook_base_url="https://example.ngrok.io",
        )


def test_platform_is_whatsapp() -> None:
    """Provider should identify as WhatsApp platform."""
    provider = _make_provider()
    assert provider.platform == Platform.WHATSAPP


def test_max_message_length() -> None:
    """Max message length should be 1600."""
    provider = _make_provider()
    assert provider.max_message_length == 1600


@pytest.mark.asyncio
async def test_validate_webhook_valid_signature() -> None:
    """Should accept a valid Twilio signature."""
    provider = _make_provider()

    # Mock the request
    request = AsyncMock(spec=Request)
    request.form = AsyncMock(return_value={"Body": "Hello", "From": "whatsapp:+1234567890"})
    request.headers = {"X-Twilio-Signature": "valid_sig"}
    request.url.path = "/api/webhooks/twilio/whatsapp"

    # Mock the validator to return True
    provider._validator.validate = MagicMock(return_value=True)  # noqa: SLF001

    result = await provider.validate_webhook(request)
    assert result.is_valid


@pytest.mark.asyncio
async def test_validate_webhook_invalid_signature() -> None:
    """Should reject an invalid Twilio signature."""
    provider = _make_provider()

    request = AsyncMock(spec=Request)
    request.form = AsyncMock(return_value={"Body": "Hello"})
    request.headers = {"X-Twilio-Signature": "bad_sig"}
    request.url.path = "/api/webhooks/twilio/whatsapp"

    provider._validator.validate = MagicMock(return_value=False)  # noqa: SLF001

    result = await provider.validate_webhook(request)
    assert not result.is_valid
    assert result.error_message is not None


@pytest.mark.asyncio
async def test_parse_inbound() -> None:
    """Should parse Twilio form data into an InboundMessage."""
    provider = _make_provider()

    form_data: dict[str, Any] = {
        "From": "whatsapp:+1234567890",
        "Body": "Hello Claude!",
        "MessageSid": "SM123456",
    }
    request = AsyncMock(spec=Request)
    request.form = AsyncMock(return_value=form_data)

    message = await provider.parse_inbound(request)
    assert message.platform == Platform.WHATSAPP
    assert message.platform_user_id == "whatsapp:+1234567890"
    assert message.content == "Hello Claude!"
    assert message.platform_message_id == "SM123456"


@pytest.mark.asyncio
async def test_send_message_short() -> None:
    """Should send a short message without splitting."""
    provider = _make_provider()

    mock_message = MagicMock()
    mock_message.sid = "SM_SENT_123"
    provider._client.messages.create = MagicMock(return_value=mock_message)  # noqa: SLF001

    result = await provider.send_message(
        OutboundMessage(
            platform=Platform.WHATSAPP,
            recipient_id="whatsapp:+1234567890",
            content="Short reply",
        )
    )

    assert result.success
    assert result.platform_message_id == "SM_SENT_123"
    assert result.parts_sent == 1


@pytest.mark.asyncio
async def test_send_message_long_is_split() -> None:
    """Should split a long message into multiple parts."""
    provider = _make_provider()

    call_count = 0
    sids: list[str] = []

    def mock_create(**kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        msg = MagicMock()
        msg.sid = f"SM_PART_{call_count}"
        sids.append(msg.sid)
        return msg

    provider._client.messages.create = mock_create  # noqa: SLF001

    # Message longer than 1600 chars
    long_content = "A" * 2000
    result = await provider.send_message(
        OutboundMessage(
            platform=Platform.WHATSAPP,
            recipient_id="whatsapp:+1234567890",
            content=long_content,
        )
    )

    assert result.success
    assert result.parts_sent >= 2
    assert call_count >= 2
