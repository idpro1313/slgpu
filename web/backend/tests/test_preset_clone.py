"""POST /api/v1/presets/{id}/clone"""

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
async def test_clone_preset_creates_new_row(client: httpx.AsyncClient) -> None:
    async with client:
        base = await client.post(
            "/api/v1/presets",
            json={"name": "base-clone", "hf_id": "Qwen/Qwen3-7B", "tp": 2, "parameters": {}},
        )
        assert base.status_code == 201
        bid = base.json()["id"]
        r = await client.post(
            f"/api/v1/presets/{bid}/clone",
            json={"name": "base-clone-copy"},
        )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "base-clone-copy"
    assert body["is_synced"] is False
    assert body["hf_id"] == "Qwen/Qwen3-7B"
    assert body["tp"] == 2


@pytest.mark.asyncio
async def test_clone_rejects_duplicate_name(client: httpx.AsyncClient) -> None:
    async with client:
        a = await client.post(
            "/api/v1/presets",
            json={"name": "dupe-a", "hf_id": "Qwen/Qwen3-7B", "parameters": {}},
        )
        assert a.status_code == 201
        b = await client.post(
            "/api/v1/presets",
            json={"name": "dupe-b", "hf_id": "Qwen/Qwen3-7B", "parameters": {}},
        )
        assert b.status_code == 201
        r = await client.post(
            f"/api/v1/presets/{a.json()['id']}/clone",
            json={"name": "dupe-b"},
        )
    assert r.status_code == 409
