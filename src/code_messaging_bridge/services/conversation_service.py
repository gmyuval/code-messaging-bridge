"""Conversation and message persistence service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from code_messaging_bridge.models import (
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from code_messaging_bridge.services.messaging.schemas import InboundMessage, Platform


class ConversationService:
    """Manages conversation and message persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_conversation(
        self,
        platform: Platform,
        platform_user_id: str,
        working_directory: str,
    ) -> Conversation:
        """Find an active conversation or create a new one."""
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.platform == platform.value,
                Conversation.platform_user_id == platform_user_id,
                Conversation.is_active.is_(True),
            )
        )
        conversation = result.scalar_one_or_none()

        if conversation is None:
            conversation = Conversation(
                platform=platform.value,
                platform_user_id=platform_user_id,
                working_directory=working_directory,
                is_active=True,
            )
            self._session.add(conversation)
            await self._session.flush()

        return conversation

    async def store_inbound_message(
        self,
        conversation: Conversation,
        inbound: InboundMessage,
    ) -> Message:
        """Persist an inbound message."""
        message = Message(
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND,
            content=inbound.content,
            platform_message_id=inbound.platform_message_id,
            status=MessageStatus.RECEIVED,
            metadata_={"raw_payload": inbound.raw_payload},
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def store_outbound_message(
        self,
        conversation: Conversation,
        content: str,
        platform_message_id: str | None = None,
        status: MessageStatus = MessageStatus.SENT,
    ) -> Message:
        """Persist an outbound message."""
        message = Message(
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            content=content,
            platform_message_id=platform_message_id,
            status=status,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def update_message_status(
        self,
        message_id: uuid.UUID,
        status: MessageStatus,
    ) -> None:
        """Update a message's processing status."""
        result = await self._session.execute(select(Message).where(Message.id == message_id))
        message = result.scalar_one()
        message.status = status
        await self._session.flush()

    async def update_claude_session_id(
        self,
        conversation: Conversation,
        session_id: str,
    ) -> None:
        """Update the Claude session ID on a conversation."""
        conversation.claude_session_id = session_id
        await self._session.flush()
