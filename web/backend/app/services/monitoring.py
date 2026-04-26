"""Health probes for monitoring stack and LiteLLM."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings
from app.models.service import ServiceStatus
from app.services.docker_client import ContainerSummary, get_docker_inspector
from app.services.stack_config import ports_for_probes_sync

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
    p = ports_for_probes_sync()
    mon = str(p["compose_project_monitoring"])
    h = s.monitoring_http_host
    prom = int(p["prometheus_port"])
    graf = int(p["grafana_port"])
    lf = int(p["langfuse_port"])
    llm = int(p["litellm_port"])
    return [
        ServiceProbe(
            key="prometheus",
            display_name="Prometheus",
            category="monitoring",
            project=mon,
            service="prometheus",
            health_url=f"http://{h}:{prom}/-/healthy",
            web_url=f"http://{h}:{prom}",
        ),
        ServiceProbe(
            key="grafana",
            display_name="Grafana",
            category="monitoring",
            project=mon,
            service="grafana",
            health_url=f"http://{h}:{graf}/api/health",
            web_url=f"http://{h}:{graf}",
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
            health_url=f"http://{h}:{lf}/api/public/health",
            web_url=f"http://{h}:{lf}",
        ),
        ServiceProbe(
            key="litellm",
            display_name="LiteLLM Proxy",
            category="gateway",
            project=mon,
            service="litellm",
            health_url=f"http://{h}:{llm}/health/liveliness",
            web_url=f"http://{h}:{llm}/ui",
        ),
    ]


@dataclass
class ProbeResult:
    probe: ServiceProbe
    status: ServiceStatus
    detail: str | None
    container: ContainerSummary | None


async def probe_all() -> list[ProbeResult]:
    s = get_settings()
    ports = ports_for_probes_sync()
    inspector = get_docker_inspector()
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

    if not inspector.is_available:
        logger.info(
            "[monitoring][probe_all][BLOCK_CHECK_DOCKER] result=unavailable "
            "socket=%s cannot_list_containers=True hint=see_docker_client_warning "
            "infer_project=%s monitoring_project=%s",
            s.docker_socket,
            ports["compose_project_infer"],
            ports["compose_project_monitoring"],
        )
    else:
        not_found = sum(1 for r in results if r.detail == "container not found")
        healthy = sum(1 for r in results if r.status == ServiceStatus.HEALTHY)
        logger.info(
            "[monitoring][probe_all][BLOCK_RESOLVE] docker=ok project=%s "
            "probes=%s container_not_found=%s healthy=%s "
            "if_not_found_check_WEB_COMPOSE_PROJECT_MONITORING",
            ports["compose_project_monitoring"],
            len(results),
            not_found,
            healthy,
        )
    return results


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
