"""Meta WhatsApp Business API messaging provider."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

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
GRAPH_API_URL = "https://graph.facebook.com/v21.0"


class MetaWhatsAppProvider(MessagingProvider):
    """Meta WhatsApp Business API messaging provider.

    Handles X-Hub-Signature-256 webhook validation, JSON payload parsing,
    and sending messages via the Meta Graph API.
    """

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        app_secret: str,
        verify_token: str,
        splitter: MessageSplitter | None = None,
    ) -> None:
        self._phone_number_id = phone_number_id
        self._access_token = access_token
        self._app_secret = app_secret
        self._verify_token = verify_token
        self._splitter = splitter or MessageSplitter(WHATSAPP_MAX_LENGTH)

    @property
    def platform(self) -> Platform:
        return Platform.WHATSAPP

    @property
    def max_message_length(self) -> int:
        return WHATSAPP_MAX_LENGTH

    async def validate_webhook(self, request: Request) -> WebhookValidationResult:
        """Validate Meta webhook signature (X-Hub-Signature-256 header)."""
        signature_header = request.headers.get("X-Hub-Signature-256", "")
        if not signature_header.startswith("sha256="):
            logger.warning("Missing or malformed X-Hub-Signature-256 header")
            return WebhookValidationResult(
                is_valid=False,
                error_message="Missing webhook signature",
            )

        raw_body = await request.body()
        expected = hmac.new(
            self._app_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        provided = signature_header.removeprefix("sha256=")

        if not hmac.compare_digest(expected, provided):
            logger.warning("Invalid X-Hub-Signature-256")
            return WebhookValidationResult(
                is_valid=False,
                error_message="Invalid webhook signature",
            )
        return WebhookValidationResult(is_valid=True)

    async def parse_inbound(self, request: Request) -> InboundMessage | None:
        """Parse Meta webhook JSON payload into an InboundMessage.

        Returns None for non-message payloads (status updates, delivery receipts, etc.).
        """
        payload = await request.json()

        # Navigate safely: entry[0].changes[0].value.messages[0]
        entries = payload.get("entry", [])
        if not entries:
            return None
        change = entries[0].get("changes", [{}])[0]
        value = change.get("value", {})
        messages = value.get("messages")
        if not messages:
            return None
        message = messages[0]

        sender_phone = message["from"]
        message_id = message["id"]
        content = message.get("text", {}).get("body", "")
        timestamp_str = message.get("timestamp", "")

        ts = datetime.now(UTC)
        if timestamp_str:
            ts = datetime.fromtimestamp(int(timestamp_str), tz=UTC)

        return InboundMessage(
            platform=Platform.WHATSAPP,
            platform_user_id=sender_phone,
            platform_message_id=message_id,
            content=content,
            timestamp=ts,
            raw_payload=payload,
        )

    async def send_message(self, message: OutboundMessage) -> SendResult:
        """Send a message via Meta Graph API, splitting if needed."""
        parts = self._splitter.split(message.content)
        last_message_id: str | None = None

        url = f"{GRAPH_API_URL}/{self._phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        for part in parts:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": message.recipient_id,
                "type": "text",
                "text": {"body": part},
            }
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        url, json=payload, headers=headers, timeout=30
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    last_message_id = data.get("messages", [{}])[0].get("id")
            except Exception:
                logger.exception("Failed to send WhatsApp message via Meta API")
                return SendResult(
                    success=False,
                    error_message="Failed to send message via Meta API",
                )

        return SendResult(
            success=True,
            platform_message_id=last_message_id,
            parts_sent=len(parts),
        )

    def verify_challenge(
        self, mode: str | None, token: str | None, challenge: str | None
    ) -> str | None:
        """Verify Meta webhook subscription challenge.

        Returns the challenge string if valid, None otherwise.
        """
        if mode == "subscribe" and token == self._verify_token:
            return challenge
        return None
