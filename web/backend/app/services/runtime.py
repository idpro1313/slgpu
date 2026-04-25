"""Inspect the running vLLM/SGLang engine."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.services.docker_client import get_docker_inspector

logger = logging.getLogger(__name__)


@dataclass
class RuntimeSnapshot:
    engine: str | None
    api_port: int | None
    container_status: str | None
    served_models: list[str]
    metrics_available: bool
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
        served_models=served,
        metrics_available=metrics_available,
        last_checked_at=datetime.now(timezone.utc),
    )


def _extract_host_port(ports: list[dict]) -> int | None:
    for port in ports:
        host_port = port.get("host_port")
        if host_port:
            return int(host_port)
    return None
