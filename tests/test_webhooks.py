"""Tests for webhook endpoints."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from code_messaging_bridge.models import Conversation, Message, MessageDirection

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_whatsapp_provider() -> MagicMock:
    """Create a mock Meta WhatsApp provider for webhook tests."""
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
            platform_user_id="1234567890",
            platform_message_id="wamid.TEST_123",
            content="Hello Claude!",
            timestamp=datetime.now(UTC),
            raw_payload={"object": "whatsapp_business_account"},
        )
    )
    return provider


def _meta_webhook_payload(body: str = "Hello Claude!", sender: str = "1234567890") -> dict:
    """Build a minimal Meta WhatsApp webhook payload."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "BIZ_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "15551234567", "phone_number_id": "123"},
                    "contacts": [{"profile": {"name": "Test"}, "wa_id": sender}],
                    "messages": [{
                        "from": sender,
                        "id": "wamid.TEST",
                        "timestamp": "1700000000",
                        "text": {"body": body},
                        "type": "text",
                    }],
                },
                "field": "messages",
            }],
        }],
    }


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.webhooks.process_whatsapp_message")
async def test_webhook_enqueues_task(
    mock_task: MagicMock,
    client: AsyncClient,
    app: Any,
    mock_whatsapp_provider: MagicMock,
    async_session: AsyncSession,  # noqa: ARG001
) -> None:
    """Webhook should enqueue a Celery task for Claude processing."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider

    app.dependency_overrides[get_whatsapp_provider] = lambda: mock_whatsapp_provider

    response = await client.post(
        "/api/webhooks/whatsapp",
        content=json.dumps(_meta_webhook_payload()),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert "OK" in response.text

    # Verify Celery task was enqueued
    mock_task.delay.assert_called_once()
    call_args = mock_task.delay.call_args
    assert call_args[0][1] == "Hello Claude!"  # content
    assert call_args[0][2] == "1234567890"  # platform_user_id

    app.dependency_overrides.pop(get_whatsapp_provider, None)


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.webhooks.process_whatsapp_message")
async def test_webhook_stores_inbound_message(
    _mock_task: MagicMock,
    client: AsyncClient,
    app: Any,
    mock_whatsapp_provider: MagicMock,
    async_session: AsyncSession,
) -> None:
    """Webhook should store the inbound message in DB before enqueuing task."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider

    app.dependency_overrides[get_whatsapp_provider] = lambda: mock_whatsapp_provider

    await client.post(
        "/api/webhooks/whatsapp",
        content=json.dumps(_meta_webhook_payload()),
        headers={"Content-Type": "application/json"},
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
    """Webhook should reject requests with invalid signature."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider
    from code_messaging_bridge.services.messaging.schemas import WebhookValidationResult

    invalid_provider = MagicMock()
    invalid_provider.validate_webhook = AsyncMock(
        return_value=WebhookValidationResult(
            is_valid=False, error_message="Invalid webhook signature"
        )
    )

    app.dependency_overrides[get_whatsapp_provider] = lambda: invalid_provider

    response = await client.post(
        "/api/webhooks/whatsapp",
        content=json.dumps(_meta_webhook_payload()),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 403

    app.dependency_overrides.pop(get_whatsapp_provider, None)


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.webhooks.process_whatsapp_message")
async def test_webhook_creates_conversation_once(
    mock_task: MagicMock,
    client: AsyncClient,
    app: Any,
    async_session: AsyncSession,
) -> None:
    """Multiple messages from the same user should reuse the same conversation."""
    from datetime import UTC, datetime

    from code_messaging_bridge.api.dependencies import get_whatsapp_provider
    from code_messaging_bridge.services.messaging.schemas import (
        InboundMessage,
        Platform,
        WebhookValidationResult,
    )

    # Each message has a different platform_message_id (not a duplicate)
    call_count = 0

    async def parse_inbound_side_effect(*_args: Any, **_kwargs: Any) -> InboundMessage:
        nonlocal call_count
        call_count += 1
        return InboundMessage(
            platform=Platform.WHATSAPP,
            platform_user_id="1234567890",
            platform_message_id=f"wamid.MSG_{call_count}",
            content=f"Message {call_count}",
            timestamp=datetime.now(UTC),
            raw_payload={},
        )

    provider = MagicMock()
    provider.validate_webhook = AsyncMock(return_value=WebhookValidationResult(is_valid=True))
    provider.parse_inbound = AsyncMock(side_effect=parse_inbound_side_effect)
    app.dependency_overrides[get_whatsapp_provider] = lambda: provider

    # Send two messages
    await client.post(
        "/api/webhooks/whatsapp",
        content=json.dumps(_meta_webhook_payload("First")),
        headers={"Content-Type": "application/json"},
    )
    await client.post(
        "/api/webhooks/whatsapp",
        content=json.dumps(_meta_webhook_payload("Second")),
        headers={"Content-Type": "application/json"},
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


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.webhooks.process_whatsapp_message")
async def test_webhook_idempotency_skips_duplicate(
    mock_task: MagicMock,
    client: AsyncClient,
    app: Any,
    mock_whatsapp_provider: MagicMock,
    async_session: AsyncSession,
) -> None:
    """Duplicate webhook delivery (same platform_message_id) should be idempotent."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider

    app.dependency_overrides[get_whatsapp_provider] = lambda: mock_whatsapp_provider

    # First delivery
    r1 = await client.post(
        "/api/webhooks/whatsapp",
        content=json.dumps(_meta_webhook_payload()),
        headers={"Content-Type": "application/json"},
    )
    assert r1.status_code == 200

    # Second delivery (same message ID from mock fixture)
    r2 = await client.post(
        "/api/webhooks/whatsapp",
        content=json.dumps(_meta_webhook_payload()),
        headers={"Content-Type": "application/json"},
    )
    assert r2.status_code == 200

    # Only one message stored, only one task enqueued
    msg_result = await async_session.execute(select(Message))
    messages = msg_result.scalars().all()
    assert len(messages) == 1

    mock_task.delay.assert_called_once()

    app.dependency_overrides.pop(get_whatsapp_provider, None)


@pytest.mark.asyncio
async def test_webhook_verify_challenge(
    client: AsyncClient,
    app: Any,
) -> None:
    """GET endpoint should return challenge when verify_token matches."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider

    provider = MagicMock()
    provider.verify_challenge = MagicMock(return_value="challenge_abc")
    app.dependency_overrides[get_whatsapp_provider] = lambda: provider

    response = await client.get(
        "/api/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "my_token",
            "hub.challenge": "challenge_abc",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge_abc"

    app.dependency_overrides.pop(get_whatsapp_provider, None)


@pytest.mark.asyncio
async def test_webhook_verify_challenge_rejected(
    client: AsyncClient,
    app: Any,
) -> None:
    """GET endpoint should return 403 when verify_token doesn't match."""
    from code_messaging_bridge.api.dependencies import get_whatsapp_provider

    provider = MagicMock()
    provider.verify_challenge = MagicMock(return_value=None)
    app.dependency_overrides[get_whatsapp_provider] = lambda: provider

    response = await client.get(
        "/api/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "challenge_abc",
        },
    )

    assert response.status_code == 403

    app.dependency_overrides.pop(get_whatsapp_provider, None)
