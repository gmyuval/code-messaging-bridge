"""add unique constraints and indexes for idempotency

Revision ID: a1b2c3d4e5f6
Revises: 3bd838f12a86
Create Date: 2026-02-16 12:00:00.000000

"""
from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "3bd838f12a86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Prevent duplicate active conversations for the same user on the same platform
    op.create_unique_constraint(
        "uq_active_conversation",
        "conversations",
        ["platform", "platform_user_id", "is_active"],
    )

    # Unique index for webhook idempotency — prevents duplicate message storage
    op.create_index(
        "ix_messages_platform_message_id",
        "messages",
        ["platform_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_platform_message_id", table_name="messages")
    op.drop_constraint("uq_active_conversation", "conversations", type_="unique")
