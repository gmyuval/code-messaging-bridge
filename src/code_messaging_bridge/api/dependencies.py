"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from code_messaging_bridge.config import get_settings
from code_messaging_bridge.db.session import DatabaseSessionManager
from code_messaging_bridge.services.conversation_service import ConversationService
from code_messaging_bridge.services.messaging.factory import ProviderFactory
from code_messaging_bridge.services.messaging.meta_whatsapp import MetaWhatsAppProvider
from code_messaging_bridge.services.messaging.schemas import Platform

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

_db_manager: DatabaseSessionManager | None = None


def get_db_manager() -> DatabaseSessionManager:
    """Get the global DatabaseSessionManager instance."""
    global _db_manager  # noqa: PLW0603
    if _db_manager is None:
        settings = get_settings()
        _db_manager = DatabaseSessionManager(
            async_url=settings.database_url,
            sync_url=settings.database_url_sync,
        )
    return _db_manager


def set_db_manager(manager: DatabaseSessionManager) -> None:
    """Set the global DatabaseSessionManager instance (for testing)."""
    global _db_manager  # noqa: PLW0603
    _db_manager = manager


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an async database session."""
    manager = get_db_manager()
    async for session in manager.get_async_session():
        yield session


def get_whatsapp_provider() -> MetaWhatsAppProvider:
    """FastAPI dependency that creates a Meta WhatsApp provider."""
    settings = get_settings()
    provider = ProviderFactory.create(Platform.WHATSAPP, settings)
    assert isinstance(provider, MetaWhatsAppProvider)  # noqa: S101
    return provider


async def get_conversation_service(
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ConversationService:
    """FastAPI dependency that creates a ConversationService."""
    return ConversationService(session)
