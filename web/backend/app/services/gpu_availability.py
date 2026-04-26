"""Which GPU indices are free vs reserved by inference slots."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.slot import EngineSlot, RunStatus
from app.services import host_info

logger = logging.getLogger(__name__)

_HOST_CACHE: tuple[float, set[int]] | None = None
_HOST_LOCK = asyncio.Lock()
_HOST_TTL_S = 30.0


def invalidate_host_gpu_cache() -> None:
    global _HOST_CACHE
    _HOST_CACHE = None


def _all_host_gpu_indices() -> set[int]:
    info = host_info.collect_host_info(get_settings().slgpu_root)
    n = info.get("nvidia") or {}
    gpus = n.get("gpus")
    if not isinstance(gpus, list):
        return set()
    out: set[int] = set()
    for g in gpus:
        if isinstance(g, dict) and "index" in g:
            try:
                out.add(int(g["index"]))
            except (TypeError, ValueError):
                continue
    return out


async def _cached_host_indices() -> set[int]:
    global _HOST_CACHE
    now = time.monotonic()
    async with _HOST_LOCK:
        if _HOST_CACHE is not None and now - _HOST_CACHE[0] < _HOST_TTL_S:
            return _HOST_CACHE[1]
        host = await asyncio.to_thread(_all_host_gpu_indices)
        _HOST_CACHE = (time.monotonic(), host)
        logger.info("[gpu_availability][cached_host_indices][BLOCK_REFRESH] n=%s", len(host))
        return host


def _parse_indices_csv(s: str | None) -> set[int]:
    if not s or not str(s).strip():
        return set()
    out: set[int] = set()
    for p in str(s).split(","):
        p = p.strip()
        if not p:
            continue
        out.add(int(p))
    return out


def _suggest_indices(available: set[int], tp: int) -> list[int] | None:
    if tp < 1 or not available:
        return None
    sorted_i = sorted(available)
    if len(sorted_i) < tp:
        return None
    for start in range(0, len(sorted_i) - tp + 1):
        block = sorted_i[start : start + tp]
        ok = True
        for a, b in zip(block, block[1:]):
            if b != a + 1:
                ok = False
                break
        if ok:
            return block
    return sorted_i[:tp]


async def compute_availability(
    *,
    tp: int,
    exclude_slot_key: str | None = None,
) -> dict[str, Any]:
    """Return available / busy (with slot ref) / suggested first ``tp`` indices."""
    host = await _cached_host_indices()
    if not host:
        return {
            "all_indices": [],
            "available": [],
            "busy": [],
            "suggested": None,
            "note": "no_gpus_in_host_info",
        }

    busy: set[int] = set()
    busy_rows: list[dict[str, Any]] = []
    active = (RunStatus.STARTING, RunStatus.REQUESTED, RunStatus.RUNNING, RunStatus.DEGRADED)
    async with session_scope() as session:
        res = await session.execute(select(EngineSlot).where(EngineSlot.observed_status.in_(active)))
        for row in res.scalars().all():
            if exclude_slot_key and row.slot_key == exclude_slot_key:
                continue
            s = _parse_indices_csv(row.gpu_indices)
            for i in s:
                busy.add(i)
                if i in host:
                    busy_rows.append(
                        {
                            "index": i,
                            "slot_key": row.slot_key,
                            "preset_name": row.preset_name,
                            "engine": row.engine,
                        }
                    )
    from app.services import gpu_state

    snap = await gpu_state.get_gpu_state_snapshot()
    uuid_to_index: dict[str, int] = {}
    for g in snap.get("gpus") or []:
        if not isinstance(g, dict):
            continue
        u, idx = g.get("uuid"), g.get("index")
        if u is not None and idx is not None:
            try:
                uuid_to_index[str(u)] = int(idx)
            except (TypeError, ValueError):
                continue
    for proc in snap.get("processes") or []:
        if not isinstance(proc, dict):
            continue
        u = proc.get("gpu_uuid")
        if u is None:
            continue
        try:
            idx = uuid_to_index.get(str(u))
        except (TypeError, KeyError):
            continue
        if idx is None or idx not in host:
            continue
        if idx in busy:
            continue
        busy.add(idx)
        sk = proc.get("slot_key")
        if sk:
            busy_rows.append(
                {
                    "index": idx,
                    "slot_key": sk,
                    "preset_name": None,
                    "engine": f"process:{proc.get('process_name', '')!s}"[:64],
                }
            )
        else:
            busy_rows.append(
                {
                    "index": idx,
                    "slot_key": "external",
                    "preset_name": None,
                    "engine": f"process:{proc.get('process_name', '')!s}"[:64],
                }
            )

    seen: set[tuple[str, int]] = set()
    unique_busy: list[dict[str, Any]] = []
    for b in busy_rows:
        k = (b["slot_key"], b["index"])
        if k in seen:
            continue
        seen.add(k)
        unique_busy.append(b)

    available = sorted(host - busy)
    sugg = _suggest_indices(set(available), tp) if tp >= 1 else None
    return {
        "all_indices": sorted(host),
        "available": available,
        "busy": unique_busy,
        "suggested": sugg,
    }
