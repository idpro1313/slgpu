"""Unit и API-тесты полной выгрузки логов Loki (M-LOG-EXPORT)."""

from __future__ import annotations

import asyncio
import gzip
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport

from app.db.session import get_engine, init_db
from app.main import app
from app.services import log_export as log_export_service
from app.services.app_log_sink import start_writer, stop_writer


def test_build_export_logql_injects_labels() -> None:
    q = log_export_service.build_export_logql(
        scope="slgpu",
        logql_custom=None,
        container=None,
        compose_service=None,
        compose_project=None,
        slgpu_slot="s1",
        slgpu_engine="vllm",
        slgpu_preset="p1",
        slgpu_run_id="run-abc",
    )
    assert 'slgpu_slot="s1"' in q
    assert 'slgpu_engine="vllm"' in q
    assert 'slgpu_preset="p1"' in q
    assert 'slgpu_run_id="run-abc"' in q
    assert q.startswith("{")


def test_build_export_logql_escapes_quotes() -> None:
    q = log_export_service.build_export_logql(
        scope="all",
        logql_custom=None,
        container='foo"bar',
        compose_service=None,
        compose_project=None,
        slgpu_slot=None,
        slgpu_engine=None,
        slgpu_preset=None,
        slgpu_run_id=None,
    )
    assert 'container="foo\\"bar"' in q


def test_build_export_logql_custom_rejects_multiline() -> None:
    with pytest.raises(ValueError, match="переводов"):
        log_export_service.build_export_logql(
            scope="custom",
            logql_custom='{job="docker-logs"}\n |= ``',
            container=None,
            compose_service=None,
            compose_project=None,
            slgpu_slot=None,
            slgpu_engine=None,
            slgpu_preset=None,
            slgpu_run_id=None,
        )


def _loki_payload_n_lines(n: int, base_ns: int = 1_000) -> dict:
    return {
        "data": {
            "resultType": "streams",
            "result": [
                {
                    "stream": {"job": "docker-logs", "container": "c1"},
                    "values": [[str(base_ns + i), f"L{i}"] for i in range(n)],
                }
            ],
        }
    }


@pytest.mark.asyncio
async def test_export_partition_recurses_when_page_saturated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    async def fake_loki(**kwargs):
        calls.append((int(kwargs["start_ns"]), int(kwargs["end_ns"])))
        if len(calls) == 1:
            # Насыщенная страница — пайплайн делит окно по времени, сами строки
            # не пишутся (данные догружаются подзапросами).
            return _loki_payload_n_lines(log_export_service._PAGE_LIMIT)
        if len(calls) == 2:
            return _loki_payload_n_lines(10, base_ns=kwargs["start_ns"])
        return _loki_payload_n_lines(15, base_ns=kwargs["start_ns"])

    monkeypatch.setattr(log_export_service, "loki_query_range", fake_loki)
    monkeypatch.setattr(log_export_service, "_job_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(log_export_service, "_flush_progress", AsyncMock())

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".gz", delete=False) as tf:
        out_path = tf.name
    try:
        with gzip.open(out_path, "wt", encoding="utf-8") as gz:
            state = log_export_service._ExportState()
            await log_export_service._export_partition(
                {},
                '{job="docker-logs"}',
                0,
                10_000_000_000,
                99,
                gz,
                state,
                redact=False,
            )
        assert state.lines_written == 25
        assert len(calls) == 3
    finally:
        import os

        try:
            os.unlink(out_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_create_log_export_pipeline_and_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_db()
    await start_writer(get_engine())
    stub = _loki_payload_n_lines(3, base_ns=1700000000000000001)

    monkeypatch.setattr(log_export_service, "loki_query_range", AsyncMock(return_value=stub))

    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            inst = await client.post(
                "/api/v1/app-config/install", json={"force": True}
            )
            assert inst.status_code == 200

            resp = await client.post(
                "/api/v1/log-exports",
                json={
                    "time_from": "2024-06-01T10:00:00+00:00",
                    "time_to": "2024-06-01T10:30:00+00:00",
                    "scope": "slgpu",
                    "redact_secrets": True,
                },
            )
            assert resp.status_code == 202, resp.text
            eid = resp.json()["export_id"]

            loop = asyncio.get_running_loop()
            deadline = loop.time() + 12.0
            last_status = None
            while loop.time() < deadline:
                g = await client.get(f"/api/v1/log-exports/{eid}")
                js = g.json()
                last_status = js.get("status")
                if last_status == "succeeded":
                    assert js.get("line_count") == 3
                    assert js.get("artifact_relpath")
                    dg = await client.get(f"/api/v1/log-exports/{eid}/download")
                    assert dg.status_code == 200, dg.text
                    assert dg.headers.get("content-disposition")
                    raw = gzip.decompress(dg.content).decode("utf-8")
                    lines = [json.loads(x) for x in raw.strip().split("\n")]
                    assert len(lines) == 3
                    assert lines[0]["labels"]["container"] == "c1"
                    return
                if last_status == "failed":
                    pytest.fail(js.get("error_message") or "export failed")
                await asyncio.sleep(0.06)
            pytest.fail(f"timeout last={last_status}")
    finally:
        await stop_writer()
