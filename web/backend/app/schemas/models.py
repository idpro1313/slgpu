"""Schemas for /api/v1/models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.model import ModelDownloadStatus


class ModelPullProgress(BaseModel):
    """Активная фоновая загрузка весов (`native.model.pull`) для данной HF-модели."""

    job_id: int
    status: str
    progress: float | None = Field(default=None, description="Доля 0..1, если известна (tqdm по файлам).")
    message: str | None = None


class HFModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hf_id: str
    revision: str | None
    slug: str
    local_path: str | None
    size_bytes: int | None
    download_status: ModelDownloadStatus
    last_error: str | None
    last_pulled_at: datetime | None
    attempts: int
    notes: str | None
    created_at: datetime
    updated_at: datetime
    pull_progress: ModelPullProgress | None = None


class HFModelCreate(BaseModel):
    hf_id: str = Field(min_length=3, max_length=256, examples=["Qwen/Qwen3.6-35B-A3B"])
    revision: str | None = None
    notes: str | None = None


class HFModelUpdate(BaseModel):
    revision: str | None = None
    notes: str | None = None


class HFModelPullRequest(BaseModel):
    revision: str | None = None


class ModelSyncResult(BaseModel):
    """Сканирование MODELS_DIR: папок затронуто (создано/обновлено) и всего в реестре."""

    touched: int
    total: int
