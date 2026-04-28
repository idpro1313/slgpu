"""POST /api/v1/presets/import-env"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from app.db.session import init_db
from app.main import app


_ENV_MINIMAL = """MODEL_ID=Qwen/Qwen3-7B
TP=2
"""


@pytest.fixture
async def client() -> httpx.AsyncClient:
    await init_db()
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_import_env_creates_preset(client: httpx.AsyncClient) -> None:
    async with client:
        r = await client.post(
            "/api/v1/presets/import-env",
            files={"file": ("upload-me.env", _ENV_MINIMAL.encode("utf-8"), "text/plain")},
            data={"overwrite": "false"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "upload-me"
    assert body["hf_id"] == "Qwen/Qwen3-7B"
    assert body["tp"] == 2


@pytest.mark.asyncio
async def test_import_env_conflict_then_overwrite(client: httpx.AsyncClient) -> None:
    async with client:
        first = await client.post(
            "/api/v1/presets/import-env",
            files={"file": ("dup.env", _ENV_MINIMAL.encode("utf-8"), "text/plain")},
            data={"overwrite": "false"},
        )
        assert first.status_code == 200

        conflict = await client.post(
            "/api/v1/presets/import-env",
            files={"file": ("dup.env", _ENV_MINIMAL.encode("utf-8"), "text/plain")},
            data={"overwrite": "false"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"] == "preset with this name already exists"

        second = await client.post(
            "/api/v1/presets/import-env",
            files={"file": ("dup.env", _ENV_MINIMAL.encode("utf-8"), "text/plain")},
            data={"overwrite": "true"},
        )
    assert second.status_code == 200
    assert second.json()["name"] == "dup"


@pytest.mark.asyncio
async def test_import_env_without_model_id_400(client: httpx.AsyncClient) -> None:
    async with client:
        r = await client.post(
            "/api/v1/presets/import-env",
            files={"file": ("bad.env", b"TP=1\n", "text/plain")},
            data={"overwrite": "false"},
        )
    assert r.status_code == 400
