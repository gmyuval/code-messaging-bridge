"""Message model."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from code_messaging_bridge.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from code_messaging_bridge.models.conversation import Conversation


class MessageDirection(enum.StrEnum):
    """Direction of a message relative to the bridge."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(enum.StrEnum):
    """Processing status of a message."""

    RECEIVED = "received"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Represents a single message within a conversation.

    Tracks the content, direction (inbound/outbound), processing status,
    and platform-specific metadata.
    """

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    direction: Mapped[MessageDirection] = mapped_column(
        SQLAlchemyEnum(MessageDirection),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    platform_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[MessageStatus] = mapped_column(
        SQLAlchemyEnum(MessageStatus),
        default=MessageStatus.RECEIVED,
        nullable=False,
    )
    metadata_: Mapped[dict[str, object] | None] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
        default=dict,
    )

    conversation: Mapped[Conversation] = relationship(
        "Conversation",
        back_populates="messages",
    )

    def __repr__(self) -> str:
        return f"Message(id={self.id!r}, direction={self.direction!r}, status={self.status!r})"
