"""Database session management for async (FastAPI) and sync (Celery) contexts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


class DatabaseSessionManager:
    """Manages both async and sync database sessions.

    Async sessions are used by FastAPI request handlers.
    Sync sessions are used by Celery workers.
    """

    def __init__(self, async_url: str, sync_url: str) -> None:
        self._async_engine = create_async_engine(async_url, pool_pre_ping=True)
        self._async_session_factory = async_sessionmaker(
            self._async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._sync_engine = create_engine(sync_url, pool_pre_ping=True)
        self._sync_session_factory = sessionmaker(
            self._sync_engine,
            class_=Session,
            expire_on_commit=False,
        )

    async def get_async_session(self) -> AsyncIterator[AsyncSession]:
        """Yield an async database session with automatic commit/rollback."""
        async with self._async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    def get_sync_session(self) -> Iterator[Session]:
        """Yield a sync database session with automatic commit/rollback."""
        with self._sync_session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    async def close(self) -> None:
        """Dispose of all database engines."""
        await self._async_engine.dispose()
        self._sync_engine.dispose()
