"""Inspect the running vLLM/SGLang engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.run import EngineRun, RunStatus
from app.services.docker_client import get_docker_inspector

logger = logging.getLogger(__name__)


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

    engine: str | None = None
    container_status: str | None = None
    api_port: int | None = None

    project = settings.compose_project_infer
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
        api_port = settings.llm_default_vllm_port if engine == "vllm" else (
            settings.llm_default_sglang_port if engine == "sglang" else None
        )

    served: list[str] = []
    metrics_available = False
    if engine and api_port:
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                response = await client.get(f"http://127.0.0.1:{api_port}/v1/models")
                if response.status_code == 200:
                    payload = response.json()
                    served = [item.get("id") for item in payload.get("data", []) if item.get("id")]
            except httpx.HTTPError:
                pass
            try:
                metrics = await client.get(f"http://127.0.0.1:{api_port}/metrics")
                metrics_available = metrics.status_code == 200
            except httpx.HTTPError:
                metrics_available = False

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
        last_checked_at=datetime.now(timezone.utc),
    )


def tail_container_logs(tail: int = 300) -> RuntimeLogs:
    settings = get_settings()
    inspector = get_docker_inspector()
    project = settings.compose_project_infer
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
    """Attach last web-requested preset/model to a runtime snapshot."""

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
