"""Messaging provider factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from code_messaging_bridge.services.messaging.schemas import Platform
from code_messaging_bridge.services.messaging.twilio_whatsapp import TwilioWhatsAppProvider

if TYPE_CHECKING:
    from code_messaging_bridge.config import Settings
    from code_messaging_bridge.services.messaging.base import MessagingProvider


class ProviderFactory:
    """Factory for creating messaging providers from configuration."""

    _registry: ClassVar[dict[Platform, type[MessagingProvider]]] = {
        Platform.WHATSAPP: TwilioWhatsAppProvider,
    }

    @classmethod
    def register(cls, platform: Platform, provider_class: type[MessagingProvider]) -> None:
        """Register a new messaging provider class."""
        cls._registry[platform] = provider_class

    @classmethod
    def create(cls, platform: Platform, settings: Settings) -> MessagingProvider:
        """Create a messaging provider instance from settings."""
        provider_class = cls._registry.get(platform)
        if provider_class is None:
            msg = f"No provider registered for platform: {platform}"
            raise ValueError(msg)

        if platform == Platform.WHATSAPP:
            return TwilioWhatsAppProvider(
                account_sid=settings.twilio_account_sid,
                auth_token=settings.twilio_auth_token,
                whatsapp_number=settings.twilio_whatsapp_number,
                webhook_base_url=settings.webhook_base_url,
            )

        msg = f"Unsupported platform: {platform}"
        raise ValueError(msg)
