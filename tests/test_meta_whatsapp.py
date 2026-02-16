"""Tests for Meta WhatsApp Business API messaging provider."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from code_messaging_bridge.services.messaging.meta_whatsapp import MetaWhatsAppProvider
from code_messaging_bridge.services.messaging.schemas import (
    OutboundMessage,
    Platform,
)

APP_SECRET = "test_app_secret"
VERIFY_TOKEN = "test_verify_token"


def _make_provider() -> MetaWhatsAppProvider:
    """Create a MetaWhatsAppProvider for tests."""
    return MetaWhatsAppProvider(
        phone_number_id="123456789",
        access_token="test_access_token",
        app_secret=APP_SECRET,
        verify_token=VERIFY_TOKEN,
    )


def _sign_payload(payload: bytes, secret: str = APP_SECRET) -> str:
    """Compute HMAC-SHA256 signature for a payload."""
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


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
    """Should accept a valid X-Hub-Signature-256."""
    provider = _make_provider()

    body = b'{"entry": []}'
    signature = _sign_payload(body)

    request = AsyncMock(spec=Request)
    request.headers = {"X-Hub-Signature-256": signature}
    request.body = AsyncMock(return_value=body)

    result = await provider.validate_webhook(request)
    assert result.is_valid


@pytest.mark.asyncio
async def test_validate_webhook_invalid_signature() -> None:
    """Should reject an invalid X-Hub-Signature-256."""
    provider = _make_provider()

    body = b'{"entry": []}'
    request = AsyncMock(spec=Request)
    request.headers = {"X-Hub-Signature-256": "sha256=bad_signature"}
    request.body = AsyncMock(return_value=body)

    result = await provider.validate_webhook(request)
    assert not result.is_valid
    assert result.error_message is not None


@pytest.mark.asyncio
async def test_validate_webhook_missing_header() -> None:
    """Should reject requests without X-Hub-Signature-256 header."""
    provider = _make_provider()

    request = AsyncMock(spec=Request)
    request.headers = {}
    request.body = AsyncMock(return_value=b"{}")

    result = await provider.validate_webhook(request)
    assert not result.is_valid


@pytest.mark.asyncio
async def test_parse_inbound() -> None:
    """Should parse Meta webhook JSON into an InboundMessage."""
    provider = _make_provider()

    payload: dict[str, Any] = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BIZ_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "123456789",
                            },
                            "contacts": [{"profile": {"name": "Test"}, "wa_id": "1234567890"}],
                            "messages": [
                                {
                                    "from": "1234567890",
                                    "id": "wamid.HBgLMTIzNDU2Nzg5MA==",
                                    "timestamp": "1700000000",
                                    "text": {"body": "Hello Claude!"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    request = AsyncMock(spec=Request)
    request.json = AsyncMock(return_value=payload)

    message = await provider.parse_inbound(request)
    assert message.platform == Platform.WHATSAPP
    assert message.platform_user_id == "1234567890"
    assert message.content == "Hello Claude!"
    assert message.platform_message_id == "wamid.HBgLMTIzNDU2Nzg5MA=="


@pytest.mark.asyncio
@patch("code_messaging_bridge.services.messaging.meta_whatsapp.httpx.AsyncClient")
async def test_send_message_short(mock_client_cls: MagicMock) -> None:
    """Should send a short message without splitting."""
    provider = _make_provider()

    mock_response = MagicMock()
    mock_response.json.return_value = {"messages": [{"id": "wamid.SENT_123"}]}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    result = await provider.send_message(
        OutboundMessage(
            platform=Platform.WHATSAPP,
            recipient_id="1234567890",
            content="Short reply",
        )
    )

    assert result.success
    assert result.platform_message_id == "wamid.SENT_123"
    assert result.parts_sent == 1


@pytest.mark.asyncio
@patch("code_messaging_bridge.services.messaging.meta_whatsapp.httpx.AsyncClient")
async def test_send_message_long_is_split(mock_client_cls: MagicMock) -> None:
    """Should split a long message into multiple parts."""
    provider = _make_provider()

    call_count = 0

    async def mock_post(*_args: Any, **_kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.json.return_value = {"messages": [{"id": f"wamid.PART_{call_count}"}]}
        resp.raise_for_status = MagicMock()
        return resp

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client_cls.return_value = mock_client

    long_content = "A" * 2000
    result = await provider.send_message(
        OutboundMessage(
            platform=Platform.WHATSAPP,
            recipient_id="1234567890",
            content=long_content,
        )
    )

    assert result.success
    assert result.parts_sent >= 2
    assert call_count >= 2


def test_verify_challenge_valid() -> None:
    """Should return challenge when mode and token match."""
    provider = _make_provider()
    result = provider.verify_challenge("subscribe", VERIFY_TOKEN, "challenge_123")
    assert result == "challenge_123"


def test_verify_challenge_invalid_token() -> None:
    """Should return None for invalid verify token."""
    provider = _make_provider()
    result = provider.verify_challenge("subscribe", "wrong_token", "challenge_123")
    assert result is None


def test_verify_challenge_wrong_mode() -> None:
    """Should return None for wrong hub.mode."""
    provider = _make_provider()
    result = provider.verify_challenge("unsubscribe", VERIFY_TOKEN, "challenge_123")
    assert result is None
