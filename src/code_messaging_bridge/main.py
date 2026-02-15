"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from code_messaging_bridge.api.dependencies import get_db_manager
from code_messaging_bridge.api.health import router as health_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize and clean up resources."""
    yield
    await get_db_manager().close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Code Messaging Bridge",
        description="WhatsApp-to-Claude Code messaging bridge",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="/api", tags=["health"])
    return app


app = create_app()
