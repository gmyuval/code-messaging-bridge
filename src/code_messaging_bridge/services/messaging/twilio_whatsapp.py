"""Twilio WhatsApp messaging provider."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioClient

from code_messaging_bridge.services.messaging.base import MessagingProvider
from code_messaging_bridge.services.messaging.message_splitter import MessageSplitter
from code_messaging_bridge.services.messaging.schemas import (
    InboundMessage,
    OutboundMessage,
    Platform,
    SendResult,
    WebhookValidationResult,
)

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)

WHATSAPP_MAX_LENGTH = 1600


class TwilioWhatsAppProvider(MessagingProvider):
    """Twilio WhatsApp messaging provider.

    Handles webhook signature verification, message parsing,
    and sending messages via the Twilio REST API.
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        whatsapp_number: str,
        webhook_base_url: str,
        splitter: MessageSplitter | None = None,
    ) -> None:
        self._client = TwilioClient(account_sid, auth_token)
        self._validator = RequestValidator(auth_token)
        self._whatsapp_number = whatsapp_number
        self._webhook_base_url = webhook_base_url.rstrip("/")
        self._splitter = splitter or MessageSplitter(WHATSAPP_MAX_LENGTH)

    @property
    def platform(self) -> Platform:
        return Platform.WHATSAPP

    @property
    def max_message_length(self) -> int:
        return WHATSAPP_MAX_LENGTH

    async def validate_webhook(self, request: Request) -> WebhookValidationResult:
        """Validate Twilio webhook signature (X-Twilio-Signature header)."""
        form_data = await request.form()
        signature = request.headers.get("X-Twilio-Signature", "")
        url = f"{self._webhook_base_url}{request.url.path}"
        params = {k: str(v) for k, v in form_data.items()}

        is_valid = self._validator.validate(url, params, signature)
        if not is_valid:
            logger.warning("Invalid Twilio webhook signature")
            return WebhookValidationResult(
                is_valid=False,
                error_message="Invalid Twilio signature",
            )
        return WebhookValidationResult(is_valid=True)

    async def parse_inbound(self, request: Request) -> InboundMessage:
        """Parse Twilio webhook form data into an InboundMessage."""
        form_data = await request.form()
        return InboundMessage(
            platform=Platform.WHATSAPP,
            platform_user_id=str(form_data.get("From", "")),
            platform_message_id=str(form_data.get("MessageSid", "")),
            content=str(form_data.get("Body", "")),
            timestamp=datetime.now(UTC),
            raw_payload={k: str(v) for k, v in form_data.items()},
        )

    async def send_message(self, message: OutboundMessage) -> SendResult:
        """Send a message via Twilio REST API, splitting if needed."""
        parts = self._splitter.split(message.content)
        last_sid: str | None = None

        for part in parts:
            try:
                twilio_message = await asyncio.to_thread(
                    self._client.messages.create,
                    body=part,
                    from_=self._whatsapp_number,
                    to=message.recipient_id,
                )
                last_sid = twilio_message.sid
            except Exception:
                logger.exception("Failed to send WhatsApp message")
                return SendResult(
                    success=False,
                    error_message="Failed to send message via Twilio",
                )

        return SendResult(
            success=True,
            platform_message_id=last_sid,
            parts_sent=len(parts),
        )
