# GRACE[M-WEB][log_exports][BLOCK_LOG_EXPORT_API]
"""Полная выгрузка логов Loki в файл ``ndjson.gz`` (фоновый job)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.models.log_export import LogExport, LogExportStatus
from app.schemas.log_exports import (
    LogExportAccepted,
    LogExportCreate,
    LogExportOut,
    LogExportsListOut,
)
from app.services import jobs as jobs_service
from app.services import log_export as log_export_service
from app.services.log_report import validate_period
from app.services.slgpu_cli import ValidationError as CliValidationError, cmd_log_export
from app.services.stack_config import sync_merged_flat
from app.services.stack_registry import raise_if_missing

router = APIRouter()
logger = logging.getLogger(__name__)


def _orm_to_out(r: LogExport) -> LogExportOut:
    return LogExportOut(
        id=r.id,
        status=r.status.value if isinstance(r.status, LogExportStatus) else str(r.status),
        job_id=r.job_id,
        time_from=r.time_from,
        time_to=r.time_to,
        scope=r.scope,
        logql=r.logql,
        redact_secrets=bool(r.redact_secrets),
        artifact_relpath=r.artifact_relpath,
        line_count=r.line_count,
        byte_size=r.byte_size,
        retention_note=r.retention_note,
        error_message=r.error_message,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=LogExportsListOut, tags=["log-exports"])
async def list_log_exports(
    session: AsyncSession = Depends(db_session),
    limit: int = Query(default=30, ge=1, le=100),
) -> LogExportsListOut:
    result = await session.execute(
        select(LogExport).order_by(LogExport.id.desc()).limit(limit)
    )
    rows = list(result.scalars().all())
    return LogExportsListOut(items=[_orm_to_out(r) for r in rows])


@router.get("/{export_id:int}", response_model=LogExportOut, tags=["log-exports"])
async def get_log_export(
    export_id: int,
    session: AsyncSession = Depends(db_session),
) -> LogExportOut:
    row = await session.get(LogExport, export_id)
    if row is None:
        raise HTTPException(status_code=404, detail="export not found")
    return _orm_to_out(row)


@router.get("/{export_id:int}/download", tags=["log-exports"])
async def download_log_export(
    export_id: int,
    session: AsyncSession = Depends(db_session),
) -> FileResponse:
    row = await session.get(LogExport, export_id)
    if row is None:
        raise HTTPException(status_code=404, detail="export not found")
    if row.status != LogExportStatus.SUCCEEDED:
        raise HTTPException(
            status_code=409,
            detail="export is not ready",
        )
    rel = (row.artifact_relpath or "").strip()
    if not rel:
        raise HTTPException(status_code=404, detail="export file missing")

    merged = sync_merged_flat()
    try:
        root = Path(str(merged.get("WEB_DATA_DIR") or "")).resolve()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    target = (root / rel).resolve()
    if not jobs_service.is_within_root(target, root):
        raise HTTPException(status_code=400, detail="invalid export path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="export file not on disk")

    return FileResponse(
        path=str(target),
        media_type="application/gzip",
        filename=target.name,
    )


@router.post(
    "",
    response_model=LogExportAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["log-exports"],
)
async def create_log_export(
    payload: LogExportCreate,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> LogExportAccepted:
    merged = sync_merged_flat()
    raise_if_missing(merged, "monitoring_up")

    if payload.scope == "custom":
        if not payload.logql or not str(payload.logql).strip():
            raise HTTPException(
                status_code=400,
                detail="При scope=custom поле logql обязательно.",
            )

    try:
        logql_resolved = log_export_service.build_export_logql(
            scope=payload.scope,
            logql_custom=payload.logql if payload.scope == "custom" else None,
            container=payload.container,
            compose_service=payload.compose_service,
            compose_project=payload.compose_project,
            slgpu_slot=payload.slgpu_slot,
            slgpu_engine=payload.slgpu_engine,
            slgpu_preset=payload.slgpu_preset,
            slgpu_run_id=payload.slgpu_run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        validate_period(
            payload.time_from,
            payload.time_to,
            max_hours=log_export_service.EXPORT_MAX_PERIOD_HOURS,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    export_row = LogExport(
        status=LogExportStatus.PENDING,
        job_id=None,
        time_from=payload.time_from,
        time_to=payload.time_to,
        scope=payload.scope,
        logql=logql_resolved,
        redact_secrets=payload.redact_secrets,
    )
    session.add(export_row)
    await session.flush()

    try:
        command = cmd_log_export(export_id=export_row.id)
    except CliValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()

    try:
        job = await jobs_service.submit(
            command,
            actor=actor,
            extra_args={"export_id": export_row.id},
        )
    except jobs_service.JobConflictError as exc:
        await session.delete(export_row)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    export_row.job_id = job.id
    await session.flush()

    logger.info(
        "[log_exports][create][BLOCK_ENQUEUED] export_id=%s job_id=%s",
        export_row.id,
        job.id,
    )

    return LogExportAccepted(
        export_id=export_row.id,
        job_id=job.id,
        correlation_id=job.correlation_id,
        message=command.summary,
    )
