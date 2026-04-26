"""Tests for /api/v1/gpu/availability."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport

from app.db.session import init_db, session_scope
from app.main import app
from app.models.slot import EngineSlot, RunStatus


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


@pytest.mark.asyncio
async def test_gpu_availability_treats_requested_slot_as_busy(client: httpx.AsyncClient) -> None:
    """4.0.0: бронь REQUESTED (ещё не RUNNING) занимает индексы в available/busy."""
    with patch("app.services.gpu_availability._all_host_gpu_indices", return_value={0, 1, 2, 3}):
        async with session_scope() as session:
            session.add(
                EngineSlot(
                    slot_key="t_req",
                    engine="vllm",
                    preset_name="p",
                    hf_id="Qwen/Qwen3-1B",
                    tp=1,
                    gpu_indices="2",
                    host_api_port=18002,
                    internal_api_port=8111,
                    desired_status=RunStatus.RUNNING,
                    observed_status=RunStatus.REQUESTED,
                )
            )
        async with client:
            r = await client.get("/api/v1/gpu/availability?tp=1")
    assert r.status_code == 200
    data = r.json()
    assert 2 not in data["available"]
    assert any(b.get("index") == 2 and b.get("slot_key") == "t_req" for b in data["busy"])
