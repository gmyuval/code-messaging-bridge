"""Platform-agnostic messaging schemas."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


class Platform(enum.StrEnum):
    """Supported messaging platforms."""

    WHATSAPP = "whatsapp"


@dataclass(frozen=True)
class InboundMessage:
    """Platform-agnostic representation of a received message."""

    platform: Platform
    platform_user_id: str
    platform_message_id: str
    content: str
    timestamp: datetime
    raw_payload: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OutboundMessage:
    """Platform-agnostic representation of a message to send."""

    platform: Platform
    recipient_id: str
    content: str
    reply_to_message_id: str | None = None


@dataclass(frozen=True)
class SendResult:
    """Result of sending a message."""

    success: bool
    platform_message_id: str | None = None
    error_message: str | None = None
    parts_sent: int = 1


@dataclass(frozen=True)
class WebhookValidationResult:
    """Result of webhook request validation."""

    is_valid: bool
    error_message: str | None = None
