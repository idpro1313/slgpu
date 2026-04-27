"""Async `docker compose` helpers (no bash `./slgpu` for web jobs)."""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

from app.services.job_log import append_job_log


def _clean_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/sbin:/usr/bin:/sbin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
        "USER": os.environ.get("USER", "root"),
        "DOCKER_HOST": os.environ.get("DOCKER_HOST", ""),
        "DOCKER_CONTEXT": os.environ.get("DOCKER_CONTEXT", ""),
        "SSH_AUTH_SOCK": os.environ.get("SSH_AUTH_SOCK", ""),
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", ""),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }


async def compose_llm_env(
    root: Path,
    interp_env_file: Path,
    *compose_args: str,
) -> tuple[int, str, str]:
    """Match scripts/cmd_up.sh ``compose_llm_env`` (env -i + --env-file)."""

    env = _clean_env()
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "--project-directory",
        str(root),
        "--env-file",
        str(interp_env_file),
        *compose_args,
        cwd=str(root),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    return proc.returncode or 0, out_b.decode("utf-8", errors="replace"), err_b.decode(
        "utf-8", errors="replace"
    )


async def compose_inherit_env(
    root: Path,
    *compose_args: str,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "--project-directory",
        str(root),
        *compose_args,
        cwd=str(root),
        env=_clean_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    return proc.returncode or 0, out_b.decode("utf-8", errors="replace"), err_b.decode(
        "utf-8", errors="replace"
    )


async def compose_with_env_file(
    root: Path,
    main_env_file: Path,
    *compose_args: str,
) -> tuple[int, str, str]:
    """``docker compose --project-directory <root> --env-file <main> ...``.

    Do not inherit the web container/host environment here: Docker Compose gives
    process env higher precedence than ``--env-file`` during interpolation, which
    can silently override values that were just written from SQLite.
    """

    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "--project-directory",
        str(root),
        "--env-file",
        str(main_env_file),
        *compose_args,
        cwd=str(root),
        env=_clean_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    return proc.returncode or 0, out_b.decode("utf-8", errors="replace"), err_b.decode(
        "utf-8", errors="replace"
    )


async def compose_monitoring(
    root: Path,
    main_env_file: Path,
    *compose_args: str,
) -> tuple[int, str, str]:
    return await compose_with_env_file(root, main_env_file, *compose_args)


async def docker_network_inspect(name: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "network",
        "inspect",
        name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=None,
    )
    out_b, err_b = await proc.communicate()
    return proc.returncode or 0, out_b.decode("utf-8", errors="replace"), err_b.decode(
        "utf-8", errors="replace"
    )


async def docker_network_create_slgpu() -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "network",
        "create",
        "--driver",
        "bridge",
        "--label",
        "com.docker.compose.project=slgpu",
        "--label",
        "com.docker.compose.network=slgpu",
        "slgpu",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_clean_env(),
    )
    out_b, err_b = await proc.communicate()
    return proc.returncode or 0, out_b.decode("utf-8", errors="replace"), err_b.decode(
        "utf-8", errors="replace"
    )


async def ensure_slgpu_network(
    log: list[str], log_lock: threading.Lock | None = None
) -> None:
    code, out, err = await docker_network_inspect("slgpu")
    if code == 0:
        # Labels must match (simplified check via inspect json would be heavy; trust if exists)
        append_job_log(log, log_lock, "[network] slgpu exists")
        return
    c2, _, e2 = await docker_network_create_slgpu()
    if c2 != 0:
        raise RuntimeError(f"docker network create slgpu failed: {e2}")
    append_job_log(log, log_lock, "[network] created slgpu")


async def run_subprocess_logged(
    argv: list[str],
    cwd: Path | None,
    env: dict[str, str] | None,
    log: list[str],
    log_lock: threading.Lock | None = None,
) -> int:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        append_job_log(
            log,
            log_lock,
            line.decode("utf-8", errors="replace").rstrip(),
        )
    return await proc.wait()
