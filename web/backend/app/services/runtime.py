"""Inspect the running vLLM/SGLang engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import session_scope
from app.models.run import EngineRun, RunStatus
from app.models.slot import EngineSlot
from app.services.docker_client import get_docker_inspector
from app.services.slot_runtime import slot_container_name
from app.services.stack_config import ports_for_probes_sync

logger = logging.getLogger(__name__)


def _llm_probe_bases(settings: Settings, engine: str, api_port: int) -> list[str]:
    """Candidates for OpenAI /v1/models and /metrics; order matters (fast path first)."""

    p = ports_for_probes_sync()
    internal_vllm = int(p["llm_default_vllm_port"])
    internal_sglang = int(p["llm_default_sglang_port"])
    port = int(api_port)
    candidates: list[str] = [f"http://{settings.llm_http_host}:{port}"]
    if engine == "vllm":
        candidates.append(f"http://vllm:{internal_vllm}")
    elif engine == "sglang":
        candidates.append(f"http://sglang:{internal_sglang}")
    # Fallback, если LLM на хосте, а llm_http_host ещё 127.0.0.1 (доп. дубли отфильтруем)
    hdi = f"http://host.docker.internal:{port}"
    if settings.llm_http_host not in ("host.docker.internal",):
        candidates.append(hdi)
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


async def _fetch_served_and_metrics(
    client: httpx.AsyncClient, bases: list[str]
) -> tuple[list[str], bool, str | None]:
    """Return (served model ids, metrics 200, base URL that answered /v1/models)."""

    served: list[str] = []
    models_base: str | None = None
    for base in bases:
        try:
            response = await client.get(f"{base}/v1/models")
            if response.status_code == 200:
                payload = response.json()
                served = [item.get("id") for item in payload.get("data", []) if item.get("id")]
                models_base = base
                break
        except httpx.HTTPError:
            continue

    metrics_bases: list[str] = []
    if models_base is not None:
        metrics_bases.append(models_base)
    metrics_bases.extend(b for b in bases if b != models_base)
    metrics_ok = False
    for base in metrics_bases:
        if base is None:
            continue
        try:
            metrics = await client.get(f"{base}/metrics")
            if metrics.status_code == 200:
                metrics_ok = True
                break
        except httpx.HTTPError:
            continue
    return served, metrics_ok, models_base


@dataclass
class RuntimeSlotProbe:
    slot_key: str
    engine: str
    preset_name: str | None
    hf_id: str | None
    api_port: int | None
    tp: int | None
    gpu_indices: str | None
    container_status: str | None
    container_name: str | None
    served_models: list[str]
    metrics_available: bool


@dataclass
class RuntimeSnapshot:
    engine: str | None
    api_port: int | None
    container_status: str | None
    preset_name: str | None
    hf_id: str | None
    tp: int | None
    served_models: list[str]
    metrics_available: bool
    last_checked_at: datetime
    slots: list[RuntimeSlotProbe] = field(default_factory=list)


@dataclass
class RuntimeLogs:
    engine: str | None
    container_name: str | None
    container_status: str | None
    tail: int
    logs: str
    last_checked_at: datetime


async def snapshot() -> RuntimeSnapshot:
    settings = get_settings()
    inspector = get_docker_inspector()
    ports = ports_for_probes_sync()
    now = datetime.now(timezone.utc)

    active = (RunStatus.RUNNING, RunStatus.DEGRADED, RunStatus.STARTING)
    slot_rows: list[EngineSlot] = []
    async with session_scope() as session:
        res = await session.execute(
            select(EngineSlot)
            .where(EngineSlot.observed_status.in_(active))
            .order_by(EngineSlot.slot_key)
        )
        slot_rows = list(res.scalars().all())

    if slot_rows:
        slot_probes: list[RuntimeSlotProbe] = []
        for row in slot_rows:
            eng = row.engine
            ap = row.host_api_port
            if ap is None:
                ap = int(ports["llm_default_vllm_port"]) if eng == "vllm" else int(ports["llm_default_sglang_port"])
            served: list[str] = []
            metrics_available = False
            bases = _llm_probe_bases(settings, eng, int(ap))
            async with httpx.AsyncClient(timeout=2.0) as client:
                served, metrics_available, _ = await _fetch_served_and_metrics(client, bases)
            cname = row.container_name or slot_container_name(eng, row.slot_key)
            cst: str | None = None
            if inspector.is_available:
                csum = inspector.get_by_name(cname) if cname else None
                cst = csum.status if csum else None
            slot_probes.append(
                RuntimeSlotProbe(
                    slot_key=row.slot_key,
                    engine=eng,
                    preset_name=row.preset_name,
                    hf_id=row.hf_id,
                    api_port=ap,
                    tp=row.tp,
                    gpu_indices=row.gpu_indices,
                    container_status=cst,
                    container_name=cname,
                    served_models=served,
                    metrics_available=metrics_available,
                )
            )
        def _sort_key(s: RuntimeSlotProbe) -> tuple[int, str]:
            return (0 if s.slot_key == "default" else 1, s.slot_key)

        slot_probes.sort(key=_sort_key)
        top = next((p for p in slot_probes if p.slot_key == "default"), slot_probes[0])
        return RuntimeSnapshot(
            engine=top.engine,
            api_port=top.api_port,
            container_status=top.container_status,
            preset_name=top.preset_name,
            hf_id=top.hf_id,
            tp=top.tp,
            served_models=top.served_models,
            metrics_available=top.metrics_available,
            last_checked_at=now,
            slots=slot_probes,
        )

    engine: str | None = None
    container_status: str | None = None
    api_port: int | None = None

    project = str(ports["compose_project_infer"])
    for candidate in ("vllm", "sglang"):
        container = inspector.get_by_service(project, candidate)
        if container is None:
            continue
        if container.status == "running":
            engine = candidate
            container_status = container.status
            api_port = _extract_host_port(container.ports)
            break
        engine = engine or candidate
        container_status = container_status or container.status

    if api_port is None:
        api_port = int(ports["llm_default_vllm_port"]) if engine == "vllm" else (
            int(ports["llm_default_sglang_port"]) if engine == "sglang" else None
        )

    served: list[str] = []
    metrics_available = False
    if engine and api_port:
        bases = _llm_probe_bases(settings, engine, api_port)
        async with httpx.AsyncClient(timeout=2.0) as client:
            served, metrics_available, _ = await _fetch_served_and_metrics(client, bases)
        if not served and not metrics_available:
            logger.info(
                "[runtime][snapshot][BLOCK_LLM_HTTP] all_probe_bases_failed bases=%r",
                bases,
            )

    if not inspector.is_available:
        logger.info(
            "[runtime][snapshot][BLOCK_CHECK_DOCKER] result=unavailable "
            "labels=vllm|sglang project=%s hint=socket_or_permissions",
            project,
        )
    elif engine is None:
        logger.info(
            "[runtime][snapshot][BLOCK_RESOLVE] no running container for "
            "com.docker.compose.project=%r service=vllm|sglang",
            project,
        )
    else:
        logger.info(
            "[runtime][snapshot] engine=%s api_port=%s container_status=%s models=%s",
            engine,
            api_port,
            container_status,
            len(served),
        )

    return RuntimeSnapshot(
        engine=engine,
        api_port=api_port,
        container_status=container_status,
        preset_name=None,
        hf_id=None,
        tp=None,
        served_models=served,
        metrics_available=metrics_available,
        last_checked_at=now,
        slots=[],
    )


async def tail_slot_logs(slot_key: str, tail: int = 300) -> RuntimeLogs:
    """Logs for a named inference slot (``engine_slots``)."""
    bounded_tail = max(1, min(tail, 2000))
    async with session_scope() as session:
        res = await session.execute(select(EngineSlot).where(EngineSlot.slot_key == slot_key))
        row = res.scalar_one_or_none()
    inspector = get_docker_inspector()
    if row is None:
        return RuntimeLogs(
            engine=None,
            container_name=None,
            container_status=None,
            tail=bounded_tail,
            logs="",
            last_checked_at=datetime.now(timezone.utc),
        )
    cname = row.container_name or slot_container_name(row.engine, slot_key)
    csum = inspector.get_by_name(cname) if inspector.is_available else None
    logs = inspector.tail_logs(csum.id, tail=bounded_tail) if csum else ""
    return RuntimeLogs(
        engine=row.engine,
        container_name=cname,
        container_status=csum.status if csum else None,
        tail=bounded_tail,
        logs=logs,
        last_checked_at=datetime.now(timezone.utc),
    )


def tail_container_logs(tail: int = 300) -> RuntimeLogs:
    settings = get_settings()
    inspector = get_docker_inspector()
    project = str(ports_for_probes_sync()["compose_project_infer"])
    bounded_tail = max(1, min(tail, 2000))

    selected_engine: str | None = None
    selected = None
    for candidate in ("vllm", "sglang"):
        container = inspector.get_by_service(project, candidate)
        if container is None:
            continue
        if container.status == "running":
            selected_engine = candidate
            selected = container
            break
        if selected is None:
            selected_engine = candidate
            selected = container

    logs = inspector.tail_logs(selected.id, tail=bounded_tail) if selected is not None else ""
    logger.info(
        "[runtime][tail_container_logs] engine=%s container=%s status=%s tail=%s bytes=%s",
        selected_engine,
        selected.name if selected else None,
        selected.status if selected else None,
        bounded_tail,
        len(logs),
    )
    return RuntimeLogs(
        engine=selected_engine,
        container_name=selected.name if selected else None,
        container_status=selected.status if selected else None,
        tail=bounded_tail,
        logs=logs,
        last_checked_at=datetime.now(timezone.utc),
    )


async def attach_run_metadata(session: AsyncSession, snap: RuntimeSnapshot) -> RuntimeSnapshot:
    """Attach last web-requested preset/model; prefer **engine_slots** when present."""
    if snap.slots:
        return snap
    query = select(EngineRun).where(EngineRun.observed_status != RunStatus.STOPPED)
    if snap.engine:
        query = query.where(EngineRun.engine == snap.engine)
    query = query.order_by(EngineRun.updated_at.desc(), EngineRun.id.desc()).limit(1)
    result = await session.execute(query)
    run = result.scalar_one_or_none()
    if run is None:
        return snap

    snap.preset_name = run.preset_name
    snap.tp = run.tp
    raw_hf_id = (run.extra or {}).get("hf_id")
    snap.hf_id = str(raw_hf_id) if raw_hf_id else None
    return snap


def _extract_host_port(ports: list[dict]) -> int | None:
    for port in ports:
        host_port = port.get("host_port")
        if host_port:
            return int(host_port)
    return None
