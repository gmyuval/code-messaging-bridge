"""Tests for webhook endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

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
    return provider


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.webhooks.process_whatsapp_message")
async def test_webhook_enqueues_task(
    mock_task: MagicMock,
    client: AsyncClient,
    app: Any,
    mock_twilio_provider: MagicMock,
    async_session: AsyncSession,
) -> None:
    """Webhook should enqueue a Celery task for Claude processing."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider

    app.dependency_overrides[get_whatsapp_provider] = lambda: mock_twilio_provider

    response = await client.post(
        "/api/webhooks/twilio/whatsapp",
        data={"Body": "Hello Claude!", "From": "whatsapp:+1234567890", "MessageSid": "SM123"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    assert "<Response/>" in response.text

    # Verify Celery task was enqueued
    mock_task.delay.assert_called_once()
    call_args = mock_task.delay.call_args
    assert call_args[0][1] == "Hello Claude!"  # content
    assert call_args[0][2] == "whatsapp:+1234567890"  # platform_user_id

    app.dependency_overrides.pop(get_whatsapp_provider, None)


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.webhooks.process_whatsapp_message")
async def test_webhook_stores_inbound_message(
    mock_task: MagicMock,
    client: AsyncClient,
    app: Any,
    mock_twilio_provider: MagicMock,
    async_session: AsyncSession,
) -> None:
    """Webhook should store the inbound message in DB before enqueuing task."""
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

    # Check inbound message was stored (outbound handled by Celery worker)
    msg_result = await async_session.execute(select(Message))
    messages = msg_result.scalars().all()
    assert len(messages) == 1
    assert messages[0].direction == MessageDirection.INBOUND
    assert messages[0].content == "Hello Claude!"

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
@patch("code_messaging_bridge.api.webhooks.process_whatsapp_message")
async def test_webhook_creates_conversation_once(
    mock_task: MagicMock,
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
    conv_result = await async_session.execute(select(Conversation))
    conversations = conv_result.scalars().all()
    assert len(conversations) == 1

    # 2 inbound messages (outbound handled by Celery worker)
    msg_result = await async_session.execute(select(Message))
    messages = msg_result.scalars().all()
    assert len(messages) == 2

    # Both tasks enqueued
    assert mock_task.delay.call_count == 2

    app.dependency_overrides.pop(get_whatsapp_provider, None)
