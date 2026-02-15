"""Tests for database models."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from code_messaging_bridge.models import (
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_conversation(async_session: AsyncSession) -> None:
    """Should be able to create and retrieve a conversation."""
    conversation = Conversation(
        platform="whatsapp",
        platform_user_id="whatsapp:+1234567890",
        working_directory="/tmp/project",
        is_active=True,
    )
    async_session.add(conversation)
    await async_session.commit()

    result = await async_session.execute(
        select(Conversation).where(Conversation.platform_user_id == "whatsapp:+1234567890")
    )
    fetched = result.scalar_one()
    assert fetched.platform == "whatsapp"
    assert fetched.is_active is True
    assert fetched.claude_session_id is None
    assert isinstance(fetched.id, uuid.UUID)


@pytest.mark.asyncio
async def test_create_message(async_session: AsyncSession) -> None:
    """Should be able to create a message linked to a conversation."""
    conversation = Conversation(
        platform="whatsapp",
        platform_user_id="whatsapp:+1234567890",
        working_directory="/tmp/project",
    )
    async_session.add(conversation)
    await async_session.flush()

    message = Message(
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        content="Hello Claude!",
        status=MessageStatus.RECEIVED,
    )
    async_session.add(message)
    await async_session.commit()

    result = await async_session.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    )
    fetched = result.scalar_one()
    assert fetched.content == "Hello Claude!"
    assert fetched.direction == MessageDirection.INBOUND
    assert fetched.status == MessageStatus.RECEIVED


@pytest.mark.asyncio
async def test_conversation_message_relationship(async_session: AsyncSession) -> None:
    """Conversation should have a messages relationship."""
    conversation = Conversation(
        platform="whatsapp",
        platform_user_id="whatsapp:+9999999999",
        working_directory="/tmp/project",
    )
    async_session.add(conversation)
    await async_session.flush()

    msg1 = Message(
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        content="First message",
        status=MessageStatus.RECEIVED,
    )
    msg2 = Message(
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        content="Response",
        status=MessageStatus.SENT,
    )
    async_session.add_all([msg1, msg2])
    await async_session.commit()

    result = await async_session.execute(
        select(Conversation).where(Conversation.id == conversation.id)
    )
    fetched = result.scalar_one()
    await async_session.refresh(fetched, ["messages"])
    assert len(fetched.messages) == 2


@pytest.mark.asyncio
async def test_message_direction_enum() -> None:
    """MessageDirection enum should have expected values."""
    assert MessageDirection.INBOUND.value == "inbound"
    assert MessageDirection.OUTBOUND.value == "outbound"


@pytest.mark.asyncio
async def test_message_status_enum() -> None:
    """MessageStatus enum should have expected values."""
    assert MessageStatus.RECEIVED.value == "received"
    assert MessageStatus.PROCESSING.value == "processing"
    assert MessageStatus.SENT.value == "sent"
    assert MessageStatus.FAILED.value == "failed"
