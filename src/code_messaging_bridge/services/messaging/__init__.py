"""Messaging provider interfaces and implementations."""

from code_messaging_bridge.services.messaging.base import MessagingProvider
from code_messaging_bridge.services.messaging.factory import ProviderFactory
from code_messaging_bridge.services.messaging.message_splitter import MessageSplitter
from code_messaging_bridge.services.messaging.meta_whatsapp import MetaWhatsAppProvider
from code_messaging_bridge.services.messaging.schemas import (
    InboundMessage,
    OutboundMessage,
    Platform,
    SendResult,
    WebhookValidationResult,
)

__all__ = [
    "InboundMessage",
    "MessageSplitter",
    "MessagingProvider",
    "MetaWhatsAppProvider",
    "OutboundMessage",
    "Platform",
    "ProviderFactory",
    "SendResult",
    "WebhookValidationResult",
]
