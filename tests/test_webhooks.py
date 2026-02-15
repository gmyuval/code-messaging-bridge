"""Tests for webhook endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from code_messaging_bridge.models import Conversation, Message, MessageDirection

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_twilio_provider() -> MagicMock:
    """Create a mock Twilio provider for webhook tests."""
    from datetime import UTC, datetime

    from code_messaging_bridge.services.messaging.schemas import (
        InboundMessage,
        Platform,
        SendResult,
        WebhookValidationResult,
    )

    provider = MagicMock()
    provider.validate_webhook = AsyncMock(return_value=WebhookValidationResult(is_valid=True))
    provider.parse_inbound = AsyncMock(
        return_value=InboundMessage(
            platform=Platform.WHATSAPP,
            platform_user_id="whatsapp:+1234567890",
            platform_message_id="SM_TEST_123",
            content="Hello Claude!",
            timestamp=datetime.now(UTC),
            raw_payload={"Body": "Hello Claude!", "From": "whatsapp:+1234567890"},
        )
    )
    provider.send_message = AsyncMock(
        return_value=SendResult(success=True, platform_message_id="SM_ECHO_456", parts_sent=1)
    )
    return provider


@pytest.mark.asyncio
async def test_webhook_echo_bot(
    client: AsyncClient,
    app: Any,
    mock_twilio_provider: MagicMock,
    async_session: AsyncSession,
) -> None:
    """Webhook should receive message, store it, and echo back."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider

    app.dependency_overrides[get_whatsapp_provider] = lambda: mock_twilio_provider

    response = await client.post(
        "/api/webhooks/twilio/whatsapp",
        data={"Body": "Hello Claude!", "From": "whatsapp:+1234567890", "MessageSid": "SM123"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    assert "<Response/>" in response.text

    # Verify message was sent back
    mock_twilio_provider.send_message.assert_called_once()
    call_args = mock_twilio_provider.send_message.call_args
    sent_message = call_args[0][0]
    assert sent_message.content == "Echo: Hello Claude!"

    app.dependency_overrides.pop(get_whatsapp_provider, None)


@pytest.mark.asyncio
async def test_webhook_stores_messages(
    client: AsyncClient,
    app: Any,
    mock_twilio_provider: MagicMock,
    async_session: AsyncSession,
) -> None:
    """Webhook should store both inbound and outbound messages in DB."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider

    app.dependency_overrides[get_whatsapp_provider] = lambda: mock_twilio_provider

    await client.post(
        "/api/webhooks/twilio/whatsapp",
        data={"Body": "Test", "From": "whatsapp:+1234567890", "MessageSid": "SM123"},
    )

    # Check conversation was created
    conv_result = await async_session.execute(select(Conversation))
    conversations = conv_result.scalars().all()
    assert len(conversations) == 1
    assert conversations[0].platform == "whatsapp"

    # Check messages were stored
    msg_result = await async_session.execute(select(Message).order_by(Message.created_at))
    messages = msg_result.scalars().all()
    assert len(messages) == 2
    assert messages[0].direction == MessageDirection.INBOUND
    assert messages[0].content == "Hello Claude!"
    assert messages[1].direction == MessageDirection.OUTBOUND
    assert "Echo:" in messages[1].content

    app.dependency_overrides.pop(get_whatsapp_provider, None)


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(
    client: AsyncClient,
    app: Any,
) -> None:
    """Webhook should reject requests with invalid Twilio signature."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider
    from code_messaging_bridge.services.messaging.schemas import WebhookValidationResult

    invalid_provider = MagicMock()
    invalid_provider.validate_webhook = AsyncMock(
        return_value=WebhookValidationResult(
            is_valid=False, error_message="Invalid Twilio signature"
        )
    )

    app.dependency_overrides[get_whatsapp_provider] = lambda: invalid_provider

    response = await client.post(
        "/api/webhooks/twilio/whatsapp",
        data={"Body": "Hello", "From": "whatsapp:+1234567890"},
    )

    assert response.status_code == 403

    app.dependency_overrides.pop(get_whatsapp_provider, None)


@pytest.mark.asyncio
async def test_webhook_creates_conversation_once(
    client: AsyncClient,
    app: Any,
    mock_twilio_provider: MagicMock,
    async_session: AsyncSession,
) -> None:
    """Multiple messages from the same user should reuse the same conversation."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider

    app.dependency_overrides[get_whatsapp_provider] = lambda: mock_twilio_provider

    # Send two messages
    await client.post(
        "/api/webhooks/twilio/whatsapp",
        data={"Body": "First", "From": "whatsapp:+1234567890", "MessageSid": "SM1"},
    )
    await client.post(
        "/api/webhooks/twilio/whatsapp",
        data={"Body": "Second", "From": "whatsapp:+1234567890", "MessageSid": "SM2"},
    )

    # Should still be one conversation
    result = await async_session.execute(select(Conversation))
    conversations = result.scalars().all()
    assert len(conversations) == 1

    # But 4 messages (2 inbound + 2 outbound)
    result = await async_session.execute(select(Message))
    messages = result.scalars().all()
    assert len(messages) == 4

    app.dependency_overrides.pop(get_whatsapp_provider, None)
