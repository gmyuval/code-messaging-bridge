"""Health check endpoint."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends
from sqlalchemy import text

from code_messaging_bridge.api.dependencies import get_async_session
from code_messaging_bridge.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """Check application health including database, Redis, and Celery status."""
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning("Database health check failed: %s", e)
        db_status = "unavailable"

    redis_status = _check_redis()
    celery_status = _check_celery()

    all_ok = all(
        s in {"connected", "available"} for s in [db_status, redis_status, celery_status]
    )
    return {
        "status": "healthy" if all_ok else "degraded",
        "database": db_status,
        "redis": redis_status,
        "celery_worker": celery_status,
    }


def _check_redis() -> str:
    """Check Redis connectivity."""
    try:
        import redis

        settings = get_settings()
        r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        return "connected"
    except Exception as e:
        logger.warning("Redis health check failed: %s", e)
        return f"error: {e}"


def _check_celery() -> str:
    """Check if at least one Celery worker is available."""
    try:
        from code_messaging_bridge.workers.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=2)
        active = inspector.active()
        if active:
            return "available"
        return "no workers"
    except Exception as e:
        logger.warning("Celery health check failed: %s", e)
        return f"error: {e}"
