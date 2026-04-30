"""Тесты агрегатора отчётов по логам и POST /log-reports (mock Loki/LiteLLM)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport

from app.db.session import get_engine, init_db
from app.main import app
from app.services import log_report as log_report_service
from app.services.app_log_sink import start_writer, stop_writer

LOKI_STUB = {
    "data": {
        "resultType": "streams",
        "result": [
            {
                "stream": {"job": "docker-logs", "container": "slgpu-vllm-qwen"},
                "values": [
                    [
                        "1700000000000000001",
                        "[runner][BLOCK_TP_VISIBLE] tensor ERROR something",
                    ],
                    [
                        "1700000003000000001",
                        "WARNING kv cache",
                    ],
                    [
                        "1700000006000000001",
                        "plain line",
                    ],
                ],
            }
        ],
    }
}


def test_redact_masks_long_sk_token() -> None:
    raw = "authorization bearer sk-12345678901234567890abcdefghij_suffix"
    out = log_report_service.redact_line(raw.lower())
    assert "12345678901234567890" not in out


def test_build_facts_contains_meta_and_counters() -> None:
    tuples = log_report_service.parse_loki_streams(LOKI_STUB)
    assert len(tuples) == 3
    dt0 = datetime(2023, 11, 15, tzinfo=timezone.utc)
    dt1 = dt0 + timedelta(hours=1)
    bundle = log_report_service.build_facts_bundle(
        tuples,
        time_from=dt0,
        time_to=dt1,
        logql='{job="docker-logs"}',
        max_lines=8000,
        loki_truncated_hint=False,
    )
    assert bundle["meta"]["lines_used"] == 3
    assert "slgpu-vllm-qwen" in bundle["by_container_total"]
    assert "BLOCK_TP_VISIBLE" in bundle["block_marker_counts"]
    assert "severity_by_container" in bundle


def test_resolved_logql_custom_requires_brace() -> None:
    q = '{job="docker-logs"} |= "test"'
    assert log_report_service.resolved_logql("custom", q).startswith("{")
    with pytest.raises(ValueError):
        log_report_service.resolved_logql("custom", 'job=oops-no-brace')


def test_validate_period_over_168h_raises():
    a = datetime(2024, 1, 1, tzinfo=timezone.utc)
    b = a + timedelta(hours=169)
    with pytest.raises(ValueError, match="168"):
        log_report_service.validate_period(a, b)


def test_ts_ns_deterministic_from_timedelta():
    dt = datetime(1970, 1, 2, tzinfo=timezone.utc)
    assert log_report_service._ts_ns(dt) == 86_400 * 1_000_000_000
    dt2 = datetime(1970, 1, 1, 0, 0, 0, 1, tzinfo=timezone.utc)
    assert log_report_service._ts_ns(dt2) == 1000


@pytest.mark.asyncio
async def test_create_log_report_pipeline_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    await init_db()
    await start_writer(get_engine())
    monkeypatch.setattr(
        log_report_service,
        "loki_query_range",
        AsyncMock(return_value=LOKI_STUB),
    )
    monkeypatch.setattr(
        log_report_service,
        "call_litellm_chat",
        AsyncMock(return_value="# Отчёт\n\nВсе стабильно."),
    )

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
                "/api/v1/log-reports",
                json={
                    "time_from": "2024-06-01T10:00:00+00:00",
                    "time_to": "2024-06-01T10:30:00+00:00",
                    "scope": "slgpu",
                    "llm_model": "fake-model",
                    "max_lines": 8000,
                },
            )
            assert resp.status_code == 202, resp.text
            rid = resp.json()["report_id"]

            loop = asyncio.get_running_loop()
            deadline = loop.time() + 8.0
            last_err = None
            while loop.time() < deadline:
                g = await client.get(f"/api/v1/log-reports/{rid}")
                js = g.json()
                if js["status"] == "succeeded":
                    assert js["facts"] is not None
                    assert js["llm_markdown"]
                    assert "Отчёт" in js["llm_markdown"]
                    return
                if js["status"] == "failed":
                    pytest.fail(js.get("error_message") or "report failed")
                await asyncio.sleep(0.06)
                last_err = js.get("status")
            pytest.fail(f"timeout last={last_err}")
    finally:
        await stop_writer()
