"""Native stack operations for web (docker compose / docker API), no `./slgpu` subprocess."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import threading
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import docker
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.job import Job, JobStatus
from app.models.preset import Preset
from app.models.slot import RunStatus
from app.models.slot import EngineSlot
from app.services import compose_exec
from app.services.env_key_aliases import coalesce_str, monitoring_image
from app.services.llm_env import merge_llm_stack_env, parse_gpu_mask
from app.services.slot_runtime import (
    internal_api_port_for,
    run_slot_docker,
    slot_container_name,
    stop_containers_for_slot_key_sync,
)
from app.services.stack_config import (
    sync_merged_flat,
    write_langfuse_litellm_env,
    write_llm_interp_env,
)
from app.services.job_log import append_job_log
from app.services.slgpu_cli import CliCommand

logger = logging.getLogger(__name__)


def _snapshot_log(log: list[str], lock: threading.Lock) -> list[str]:
    with lock:
        return list(log)


async def _flush_native_job_stream(
    job_id: int, log: list[str], lock: threading.Lock, job_kind: str
) -> None:
    """Persist tail of in-progress log so UI poll shows docker pull / compose output."""

    lines = _snapshot_log(log, lock)
    text = "\n".join(lines)
    tail = text[-8000:] if text else None
    last = next((s for s in reversed(lines) if s.strip()), None)
    try:
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
                return
            if tail:
                job.stdout_tail = tail
            # HF pull updates ``message`` via tqdm; do not overwrite.
            if last and job_kind != "native.model.pull":
                job.message = last[:2000]
    except Exception:  # noqa: BLE001
        logger.debug("[native_jobs][_flush_native_job_stream] failed", exc_info=True)


async def _native_log_poller(
    job_id: int,
    log: list[str],
    lock: threading.Lock,
    stop: asyncio.Event,
    job_kind: str,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.2)
            return
        except TimeoutError:
            await _flush_native_job_stream(job_id, log, lock, job_kind)

_LL_YML = "docker/docker-compose.llm.yml"
_MON_YML = "docker/docker-compose.monitoring.yml"

_CONFIG_FILES: list[tuple[str, str]] = [
    ("configs/monitoring/loki/loki-config.yaml", "configs/monitoring/loki/loki-config.yaml"),
    ("configs/monitoring/promtail/promtail-config.yml", "configs/monitoring/promtail/promtail-config.yml"),
    ("configs/monitoring/prometheus/prometheus.yml", "configs/monitoring/prometheus/prometheus.yml"),
    ("configs/monitoring/prometheus/prometheus-alerts.yml", "configs/monitoring/prometheus/prometheus-alerts.yml"),
    ("configs/monitoring/langfuse/minio-bucket-init.sh", "configs/monitoring/langfuse/minio-bucket-init.sh"),
    ("configs/monitoring/litellm/init-litellm-db.sh", "configs/monitoring/litellm/init-litellm-db.sh"),
    ("configs/monitoring/litellm/litellm-entrypoint.sh", "configs/monitoring/litellm/litellm-entrypoint.sh"),
    ("configs/monitoring/litellm/config.yaml", "configs/monitoring/litellm/config.yaml"),
]


async def _ensure_config_files_async(
    root: Path, log: list[str], log_lock: threading.Lock
) -> None:
    import subprocess

    for rel, gitrel in _CONFIG_FILES:
        abs_path = (root / rel).resolve()
        if abs_path.is_dir():
            append_job_log(log, log_lock, f"[config] removing dir {rel}")
            shutil.rmtree(abs_path)
        if abs_path.is_file():
            continue
        if (root / ".git").exists():
            r = subprocess.run(
                ["git", "checkout", "--", gitrel],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )
            if r.returncode == 0:
                append_job_log(log, log_lock, f"[config] restored {gitrel}")
        if not abs_path.is_file():
            raise RuntimeError(f"missing {gitrel}")


def _mkdir_data_dirs(
    root: Path, merged: dict[str, str], log: list[str], log_lock: threading.Lock
) -> None:
    keys = (
        "MODELS_DIR",
        "PRESETS_DIR",
        "WEB_DATA_DIR",
        "PROMETHEUS_DATA_DIR",
        "GRAFANA_DATA_DIR",
        "LOKI_DATA_DIR",
        "PROMTAIL_DATA_DIR",
        "LANGFUSE_POSTGRES_DATA_DIR",
        "LANGFUSE_CLICKHOUSE_DATA_DIR",
        "LANGFUSE_CLICKHOUSE_LOGS_DIR",
        "LANGFUSE_MINIO_DATA_DIR",
        "LANGFUSE_REDIS_DATA_DIR",
    )
    for k in keys:
        v = merged.get(k)
        if not v:
            continue
        p = Path(v)
        if not p.is_absolute():
            p = (root / v[2:] if v.startswith("./") else root / v).resolve()
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            append_job_log(log, log_lock, f"[mkdir] {k}={p} err={exc}")


def _write_tmp_monitoring_env(merged: dict[str, str]) -> Path:
    # Ephemeral file for a single `docker compose --env-file` call. Must not live under
    # repo `data/`: on the host that tree is often root-owned or chowned to another
    # UID than the web app, which causes EACCES on mkstemp.
    fd, name = tempfile.mkstemp(prefix="slgpu-mon-", suffix=".env")
    os.close(fd)
    p = Path(name)
    body = "\n".join(f"{k}={v}" for k, v in sorted(merged.items()) if v is not None) + "\n"
    p.write_text(body, encoding="utf-8")
    os.chmod(p, 0o600)
    return p


async def _finalize_native_job(
    job_id: int,
    command: CliCommand,
    exit_code: int,
    lines: list[str],
) -> None:
    text = "\n".join(lines)
    async with session_scope() as session:
        job = await session.get(Job, job_id)
        if job is None:
            return
        if job.status == JobStatus.CANCELLED:
            return
        job.exit_code = exit_code
        job.finished_at = datetime.now(timezone.utc)
        job.status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
        job.stdout_tail = text[-8000:] if text else None
        job.stderr_tail = None
        if exit_code != 0:
            job.message = f"exit={exit_code}"


async def handle_native_job(job_id: int, command: CliCommand, args: dict[str, Any]) -> None:
    log: list[str] = []
    log_lock = threading.Lock()
    stop = asyncio.Event()
    poll_task = asyncio.create_task(
        _native_log_poller(job_id, log, log_lock, stop, command.kind)
    )
    code = 0
    try:
        if command.kind == "native.slot.up":
            code = await _native_slot_up(args, log, log_lock)
        elif command.kind == "native.slot.down":
            code = await _native_slot_down(args, log, log_lock)
        elif command.kind == "native.slot.restart":
            code = await _native_slot_restart(args, log, log_lock)
        elif command.kind == "native.monitoring.up":
            code = await _native_monitoring_up(log, log_lock)
        elif command.kind == "native.monitoring.down":
            code = await _native_monitoring_down(log, log_lock)
        elif command.kind == "native.monitoring.restart":
            code = await _native_monitoring_restart(log, log_lock)
        elif command.kind == "native.monitoring.fix-perms":
            code = await _native_fix_perms(log, log_lock)
        elif command.kind == "native.model.pull":
            code = await _native_model_pull(job_id, args, log, log_lock)
        elif command.kind == "native.bench.scenario":
            code = await _native_bench_scenario(args, log, log_lock)
        elif command.kind == "native.bench.load":
            code = await _native_bench_load(args, log, log_lock)
        else:
            append_job_log(log, log_lock, f"[native] unknown kind {command.kind}")
            code = 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("[native_jobs][handle_native_job][BLOCK_FAILURE]")
        append_job_log(log, log_lock, f"[native] error: {exc}")
        code = 1
    finally:
        stop.set()
        try:
            await asyncio.wait_for(poll_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        await _flush_native_job_stream(job_id, log, log_lock, command.kind)
    await _finalize_native_job(job_id, command, code, _snapshot_log(log, log_lock))


def _list_ints_from_args(raw: Any) -> list[int] | None:
    if not isinstance(raw, list) or not raw:
        return None
    return [int(x) for x in raw]


async def _resolve_gpu_indices(
    preset_name: str,
    tp_arg: int | None,
    merged: dict[str, str],
    log: list[str],
    log_lock: threading.Lock,
) -> list[int]:
    t_default = 8
    try:
        t_default = int(merged.get("TP", "8"))
    except ValueError:
        t_default = 8
    async with session_scope() as s:
        r = await s.execute(select(Preset).where(Preset.name == preset_name))
        pr = r.scalar_one_or_none()
    tpi = int(tp_arg) if tp_arg is not None else (int(pr.tp) if pr and pr.tp is not None else t_default)
    if pr and pr.gpu_mask and str(pr.gpu_mask).strip():
        parsed = parse_gpu_mask(pr.gpu_mask)
        if parsed:
            if len(parsed) == tpi:
                return parsed
            append_job_log(
                log,
                log_lock,
                f"[slot] gpu_mask len {len(parsed)} != tp {tpi}, using 0..{tpi-1}",
            )
    return list(range(tpi))


def _default_host_port(merged: dict[str, str], engine: str, port_arg: Any) -> int:
    if port_arg is not None:
        return int(port_arg)
    if engine == "vllm":
        return int(merged.get("LLM_API_PORT", "8111"))
    return int(merged.get("LLM_API_PORT", merged.get("LLM_API_PORT_SGLANG", "8222")))


async def _db_mark_slot_running(
    slot_key: str,
    engine: str,
    preset: str,
    host_api_port: int,
    internal_port: int,
    gpu_indices: list[int],
    tp: int,
    container_id: str,
    cname: str,
    hf_id: str | None,
) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    async with session_scope() as s:
        r = await s.execute(select(EngineSlot).where(EngineSlot.slot_key == slot_key))
        row = r.scalar_one_or_none()
        if row is None:
            logger.error(
                "[native_jobs][_db_mark_slot_running][BLOCK_MISSING_ROW] slot_key=%s",
                slot_key,
            )
            return
        row.engine = engine
        row.preset_name = preset
        row.hf_id = hf_id
        row.tp = tp
        row.gpu_indices = ",".join(str(i) for i in gpu_indices)
        row.host_api_port = host_api_port
        row.internal_api_port = internal_port
        row.container_id = container_id
        row.container_name = cname
        row.desired_status = RunStatus.RUNNING
        row.observed_status = RunStatus.RUNNING
        row.last_error = None
        row.stopped_at = None
        row.started_at = now


async def _db_mark_slot_failed(slot_key: str, err: str | None) -> None:
    async with session_scope() as s:
        r = await s.execute(select(EngineSlot).where(EngineSlot.slot_key == slot_key))
        row = r.scalar_one_or_none()
        if row is None:
            return
        row.desired_status = RunStatus.FAILED
        row.observed_status = RunStatus.FAILED
        row.last_error = (err or "unknown")[:2000]
        if row.stopped_at is None:
            from datetime import datetime, timezone

            row.stopped_at = datetime.now(timezone.utc)


async def _db_mark_stopped_by_key(slot_key: str) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    async with session_scope() as s:
        r = await s.execute(select(EngineSlot).where(EngineSlot.slot_key == slot_key))
        row = r.scalar_one_or_none()
        if row is None:
            return
        row.desired_status = RunStatus.STOPPED
        row.observed_status = RunStatus.STOPPED
        row.stopped_at = now
        row.container_id = None
        row.container_name = None


async def _native_slot_up(args: dict[str, Any], log: list[str], log_lock: threading.Lock) -> int:
    """Docker-py slot: ``gpu_indices`` in args, or from preset/TP; ``host_api_port`` required for slot API."""
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    (root / "data").mkdir(parents=True, exist_ok=True)
    _mkdir_data_dirs(root, merged, log, log_lock)

    slot_key = str(args.get("slot_key", "default"))
    engine = str(args.get("engine", "vllm"))
    preset = str(args.get("preset", ""))
    port_arg = args.get("port")
    tp = args.get("tp")
    tp_i = int(tp) if tp is not None else None
    if "host_api_port" in args and args.get("host_api_port") is not None:
        host_api_port = int(args["host_api_port"])
    else:
        host_api_port = _default_host_port(merged, engine, port_arg)

    gpu_indices: list[int] | None = _list_ints_from_args(args.get("gpu_indices"))
    if gpu_indices is None:
        gpu_indices = await _resolve_gpu_indices(preset, tp_i, merged, log, log_lock)
    t_eff = len(gpu_indices)
    if tp_i is not None and t_eff != tp_i:
        append_job_log(
            log,
            log_lock,
            f"[slot] override TP to match gpu list: {t_eff} (arg was {tp_i})",
        )
    m = merge_llm_stack_env(root, dict(merged), preset, engine, None, t_eff, gpu_indices)
    append_job_log(
        log,
        log_lock,
        f"[slot] up {slot_key} {engine} preset={preset} port={host_api_port} "
        f"TP={m.get('TP')} GPUs={m.get('NVIDIA_VISIBLE_DEVICES')}",
    )

    async with session_scope() as s:
        prq = await s.execute(select(Preset).where(Preset.name == preset))
        pr = prq.scalar_one_or_none()
    hf_id = pr.hf_id if pr else None
    int_port = internal_api_port_for(engine)

    res = await run_slot_docker(
        root=root,
        slot_key=slot_key,
        engine=engine,
        preset=preset,
        host_api_port=host_api_port,
        gpu_indices=gpu_indices,
        tp=t_eff,
        log=log,
        log_lock=log_lock,
    )
    if not res.get("ok"):
        err = res.get("error", "start failed")
        append_job_log(log, log_lock, f"[slot] {err}")
        await _db_mark_slot_failed(slot_key, str(err))
        return 1
    cid = str(res.get("container_id") or "")
    cname = str(res.get("container_name") or slot_container_name(engine, slot_key))
    await _db_mark_slot_running(
        slot_key,
        engine,
        preset,
        host_api_port,
        int_port,
        gpu_indices,
        t_eff,
        cid,
        cname,
        hf_id,
    )
    return 0


async def _native_slot_down(args: dict[str, Any], log: list[str], log_lock: threading.Lock) -> int:
    slot_key = str(args.get("slot_key", "default"))
    code = await asyncio.to_thread(
        stop_containers_for_slot_key_sync, slot_key, log, log_lock
    )
    await _db_mark_stopped_by_key(slot_key)
    return int(code)


async def _native_slot_restart(args: dict[str, Any], log: list[str], log_lock: threading.Lock) -> int:
    slot_key = str(args.get("slot_key", "default"))
    preset = str(args.get("preset", ""))
    async with session_scope() as s:
        r = await s.execute(select(EngineSlot).where(EngineSlot.slot_key == slot_key))
        sl = r.scalar_one_or_none()
    if not sl:
        append_job_log(log, log_lock, f"[slot] restart: unknown {slot_key}")
        return 1
    host_api_port = int(
        args.get("host_api_port")
        or sl.host_api_port
        or _default_host_port(sync_merged_flat(), sl.engine, None)
    )
    tp = args.get("tp", sl.tp)
    g = _list_ints_from_args(args.get("gpu_indices"))
    if g is None and sl.gpu_indices:
        g = [int(x) for x in str(sl.gpu_indices).split(",") if x.strip().isdigit()]
    d_args = {"slot_key": slot_key, "engine": sl.engine}
    await _native_slot_down(d_args, log, log_lock)
    up: dict[str, Any] = {
        "slot_key": slot_key,
        "engine": sl.engine,
        "preset": preset or (sl.preset_name or ""),
        "host_api_port": host_api_port,
        "tp": tp,
    }
    if g:
        up["gpu_indices"] = g
    return await _native_slot_up(up, log, log_lock)


async def _monitoring_bootstrap(
    root: Path, env_file: Path, log: list[str], log_lock: threading.Lock
) -> None:
    bootstrap_dir = root / "data" / "monitoring" / ".bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)

    async def _one(svc: str, marker_name: str) -> None:
        marker = bootstrap_dir / marker_name
        if marker.is_file():
            append_job_log(log, log_lock, f"[bootstrap] skip {svc} (done)")
            return
        c, o, e = await compose_exec.compose_monitoring(
            root, env_file, "-f", _MON_YML, "--profile", "bootstrap", "rm", "-f", "-s", "-v", svc
        )
        if o.strip():
            append_job_log(log, log_lock, o.strip())
        if e.strip():
            append_job_log(log, log_lock, e.strip())
        c, o, e = await compose_exec.compose_monitoring(
            root,
            env_file,
            "-f",
            _MON_YML,
            "--profile",
            "bootstrap",
            "up",
            "--abort-on-container-exit",
            "--exit-code-from",
            svc,
            svc,
        )
        append_job_log(log, log_lock, o.strip())
        if e.strip():
            append_job_log(log, log_lock, e.strip())
        if c != 0:
            raise RuntimeError(f"bootstrap {svc} failed exit={c}")
        c2, o2, e2 = await compose_exec.compose_monitoring(
            root, env_file, "-f", _MON_YML, "--profile", "bootstrap", "rm", "-f", "-s", "-v", svc
        )
        if o2.strip():
            append_job_log(log, log_lock, o2.strip())
        if e2.strip():
            append_job_log(log, log_lock, e2.strip())
        marker.touch()

    await _one("minio-bucket-init", "minio-bucket-init.done")
    await _one("litellm-pg-init", "litellm-pg-init.done")


async def _native_monitoring_up(log: list[str], log_lock: threading.Lock) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    write_langfuse_litellm_env(
        root,
        {k: merged[k] for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") if k in merged},
    )
    _mkdir_data_dirs(root, merged, log, log_lock)
    await _ensure_config_files_async(root, log, log_lock)
    env_file = _write_tmp_monitoring_env(merged)
    try:
        await compose_exec.ensure_slgpu_network(log, log_lock)
        await _monitoring_bootstrap(root, env_file, log, log_lock)
        c, o, e = await compose_exec.compose_monitoring(root, env_file, "-f", _MON_YML, "up", "-d")
        append_job_log(log, log_lock, o.strip())
        if e.strip():
            append_job_log(log, log_lock, e.strip())
        return 0 if c == 0 else c
    finally:
        env_file.unlink(missing_ok=True)


async def _native_monitoring_down(log: list[str], log_lock: threading.Lock) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    env_file = _write_tmp_monitoring_env(merged)
    try:
        c, o, e = await compose_exec.compose_monitoring(root, env_file, "-f", _MON_YML, "down")
        append_job_log(log, log_lock, o + e)
        return 0 if c == 0 else c
    finally:
        env_file.unlink(missing_ok=True)


async def _native_monitoring_restart(log: list[str], log_lock: threading.Lock) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    write_langfuse_litellm_env(
        root,
        {
            k: merged[k]
            for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
            if k in merged
        },
    )
    await _ensure_config_files_async(root, log, log_lock)
    env_file = _write_tmp_monitoring_env(merged)
    try:
        await compose_exec.ensure_slgpu_network(log, log_lock)
        c, o, e = await compose_exec.compose_monitoring(
            root, env_file, "-f", _MON_YML, "up", "-d", "--force-recreate"
        )
        append_job_log(log, log_lock, o + e)
        return 0 if c == 0 else c
    finally:
        env_file.unlink(missing_ok=True)


def _id_from_image(
    client: docker.DockerClient, image: str, log: list[str], log_lock: threading.Lock
) -> tuple[str, str]:
    try:
        out = client.containers.run(
            image,
            entrypoint=["sh", "-c", "id -u && id -g"],
            remove=True,
            stdout=True,
            stderr=True,
        )
        lines = out.decode("utf-8").strip().split()
        if len(lines) >= 2:
            return lines[0], lines[1]
    except docker.errors.DockerException as exc:
        append_job_log(log, log_lock, f"[fix-perms] id_from {image}: {exc}")
    return "999", "999"


def _chown_dir(
    client: docker.DockerClient,
    host_path: Path,
    uid: str,
    gid: str,
    log: list[str],
    log_lock: threading.Lock,
) -> None:
    if not str(host_path):
        return
    parent = host_path.parent
    base = host_path.name
    try:
        client.containers.run(
            "alpine:latest",
            entrypoint=[
                "sh",
                "-c",
                f"mkdir -p '/p/{base}' && chown -R {uid}:{gid} '/p/{base}'",
            ],
            user="0:0",
            volumes={str(parent): {"bind": "/p", "mode": "rw"}},
            remove=True,
        )
    except docker.errors.DockerException as exc:
        append_job_log(log, log_lock, f"[fix-perms] chown {host_path}: {exc}")


async def _native_fix_perms(log: list[str], log_lock: threading.Lock) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()

    def path_for(key: str, default_rel: str) -> Path:
        v = merged.get(key, "")
        if not v:
            p = root / default_rel
        elif v.startswith("./"):
            p = (root / v[2:]).resolve()
        else:
            p = Path(v)
            if not p.is_absolute():
                p = (root / v).resolve()
        return p

    gdir = path_for("GRAFANA_DATA_DIR", "data/monitoring/grafana")
    pdir = path_for("PROMETHEUS_DATA_DIR", "data/monitoring/prometheus")
    ldir = path_for("LOKI_DATA_DIR", "data/monitoring/loki")
    ptdir = path_for("PROMTAIL_DATA_DIR", "data/monitoring/promtail")
    lf_p = path_for("LANGFUSE_POSTGRES_DATA_DIR", "data/monitoring/langfuse/postgres")
    lf_c = path_for("LANGFUSE_CLICKHOUSE_DATA_DIR", "data/monitoring/langfuse/clickhouse")
    lf_cl = path_for("LANGFUSE_CLICKHOUSE_LOGS_DIR", "data/monitoring/langfuse/clickhouse-logs")
    lf_m = path_for("LANGFUSE_MINIO_DATA_DIR", "data/monitoring/langfuse/minio")
    lf_r = path_for("LANGFUSE_REDIS_DATA_DIR", "data/monitoring/langfuse/redis")

    gimg = monitoring_image(merged, "GRAFANA_IMAGE")
    pimg = monitoring_image(merged, "PROMETHEUS_IMAGE")
    limg = monitoring_image(merged, "LOKI_IMAGE")
    pgimg = monitoring_image(merged, "LANGFUSE_POSTGRES_IMAGE")
    minioimg = monitoring_image(merged, "MINIO_IMAGE")
    redisimg = monitoring_image(merged, "LANGFUSE_REDIS_IMAGE")

    def run_sync() -> None:
        client = docker.from_env()
        gu, gg = _id_from_image(client, gimg, log, log_lock)
        pu, pg = _id_from_image(client, pimg, log, log_lock)
        lu, lg = _id_from_image(client, limg, log, log_lock)
        if lu == "999":
            lu, lg = "10001", "10001"
        pg_u, pg_g = _id_from_image(client, pgimg, log, log_lock)
        ru, rg = _id_from_image(client, redisimg, log, log_lock)
        mu, mg = _id_from_image(client, minioimg, log, log_lock)

        _chown_dir(client, gdir, gu, gg, log, log_lock)
        _chown_dir(client, pdir, pu, pg, log, log_lock)
        _chown_dir(client, ldir, lu, lg, log, log_lock)
        _chown_dir(client, ptdir, "0", "0", log, log_lock)
        _chown_dir(client, lf_p, pg_u, pg_g, log, log_lock)
        _chown_dir(client, lf_c, "101", "101", log, log_lock)
        _chown_dir(client, lf_cl, "101", "101", log, log_lock)
        _chown_dir(client, lf_m, mu, mg, log, log_lock)
        _chown_dir(client, lf_r, ru, rg, log, log_lock)

    await asyncio.to_thread(run_sync)
    append_job_log(log, log_lock, "[fix-perms] done")
    return 0


def _try_make_job_tqdm(
    lock: threading.Lock,
    state: dict[str, Any],
) -> type | None:
    try:
        from tqdm.auto import tqdm as tqdm_base
    except ImportError:
        return None

    class JobTqdm(tqdm_base):  # type: ignore[misc,valid-type]
        def update(self, n: int = 1) -> bool | None:
            r = super().update(n)
            with lock:
                state["n"] = int(self.n)
                state["total"] = self.total
                state["desc"] = str(getattr(self, "desc", "") or "")
            return r

    return JobTqdm


async def _flush_pull_progress(job_id: int, lock: threading.Lock, state: dict[str, Any]) -> None:
    with lock:
        n = int(state.get("n") or 0)
        total = state.get("total")
        desc = str(state.get("desc") or "").strip()
    pct: float | None = None
    if isinstance(total, (int, float)) and float(total) > 0:
        pct = min(1.0, float(n) / float(total))
    msg: str | None = desc[:2000] if desc else None
    if not msg and isinstance(total, (int, float)) and float(total) > 0:
        msg = f"{n} / {int(total)}"
    try:
        async with session_scope() as session:
            job = await session.get(Job, job_id)
            if job is None or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
                return
            if pct is not None:
                job.progress = pct
            if msg:
                job.message = msg
    except Exception:  # noqa: BLE001
        logger.debug("[native_model_pull] progress flush failed", exc_info=True)


async def _native_model_pull(
    job_id: int, args: dict[str, Any], log: list[str], log_lock: threading.Lock
) -> int:
    from huggingface_hub import snapshot_download

    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    hf_id = str(args.get("hf_id", ""))
    revision = args.get("revision") or None
    token = merged.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")

    models_dir = Path(merged.get("MODELS_DIR", "./data/models"))
    if not models_dir.is_absolute():
        models_dir = (root / models_dir.as_posix().lstrip("./")).resolve()
    target = models_dir / hf_id
    target.mkdir(parents=True, exist_ok=True)

    hf_state_lock = threading.Lock()
    state: dict[str, Any] = {"n": 0, "total": None, "desc": ""}
    stop = asyncio.Event()

    async def poller() -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.5)
                return
            except TimeoutError:
                await _flush_pull_progress(job_id, hf_state_lock, state)

    poll_task = asyncio.create_task(poller())

    def run_dl() -> None:
        kwargs: dict[str, Any] = dict(
            repo_id=hf_id,
            local_dir=str(target),
            local_dir_use_symlinks=False,
            revision=revision,
            token=token or None,
        )
        tqdm_cls = _try_make_job_tqdm(hf_state_lock, state)
        if tqdm_cls is not None:
            kwargs["tqdm_class"] = tqdm_cls
        try:
            snapshot_download(**kwargs)
        except TypeError:
            if "tqdm_class" not in kwargs:
                raise
            kwargs.pop("tqdm_class", None)
            snapshot_download(**kwargs)

    append_job_log(log, log_lock, f"[pull] {hf_id} -> {target}")
    code = 0
    try:
        await asyncio.to_thread(run_dl)
    except Exception as exc:  # noqa: BLE001
        append_job_log(log, log_lock, f"[pull] failed: {exc}")
        code = 1
    finally:
        stop.set()
        with suppress(TimeoutError):
            await asyncio.wait_for(poll_task, timeout=5.0)
        with suppress(asyncio.CancelledError):
            if not poll_task.done():
                poll_task.cancel()
                await poll_task
        await _flush_pull_progress(job_id, hf_state_lock, state)
    return code


async def _native_bench_scenario(args: dict[str, Any], log: list[str], log_lock: threading.Lock) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    engine = str(args.get("engine", "vllm"))
    preset = str(args.get("preset", ""))
    rounds = int(args.get("rounds", 1))
    warmup = int(args.get("warmup_requests", 3))
    m = merge_llm_stack_env(root, merged, preset, engine, None, None, None)
    from datetime import datetime as dt

    ts = dt.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = root / "data" / "bench" / "results" / engine / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    host = "vllm" if engine == "vllm" else "sglang"
    internal_port = m.get("LLM_API_PORT", "8111" if engine == "vllm" else "8222")
    base_url = f"http://{host}:{internal_port}/v1"
    env = os.environ.copy()
    env["MAX_MODEL_LEN"] = m.get("MAX_MODEL_LEN", "32768")
    bench_name = coalesce_str(m, "SERVED_MODEL_NAME", "SLGPU_SERVED_MODEL_NAME", default="")
    if bench_name:
        env["BENCH_MODEL_NAME"] = bench_name
    elif m.get("MODEL_ID"):
        env["BENCH_MODEL_NAME"] = m["MODEL_ID"]
    argv = [
        "python3",
        str(root / "scripts" / "bench_openai.py"),
        "--base-url",
        base_url,
        "--engine",
        engine,
        "--output-dir",
        str(out_dir),
        "--rounds",
        str(rounds),
        "--warmup-requests",
        str(warmup),
    ]
    append_job_log(log, log_lock, f"[bench] scenario -> {out_dir}")
    code = await compose_exec.run_subprocess_logged(argv, root, env, log, log_lock)
    return code


async def _native_bench_load(args: dict[str, Any], log: list[str], log_lock: threading.Lock) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    engine = str(args.get("engine", "vllm"))
    preset = str(args.get("preset", ""))
    m = merge_llm_stack_env(root, merged, preset, engine, None, None, None)
    from datetime import datetime as dt

    ts = dt.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = root / "data" / "bench" / "results" / engine / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    host = "vllm" if engine == "vllm" else "sglang"
    internal_port = m.get("LLM_API_PORT", "8111" if engine == "vllm" else "8222")
    base_url = f"http://{host}:{internal_port}/v1"
    env = os.environ.copy()
    env["MAX_MODEL_LEN"] = m.get("MAX_MODEL_LEN", "32768")
    bench_name = coalesce_str(m, "SERVED_MODEL_NAME", "SLGPU_SERVED_MODEL_NAME", default="")
    if bench_name:
        env["BENCH_MODEL_NAME"] = bench_name
    elif m.get("MODEL_ID"):
        env["BENCH_MODEL_NAME"] = m["MODEL_ID"]
    burst = args.get("burst")
    argv = [
        "python3",
        str(root / "scripts" / "bench_load.py"),
        "--base-url",
        base_url,
        "--engine",
        engine,
        "--output-dir",
        str(out_dir),
        "--users",
        str(int(args.get("users", 250))),
        "--duration",
        str(int(args.get("duration", 900))),
        "--ramp-up",
        str(int(args.get("ramp_up", 120))),
        "--ramp-down",
        str(int(args.get("ramp_down", 60))),
        "--think-time",
        str(args.get("think_time", "2000,5000")),
        "--max-prompt-tokens",
        str(int(args.get("max_prompt", 512))),
        "--max-output-tokens",
        str(int(args.get("max_output", 256))),
        "--report-interval",
        str(float(args.get("report_interval", 5))),
        "--warmup-requests",
        str(int(args.get("warmup_requests", 3))),
    ]
    if burst:
        argv.append("--burst")
    append_job_log(log, log_lock, f"[bench] load -> {out_dir}")
    return await compose_exec.run_subprocess_logged(argv, root, env, log, log_lock)
