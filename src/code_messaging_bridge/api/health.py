"""Health check endpoint."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from code_messaging_bridge.api.dependencies import get_async_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """Check application health including database connectivity."""
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning("Database health check failed: %s", e)
        db_status = "unavailable"

    status = "healthy" if db_status == "connected" else "unhealthy"
    return {"status": status, "database": db_status}
