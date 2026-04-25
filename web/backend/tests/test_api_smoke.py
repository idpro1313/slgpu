"""Smoke tests for the FastAPI app.

These tests do not need Docker, NVIDIA, or the slgpu repo to be a real
clone - the conftest fixture points the backend at a tmp directory.
The DB is bootstrapped explicitly here because httpx's ASGI transport
does not fire FastAPI startup hooks by default.
"""

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
async def test_healthz_returns_200(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload
    assert "database_url_masked" in payload


@pytest.mark.asyncio
async def test_monitoring_action_rejects_unknown(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.post(
            "/api/v1/monitoring/action", json={"action": "nuke"}
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_models_list_starts_empty(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.get("/api/v1/models")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_model_validates_hf_id(client: httpx.AsyncClient) -> None:
    async with client:
        bad = await client.post("/api/v1/models", json={"hf_id": "invalid input"})
        assert bad.status_code == 400
        good = await client.post("/api/v1/models", json={"hf_id": "Qwen/Qwen3-7B"})
        assert good.status_code == 201
        body = good.json()
        assert body["hf_id"] == "Qwen/Qwen3-7B"
        assert body["slug"] == "qwen3-7b"
