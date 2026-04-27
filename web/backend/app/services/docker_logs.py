"""Read-only Docker container list and log tail for UI (not slot-specific)."""

from __future__ import annotations

import re
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
