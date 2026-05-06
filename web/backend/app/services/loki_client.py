# GRACE[M-LOG-REPORT][loki_http][BLOCK_LOKI_HTTP]
"""HTTP клиент к Loki query_range (из slgpu-web по Docker DNS).

CONTRACT:
  PURPOSE: Выполнить LogQL query_range против внутреннего ``LOKI_SERVICE_NAME:LOKI_INTERNAL_PORT``.
  INPUTS: merged stack dict, query string, nano start/end, limit, direction (forward/backward).
  OUTPUTS: JSON ответа Loki или исключение httpx.HTTPError / RuntimeError.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.stack_config import sync_merged_flat

logger = logging.getLogger(__name__)

# Loki HTTP API: только ``forward`` / ``backward`` (нижний регистр); ``BACKWARD`` даёт 400.
_DEFAULT_DIRECTION = "backward"

# Должен быть ≤ limits_config.max_entries_limit_per_query в loki-config (шаблон: 25000).
_LOKI_QUERY_MAX_LINES = 25_000

# Дефолт Loki до bump в шаблоне slgpu; при 400 повторяем запрос с этим limit.
_LOKI_FALLBACK_LIMIT = 5000


def loki_http_base_from_merged(merged: dict[str, str]) -> str:
    host = str(merged.get("LOKI_SERVICE_NAME") or "").strip()
    if not host:
        raise RuntimeError("missing stack param LOKI_SERVICE_NAME")
    try:
        port = int(merged["LOKI_INTERNAL_PORT"])
    except KeyError as exc:
        raise RuntimeError("missing stack param LOKI_INTERNAL_PORT") from exc
    except ValueError as exc:
        raise RuntimeError("invalid LOKI_INTERNAL_PORT") from exc
    return f"http://{host}:{port}"


def loki_base_url_sync() -> str:
    merged = sync_merged_flat()
    return loki_http_base_from_merged(merged)


async def query_range(
    *,
    query: str,
    start_ns: int,
    end_ns: int,
    limit: int,
    merged: dict[str, str] | None = None,
    timeout_sec: float = 120.0,
    direction: str | None = None,
) -> dict[str, Any]:
    """GET /loki/api/v1/query_range — см. Grafana Loki API."""

    base = loki_http_base_from_merged(merged or sync_merged_flat())
    url = f"{base}/loki/api/v1/query_range"
    lim = max(1, min(int(limit), _LOKI_QUERY_MAX_LINES))
    dir_raw = (direction or _DEFAULT_DIRECTION).strip().lower()
    dir_eff = dir_raw if dir_raw in ("forward", "backward") else _DEFAULT_DIRECTION
    params = {
        "query": query,
        "start": str(start_ns),
        "end": str(end_ns),
        "limit": str(lim),
        "direction": dir_eff,
    }
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        response = await client.get(url, params=params)
        if response.status_code == 400 and lim > _LOKI_FALLBACK_LIMIT:
            logger.warning(
                "[log_report][loki][BLOCK_LOKI_HTTP_RETRY] status=400 limit=%s→%s body=%s",
                lim,
                _LOKI_FALLBACK_LIMIT,
                (response.text or "")[:500],
            )
            params_fb = dict(params)
            params_fb["limit"] = str(_LOKI_FALLBACK_LIMIT)
            response = await client.get(url, params=params_fb)
        if response.status_code != 200:
            logger.warning(
                "[log_report][loki][BLOCK_LOKI_HTTP] status=%s body=%s",
                response.status_code,
                (response.text or "")[:800],
            )
        response.raise_for_status()
        return response.json()
