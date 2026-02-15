"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from code_messaging_bridge.api.dependencies import get_db_manager
from code_messaging_bridge.api.health import router as health_router
from code_messaging_bridge.api.webhooks import router as webhooks_router
from code_messaging_bridge.config import get_settings
from code_messaging_bridge.logging_config import configure_logging

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize and clean up resources."""
    yield
    await get_db_manager().close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(json_format=not settings.debug)

    app = FastAPI(
        title="Code Messaging Bridge",
        description="WhatsApp-to-Claude Code messaging bridge",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(webhooks_router, prefix="/api", tags=["webhooks"])
    return app


app = create_app()
