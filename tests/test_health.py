"""Tests for health check endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.health._check_redis", return_value="connected")
@patch("code_messaging_bridge.api.health._check_celery", return_value="available")
async def test_health_check_returns_healthy(
    _mock_celery: object,
    _mock_redis: object,
    client: AsyncClient,
) -> None:
    """Health endpoint should return healthy status when all subsystems are up."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["redis"] == "connected"
    assert data["celery_worker"] == "available"


@pytest.mark.asyncio
async def test_health_check_response_structure(client: AsyncClient) -> None:
    """Health endpoint should return expected JSON structure."""
    response = await client.get("/api/health")
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "redis" in data
    assert "celery_worker" in data


@pytest.mark.asyncio
@patch("code_messaging_bridge.api.health._check_redis", return_value="error: connection refused")
@patch("code_messaging_bridge.api.health._check_celery", return_value="no workers")
async def test_health_check_degraded(
    _mock_celery: object,
    _mock_redis: object,
    client: AsyncClient,
) -> None:
    """Health endpoint should return degraded when subsystems are down."""
    response = await client.get("/api/health")
    data = response.json()
    assert data["status"] == "degraded"
