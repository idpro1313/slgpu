"""Schemas for user-editable application settings."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PublicAccessSettings(BaseModel):
    server_host: str | None = Field(
        default=None,
        description="Public hostname or IP used for browser links to monitoring UIs.",
    )
    effective_server_host: str
    grafana_url: str
    prometheus_url: str
    langfuse_url: str
    litellm_ui_url: str
    litellm_api_url: str


class PublicAccessSettingsUpdate(BaseModel):
    server_host: str | None = Field(default=None, max_length=253)
