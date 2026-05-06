"""Live GPU metrics via nvidia-smi in an ephemeral GPU-enabled container."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import docker
from docker.types import DeviceRequest

logger = logging.getLogger(__name__)

_TTL_S = 3.0
_cache: tuple[float, dict[str, Any]] | None = None
_lock = asyncio.Lock()


def invalidate_gpu_state_cache() -> None:
    global _cache
    _cache = None


def _run_nvidia_smi_probes() -> dict[str, Any]:
    """Sync: single ephemeral container, CSV for gpu + compute processes."""
    try:
        from app.services.stack_config import (
            host_gpu_docker_probe_enabled,
            nvidia_smi_docker_image_for_stack,
            sync_merged_flat,
        )

        merged = sync_merged_flat()
    except Exception:  # noqa: BLE001
        merged = {}
    if not host_gpu_docker_probe_enabled(merged):
        logger.info("[gpu_state][run_nvidia_smi_probes][BLOCK_DISABLED] HOST_GPU_DOCKER_PROBE=off")
        return {"available": False, "error": "host_gpu_docker_probe_disabled", "gpus": []}

    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException as exc:
        logger.info("[gpu_state][run_nvidia_smi_probes][BLOCK_DOCKER] %s", exc)
        return {"available": False, "error": "docker_unavailable", "gpus": []}

    image = nvidia_smi_docker_image_for_stack(merged)
    device_requests = [DeviceRequest(count=-1, capabilities=[["gpu"]])]
    script = r"""
set -e
nvidia-smi --query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu,utilization.memory \
  --format=csv,noheader,nounits
