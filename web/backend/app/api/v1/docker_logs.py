"""Read-only API: list Docker containers and tail logs (UI page «Docker / логи»)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.docker_logs import (
    DockerContainerLogsOut,
    DockerContainerRow,
    DockerContainersListOut,
    DockerDaemonLogOut,
    DockerEngineEventsOut,
)
from app.services import docker_logs as docker_logs_service

router = APIRouter()


@router.get("/containers", response_model=DockerContainersListOut)
async def list_docker_containers(
    scope: str = Query(
        default="slgpu",
        description="'slgpu' — только slgpu-стек; 'all' — все контейнеры на хосте",
    ),
) -> DockerContainersListOut:
    if scope not in ("slgpu", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope must be 'slgpu' or 'all'",
        )
    ok, sc, rows = docker_logs_service.list_containers(
        scope=scope  # type: ignore[arg-type]
    )
    now = datetime.now(timezone.utc)
    items = [
        DockerContainerRow(
            id=c.id,
            short_id=(c.id or "")[:12],
            name=c.name,
            image=c.image,
            status=c.status,
            health=c.health,
            compose_project=c.project,
            compose_service=c.service,
        )
        for c in rows
    ]
    return DockerContainersListOut(
        docker_available=ok,
        scope=sc,
        containers=items,
        last_checked_at=now,
    )


@router.get("/containers/{container_ref}/logs", response_model=DockerContainerLogsOut)
async def get_container_logs(
    container_ref: str,
    tail: int = Query(default=400, ge=1, le=5000),
) -> DockerContainerLogsOut:
    try:
        ref = docker_logs_service.validate_container_ref(container_ref)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    ok, csum, text, bounded = docker_logs_service.tail_container_logs(ref, tail=tail)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="docker socket unavailable",
        )
    if csum is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="container not found",
        )
    now = datetime.now(timezone.utc)
    return DockerContainerLogsOut(
        container_id=csum.id,
        container_name=csum.name,
        tail=bounded,
        logs=text,
        docker_available=True,
        last_checked_at=now,
    )


@router.get("/engine-events", response_model=DockerEngineEventsOut)
async def get_docker_engine_events(
    since_sec: int = Query(
        3600,
        ge=60,
        le=604800,
        description="Сколько секунд назад начать (окно [since, now])",
    ),
    limit: int = Query(
        2000,
        ge=1,
        le=10_000,
        description="Максимум последних событий (если за окно больше — остаются самые свежие)",
    ),
) -> DockerEngineEventsOut:
    lo = max(1, min(limit, 10_000))
    ok, text = await asyncio.to_thread(
        docker_logs_service.collect_engine_events_tail,
        since_sec,
        lo,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="docker socket unavailable",
        )
    now = datetime.now(timezone.utc)
    return DockerEngineEventsOut(
        docker_available=True,
        since_sec=since_sec,
        limit=lo,
        events_text=text,
        last_checked_at=now,
    )


@router.get("/daemon-log", response_model=DockerDaemonLogOut)
async def get_docker_daemon_log(
    lines: int = Query(400, ge=1, le=2000, description="Строк с конца (journalctl -n)"),
) -> DockerDaemonLogOut:
    n = max(1, min(lines, 2000))
    text, hint = await asyncio.to_thread(
        docker_logs_service.tail_daemon_journal,
        n,
    )
    now = datetime.now(timezone.utc)
    return DockerDaemonLogOut(
        lines=n,
        text=text,
        journal_note=hint,
        last_checked_at=now,
    )
