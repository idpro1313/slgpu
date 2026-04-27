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
    database_url: str = Field(
        default="sqlite+aiosqlite:////data/slgpu-web.db",
        description="SQLAlchemy async URL. Use absolute path inside the container.",
    )

    docker_socket: str = "unix:///var/run/docker.sock"

    # Задаётся в `docker/docker-compose.web.yml` / bootstrap env (без кода-дефолта 127.0.0.1).
    monitoring_http_host: str = Field(
        default="host.docker.internal",
        description="Host for HTTP health checks to monitoring services (from inside slgpu-web).",
    )

    # Тот же принцип: из slgpu-web к published LLM портам на хосте — не 127.0.0.1 контейнера web.
    llm_http_host: str = Field(
        default="host.docker.internal",
        description="Host for /v1/models and /metrics probes to the LLM stack (published on host or Docker DNS).",
    )

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    static_dir: Path | None = None

    docker_host_probe_image: str = Field(
        default="busybox:1.36",
        description=(
            "Образ для docker run с bind-mount хостовых /proc и /etc "
            "(дашборд «Сервер»: CPU/RAM/ОС с хоста, а не из namespace web)."
        ),
    )
    nvidia_smi_docker_image: str = Field(
        default="nvidia/cuda:12.4.1-base-ubuntu22.04",
        description=(
            "Образ с nvidia-smi для опроса GPU на хосте через Docker (NVIDIA Container Toolkit)."
        ),
    )

    @property
    def slgpu_cli(self) -> Path:
        return self.slgpu_root / "slgpu"

    @property
    def models_presets_dir(self) -> Path:
        from app.services.stack_config import presets_dir_sync

        return presets_dir_sync()

    @property
    def main_env_path(self) -> Path:
        return self.slgpu_root / "configs" / "main.env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
