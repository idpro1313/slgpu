"""Read-only Docker daemon access.

Mutations are NOT done here on purpose - they belong to the slgpu CLI.
The classes in this module only inspect containers, return ports and
fetch tail logs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import docker
from docker.errors import DockerException, NotFound

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ContainerSummary:
    id: str
    name: str
    image: str
    status: str
    health: str | None
    project: str | None
    service: str | None
    ports: list[dict[str, Any]]
    started_at: datetime | None
    labels: dict[str, str]


class DockerInspector:
    def __init__(self) -> None:
        settings = get_settings()
        try:
            self._client = docker.DockerClient(base_url=settings.docker_socket)
        except DockerException as exc:
            msg = f"[docker_client][__init__] cannot connect: {exc}"
            if "Permission" in str(exc) or "PermissionError" in type(exc).__name__:
                msg += (
                    " — for bind-mounted /var/run/docker.sock, the app user (10001) needs "
                    "a supplementary group with the same GID as the socket; see web/docker-entrypoint.sh."
                )
            logger.warning(msg)
            self._client = None
        # TTL list cache for get_by_service fallbacks (many probes per /dashboard)
        self._all_cont_cache: tuple[float, list] | None = None

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def _project_filter(self, project: str) -> dict[str, Any]:
        return {"label": [f"com.docker.compose.project={project}"]}

    def list_project(self, project: str) -> list[ContainerSummary]:
        if not self._client:
            return []
        try:
            containers = self._client.containers.list(all=True, filters=self._project_filter(project))
        except DockerException as exc:
            logger.warning("[docker_client][list_project] %s", exc)
            return []
        return [self._summary(c) for c in containers]

    def get_by_service(self, project: str, service: str) -> ContainerSummary | None:
        if not self._client:
            return None
        filters = {
            "label": [
                f"com.docker.compose.project={project}",
                f"com.docker.compose.service={service}",
            ]
        }
        try:
            containers = self._client.containers.list(all=True, filters=filters)
        except DockerException as exc:
            logger.warning("[docker_client][get_by_service] %s", exc)
            return None
        if containers:
            return self._summary(containers[0])
        fb = self._get_by_service_fallback(project, service)
        if fb is not None:
            logger.debug(
                "[docker_client][get_by_service] fallback project=%r service=%r",
                project,
                service,
            )
            return fb
        logger.debug(
            "[docker_client][get_by_service] no match project=%r service=%r",
            project,
            service,
        )
        return None

    @staticmethod
    def _norm_compose_id(value: str) -> str:
        return (value or "").replace("_", "-").casefold()

    def _all_containers_cached(self) -> list:
        if not self._client:
            return []
        now = time.monotonic()
        if self._all_cont_cache is not None and now - self._all_cont_cache[0] < 1.5:
            return self._all_cont_cache[1]
        try:
            lst = self._client.containers.list(all=True)
        except DockerException as exc:
            logger.warning("[docker_client][_all_containers_cached] %s", exc)
            return []
        self._all_cont_cache = (now, lst)
        return lst

    def _get_by_service_fallback(self, project: str, service: str) -> ContainerSummary | None:
        """When exact Docker label filter returns nothing, try normalized labels or Compose-style names (Portainer, v1/v2 naming)."""
        p_w, s_w = self._norm_compose_id(project), self._norm_compose_id(service)
        hyp = f"{project}-{service}"
        uproj = project.replace("-", "_")
        userv = service.replace("-", "_")
        und = f"{uproj}_{userv}"
        for c in self._all_containers_cached():
            c = c if c.attrs else self._client.containers.get(c.id)
            attrs = c.attrs
            if not attrs:
                continue
            labels: dict[str, str] = (attrs.get("Config") or {}).get("Labels") or {}
            p = self._norm_compose_id(labels.get("com.docker.compose.project", ""))
            s = self._norm_compose_id(labels.get("com.docker.compose.service", ""))
            if p == p_w and s == s_w:
                return self._summary(c)
        for c in self._all_containers_cached():
            c = c if c.attrs else self._client.containers.get(c.id)
            attrs = c.attrs
            if not attrs:
                continue
            name = (attrs.get("Name") or getattr(c, "name", None) or "").lstrip("/")
            if name.startswith(f"{hyp}-") or name == hyp:
                return self._summary(c)
            if name.startswith(f"{und}_") or name == und:
                return self._summary(c)
            # Стабильные имена из репозитория (container_name: slgpu-*, slgpu-monitoring-*),
            # независимы от `COMPOSE_PROJECT_NAME` (лейблы остаётся primary).
            st_llm = f"slgpu-{service}"
            if name == st_llm or name.startswith(f"{st_llm}-"):
                return self._summary(c)
            st_mon = f"slgpu-monitoring-{service}"
            if name == st_mon or name.startswith(f"{st_mon}-"):
                return self._summary(c)
        return None

    def get_by_name(self, name: str) -> ContainerSummary | None:
        """Exact container name (with or without leading slash), e.g. ``slgpu-vllm``."""
        if not self._client or not name:
            return None
        n = name.lstrip("/")
        try:
            c = self._client.containers.get(n)
        except NotFound:
            return None
        except DockerException as exc:
            logger.warning("[docker_client][get_by_name] %s", exc)
            return None
        return self._summary(c)

    def tail_logs(self, container_id: str, tail: int = 200) -> str:
        if not self._client:
            return ""
        try:
            container = self._client.containers.get(container_id)
            data = container.logs(tail=tail, stdout=True, stderr=True, timestamps=False)
            return data.decode("utf-8", errors="replace")
        except NotFound:
            return ""
        except DockerException as exc:
            logger.warning("[docker_client][tail_logs] %s", exc)
            return ""

    def _summary(self, container: Any) -> ContainerSummary:
        attrs = container.attrs or {}
        state = attrs.get("State", {}) or {}
        health = (state.get("Health") or {}).get("Status")
        labels: dict[str, str] = (attrs.get("Config") or {}).get("Labels") or {}
        ports_raw = (attrs.get("NetworkSettings") or {}).get("Ports") or {}
        ports: list[dict[str, Any]] = []
        for inside, mappings in ports_raw.items():
            if not mappings:
                continue
            for mapping in mappings:
                ports.append({
                    "container": inside,
                    "host_ip": mapping.get("HostIp"),
                    "host_port": int(mapping["HostPort"]) if mapping.get("HostPort") else None,
                })
        started_at = _parse_iso(state.get("StartedAt"))
        return ContainerSummary(
            id=container.id or "",
            name=(attrs.get("Name") or "").lstrip("/"),
            image=(attrs.get("Config") or {}).get("Image") or "",
            status=state.get("Status") or "unknown",
            health=health,
            project=labels.get("com.docker.compose.project"),
            service=labels.get("com.docker.compose.service"),
            ports=ports,
            started_at=started_at,
            labels=labels,
        )


@lru_cache(maxsize=1)
def get_docker_inspector() -> DockerInspector:
    """One shared client per process: avoids log spam and duplicate TCP handshakes to the socket."""
    return DockerInspector()


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw or raw.startswith("0001"):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
