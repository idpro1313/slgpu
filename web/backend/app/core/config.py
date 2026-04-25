"""Application configuration. Loaded from environment (WEB_* in main.env; compose from repo root)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WEB_",
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "slgpu-web"
    api_v1_prefix: str = "/api/v1"
    log_level: str = Field(
        default="INFO",
        description="Root log level: DEBUG, INFO, WARNING, …",
    )

    slgpu_root: Path = Field(default=Path("/slgpu"))
    data_dir: Path = Field(default=Path("/data"))
    # Must match Docker label com.docker.compose.project for each stack (see `docker ps --format '{{.Label "com.docker.compose.project"}}'`)
    compose_project_infer: str = Field(
        default="slgpu",
        description="Compose project name for the vLLM/SGLang stack",
    )
    compose_project_monitoring: str = Field(
        default="slgpu-monitoring",
        description="Compose project name for docker/docker-compose.monitoring.yml stack",
    )
    database_url: str = Field(
        default="sqlite+aiosqlite:////data/slgpu-web.db",
        description="SQLAlchemy async URL. Use absolute path inside the container.",
    )

    docker_socket: str = "unix:///var/run/docker.sock"

    llm_default_vllm_port: int = 8111
    llm_default_sglang_port: int = 8222
    grafana_port: int = 3000
    prometheus_port: int = 9090
    langfuse_port: int = 3001
    litellm_port: int = 4000
    loki_port: int = 3100

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    static_dir: Path | None = None

    job_log_tail_kb: int = 64
    health_poll_seconds: float = 8.0

    @property
    def slgpu_cli(self) -> Path:
        return self.slgpu_root / "slgpu"

    @property
    def models_presets_dir(self) -> Path:
        return self.slgpu_root / "configs" / "models"

    @property
    def main_env_path(self) -> Path:
        return self.slgpu_root / "main.env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
