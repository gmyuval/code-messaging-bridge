"""Celery tasks for message processing."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from celery import Task
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from code_messaging_bridge.config import Settings, get_settings
from code_messaging_bridge.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


class DatabaseTask(Task):  # type: ignore[misc]
    """Custom Celery Task base that initializes DB session factory once per worker."""

    _session_factory: sessionmaker[Session] | None = None
    _settings: Settings | None = None

    @property
    def settings(self) -> Settings:
        """Get cached application settings."""
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Get cached session factory (initialized once per worker process)."""
        if self._session_factory is None:
            engine = create_engine(self.settings.database_url_sync, pool_pre_ping=True)
            self._session_factory = sessionmaker(engine, expire_on_commit=False)
        return self._session_factory


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=DatabaseTask,
    name="process_whatsapp_message",
    max_retries=0,
)
def process_whatsapp_message(
    self: DatabaseTask,
    conversation_id: str,
    content: str,
    platform_user_id: str,
) -> dict[str, Any]:
    """Process a WhatsApp message through Claude Code.

    This task runs on the HOST machine (not Docker) because Claude Code CLI
    needs access to the local filesystem and git.
    """
    logger.info(
        "Processing message for conversation %s from %s",
        conversation_id,
        platform_user_id,
    )

    with self.session_factory() as session:
        try:
            from code_messaging_bridge.services.processor import MessageProcessor

            processor = MessageProcessor(session, self.settings)
            processor.process_message(
                conversation_id=uuid.UUID(conversation_id),
                content=content,
                platform_user_id=platform_user_id,
            )
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Failed to process message for conversation %s", conversation_id)
            _send_error_message(self.settings, platform_user_id)
            raise

    return {"status": "completed", "conversation_id": conversation_id}


def _send_error_message(settings: Settings, recipient_id: str) -> None:
    """Send a user-friendly error message via WhatsApp when processing fails."""
    try:
        import httpx

        url = (
            f"https://graph.facebook.com/v21.0/"
            f"{settings.meta_phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {settings.meta_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_id,
            "type": "text",
            "text": {
                "body": (
                    "Sorry, something went wrong while processing your message. "
                    "Please try again in a moment."
                ),
            },
        }
        httpx.post(url, json=payload, headers=headers, timeout=30)
    except Exception:
        logger.exception("Failed to send error message to %s", recipient_id)
