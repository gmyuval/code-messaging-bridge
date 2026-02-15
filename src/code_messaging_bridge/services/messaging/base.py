"""Abstract messaging provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

    from code_messaging_bridge.services.messaging.schemas import (
        InboundMessage,
        OutboundMessage,
        Platform,
        SendResult,
        WebhookValidationResult,
    )


class MessagingProvider(ABC):
    """Abstract interface for messaging platform providers.

    To add a new platform:
    1. Create a new class inheriting from MessagingProvider
    2. Implement all abstract methods
    3. Register it in the ProviderFactory
    """

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """Return the platform identifier for this provider."""
        ...

    @property
    @abstractmethod
    def max_message_length(self) -> int:
        """Return the maximum single message length for this platform."""
        ...

    @abstractmethod
    async def validate_webhook(self, request: Request) -> WebhookValidationResult:
        """Validate that an incoming webhook request is authentic."""
        ...

    @abstractmethod
    async def parse_inbound(self, request: Request) -> InboundMessage | None:
        """Parse an incoming webhook request into a platform-agnostic InboundMessage.

        Returns None for non-message events (e.g., status updates, delivery receipts).
        """
        ...

    @abstractmethod
    async def send_message(self, message: OutboundMessage) -> SendResult:
        """Send a message to the platform, splitting if needed."""
        ...
