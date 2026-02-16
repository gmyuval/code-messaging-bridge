"""Messaging provider factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from code_messaging_bridge.services.messaging.meta_whatsapp import MetaWhatsAppProvider
from code_messaging_bridge.services.messaging.schemas import Platform

if TYPE_CHECKING:
    from collections.abc import Callable

    from code_messaging_bridge.config import Settings
    from code_messaging_bridge.services.messaging.base import MessagingProvider


def _create_whatsapp(settings: Settings) -> MetaWhatsAppProvider:
    return MetaWhatsAppProvider(
        phone_number_id=settings.meta_phone_number_id,
        access_token=settings.meta_access_token,
        app_secret=settings.meta_app_secret,
        verify_token=settings.meta_verify_token,
    )


class ProviderFactory:
    """Factory for creating messaging providers from configuration."""

    _registry: ClassVar[dict[Platform, Callable[[Settings], MessagingProvider]]] = {
        Platform.WHATSAPP: _create_whatsapp,
    }

    @classmethod
    def register(
        cls, platform: Platform, factory: Callable[[Settings], MessagingProvider]
    ) -> None:
        """Register a factory callable for a platform."""
        cls._registry[platform] = factory

    @classmethod
    def create(cls, platform: Platform, settings: Settings) -> MessagingProvider:
        """Create a messaging provider instance from settings."""
        factory = cls._registry.get(platform)
        if factory is None:
            msg = f"No provider registered for platform: {platform}"
            raise ValueError(msg)
        return factory(settings)
