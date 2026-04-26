"""Job runner uses argv only and respects advisory locks."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.db.session import init_db
from app.services import jobs as jobs_service
from app.services.jobs import _exec_argv_for_cli
from app.services.slgpu_cli import CliCommand, cmd_up


@pytest.fixture
async def initialized_db() -> None:
    await init_db()


@pytest.mark.asyncio
async def test_submit_runs_argv_and_records_exit(initialized_db, tmp_path: Path) -> None:
    script = tmp_path / "echo.sh"
    script.write_text("#!/bin/sh\necho hi-from-runner\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    command = CliCommand(
        kind="test.echo",
        argv=["/bin/sh", str(script)],
        scope="test",
        resource="echo",
        summary="echo runner",
    )
    job = await jobs_service.submit(command, actor="pytest")
    for _ in range(50):
        await asyncio.sleep(0.1)
        async with jobs_service.session_scope() as session:
            from app.models.job import Job, JobStatus

            refreshed = await session.get(Job, job.id)
            assert refreshed is not None
            if refreshed.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
                assert refreshed.exit_code == 0
                assert refreshed.stdout_tail and "hi-from-runner" in refreshed.stdout_tail
                return
    pytest.fail("job did not finish in time")


@pytest.mark.asyncio
async def test_advisory_lock_blocks_concurrent_jobs(initialized_db, tmp_path: Path) -> None:
    sleeper = tmp_path / "sleep.sh"
    sleeper.write_text("#!/bin/sh\nsleep 0.5\n", encoding="utf-8")
    sleeper.chmod(0o755)

    command = CliCommand(
        kind="test.sleep",
        argv=["/bin/sh", str(sleeper)],
        scope="engine",
        resource="vllm",
        summary="sleep",
    )
    await jobs_service.submit(command)
    with pytest.raises(jobs_service.JobConflictError):
        await jobs_service.submit(command)


def test_session_scope_helper_exists():
    assert callable(jobs_service.session_scope)


def test_exec_argv_wraps_repo_slgpu_with_bash(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "slgpu").write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    cmd = cmd_up(root, "vllm", "deepseek-v4-flash")
    out = _exec_argv_for_cli(cmd, root)
    assert out == [
        "/bin/bash",
        str(root / "slgpu"),
        "up",
        "vllm",
        "-m",
        "deepseek-v4-flash",
    ]


def test_exec_argv_passes_through_other_commands(tmp_path: Path) -> None:
    script = tmp_path / "tool.sh"
    script.write_text("#!/bin/sh\necho\n", encoding="utf-8")
    cmd = CliCommand(
        kind="test.other",
        argv=[str(script), "a"],
        scope="test",
        resource="x",
    )
    assert _exec_argv_for_cli(cmd, tmp_path) == [str(script), "a"]
