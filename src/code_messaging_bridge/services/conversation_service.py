"""Conversation and message persistence service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from code_messaging_bridge.models import (
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
)

logger = logging.getLogger(__name__)

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
        """Find an active conversation or create a new one.

        Uses a retry-after-IntegrityError pattern to handle concurrent requests
        that may both try to create a conversation for the same user. The
        conversations table has a unique constraint on (platform, platform_user_id,
        is_active) to prevent duplicates at the database level.
        """
        conversation = await self._find_active_conversation(platform, platform_user_id)
        if conversation is not None:
            return conversation

        try:
            conversation = Conversation(
                platform=platform.value,
                platform_user_id=platform_user_id,
                working_directory=working_directory,
                is_active=True,
            )
            self._session.add(conversation)
            await self._session.flush()
            return conversation
        except IntegrityError:
            logger.info(
                "Concurrent conversation creation for %s:%s, retrying SELECT",
                platform.value,
                platform_user_id,
            )
            await self._session.rollback()
            conversation = await self._find_active_conversation(platform, platform_user_id)
            if conversation is None:
                msg = (
                    f"Failed to find conversation after IntegrityError "
                    f"for {platform.value}:{platform_user_id}"
                )
                raise RuntimeError(msg) from None
            return conversation

    async def _find_active_conversation(
        self,
        platform: Platform,
        platform_user_id: str,
    ) -> Conversation | None:
        """Find an active conversation for the given platform and user."""
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.platform == platform.value,
                Conversation.platform_user_id == platform_user_id,
                Conversation.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

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

    async def message_exists(self, platform_message_id: str) -> bool:
        """Check if a message with the given platform_message_id already exists."""
        result = await self._session.execute(
            select(Message.id).where(
                Message.platform_message_id == platform_message_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def update_claude_session_id(
        self,
        conversation: Conversation,
        session_id: str,
    ) -> None:
        """Update the Claude session ID on a conversation."""
        conversation.claude_session_id = session_id
        await self._session.flush()
