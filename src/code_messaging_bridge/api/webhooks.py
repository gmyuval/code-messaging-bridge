"""Webhook endpoints for messaging platforms."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from code_messaging_bridge.api.dependencies import (
    get_async_session,
    get_whatsapp_provider,
)
from code_messaging_bridge.config import get_settings
from code_messaging_bridge.rate_limiter import RateLimiter
from code_messaging_bridge.services.conversation_service import ConversationService
from code_messaging_bridge.workers.tasks import process_whatsapp_message

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from code_messaging_bridge.services.messaging.meta_whatsapp import MetaWhatsAppProvider

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-phone-number rate limiter (10 messages per 60 seconds)
_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)


@router.get("/webhooks/whatsapp")
async def whatsapp_webhook_verify(
    request: Request,
    provider: MetaWhatsAppProvider = Depends(get_whatsapp_provider),
) -> Response:
    """Handle Meta webhook verification challenge."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    result = provider.verify_challenge(mode, token, challenge)
    if result is not None:
        return PlainTextResponse(content=result)

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    provider: MetaWhatsAppProvider = Depends(get_whatsapp_provider),
    db: AsyncSession = Depends(get_async_session),
) -> Response:
    """Receive inbound WhatsApp messages and enqueue Claude processing."""
    settings = get_settings()

    # 1. Validate webhook signature
    validation = await provider.validate_webhook(request)
    if not validation.is_valid:
        raise HTTPException(status_code=403, detail=validation.error_message)

    # 2. Parse inbound message (None for non-message events like status updates)
    inbound = await provider.parse_inbound(request)
    if inbound is None:
        logger.debug("Ignoring non-message webhook event")
        return Response(content="OK", media_type="text/plain")
    logger.info(
        "Received WhatsApp message from %s: %s",
        inbound.platform_user_id,
        inbound.content[:100],
    )

    # 3. Phone number whitelist check
    if (
        settings.allowed_phone_numbers
        and inbound.platform_user_id not in settings.allowed_phone_numbers
    ):
        logger.warning("Rejected message from non-whitelisted number: %s", inbound.platform_user_id)
        raise HTTPException(status_code=403, detail="Phone number not authorized")

    # 4. Rate limiting
    if not _rate_limiter.is_allowed(inbound.platform_user_id):
        logger.warning("Rate limit exceeded for %s", inbound.platform_user_id)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # 5. Get or create conversation
    conversation_service = ConversationService(db)
    conversation = await conversation_service.get_or_create_conversation(
        platform=inbound.platform,
        platform_user_id=inbound.platform_user_id,
        working_directory=settings.claude_working_directory,
    )

    # 6. Store inbound message
    await conversation_service.store_inbound_message(conversation, inbound)

    # 7. Commit so the Celery worker can see the conversation and message
    await db.commit()

    # 8. Enqueue Claude processing task
    process_whatsapp_message.delay(
        str(conversation.id),
        inbound.content,
        inbound.platform_user_id,
    )

    # 9. Acknowledge receipt
    return Response(content="OK", media_type="text/plain")
