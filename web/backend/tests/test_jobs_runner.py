"""Job runner: only native.* jobs; in-process lock per (scope, resource)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db.session import init_db, session_scope
from app.models.job import Job, JobStatus
from app.services import jobs as jobs_service
from app.services.jobs import JobConflictError, submit
from app.services.slgpu_cli import cmd_pull, cmd_slot_up


@pytest.fixture
async def initialized_db() -> None:
    await init_db()


def test_session_scope_helper_exists() -> None:
    assert callable(session_scope)


@pytest.mark.asyncio
async def test_second_submit_same_slot_resource_raises_conflict(
    initialized_db: None,
) -> None:
    """While first native.slot.up is in-flight, second submit for same slot must fail."""
    cmd1 = cmd_slot_up(
        slot_key="lock-test",
        engine="vllm",
        preset="qwen3.6-35b-a3b",
        host_api_port=8111,
        gpu_indices=[0, 1, 2, 3, 4, 5, 6, 7],
    )
    cmd2 = cmd_slot_up(
        slot_key="lock-test",
        engine="vllm",
        preset="qwen3.6-35b-a3b",
        host_api_port=8111,
        gpu_indices=[0, 1, 2, 3, 4, 5, 6, 7],
    )

    async def _slow_then_succeed(job_id: int, command, args: dict) -> None:
        await asyncio.sleep(0.35)
        from app.services.native_jobs import _finalize_native_job

        await _finalize_native_job(job_id, command, 0, [])

    with patch("app.services.jobs.handle_native_job", new=_slow_then_succeed):
        j1 = await submit(cmd1, actor="pytest")
        assert j1.kind == "native.slot.up"
        with pytest.raises(JobConflictError):
            await submit(cmd2, actor="pytest")
        await asyncio.sleep(0.45)

    async with session_scope() as session:
        done = await session.get(Job, j1.id)
        assert done is not None
        assert done.status == JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_non_native_job_fails_with_message(initialized_db: None) -> None:
    """Jobs that are not native.* are marked failed (v5 contract)."""
    from app.services.slgpu_cli import CliCommand

    cmd = CliCommand(
        kind="legacy.test",
        argv=["/bin/true"],
        scope="test",
        resource="x",
        summary="should not run",
    )
    job = await submit(cmd, actor="pytest")
    for _ in range(50):
        await asyncio.sleep(0.05)
        async with session_scope() as session:
            row = await session.get(Job, job.id)
            assert row is not None
            if row.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
                assert row.status == JobStatus.FAILED
                assert "native.*" in (row.message or "")
                return
    pytest.fail("job did not finish in time")


@pytest.mark.asyncio
async def test_force_model_pull_halt_cancels_job_and_releases_lock(initialized_db: None) -> None:
    cmd = cmd_pull(Path("."), "XiaomiMiMo/MiMo-V2.5")

    async def _slow_native_job(job_id: int, command, args: dict) -> None:  # noqa: ARG001
        await asyncio.sleep(10)

    with patch("app.services.jobs.handle_native_job", new=_slow_native_job):
        job = await submit(cmd, actor="pytest")
        cancelled = await jobs_service.force_model_pull_halt("XiaomiMiMo/MiMo-V2.5")
        assert job.id in cancelled

        retry = await submit(cmd, actor="pytest")
        await jobs_service.force_model_pull_halt("XiaomiMiMo/MiMo-V2.5")

    async with session_scope() as session:
        row = await session.get(Job, job.id)
        retry_row = await session.get(Job, retry.id)
        assert row is not None
        assert retry_row is not None
        assert row.status == JobStatus.CANCELLED
        assert retry_row.status == JobStatus.CANCELLED
