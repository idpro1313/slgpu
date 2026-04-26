"""Benchmark runs under data/bench/results (scenario + load)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.core.config import get_settings
from app.schemas.common import JobAccepted
from app.services import jobs as jobs_service
from app.services.slgpu_cli import cmd_bench_load, cmd_bench_scenario

router = APIRouter()


class BenchScenarioBody(BaseModel):
    engine: str = "vllm"
    preset: str
    rounds: int = 1
    warmup_requests: int = 3


class BenchLoadBody(BaseModel):
    engine: str = "vllm"
    preset: str
    users: int = 250
    duration: int = 900
    ramp_up: int = 120
    ramp_down: int = 60
    think_time: str = "2000,5000"
    max_prompt: int = 512
    max_output: int = 256
    report_interval: float = 5.0
    warmup_requests: int = 3
    burst: bool = False


def _results_root() -> Path:
    return get_settings().slgpu_root / "data" / "bench" / "results"


@router.get("/runs")
async def list_runs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    root = _results_root()
    if not root.is_dir():
        return out
    for engine_dir in sorted(root.iterdir()):
        if not engine_dir.is_dir():
            continue
        eng = engine_dir.name
        for run_dir in sorted(engine_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            summ = run_dir / "summary.json"
            kind = "unknown"
            if summ.is_file():
                try:
                    data = json.loads(summ.read_text(encoding="utf-8"))
                    kind = "load" if "users" in data else "scenario"
                except json.JSONDecodeError:
                    pass
            out.append(
                {
                    "engine": eng,
                    "timestamp": run_dir.name,
                    "kind": kind,
                    "path": str(run_dir.relative_to(get_settings().slgpu_root)),
                }
            )
    return out[:200]


@router.get("/runs/{engine}/{ts}/summary")
async def get_summary(engine: str, ts: str) -> dict[str, Any]:
    p = _results_root() / engine / ts / "summary.json"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="summary not found")
    return json.loads(p.read_text(encoding="utf-8"))


@router.post("/scenario", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def bench_scenario(
    payload: BenchScenarioBody,
    actor: str | None = Depends(actor_from_header),
    _session: AsyncSession = Depends(db_session),
) -> JobAccepted:
    settings = get_settings()
    cmd = cmd_bench_scenario(
        settings.slgpu_root,
        engine=payload.engine,
        preset=payload.preset,
        rounds=payload.rounds,
        warmup_requests=payload.warmup_requests,
    )
    try:
        job = await jobs_service.submit(
            cmd,
            actor=actor,
            extra_args=payload.model_dump(),
        )
    except jobs_service.JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobAccepted(
        job_id=job.id,
        correlation_id=job.correlation_id,
        kind=job.kind,
        status=job.status.value,
        message=cmd.summary,
    )


@router.post("/load", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def bench_load(
    payload: BenchLoadBody,
    actor: str | None = Depends(actor_from_header),
    _session: AsyncSession = Depends(db_session),
) -> JobAccepted:
    settings = get_settings()
    cmd = cmd_bench_load(settings.slgpu_root)
    try:
        job = await jobs_service.submit(
            cmd,
            actor=actor,
            extra_args=payload.model_dump(),
        )
    except jobs_service.JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobAccepted(
        job_id=job.id,
        correlation_id=job.correlation_id,
        kind=job.kind,
        status=job.status.value,
        message=cmd.summary,
    )
