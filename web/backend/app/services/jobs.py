"""Фоновый runner заданий стека (только ``native.*`` → docker compose / docker-py).

`CliCommand` из `app.services.slgpu_cli` — дескриптор вида; web ставит `native.monitoring.*` и др.
Задача пишет `Job`, in-process lock на (scope, resource), asyncio task, лог
(один процесс Uvicorn; не PostgreSQL advisory lock).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from typing import Any

from app.db.session import session_scope
from app.models.audit import AuditEvent
from app.models.job import Job, JobStatus
from app.services.native_jobs import handle_native_job
from app.services.slgpu_cli import CliCommand

logger = logging.getLogger(__name__)


def _lock_key(scope: str, resource: str | None) -> tuple[str, str]:
    return (scope, resource or "*")


# Один in-flight job на (scope, resource); discard() идемпотентен (force-stop + finally).
_held: set[tuple[str, str]] = set()
_lock_guard = asyncio.Lock()
_task_by_lock: dict[tuple[str, str], asyncio.Task[None]] = {}


async def _acquire_lock(scope: str, resource: str | None) -> bool:
    key = _lock_key(scope, resource)
    async with _lock_guard:
        if key in _held:
            return False
        _held.add(key)
        return True


async def _release_lock(scope: str, resource: str | None) -> None:
    key = _lock_key(scope, resource)
    async with _lock_guard:
        _held.discard(key)


class JobConflictError(RuntimeError):
    """Raised when a mutating job collides with an in-flight one."""


async def submit(
    command: CliCommand,
    *,
    actor: str | None = None,
    extra_args: dict[str, Any] | None = None,
) -> Job:
    """Persist a job row and start its execution in the background."""

    correlation_id = str(uuid.uuid4())
    locked = await _acquire_lock(command.scope, command.resource)
    if not locked:
        raise JobConflictError(
            f"another job is running for scope={command.scope} resource={command.resource}"
        )

    async with session_scope() as session:
        job = Job(
            correlation_id=correlation_id,
            kind=command.kind,
            scope=command.scope,
            resource=command.resource,
            status=JobStatus.QUEUED,
            command=list(command.argv),
            args=extra_args or {},
            actor=actor,
            message=command.summary,
        )
        session.add(job)
        session.add(
            AuditEvent(
                actor=actor,
                action=command.kind,
                target=command.resource,
                correlation_id=correlation_id,
                payload={"argv": list(command.argv), "args": extra_args or {}},
                note=command.summary,
            )
        )
        await session.flush()
        job_id = job.id

    key = _lock_key(command.scope, command.resource)
    task = asyncio.create_task(_run_job(job_id, command))
    async with _lock_guard:
        _task_by_lock[key] = task

    async with session_scope() as session:
        return await session.get(Job, job_id)  # type: ignore[return-value]


async def _run_job(job_id: int, command: CliCommand) -> None:
    key = _lock_key(command.scope, command.resource)
    try:
        await _run_job_body(job_id, command)
    except asyncio.CancelledError:
        logger.info(
            "[jobs][_run_job][BLOCK_CANCELLED] job_id=%s kind=%s", job_id, command.kind
        )
        await _mark_job_cancelled(job_id)
        raise
    finally:
        async with _lock_guard:
            _task_by_lock.pop(key, None)
        await _release_lock(command.scope, command.resource)


async def _mark_job_cancelled(job_id: int) -> None:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
            return
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(timezone.utc)
        job.exit_code = -1
        if not job.message or "[cancelled" not in (job.message or ""):
            job.message = f"{job.message or ''} [cancelled: asyncio task]".strip()


async def _run_job_body(job_id: int, command: CliCommand) -> None:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        if job.status == JobStatus.CANCELLED:
            return
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job_args: dict = dict(job.args or {})

    if command.kind.startswith("native."):
        await handle_native_job(job_id, command, job_args)
        return

    async with session_scope() as session:
        job2 = await session.get(Job, job_id)
        if job2 is None or job2.status == JobStatus.CANCELLED:
            return
        job2.exit_code = 1
        job2.finished_at = datetime.now(timezone.utc)
        job2.status = JobStatus.FAILED
        job2.message = "only native.* jobs are supported (slgpu-web 5.x)"


async def list_recent(limit: int = 50) -> list[Job]:
    async with session_scope() as session:
        result = await session.execute(
            select(Job).order_by(Job.id.desc()).limit(limit)
        )
        return list(result.scalars().all())


def is_within_root(target: Path, root: Path) -> bool:
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


async def mark_resource_jobs_cancelled(
    resource: str,
    *,
    note: str = "[cancelled: force stop]",
) -> list[int]:
    """Set queued/running jobs for this resource to cancelled (UI force-stop)."""

    ids: list[int] = []
    now = datetime.now(timezone.utc)
    async with session_scope() as session:
        r = await session.execute(
            select(Job).where(
                Job.resource == resource,
                Job.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)),
            )
        )
        for j in r.scalars():
            j.status = JobStatus.CANCELLED
            j.finished_at = now
            j.exit_code = -1
            j.message = f"{(j.message or '').strip()} {note}".strip()[:2000]
            ids.append(int(j.id))
    return ids


async def force_engine_slot_halt(slot_key: str) -> list[int]:
    """Mark jobs cancelled, cancel asyncio task, clear lock, docker stop (best-effort)."""

    from app.services.slot_runtime import stop_containers_for_slot_key_sync

    resource = f"slot:{slot_key}"
    key = _lock_key("engine", resource)

    cancelled: list[int] = await mark_resource_jobs_cancelled(resource)

    async with _lock_guard:
        t = _task_by_lock.get(key)
    if t is not None and not t.done():
        t.cancel()
    # Снимаем lock сразу (discard идемпотентен с finally задачи).
    await _release_lock("engine", resource)

    log: list[str] = []
    await asyncio.to_thread(stop_containers_for_slot_key_sync, slot_key, log, None)

    if t is not None and not t.done():
        try:
            await asyncio.wait_for(t, timeout=1.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
    if cancelled:
        logger.info(
            "[jobs][force_engine_slot_halt][BLOCK_OK] slot_key=%s cancelled_ids=%s",
            slot_key,
            cancelled,
        )
    return cancelled


async def force_model_pull_halt(hf_id: str) -> list[int]:
    """Mark model pull jobs cancelled and clear the in-process model lock."""

    key = _lock_key("model", hf_id)
    cancelled: list[int] = await mark_resource_jobs_cancelled(
        hf_id, note="[cancelled: model pull force stop]"
    )

    async with _lock_guard:
        t = _task_by_lock.get(key)
    if t is not None and not t.done():
        t.cancel()
    # Снимаем lock сразу: зависший HF pull не должен блокировать повторную докачку из UI.
    await _release_lock("model", hf_id)

    if t is not None and not t.done():
        try:
            await asyncio.wait_for(t, timeout=1.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
    if cancelled:
        logger.info(
            "[jobs][force_model_pull_halt][BLOCK_OK] hf_id=%s cancelled_ids=%s",
            hf_id,
            cancelled,
        )
    return cancelled
