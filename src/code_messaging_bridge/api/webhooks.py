"""Webhook endpoints for messaging platforms."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from code_messaging_bridge.api.dependencies import (
    get_async_session,
    get_whatsapp_provider,
)
from code_messaging_bridge.config import get_settings
from code_messaging_bridge.services.conversation_service import ConversationService
from code_messaging_bridge.services.messaging.schemas import OutboundMessage

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from code_messaging_bridge.services.messaging.twilio_whatsapp import TwilioWhatsAppProvider

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhooks/twilio/whatsapp")
async def twilio_whatsapp_webhook(
    request: Request,
    provider: TwilioWhatsAppProvider = Depends(get_whatsapp_provider),
    db: AsyncSession = Depends(get_async_session),
) -> Response:
    """Receive and process inbound WhatsApp messages from Twilio.

    Currently implements an echo bot. In Phase 3, this will
    enqueue a Celery task to process the message through Claude.
    """
    settings = get_settings()

    # 1. Validate webhook signature
    validation = await provider.validate_webhook(request)
    if not validation.is_valid:
        raise HTTPException(status_code=403, detail=validation.error_message)

    # 2. Parse inbound message
    inbound = await provider.parse_inbound(request)
    logger.info(
        "Received WhatsApp message from %s: %s",
        inbound.platform_user_id,
        inbound.content[:100],
    )

    # 3. Get or create conversation
    conversation_service = ConversationService(db)
    conversation = await conversation_service.get_or_create_conversation(
        platform=inbound.platform,
        platform_user_id=inbound.platform_user_id,
        working_directory=settings.claude_working_directory,
    )

    # 4. Store inbound message
    await conversation_service.store_inbound_message(conversation, inbound)

    # 5. Echo back (Phase 2) — replaced by Claude task enqueue in Phase 3
    echo_content = f"Echo: {inbound.content}"
    result = await provider.send_message(
        OutboundMessage(
            platform=inbound.platform,
            recipient_id=inbound.platform_user_id,
            content=echo_content,
        )
    )

    # 6. Store outbound message
    await conversation_service.store_outbound_message(
        conversation,
        echo_content,
        result.platform_message_id,
    )

    await db.commit()

    # 7. Return empty TwiML (we send via REST API, not TwiML response)
    return Response(content="<Response/>", media_type="application/xml")
