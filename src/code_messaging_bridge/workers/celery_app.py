"""Celery application factory."""

from __future__ import annotations

from celery import Celery

from code_messaging_bridge.config import get_settings


def create_celery_app() -> Celery:
    """Create and configure the Celery application."""
    settings = get_settings()
    app = Celery("code_messaging_bridge", broker=settings.redis_url)
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_time_limit=600,
        worker_concurrency=2,
        worker_prefetch_multiplier=1,
        task_track_started=True,
    )
    return app


celery_app = create_celery_app()
