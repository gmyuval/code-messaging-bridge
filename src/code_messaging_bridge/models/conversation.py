"""Conversation model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from code_messaging_bridge.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from code_messaging_bridge.models.message import Message


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Represents a conversation between a user and Claude Code.

    Each conversation tracks the messaging platform, the user's platform-specific
    identifier, and the Claude Code session ID for conversation continuity.
    """

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint(
            "platform",
            "platform_user_id",
            "is_active",
            name="uq_active_conversation",
        ),
    )

    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    platform_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    claude_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    working_directory: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"Conversation(id={self.id!r}, platform={self.platform!r}, "
            f"user={self.platform_user_id!r}, active={self.is_active!r})"
        )
