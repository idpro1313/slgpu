"""Job listing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.models.job import Job
from app.schemas.jobs import JobOut

router = APIRouter()


@router.get("", response_model=list[JobOut])
async def list_jobs(
    limit: int = Query(default=50, ge=1, le=500),
    session: AsyncSession = Depends(db_session),
) -> list[Job]:
    result = await session.execute(select(Job).order_by(Job.id.desc()).limit(limit))
    return list(result.scalars().all())


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, session: AsyncSession = Depends(db_session)) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
