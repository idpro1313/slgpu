"""Schemas for Docker container list and log tail (read-only UI)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DockerContainerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Full container id")
    short_id: str = Field(description="12-char prefix for display")
    name: str
    image: str
    status: str
    health: str | None = None
    compose_project: str | None = None
    compose_service: str | None = None


class DockerContainersListOut(BaseModel):
    docker_available: bool
    scope: str
    containers: list[DockerContainerRow]
    last_checked_at: datetime


class DockerContainerLogsOut(BaseModel):
    container_id: str
    container_name: str | None
    tail: int
    logs: str
    docker_available: bool
    last_checked_at: datetime


class DockerEngineEventsOut(BaseModel):
    """Хвост событий Docker Engine API (``/events``), тот же socket, что и для контейнеров."""

    docker_available: bool
    since_sec: int
    limit: int
    events_text: str
    last_checked_at: datetime


class DockerDaemonLogOut(BaseModel):
    """Best-effort лог **демона** dockerd через ``journalctl`` (на хосте с systemd)."""

    lines: int
    text: str
    journal_note: str | None = Field(
        default=None,
        description="Если пусто: подсказка, почему нет journalctl или нет логов",
    )
    last_checked_at: datetime
