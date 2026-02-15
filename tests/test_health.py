"""Tests for health check endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_returns_healthy(client: AsyncClient) -> None:
    """Health endpoint should return healthy status with database connected."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_health_check_response_structure(client: AsyncClient) -> None:
    """Health endpoint should return expected JSON structure."""
    response = await client.get("/api/health")
    data = response.json()
    assert "status" in data
    assert "database" in data
