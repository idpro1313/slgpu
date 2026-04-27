"""Read-only Docker container list and log tail for UI (not slot-specific)."""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Literal

from app.services.docker_client import ContainerSummary, get_docker_inspector

_SCOPE_SLGPU = "slgpu"
_SCOPE_ALL = "all"
_REF_RE = re.compile(r"^[\w][\w.@-]{0,200}$")


def _match_slgpu_stack(c: ContainerSummary) -> bool:
    n = (c.name or "").lower()
    if n.startswith("slgpu"):
        return True
    proj = (c.project or "").lower()
    if "slgpu" in proj:
        return True
    slot = (c.labels or {}).get("com.develonica.slgpu.slot")
    if slot:
        return True
    return False


def list_containers(
    scope: Literal["slgpu", "all"] = "slgpu",
) -> tuple[bool, str, list[ContainerSummary]]:
    """Return (docker_available, scope, rows)."""

    insp = get_docker_inspector()
    if not insp.is_available:
        return False, scope, []
    raw = insp.list_all_containers()
    if scope == _SCOPE_ALL:
        rows = sorted(raw, key=lambda x: (x.name or "").lower())
        return True, scope, rows
    rows = sorted(
        [c for c in raw if _match_slgpu_stack(c)],
        key=lambda x: (x.name or "").lower(),
    )
    return True, scope, rows


def tail_container_logs(
    ref: str, tail: int = 400
) -> tuple[bool, ContainerSummary | None, str, int]:
    """Return (docker_available, container_or_none, log_text, bounded_tail)."""

    bounded = max(1, min(tail, 5000))
    insp = get_docker_inspector()
    if not insp.is_available:
        return False, None, "", bounded
    csum = insp.resolve_container(ref)
    if csum is None:
        return True, None, "", bounded
    text = insp.tail_logs(csum.id, tail=bounded)
    return True, csum, text, bounded


def validate_container_ref(raw: str) -> str:
    s = (raw or "").strip()
    if not s or len(s) > 200:
        raise ValueError("invalid container reference")
    if not _REF_RE.match(s):
        raise ValueError("invalid container reference")
    return s


def collect_engine_events_tail(since_sec: int, max_events: int) -> tuple[bool, str]:
    """Tail of Docker Engine ``/events`` (same socket as контейнеры)."""
    bounded_n = max(1, min(max_events, 10_000))
    insp = get_docker_inspector()
    if not insp.is_available:
        return False, ""
    return True, insp.collect_engine_events_tail(since_sec, bounded_n)


def tail_daemon_journal(lines: int) -> tuple[str, str | None]:
    """
    Best-effort ``journalctl -u docker`` (linux+systemd). From web-контейнера часто недоступно:
    тогда возвращаем пустой текст и подсказку.
    """
    n = max(1, min(lines, 2000))
    if not shutil.which("journalctl"):
        return (
            "",
            "journalctl недоступен в этой среде. Логи демона dockerd смотрите на хосте: "
            "`journalctl -u docker.service -n 200 --no-pager` (или `-u docker`).",
        )
    cmd = [
        "journalctl",
        "-u",
        "docker.service",
        "-n",
        str(n),
        "--no-pager",
        "-o",
        "short-iso",
    ]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "", f"не удалось выполнить journalctl: {exc}"
    if r.returncode == 0:
        out1 = (r.stdout or "").rstrip()
        if out1:
            return out1 + "\n", None
    # Try unit name "docker" (older / alternate)
    cmd2 = [
        "journalctl",
        "-u",
        "docker",
        "-n",
        str(n),
        "--no-pager",
        "-o",
        "short-iso",
    ]
    try:
        r2 = subprocess.run(
            cmd2,
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "", f"не удалось выполнить journalctl: {exc}"
    if r2.returncode == 0:
        out2 = (r2.stdout or "").rstrip()
        if out2:
            return out2 + "\n", None
    if r.returncode == 0 or r2.returncode == 0:
        return "", None
    err = (r.stderr or r2.stderr or "").strip() or (r.stdout or r2.stdout or "").strip()
    detail = err[:800] if err else "нет вывода"
    return (
        "",
        "journalctl не вернул лог docker (часто так в контейнере без доступа к journal хоста). "
        f"Деталь: {detail}",
    )
