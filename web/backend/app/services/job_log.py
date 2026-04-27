"""Thread-safe append for background job logs (native stack, slot docker, etc.)."""

from __future__ import annotations

import threading


def append_job_log(log: list[str], lock: threading.Lock | None, line: str) -> None:
    """Append one line; ``lock`` must be shared with concurrent readers (UI poll flush)."""

    if lock is not None:
        with lock:
            log.append(line)
    else:
        log.append(line)
