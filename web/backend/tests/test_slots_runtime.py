"""Runtime slots API: list, validation, snapshot shape."""

from __future__ import annotations

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
async def test_runtime_slots_list_empty_initially(client: httpx.AsyncClient) -> None:
    async with client:
        r = await client.get("/api/v1/runtime/slots")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_slot_rejects_missing_preset(client: httpx.AsyncClient) -> None:
    async with client:
        r = await client.post(
            "/api/v1/runtime/slots",
            json={"engine": "vllm", "preset": "no-such-preset", "tp": 1},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_slot_accepts_queued_job(client: httpx.AsyncClient) -> None:
    async with client:
        pr = await client.post(
            "/api/v1/presets",
            json={"name": "slotp", "hf_id": "Qwen/Qwen3-7B", "tp": 1, "parameters": {}},
        )
        assert pr.status_code == 201
        r = await client.post(
            "/api/v1/runtime/slots",
            json={"engine": "vllm", "preset": "slotp", "tp": 1, "gpu_indices": [0]},
        )
    assert r.status_code == 202
    assert r.json()["kind"] in ("native.slot.up",)


@pytest.mark.asyncio
async def test_snapshot_has_slots_key(client: httpx.AsyncClient) -> None:
    async with client:
        snap = await client.get("/api/v1/runtime/snapshot")
    assert snap.status_code == 200
    j = snap.json()
    assert "slots" in j
    assert isinstance(j["slots"], list)
