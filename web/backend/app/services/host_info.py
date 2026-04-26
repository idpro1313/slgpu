"""Host / container-visible hardware and OS snapshot for the dashboard.

Читает `/proc`, диск под `slgpu_root`, опционально `nvidia-smi` (если драйвер доступен
в окружении контейнера — см. NVIDIA Container Toolkit и опциональный GPU для slgpu-web).
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

logger = logging.getLogger(__name__)


def _read_os_pretty() -> str:
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("PRETTY_NAME="):
                v = line.split("=", 1)[1].strip().strip('"')
                if v:
                    return v
    except OSError:
        pass
    return platform.platform()


def _cpu_from_proc() -> tuple[str | None, int]:
    model: str | None = None
    processors = 0
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("model name") or line.startswith("Model name"):
                    if model is None:
                        model = line.split(":", 1)[1].strip()
                elif line.startswith("processor") or line.startswith("Processor"):
                    processors += 1
    except OSError:
        pass
    cores = processors or (os.cpu_count() or 0)
    return model, cores


def _meminfo_bytes() -> tuple[int | None, int | None]:
    total: int | None = None
    available: int | None = None
    try:
        with open("/proc/meminfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        total = int(parts[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        available = int(parts[1]) * 1024
    except OSError:
        pass
    return total, available


def _nvidia_smi_snapshot() -> dict[str, Any] | None:
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
            "note": "nvidia-smi не найден в контейнере (установите драйвер NVIDIA в образ или подключите GPU к slgpu-web).",
        }
    except subprocess.TimeoutExpired:
        return {"smi_available": False, "note": "nvidia-smi: таймаут."}

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()[:300]
        return {
            "smi_available": False,
            "note": err or "nvidia-smi завершился с ошибкой.",
        }

    gpus: list[dict[str, Any]] = []
    for line in r.stdout.strip().splitlines():
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

    driver_ver: str | None = None
    cuda_ver: str | None = None
    try:
        r2 = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        if r2.stdout:
            for ln in r2.stdout.splitlines():
                if "Driver Version:" in ln:
                    m = re.search(r"Driver Version:\s*([\d.]+)", ln)
                    if m:
                        driver_ver = m.group(1)
                    m = re.search(r"CUDA Version:\s*([\d.]+)", ln)
                    if m:
                        cuda_ver = m.group(1)
                    break
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {
        "smi_available": True,
        "driver_version": driver_ver,
        "cuda_version": cuda_ver,
        "gpus": gpus,
    }


def collect_host_info(slgpu_root: Path) -> dict[str, Any]:
    cpu_model, cpu_cores = _cpu_from_proc()
    mem_total, mem_avail = _meminfo_bytes()
    try:
        du = shutil.disk_usage(slgpu_root)
        disk_total, disk_used, disk_free = du.total, du.used, du.free
    except OSError:
        disk_total = disk_used = disk_free = 0

    nvidia = _nvidia_smi_snapshot()

    return {
        "hostname": platform.node() or None,
        "os_pretty": _read_os_pretty(),
        "kernel": platform.release(),
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
