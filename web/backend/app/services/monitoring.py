"""Health probes for monitoring stack and LiteLLM."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.models.service import ServiceStatus
from app.services.docker_client import ContainerSummary, DockerInspector

logger = logging.getLogger(__name__)


@dataclass
class ServiceProbe:
    key: str
    display_name: str
    category: str
    project: str
    service: str
    health_url: str | None
    web_url: str | None


def _settings_probes() -> list[ServiceProbe]:
    s = get_settings()
    mon = s.compose_project_monitoring
    return [
        ServiceProbe(
            key="prometheus",
            display_name="Prometheus",
            category="monitoring",
            project=mon,
            service="prometheus",
            health_url=f"http://127.0.0.1:{s.prometheus_port}/-/healthy",
            web_url=f"http://127.0.0.1:{s.prometheus_port}",
        ),
        ServiceProbe(
            key="grafana",
            display_name="Grafana",
            category="monitoring",
            project=mon,
            service="grafana",
            health_url=f"http://127.0.0.1:{s.grafana_port}/api/health",
            web_url=f"http://127.0.0.1:{s.grafana_port}",
        ),
        ServiceProbe(
            key="loki",
            display_name="Loki",
            category="monitoring",
            project=mon,
            service="loki",
            health_url=None,
            web_url=None,
        ),
        ServiceProbe(
            key="promtail",
            display_name="Promtail",
            category="monitoring",
            project=mon,
            service="promtail",
            health_url=None,
            web_url=None,
        ),
        ServiceProbe(
            key="dcgm-exporter",
            display_name="NVIDIA DCGM Exporter",
            category="monitoring",
            project=mon,
            service="dcgm-exporter",
            health_url=None,
            web_url=None,
        ),
        ServiceProbe(
            key="node-exporter",
            display_name="Node Exporter",
            category="monitoring",
            project=mon,
            service="node-exporter",
            health_url=None,
            web_url=None,
        ),
        ServiceProbe(
            key="langfuse",
            display_name="Langfuse",
            category="monitoring",
            project=mon,
            service="langfuse-web",
            health_url=f"http://127.0.0.1:{s.langfuse_port}/api/public/health",
            web_url=f"http://127.0.0.1:{s.langfuse_port}",
        ),
        ServiceProbe(
            key="litellm",
            display_name="LiteLLM Proxy",
            category="gateway",
            project=mon,
            service="litellm",
            health_url=f"http://127.0.0.1:{s.litellm_port}/health/liveliness",
            web_url=f"http://127.0.0.1:{s.litellm_port}/ui",
        ),
    ]


@dataclass
class ProbeResult:
    probe: ServiceProbe
    status: ServiceStatus
    detail: str | None
    container: ContainerSummary | None


async def probe_all() -> list[ProbeResult]:
    inspector = DockerInspector()
    results: list[ProbeResult] = []
    async with httpx.AsyncClient(timeout=2.0) as client:
        for probe in _settings_probes():
            container = inspector.get_by_service(probe.project, probe.service)
            status = ServiceStatus.UNKNOWN
            detail: str | None = None
            if container is None:
                status = ServiceStatus.DOWN
                detail = "container not found"
            elif container.status != "running":
                status = ServiceStatus.DOWN
                detail = f"container status={container.status}"
            elif probe.health_url:
                try:
                    response = await client.get(probe.health_url)
                    if 200 <= response.status_code < 400:
                        status = ServiceStatus.HEALTHY
                    else:
                        status = ServiceStatus.DEGRADED
                        detail = f"HTTP {response.status_code}"
                except (httpx.HTTPError, OSError) as exc:
                    status = ServiceStatus.DEGRADED
                    detail = f"probe failed: {exc.__class__.__name__}"
            else:
                status = ServiceStatus.HEALTHY
            results.append(ProbeResult(probe=probe, status=status, detail=detail, container=container))
    return results


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
