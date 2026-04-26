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
from typing import Any

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


_active_locks: dict[tuple[str, str], int] = {}
_lock_guard = asyncio.Lock()


async def _acquire_lock(scope: str, resource: str | None) -> bool:
    key = (scope, resource or "*")
    async with _lock_guard:
        if _active_locks.get(key, 0) > 0:
            return False
        _active_locks[key] = _active_locks.get(key, 0) + 1
        return True


async def _release_lock(scope: str, resource: str | None) -> None:
    key = (scope, resource or "*")
    async with _lock_guard:
        if _active_locks.get(key, 0) > 0:
            _active_locks[key] -= 1
            if _active_locks[key] <= 0:
                _active_locks.pop(key, None)


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

    asyncio.create_task(_run_job(job_id, command))
    async with session_scope() as session:
        return await session.get(Job, job_id)  # type: ignore[return-value]


async def _run_job(job_id: int, command: CliCommand) -> None:
    settings = get_settings()
    cwd = settings.slgpu_root
    stdout_tail: deque[str] = deque(maxlen=400)
    stderr_tail: deque[str] = deque(maxlen=400)

    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            await _release_lock(command.scope, command.resource)
            return
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job_args: dict = dict(job.args or {})

    if command.kind.startswith("native."):
        await handle_native_job(job_id, command, job_args)
        await _release_lock(command.scope, command.resource)
        return

    exit_code = -1
    argv = _exec_argv_for_cli(command, cwd)
    slgpu_entry = str(cwd / "slgpu")
    if len(argv) >= 2 and argv[0] == "/bin/bash" and argv[1] == slgpu_entry:
        logger.info("[jobs] slgpu via bash (cwd=%s): %s", cwd, join_for_display(argv))
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
        logger.exception("[jobs][_run_job] unexpected failure")
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
        await _release_lock(command.scope, command.resource)


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
