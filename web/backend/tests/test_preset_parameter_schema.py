"""GET /api/v1/presets/parameter-schema"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from app.db.session import init_db
from app.main import app
from app.services.presets import PRESET_RUNTIME_KEYS, preset_runtime_schema_rows


@pytest.fixture
async def client() -> httpx.AsyncClient:
    await init_db()
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_parameter_schema_api_matches_runtime_keys(client: httpx.AsyncClient) -> None:
    async with client:
        r = await client.get("/api/v1/presets/parameter-schema")
    assert r.status_code == 200
    body = r.json()
    keys_api = {row["key"] for row in body["rows"]}
    assert keys_api == set(PRESET_RUNTIME_KEYS)
    assert len(body["rows"]) == len(PRESET_RUNTIME_KEYS)


def test_preset_runtime_schema_rows_covers_all_keys() -> None:
    keys_rows = {row["key"] for row in preset_runtime_schema_rows()}
    assert keys_rows == set(PRESET_RUNTIME_KEYS)
