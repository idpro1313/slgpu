"""Tests for /api/v1/gpu/availability."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport

from app.db.session import init_db
from app.main import app


@pytest.fixture
async def client() -> httpx.AsyncClient:
    await init_db()
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_gpu_availability_suggests_block_when_gpus_free(client: httpx.AsyncClient) -> None:
    with patch("app.services.gpu_availability._all_host_gpu_indices", return_value={0, 1, 2, 3}):
        async with client:
            r = await client.get("/api/v1/gpu/availability?tp=2")
    assert r.status_code == 200
    data = r.json()
    assert data["all_indices"] == [0, 1, 2, 3]
    assert data["available"] == [0, 1, 2, 3]
    assert data["suggested"] == [0, 1]
    assert data["busy"] == []


@pytest.mark.asyncio
async def test_gpu_availability_respects_no_host_gpus(client: httpx.AsyncClient) -> None:
    with patch("app.services.gpu_availability._all_host_gpu_indices", return_value=set()):
        async with client:
            r = await client.get("/api/v1/gpu/availability?tp=1")
    assert r.status_code == 200
    assert r.json()["note"] == "no_gpus_in_host_info"
