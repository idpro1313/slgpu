"""Tests for /api/v1/gpu/state (nvidia-smi path mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
async def test_gpu_state_returns_payload_when_smi_ok(client: httpx.AsyncClient) -> None:
    fake = {
        "available": True,
        "error": None,
        "gpus": [
            {
                "index": 0,
                "uuid": "GPU-0",
                "name": "Test GPU",
                "memory_used_mib": 1000,
                "memory_total_mib": 80000,
                "utilization_gpu": 5,
                "utilization_memory": 1,
            }
        ],
        "processes": [],
    }
    with patch("app.services.gpu_state._run_nvidia_smi_probes", return_value=fake), patch(
        "app.services.gpu_state._driver_cuda", return_value=("555.0", "12.0")
    ):
        async with client:
            r = await client.get("/api/v1/gpu/state")
    assert r.status_code == 200
    body = r.json()
    assert body["smi_available"] is True
    assert body["error"] is None
    assert body["driver_version"] == "555.0"
    assert body["cuda_version"] == "12.0"
    assert len(body["gpus"]) == 1
    assert body["gpus"][0]["index"] == 0


@pytest.mark.asyncio
async def test_gpu_state_reports_unavailable(client: httpx.AsyncClient) -> None:
    snap = {
        "available": False,
        "error": "docker_unavailable",
        "gpus": [],
        "processes": [],
        "driver_version": None,
        "cuda_version": None,
    }
    with patch(
        "app.services.gpu_state.get_gpu_state_snapshot",
        new=AsyncMock(return_value=snap),
    ):
        async with client:
            r = await client.get("/api/v1/gpu/state")
    assert r.status_code == 200
    body = r.json()
    assert body["smi_available"] is False
    assert body["gpus"] == []
