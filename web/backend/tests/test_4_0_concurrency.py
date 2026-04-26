"""4.0.0: slot reservation, GPU busy overlap, slot down by label (mocked)."""

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
async def test_second_slot_rejects_overlapping_gpu(client: httpx.AsyncClient) -> None:
    with patch("app.services.gpu_availability._all_host_gpu_indices", return_value={0, 1, 2, 3}):
        async with client:
            pr = await client.post(
                "/api/v1/presets",
                json={"name": "cux", "hf_id": "Qwen/Qwen3-7B", "tp": 1, "parameters": {}},
            )
            assert pr.status_code == 201
            r1 = await client.post(
                "/api/v1/runtime/slots",
                json={
                    "engine": "vllm",
                    "preset": "cux",
                    "tp": 1,
                    "gpu_indices": [0],
                    "slot_key": "first",
                },
            )
            assert r1.status_code == 202
            r2 = await client.post(
                "/api/v1/runtime/slots",
                json={
                    "engine": "vllm",
                    "preset": "cux",
                    "tp": 1,
                    "gpu_indices": [0],
                    "slot_key": "second",
                },
            )
    assert r2.status_code == 409


def test_stop_containers_for_slot_key_sync_removes_labeled() -> None:
    from app.services import slot_runtime as sr

    class C:
        def __init__(self, name: str) -> None:
            self.name = name
            self.stopped = False
            self.removed = False

        def stop(self, timeout: int = 20) -> None:  # noqa: ARG002
            self.stopped = True

        def remove(self) -> None:
            self.removed = True

    c = C("slgpu-vllm-ghost")
    with patch("docker.from_env") as mock_from:
        dclient = mock_from.return_value
        dclient.ping = lambda: True
        dclient.containers.list = lambda *a, **k: [c]  # noqa: ARG005
        dclient.containers.get = lambda name: c  # noqa: ARG005
        log: list[str] = []
        code = sr.stop_containers_for_slot_key_sync("ghost", log)
    assert code == 0
    assert c.stopped and c.removed
