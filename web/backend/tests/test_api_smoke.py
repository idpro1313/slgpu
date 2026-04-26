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

from app.core.config import get_settings
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
async def test_models_list_discovers_local_model_folders(client: httpx.AsyncClient) -> None:
    settings = get_settings()
    models_root = settings.slgpu_root.parent / "models"
    model_dir = models_root / "Qwen" / "Qwen3-30B-A3B"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model-00001-of-00001.safetensors").write_bytes(b"weights")

    async with client:
        response = await client.get("/api/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["hf_id"] == "Qwen/Qwen3-30B-A3B"
    assert payload[0]["download_status"] == "ready"
    assert payload[0]["local_path"].endswith("models/Qwen/Qwen3-30B-A3B")


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


@pytest.mark.asyncio
async def test_update_preset_allows_hf_id_and_parameters(client: httpx.AsyncClient) -> None:
    async with client:
        created = await client.post(
            "/api/v1/presets",
            json={
                "name": "qwen3",
                "hf_id": "Qwen/Qwen3-7B",
                "tp": 4,
                "parameters": {"MAX_MODEL_LEN": "32768"},
            },
        )
        assert created.status_code == 201
        preset_id = created.json()["id"]

        updated = await client.patch(
            f"/api/v1/presets/{preset_id}",
            json={
                "hf_id": "Qwen/Qwen3-30B-A3B",
                "tp": 8,
                "parameters": {"MAX_MODEL_LEN": "262144", "KV_CACHE_DTYPE": "fp8_e4m3"},
            },
        )

    assert updated.status_code == 200
    body = updated.json()
    assert body["hf_id"] == "Qwen/Qwen3-30B-A3B"
    assert body["tp"] == 8
    assert body["parameters"]["MAX_MODEL_LEN"] == "262144"
    assert body["is_synced"] is False


@pytest.mark.asyncio
async def test_delete_preset_can_remove_exported_file(client: httpx.AsyncClient) -> None:
    async with client:
        created = await client.post(
            "/api/v1/presets",
            json={
                "name": "delete-me",
                "hf_id": "Qwen/Qwen3-7B",
                "parameters": {"MAX_MODEL_LEN": "32768"},
            },
        )
        assert created.status_code == 201
        preset_id = created.json()["id"]
        exported = await client.post(f"/api/v1/presets/{preset_id}/export")
        file_path = exported.json()["file_path"]
        deleted = await client.delete(f"/api/v1/presets/{preset_id}?delete_file=true")
        fetched = await client.get(f"/api/v1/presets/{preset_id}")

    assert exported.status_code == 200
    assert deleted.status_code == 200
    assert deleted.json()["deleted_file"] == file_path
    assert fetched.status_code == 404


@pytest.mark.asyncio
async def test_delete_model_can_remove_local_files(client: httpx.AsyncClient) -> None:
    settings = get_settings()
    model_dir = settings.slgpu_root.parent / "models" / "Qwen" / "Qwen3-Delete"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_bytes(b"weights")

    async with client:
        models = await client.get("/api/v1/models")
        model_id = next(item["id"] for item in models.json() if item["hf_id"] == "Qwen/Qwen3-Delete")
        deleted = await client.delete(f"/api/v1/models/{model_id}?delete_files=true")
        after = await client.get("/api/v1/models")

    assert deleted.status_code == 200
    assert deleted.json()["deleted_files"] is True
    assert not model_dir.exists()
    assert all(item["hf_id"] != "Qwen/Qwen3-Delete" for item in after.json())


@pytest.mark.asyncio
async def test_runtime_snapshot_includes_requested_preset_and_model(
    client: httpx.AsyncClient,
) -> None:
    async with client:
        preset = await client.post(
            "/api/v1/presets",
            json={
                "name": "qwen3",
                "hf_id": "Qwen/Qwen3-30B-A3B",
                "tp": 8,
                "parameters": {},
            },
        )
        assert preset.status_code == 201

        up = await client.post(
            "/api/v1/runtime/up",
            json={"engine": "vllm", "preset": "qwen3", "port": 8111, "tp": None},
        )
        assert up.status_code == 202

        snapshot = await client.get("/api/v1/runtime/snapshot")

    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["preset_name"] == "qwen3"
    assert body["hf_id"] == "Qwen/Qwen3-30B-A3B"
    assert body["tp"] == 8


@pytest.mark.asyncio
async def test_runtime_logs_returns_empty_without_docker(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.get("/api/v1/runtime/logs?tail=50")

    assert response.status_code == 200
    body = response.json()
    assert body["tail"] == 50
    assert body["logs"] == ""
    assert body["container_name"] is None


@pytest.mark.asyncio
async def test_public_access_settings_drive_external_ui_links(client: httpx.AsyncClient) -> None:
    async with client:
        updated = await client.patch(
            "/api/v1/settings/public-access",
            json={"server_host": "llm.example.local"},
        )
        services = await client.get("/api/v1/monitoring/services")
        litellm = await client.get("/api/v1/litellm/info")

    assert updated.status_code == 200
    assert updated.json()["effective_server_host"] == "llm.example.local"
    assert services.status_code == 200
    by_key = {item["key"]: item for item in services.json()}
    assert by_key["grafana"]["url"] == "http://llm.example.local:3000"
    assert by_key["litellm"]["url"] == "http://llm.example.local:4000/ui"
    assert litellm.status_code == 200
    assert litellm.json()["ui_url"] == "http://llm.example.local:4000/ui"


@pytest.mark.asyncio
async def test_activity_includes_ui_after_preset_and_settings(client: httpx.AsyncClient) -> None:
    """Лента /activity: UI-события (audit без correlation) + CLI-записи (jobs)."""
    async with client:
        await client.post(
            "/api/v1/presets",
            json={"name": "act-test", "hf_id": "Qwen/Qwen3-7B", "tp": 1, "parameters": {}},
        )
        await client.patch(
            "/api/v1/settings/public-access",
            json={"server_host": "example.test"},
        )
        act = await client.get("/api/v1/activity?limit=50")

    assert act.status_code == 200
    body = act.json()
    assert isinstance(body, list)
    types = {row["type"] for row in body}
    assert "ui" in types
    actions = {row["action"] for row in body if row["type"] == "ui"}
    assert "preset.create" in actions
    assert "settings.public_access" in actions