echo '---'
nvidia-smi --query-compute-apps=pid,process_name,used_memory,gpu_uuid --format=csv,noheader
"""
    try:
        out = client.containers.run(
            image,
            ["sh", "-c", script],
            remove=True,
            device_requests=device_requests,
            stdout=True,
            stderr=True,
            network_mode="none",
        )
    except (docker.errors.ImageNotFound, docker.errors.ContainerError, docker.errors.DockerException) as exc:
        logger.info("[gpu_state][run_nvidia_smi_probes][BLOCK_SMI_RUN] %s", exc)
        return {"available": False, "error": str(exc)[:500], "gpus": []}

    text = out.decode("utf-8", errors="replace") if isinstance(out, bytes) else str(out)
    gpus, processes = _parse_smi_csv(text)
    return {"available": True, "error": None, "gpus": gpus, "processes": processes}


def _parse_smi_csv(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if "---" not in text:
        return _parse_gpus_only(text)
    a, b = text.split("---", 1)
    gpus = _lines_to_gpu_rows(a)
    procs: list[dict[str, Any]] = []
    for line in b.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # pid, name, used_mem, uuid
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        used = parts[2]
        u_mib: int | str = int(used) if used.isdigit() else used
        pid_entry: dict[str, Any] = {
            "pid": pid,
            "process_name": parts[1] if len(parts) > 1 else "",
            "used_memory_mib": u_mib,
            "gpu_uuid": parts[3] if len(parts) > 3 else None,
        }
        procs.append(pid_entry)
    return gpus, procs


def _enrich_processes_with_slot_keys(
    data: dict[str, Any], slot_key_engine: list[tuple[str, str]]
) -> dict[str, Any]:
    """Map host PIDs from nvidia-smi to slot_key via ``docker top`` (sync, in worker thread)."""
    procs = data.get("processes")
    if not isinstance(procs, list) or not procs:
        return data
    try:
        import docker
    except ImportError:
        for p in procs:
            if isinstance(p, dict):
                p.setdefault("slot_key", None)
        return data

    from app.services.slot_runtime import slot_container_name

    pid_to_slot: dict[int, str] = {}
    try:
        client = docker.from_env()
        client.ping()
    except docker.errors.DockerException:
        for p in procs:
            if isinstance(p, dict):
                p.setdefault("slot_key", None)
        return data

    for slot_key, engine in slot_key_engine:
        cname = slot_container_name(engine, slot_key)
        try:
            c = client.containers.get(cname)
            top = c.top()
            for row in top.get("Processes") or []:
                if not row:
                    continue
                try:
                    pid = int(row[1]) if len(row) > 1 else int(row[0])
                except (ValueError, TypeError, IndexError):
                    continue
                pid_to_slot[pid] = slot_key
        except (docker.errors.DockerException, KeyError, TypeError):
            continue

    for p in procs:
        if not isinstance(p, dict):
            continue
        pid = p.get("pid")
        p["slot_key"] = pid_to_slot.get(int(pid)) if isinstance(pid, int) else None
    logger.info(
        "[gpu_state][_enrich_processes_with_slot_keys][BLOCK_PIDS_MAP] n_slots=%s n_mapped=%s",
        len(slot_key_engine),
        len(pid_to_slot),
    )
    return data


def _parse_gpus_only(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return _lines_to_gpu_rows(text), []


def _lines_to_gpu_rows(block: str) -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    for line in block.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        def _i(s: str) -> int | str:
            s = s.strip()
            if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                return int(s)
            return s

        try:
            idx = int(parts[0])
        except ValueError:
            idx = len(gpus)
        gpus.append(
            {
                "index": idx,
                "uuid": parts[1] if len(parts) > 1 else None,
                "name": parts[2] if len(parts) > 2 else "",
                "memory_used_mib": _i(parts[3] if len(parts) > 3 else "0"),
                "memory_total_mib": _i(parts[4] if len(parts) > 4 else "0"),
                "utilization_gpu": _i(parts[5] if len(parts) > 5 else "0"),
                "utilization_memory": _i(parts[6] if len(parts) > 6 else "0"),
            }
        )
    return gpus


async def get_gpu_state_snapshot() -> dict[str, Any]:
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.models.slot import EngineSlot, RunStatus

    global _cache
    now = time.monotonic()
    async with _lock:
        if _cache is not None and now - _cache[0] < _TTL_S:
            return _cache[1]
        active = (
            RunStatus.STARTING,
            RunStatus.REQUESTED,
            RunStatus.RUNNING,
            RunStatus.DEGRADED,
        )
        sk_eng: list[tuple[str, str]] = []
        async with session_scope() as s:
            res = await s.execute(
                select(EngineSlot.slot_key, EngineSlot.engine).where(
                    EngineSlot.observed_status.in_(active)
                )
            )
            sk_eng = [(row[0], row[1]) for row in res.all()]
        data = await asyncio.to_thread(_run_nvidia_smi_probes)
        data = await asyncio.to_thread(_enrich_processes_with_slot_keys, data, sk_eng)
        driver_ver, cuda_ver = _driver_cuda()
        payload = {**data, "driver_version": driver_ver, "cuda_version": cuda_ver}
        _cache = (time.monotonic(), payload)
        return payload


def _driver_cuda() -> tuple[str | None, str | None]:
    """Best-effort: secondary full nvidia-smi for header (small)."""
    import re

    try:
        from app.services.stack_config import (
            host_gpu_docker_probe_enabled,
            nvidia_smi_docker_image_for_stack,
            sync_merged_flat,
        )

        merged = sync_merged_flat()
    except Exception:  # noqa: BLE001
        merged = {}
    if not host_gpu_docker_probe_enabled(merged):
        return None, None
    try:
        client = docker.from_env()
    except docker.errors.DockerException:
        return None, None
    device_requests = [DeviceRequest(count=-1, capabilities=[["gpu"]])]
    image = nvidia_smi_docker_image_for_stack(merged)
    try:
        out = client.containers.run(
            image,
            ["nvidia-smi"],
            remove=True,
            device_requests=device_requests,
            stdout=True,
            stderr=True,
            network_mode="none",
        )
    except docker.errors.DockerException:
        return None, None
    txt = out.decode("utf-8", errors="replace") if isinstance(out, bytes) else str(out)
    d = c = None
    for ln in txt.splitlines():
        if "Driver Version:" in ln:
            m = re.search(r"Driver Version:\s*([\d.]+)", ln)
            if m:
                d = m.group(1)
            m2 = re.search(r"CUDA Version:\s*([\d.]+)", ln)
            if m2:
                c = m2.group(1)
            break
    return d, c
