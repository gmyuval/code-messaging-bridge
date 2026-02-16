"""Shared pytest fixtures."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure tests run in debug mode (skips Meta API credential validation)
os.environ.setdefault("CMB_DEBUG", "true")

from code_messaging_bridge.api.dependencies import get_async_session  # noqa: E402
from code_messaging_bridge.main import create_app  # noqa: E402
from code_messaging_bridge.models import Base  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
def app() -> Any:
    """Create a FastAPI app for testing."""
    return create_app()


@pytest.fixture
async def async_session() -> AsyncIterator[AsyncSession]:
    """Create an async SQLite session for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(app: Any, async_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Create an HTTP test client with database session override."""

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield async_session

    app.dependency_overrides[get_async_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
