"""Background runner for CLI commands.

Each `CliCommand` produced by `app.services.slgpu_cli` is enqueued
through `submit`, which stores a `Job` row, validates an advisory lock
on `(scope, resource)` and spawns an asyncio task that streams stdout
and stderr into the database.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import uuid
from collections import deque
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.audit import AuditEvent
from app.models.job import Job, JobStatus
from app.services.native_jobs import handle_native_job
from app.services.slgpu_cli import CliCommand

logger = logging.getLogger(__name__)


def _exec_argv_for_cli(command: CliCommand, cwd: Path) -> list[str]:
    """Run the repo `slgpu` entrypoint with bash.

    `asyncio.create_subprocess_exec` uses execve(2) on argv[0]. If the bind mount
    dropped the executable bit (common for repos edited on Windows / synced via
    OneDrive), ``./slgpu`` fails with EACCES even though ``bash slgpu`` works.
    All allowlisted CLI commands use ``{cwd}/slgpu`` as argv[0].
    """

    if not command.argv:
        return list(command.argv)
    entry = str(cwd / "slgpu")
    if command.argv[0] == entry:
        return ["/bin/bash", entry, *command.argv[1:]]
    return list(command.argv)


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
    settings = get_settings()
    cwd = settings.slgpu_root
    stdout_tail: deque[str] = deque(maxlen=400)
    stderr_tail: deque[str] = deque(maxlen=400)

    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job_args: dict = dict(job.args or {})

    if command.kind.startswith("native."):
        await handle_native_job(job_id, command, job_args)
        return

    exit_code = -1
    argv = _exec_argv_for_cli(command, cwd)
    slgpu_entry = str(cwd / "slgpu")
    if len(argv) >= 2 and argv[0] == "/bin/bash" and argv[1] == slgpu_entry:
        logger.info(
            "[jobs][_run_job][BLOCK_SLGPU_BASH] cwd=%s argv=%s",
            cwd,
            join_for_display(argv),
        )
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=None,
        )

        async def _drain(stream: asyncio.StreamReader, sink: deque[str]) -> None:
            assert stream is not None
            while True:
                chunk = await stream.readline()
                if not chunk:
                    break
                sink.append(chunk.decode("utf-8", errors="replace").rstrip("\n"))

        await asyncio.gather(
            _drain(process.stdout, stdout_tail),  # type: ignore[arg-type]
            _drain(process.stderr, stderr_tail),  # type: ignore[arg-type]
        )
        exit_code = await process.wait()
    except FileNotFoundError as exc:
        stderr_tail.append(f"[runner] {exc}")
        exit_code = 127
    except Exception as exc:  # noqa: BLE001
        logger.exception("[jobs][_run_job][BLOCK_UNEXPECTED]")
        stderr_tail.append(f"[runner] {exc}")
        exit_code = 1
    finally:
        await _finalize_job(
            job_id=job_id,
            command=command,
            exit_code=exit_code,
            stdout_tail=list(stdout_tail),
            stderr_tail=list(stderr_tail),
        )


async def _finalize_job(
    *,
    job_id: int,
    command: CliCommand,
    exit_code: int,
    stdout_tail: Iterable[str],
    stderr_tail: Iterable[str],
) -> None:
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        if job.status == JobStatus.CANCELLED:
            return
        job.exit_code = exit_code
        job.finished_at = datetime.now(timezone.utc)
        job.status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
        job.stdout_tail = "\n".join(stdout_tail) if stdout_tail else None
        job.stderr_tail = "\n".join(stderr_tail) if stderr_tail else None
        if exit_code != 0 and not job.message:
            job.message = f"exit={exit_code}"


def join_for_display(argv: list[str]) -> str:
    return " ".join(shlex.quote(p) for p in argv)


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
