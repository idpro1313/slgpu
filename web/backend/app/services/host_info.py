"""Host hardware and OS snapshot for the dashboard.

По умолчанию slgpu-web **без GPU**: ``nvidia-smi`` внутри контейнера недоступен. Чтобы
показывать **железо сервера**, при доступном Docker socket:

- CPU, RAM, ядро, hostname и ОС читаются из **хостовых** ``/proc`` и ``/etc`` через
  эфемерный контейнер (bind-mount).
- NVIDIA: эфемерный контейнер с ``device_requests=gpu`` и образом с ``nvidia-smi``
  (нужен `NVIDIA Container Toolkit` на хосте).

Если Docker недоступен или проба не удалась — прежний fallback: чтение из
namespace текущего процесса и локальный ``nvidia-smi``.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PROC_RO = {"/proc": {"bind": "/host/proc", "mode": "ro"}}


def _read_os_pretty_from_text(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("PRETTY_NAME="):
            v = line.split("=", 1)[1].strip().strip('"')
            if v:
                return v
    return None


def _read_os_pretty() -> str:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
        v = _read_os_pretty_from_text(text)
        if v:
            return v
    except OSError:
        pass
    return platform.platform()


def _cpu_from_proc_text(text: str) -> tuple[str | None, int]:
    model: str | None = None
    processors = 0
    for line in text.splitlines():
        if line.startswith("model name") or line.startswith("Model name"):
            if model is None:
                model = line.split(":", 1)[1].strip()
        elif line.startswith("processor") or line.startswith("Processor"):
            processors += 1
    cores = processors or 0
    return model, cores


def _cpu_from_proc() -> tuple[str | None, int]:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            return _cpu_from_proc_text(f.read())
    except OSError:
        return None, os.cpu_count() or 0


def _meminfo_bytes_from_text(text: str) -> tuple[int | None, int | None]:
    total: int | None = None
    available: int | None = None
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2:
                total = int(parts[1]) * 1024
        elif line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2:
                available = int(parts[1]) * 1024
    return total, available


def _meminfo_bytes() -> tuple[int | None, int | None]:
    try:
        with open("/proc/meminfo", encoding="utf-8", errors="replace") as f:
            return _meminfo_bytes_from_text(f.read())
    except OSError:
        return None, None


def _kernel_from_proc_version_text(text: str) -> str | None:
    line = text.strip().splitlines()[0] if text.strip() else ""
    m = re.match(r"Linux version (\S+)", line)
    return m.group(1) if m else None


def _try_docker_client() -> Any | None:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001
        logger.debug("[host_info] docker unavailable: %s", exc)
        return None


def _docker_cat(
    client: Any,
    image: str,
    inner_path: str,
    *,
    volumes: dict[str, dict[str, str]] | None = None,
) -> str | None:
    import docker

    kw: dict[str, Any] = {
        "image": image,
        "command": ["cat", inner_path],
        "remove": True,
        "stdout": True,
        "stderr": True,
        "network_mode": "none",
    }
    if volumes:
        kw["volumes"] = volumes
    try:
        out = client.containers.run(**kw)
    except docker.errors.ImageNotFound:
        logger.warning("[host_info] probe image not found: %s", image)
        return None
    except docker.errors.ContainerError as exc:
        logger.info("[host_info] docker cat %s failed: %s", inner_path, exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.info("[host_info] docker run failed: %s", exc)
        return None

    if isinstance(out, bytes):
        return out.decode("utf-8", errors="replace")
    return str(out)


def _collect_host_via_docker_bind_mounts(
    client: Any,
    probe_image: str,
) -> dict[str, Any] | None:
    cpu_t = _docker_cat(client, probe_image, "/host/proc/cpuinfo", volumes=_PROC_RO)
    mem_t = _docker_cat(client, probe_image, "/host/proc/meminfo", volumes=_PROC_RO)
    ver_t = _docker_cat(client, probe_image, "/host/proc/version", volumes=_PROC_RO)
    if not cpu_t or not mem_t or not ver_t:
        return None

    os_t = _docker_cat(
        client,
        probe_image,
        "/host/os-release",
        volumes={"/etc/os-release": {"bind": "/host/os-release", "mode": "ro"}},
    )
    if not os_t:
        return None

    hn_t = _docker_cat(
        client,
        probe_image,
        "/host/hostname",
        volumes={"/etc/hostname": {"bind": "/host/hostname", "mode": "ro"}},
    )
    if not hn_t or not hn_t.strip():
        hn_t = _docker_cat(
            client,
            probe_image,
            "/host/proc/sys/kernel/hostname",
            volumes=_PROC_RO,
        )

    cpu_model, cpu_cores = _cpu_from_proc_text(cpu_t)
    mem_total, mem_avail = _meminfo_bytes_from_text(mem_t)
    kernel = _kernel_from_proc_version_text(ver_t) or platform.release()
    os_pretty = _read_os_pretty_from_text(os_t) if os_t else _read_os_pretty()
    hostname = hn_t.strip() if hn_t else None

    return {
        "hostname": hostname or None,
        "os_pretty": os_pretty,
        "kernel": kernel,
        "cpu_model": cpu_model,
        "cpu_logical_cores": cpu_cores or (os.cpu_count() or 0),
        "memory_total_bytes": mem_total,
        "memory_available_bytes": mem_avail,
        "_source": "docker_host_mounts",
    }


def _parse_nvidia_csv(stdout: str) -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    for line in stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 3:
            try:
                idx = int(parts[0])
            except ValueError:
                idx = len(gpus)
            gpus.append(
                {
                    "index": idx,
                    "name": parts[1],
                    "memory_total_mib": int(parts[2]) if parts[2].isdigit() else parts[2],
                }
            )
    return gpus


def _parse_driver_cuda_from_smi_text(text: str) -> tuple[str | None, str | None]:
    driver_ver: str | None = None
    cuda_ver: str | None = None
    for ln in text.splitlines():
        if "Driver Version:" in ln:
            m = re.search(r"Driver Version:\s*([\d.]+)", ln)
            if m:
                driver_ver = m.group(1)
            m = re.search(r"CUDA Version:\s*([\d.]+)", ln)
            if m:
                cuda_ver = m.group(1)
            break
    return driver_ver, cuda_ver


def _nvidia_smi_snapshot_local() -> dict[str, Any] | None:
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except FileNotFoundError:
        return {
            "smi_available": False,
            "note": "nvidia-smi не найден в контейнере web; ожидается опрос GPU через Docker на хосте.",
        }
    except subprocess.TimeoutExpired:
        return {"smi_available": False, "note": "nvidia-smi: таймаут."}

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()[:300]
        return {
            "smi_available": False,
            "note": err or "nvidia-smi завершился с ошибкой.",
        }

    gpus = _parse_nvidia_csv(r.stdout)
    driver_ver, cuda_ver = None, None
    try:
        r2 = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        if r2.stdout:
            driver_ver, cuda_ver = _parse_driver_cuda_from_smi_text(r2.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {
        "smi_available": True,
        "driver_version": driver_ver,
        "cuda_version": cuda_ver,
        "gpus": gpus,
        "source": "local",
    }


def _nvidia_smi_via_docker(client: Any, image: str) -> dict[str, Any] | None:
    import docker

    device_requests = [docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])]
    try:
        out_csv = client.containers.run(
            image,
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            remove=True,
            device_requests=device_requests,
            stdout=True,
            stderr=True,
            network_mode="none",
        )
    except docker.errors.ImageNotFound:
        logger.warning("[host_info] NVIDIA probe image missing: %s", image)
        return None
    except docker.errors.ContainerError as exc:
        err = str(exc)
        logger.info("[host_info] nvidia-smi docker: %s", err[:400])
        return {
            "smi_available": False,
            "note": (
                "GPU через Docker недоступен (нужен NVIDIA Container Toolkit на хосте и образ с nvidia-smi). "
                f"Детали: {err[:280]}"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        logger.info("[host_info] nvidia docker run failed: %s", exc)
        return None

    csv_text = (
        out_csv.decode("utf-8", errors="replace") if isinstance(out_csv, bytes) else str(out_csv)
    )
    gpus = _parse_nvidia_csv(csv_text)
    driver_ver, cuda_ver = None, None
    try:
        out_full = client.containers.run(
            image,
            ["nvidia-smi"],
            remove=True,
            device_requests=device_requests,
            stdout=True,
            stderr=True,
            network_mode="none",
        )
        full_txt = (
            out_full.decode("utf-8", errors="replace")
            if isinstance(out_full, bytes)
            else str(out_full)
        )
        driver_ver, cuda_ver = _parse_driver_cuda_from_smi_text(full_txt)
    except Exception:  # noqa: BLE001
        pass

    return {
        "smi_available": True,
        "driver_version": driver_ver,
        "cuda_version": cuda_ver,
        "gpus": gpus,
        "source": "docker_gpu",
    }


def collect_host_info(slgpu_root: Path) -> dict[str, Any]:
    settings = get_settings()
    client = _try_docker_client()

    host_partial: dict[str, Any] | None = None
    if client is not None:
        host_partial = _collect_host_via_docker_bind_mounts(
            client,
            settings.docker_host_probe_image,
        )

    if host_partial:
        hostname = host_partial["hostname"]
        os_pretty = host_partial["os_pretty"]
        kernel = host_partial["kernel"]
        cpu_model = host_partial["cpu_model"]
        cpu_cores = host_partial["cpu_logical_cores"]
        mem_total = host_partial["memory_total_bytes"]
        mem_avail = host_partial["memory_available_bytes"]
    else:
        cpu_model, cpu_cores = _cpu_from_proc()
        mem_total, mem_avail = _meminfo_bytes()
        os_pretty = _read_os_pretty()
        kernel = platform.release()
        hostname = platform.node() or None

    try:
        du = shutil.disk_usage(slgpu_root)
        disk_total, disk_used, disk_free = du.total, du.used, du.free
    except OSError:
        disk_total = disk_used = disk_free = 0

    docker_nv = None
    if client is not None:
        try:
            from app.services.stack_config import (
                host_gpu_docker_probe_enabled,
                nvidia_smi_docker_image_for_stack,
                sync_merged_flat,
            )

            _merged = sync_merged_flat()
        except Exception:  # noqa: BLE001
            _merged = {}
        if host_gpu_docker_probe_enabled(_merged):
            docker_nv = _nvidia_smi_via_docker(
                client, nvidia_smi_docker_image_for_stack(_merged)
            )
    local_nv = _nvidia_smi_snapshot_local()

    if docker_nv and docker_nv.get("smi_available"):
        nvidia = docker_nv
    elif local_nv and local_nv.get("smi_available"):
        nvidia = local_nv
    elif docker_nv:
        nvidia = docker_nv
    else:
        nvidia = local_nv or {"smi_available": False, "note": "Не удалось опросить NVIDIA."}

    return {
        "hostname": hostname,
        "os_pretty": os_pretty,
        "kernel": kernel,
        "arch": platform.machine(),
        "cpu_model": cpu_model,
        "cpu_logical_cores": cpu_cores,
        "memory_total_bytes": mem_total,
        "memory_available_bytes": mem_avail,
        "disk_slgpu_path": str(slgpu_root.resolve()),
        "disk_slgpu_total_bytes": disk_total,
        "disk_slgpu_used_bytes": disk_used,
        "disk_slgpu_free_bytes": disk_free,
        "nvidia": nvidia,
    }
