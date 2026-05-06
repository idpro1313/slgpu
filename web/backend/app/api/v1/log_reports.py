# GRACE[M-WEB][log_reports][BLOCK_LOG_REPORT_API]
"""On-demand сводный отчёт по логам из Loki + LLM-сводка (LiteLLM или внешний OpenAI-compatible API)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import actor_from_header, db_session
from app.models.log_report import LogReport, LogReportStatus
from app.schemas.log_reports import (
    LogReportAccepted,
    LogReportCreate,
    LogReportLlmCatalogSourceOut,
    LogReportOut,
    LogReportsListOut,
)
from app.services import jobs as jobs_service
from app.services import log_report as log_report_service
from app.services.slgpu_cli import ValidationError as CliValidationError, cmd_log_report
from app.services.stack_config import sync_merged_flat
from app.services.stack_registry import raise_if_missing

router = APIRouter()
logger = logging.getLogger(__name__)


def _orm_to_out(r: LogReport) -> LogReportOut:
    return LogReportOut(
        id=r.id,
        status=r.status.value if isinstance(r.status, LogReportStatus) else str(r.status),
        job_id=r.job_id,
        time_from=r.time_from,
        time_to=r.time_to,
        scope=r.scope,
        logql=r.logql,
        llm_model=r.llm_model,
        max_lines=int(r.max_lines),
        facts=r.facts,
        llm_markdown=r.llm_markdown,
        error_message=r.error_message,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=LogReportsListOut, tags=["log-reports"])
async def list_log_reports(
    session: AsyncSession = Depends(db_session),
    limit: int = Query(default=20, ge=1, le=100),
) -> LogReportsListOut:
    result = await session.execute(
        select(LogReport).order_by(LogReport.id.desc()).limit(limit)
    )
    rows = list(result.scalars().all())
    return LogReportsListOut(items=[_orm_to_out(r) for r in rows])


@router.get(
    "/llm-catalog-source",
    response_model=LogReportLlmCatalogSourceOut,
    tags=["log-reports"],
)
async def log_report_llm_catalog_source() -> LogReportLlmCatalogSourceOut:
    merged = sync_merged_flat()
    return LogReportLlmCatalogSourceOut(
        use_litellm_model_catalog=log_report_service.use_litellm_model_catalog(merged),
    )


@router.get("/{report_id:int}", response_model=LogReportOut, tags=["log-reports"])
async def get_log_report(
    report_id: int,
    session: AsyncSession = Depends(db_session),
) -> LogReportOut:
    row = await session.get(LogReport, report_id)
    if row is None:
        raise HTTPException(status_code=404, detail="report not found")
    return _orm_to_out(row)


@router.post(
    "",
    response_model=LogReportAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["log-reports"],
)
async def create_log_report(
    payload: LogReportCreate,
    session: AsyncSession = Depends(db_session),
    actor: str | None = Depends(actor_from_header),
) -> LogReportAccepted:
    merged = sync_merged_flat()
    raise_if_missing(merged, "monitoring_up")

    if payload.scope == "custom":
        raw_q = payload.logql
        if raw_q is None or not str(raw_q).strip():
            raise HTTPException(
                status_code=400,
                detail="При scope=custom поле logql обязательно.",
            )
    try:
        logql_resolved = log_report_service.resolved_logql(
            payload.scope,
            payload.logql if payload.scope == "custom" else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        dt_from, dt_to = log_report_service.validate_period(
            payload.time_from, payload.time_to
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    lm = payload.llm_model.strip()
    if not lm:
        raise HTTPException(status_code=400, detail="llm_model не может быть пустым")

    report = LogReport(
        status=LogReportStatus.PENDING,
        job_id=None,
        time_from=dt_from,
        time_to=dt_to,
        scope=payload.scope,
        logql=logql_resolved,
        llm_model=lm,
        max_lines=payload.max_lines,
    )
    session.add(report)
    await session.flush()

    try:
        command = cmd_log_report(report_id=report.id)
    except CliValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Release SQLite write lock before `jobs.submit()`, which opens a second session
    # (Job + audit_events INSERT). Holding the request tx here caused database is locked
    # (same pattern as `POST /models/{id}/pull`).
    await session.commit()

    try:
        job = await jobs_service.submit(
            command,
            actor=actor,
            extra_args={"report_id": report.id},
        )
    except jobs_service.JobConflictError as exc:
        await session.delete(report)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    report.job_id = job.id
    await session.flush()

    logger.info(
        "[log_reports][create][BLOCK_ENQUEUED] report_id=%s job_id=%s",
        report.id,
        job.id,
    )

    return LogReportAccepted(
        report_id=report.id,
        job_id=job.id,
        correlation_id=job.correlation_id,
        message=command.summary,
    )
