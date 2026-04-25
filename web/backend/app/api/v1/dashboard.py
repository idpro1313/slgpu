"""Aggregated dashboard data for the home page."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session
from app.models.job import Job, JobStatus
from app.models.model import HFModel, ModelDownloadStatus
from app.models.preset import Preset
from app.services.docker_client import get_docker_inspector
from app.services.monitoring import probe_all
from app.services.runtime import snapshot as runtime_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def dashboard(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:
    models_total = (await session.execute(select(func.count(HFModel.id)))).scalar_one()
    ready_total = (
        await session.execute(
            select(func.count(HFModel.id)).where(
                HFModel.download_status == ModelDownloadStatus.READY
            )
        )
    ).scalar_one()
    presets_total = (await session.execute(select(func.count(Preset.id)))).scalar_one()
    active_jobs = (
        await session.execute(
            select(func.count(Job.id)).where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
        )
    ).scalar_one()

    runtime = await runtime_snapshot()
    services = await probe_all()
    healthy = sum(1 for s in services if s.status.value == "healthy")
    total = len(services)
    logger.info(
        "[api][dashboard][BLOCK_AGGREGATE] docker=%s models=%s presets=%s jobs_active=%s "
        "services_healthy=%s/%s runtime_engine=%s",
        "up" if get_docker_inspector().is_available else "down",
        models_total,
        presets_total,
        active_jobs,
        healthy,
        total,
        runtime.engine,
    )

    return {
        "metrics": {
            "models_total": models_total,
            "models_ready": ready_total,
            "presets_total": presets_total,
            "active_jobs": active_jobs,
            "services_healthy": healthy,
            "services_total": total,
        },
        "runtime": {
            "engine": runtime.engine,
            "api_port": runtime.api_port,
            "container_status": runtime.container_status,
            "served_models": runtime.served_models,
            "metrics_available": runtime.metrics_available,
            "last_checked_at": runtime.last_checked_at,
        },
        "services": [
            {
                "key": probe.probe.key,
                "display_name": probe.probe.display_name,
                "category": probe.probe.category,
                "status": probe.status,
                "detail": probe.detail,
                "url": probe.probe.web_url,
                "container_status": probe.container.status if probe.container else None,
            }
            for probe in services
        ],
    }
