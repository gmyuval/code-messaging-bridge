"""Message processing orchestrator."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from code_messaging_bridge.models import Conversation, Message, MessageDirection, MessageStatus
from code_messaging_bridge.services.claude.response_formatter import ResponseFormatter
from code_messaging_bridge.services.claude.runner import ClaudeCodeRunner
from code_messaging_bridge.services.claude.schemas import ClaudeInvocation
from code_messaging_bridge.services.messaging.message_splitter import MessageSplitter

if TYPE_CHECKING:
    import uuid as uuid_mod

    from sqlalchemy.orm import Session

    from code_messaging_bridge.config import Settings

logger = logging.getLogger(__name__)


class MessageProcessor:
    """Orchestrates the full message processing pipeline.

    Load conversation → invoke Claude CLI → format response →
    send via Twilio → store outbound message.

    Designed for synchronous execution inside Celery workers.
    """

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._runner = ClaudeCodeRunner(settings)
        self._formatter = ResponseFormatter()
        self._splitter = MessageSplitter()

    def process_message(
        self,
        conversation_id: uuid_mod.UUID,
        content: str,
        platform_user_id: str,
    ) -> None:
        """Process a single inbound message through the Claude pipeline."""
        # 1. Load conversation
        conversation = self._session.get(Conversation, conversation_id)
        if conversation is None:
            logger.error("Conversation %s not found", conversation_id)
            return

        # 2. Build Claude invocation
        invocation = ClaudeInvocation(
            prompt=content,
            session_id=conversation.claude_session_id,
            working_directory=conversation.working_directory,
            max_turns=self._settings.claude_max_turns,
        )

        # 3. Invoke Claude
        result = self._runner.invoke(invocation)
        logger.info(
            "Claude result: success=%s, cost=$%s, turns=%s",
            result.success,
            result.cost_usd,
            result.num_turns,
        )

        # 4. Update Claude session ID for conversation continuity
        if result.session_id:
            conversation.claude_session_id = result.session_id
            self._session.flush()

        # 5. Format response
        if result.success:
            response_text = self._formatter.format(result.output)
        else:
            response_text = f"Sorry, I encountered an error: {result.error_message}"

        # 6. Send via Twilio
        self._send_whatsapp_response(platform_user_id, response_text)

        # 7. Store outbound message
        outbound = Message(
            conversation_id=conversation_id,
            direction=MessageDirection.OUTBOUND,
            content=response_text,
            status=MessageStatus.SENT,
        )
        self._session.add(outbound)
        self._session.flush()

    def _send_whatsapp_response(self, recipient_id: str, text: str) -> None:
        """Send a response to the user via Twilio WhatsApp."""
        from twilio.rest import Client

        client = Client(
            self._settings.twilio_account_sid,
            self._settings.twilio_auth_token,
        )
        parts = self._splitter.split(text)
        from_number = f"whatsapp:{self._settings.twilio_whatsapp_number}"
        for part in parts:
            client.messages.create(body=part, from_=from_number, to=recipient_id)
