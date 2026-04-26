"""Native stack operations for web (docker compose / docker API), no `./slgpu` subprocess."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import docker

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.job import Job, JobStatus
from app.services import compose_exec
from app.services.stack_config import (
    parse_dotenv_text,
    presets_dir_sync,
    sync_merged_flat,
    write_langfuse_litellm_env,
    write_llm_interp_env,
)
from app.services.slgpu_cli import CliCommand

logger = logging.getLogger(__name__)

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


async def _ensure_config_files_async(root: Path, log: list[str]) -> None:
    import subprocess

    for rel, gitrel in _CONFIG_FILES:
        abs_path = (root / rel).resolve()
        if abs_path.is_dir():
            log.append(f"[config] removing dir {rel}")
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
                log.append(f"[config] restored {gitrel}")
        if not abs_path.is_file():
            raise RuntimeError(f"missing {gitrel}")


def _mkdir_data_dirs(root: Path, merged: dict[str, str], log: list[str]) -> None:
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
            log.append(f"[mkdir] {k}={p} err={exc}")


def _merge_llm(
    root: Path,
    merged: dict[str, str],
    preset: str,
    engine: str,
    port: int | None,
    tp: int | None,
) -> dict[str, str]:
    m = dict(merged)
    presets_dir = presets_dir_sync()
    pf = presets_dir / f"{preset}.env"
    if pf.is_file():
        m.update(parse_dotenv_text(pf.read_text(encoding="utf-8")))
    if tp is not None:
        m["TP"] = str(tp)
    override_nv = m.get("SLGPU_NVIDIA_VISIBLE_DEVICES", "").strip()
    if override_nv:
        m["NVIDIA_VISIBLE_DEVICES"] = override_nv
    else:
        try:
            tpi = int(m.get("TP", "8"))
        except ValueError:
            tpi = 8
        m["NVIDIA_VISIBLE_DEVICES"] = ",".join(str(i) for i in range(max(1, tpi)))
    if port is not None:
        m["LLM_API_PORT"] = str(port)
    elif engine == "sglang" and "LLM_API_PORT" not in m:
        m["LLM_API_PORT"] = m.get("LLM_API_PORT_SGLANG", "8222")
    return m


def _write_tmp_monitoring_env(root: Path, merged: dict[str, str]) -> Path:
    fd, name = tempfile.mkstemp(prefix="slgpu-mon-", suffix=".env", dir=str(root / "data"))
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
        job.exit_code = exit_code
        job.finished_at = datetime.now(timezone.utc)
        job.status = JobStatus.SUCCEEDED if exit_code == 0 else JobStatus.FAILED
        job.stdout_tail = text[-8000:] if text else None
        job.stderr_tail = None
        if exit_code != 0:
            job.message = f"exit={exit_code}"


async def handle_native_job(job_id: int, command: CliCommand, args: dict[str, Any]) -> None:
    log: list[str] = []
    code = 0
    try:
        if command.kind == "native.llm.up":
            code = await _native_llm_up(args, log)
        elif command.kind == "native.llm.down":
            code = await _native_llm_down(args, log)
        elif command.kind == "native.llm.restart":
            code = await _native_llm_restart(args, log)
        elif command.kind == "native.monitoring.up":
            code = await _native_monitoring_up(log)
        elif command.kind == "native.monitoring.down":
            code = await _native_monitoring_down(log)
        elif command.kind == "native.monitoring.restart":
            code = await _native_monitoring_restart(log)
        elif command.kind == "native.monitoring.fix-perms":
            code = await _native_fix_perms(log)
        elif command.kind == "native.model.pull":
            code = await _native_model_pull(args, log)
        elif command.kind == "native.bench.scenario":
            code = await _native_bench_scenario(args, log)
        elif command.kind == "native.bench.load":
            code = await _native_bench_load(args, log)
        else:
            log.append(f"[native] unknown kind {command.kind}")
            code = 1
    except Exception as exc:  # noqa: BLE001
        logger.exception("[native_jobs] failure")
        log.append(f"[native] error: {exc}")
        code = 1
    await _finalize_native_job(job_id, command, code, log)


async def _native_llm_up(args: dict[str, Any], log: list[str]) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    engine = str(args.get("engine", "vllm"))
    preset = str(args.get("preset", ""))
    port = args.get("port")
    tp = args.get("tp")
    port_i = int(port) if port is not None else None
    tp_i = int(tp) if tp is not None else None
    m = _merge_llm(root, merged, preset, engine, port_i, tp_i)
    log.append(
        f"[llm] up {engine} preset={preset} port={m.get('LLM_API_PORT')} TP={m.get('TP')} GPUs={m.get('NVIDIA_VISIBLE_DEVICES')}"
    )

    (root / "data").mkdir(parents=True, exist_ok=True)
    fd, interp_name = tempfile.mkstemp(prefix="slgpu-llm-", suffix=".env", dir=str(root / "data"))
    os.close(fd)
    interp = Path(interp_name)
    write_llm_interp_env(interp, m)

    await compose_exec.ensure_slgpu_network(log)
    _mkdir_data_dirs(root, merged, log)

    for op in (
        ("stop", "vllm", "sglang"),
        ("rm", "-f", "vllm", "sglang"),
    ):
        c, o, e = await compose_exec.compose_llm_env(root, interp, "-f", _LL_YML, *op)
        log.append(o.strip())
        if e.strip():
            log.append(e.strip())
    profile = "vllm" if engine == "vllm" else "sglang"
    c, o, e = await compose_exec.compose_llm_env(
        root, interp, "-f", _LL_YML, "--profile", profile, "up", "-d"
    )
    log.append(o.strip())
    if e.strip():
        log.append(e.strip())
    try:
        interp.unlink(missing_ok=True)
    except OSError:
        pass
    return 0 if c == 0 else c


async def _native_llm_down(args: dict[str, Any], log: list[str]) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    all_mon = bool(args.get("include_monitoring"))
    if all_mon:
        c, o, e = await compose_exec.compose_inherit_env(root, "-f", _LL_YML, "stop")
        log.append(o + e)
        c2, o2, e2 = await compose_exec.compose_inherit_env(root, "-f", _MON_YML, "stop")
        log.append(o2 + e2)
        return 0 if c == 0 and c2 == 0 else 1
    c, o, e = await compose_exec.compose_inherit_env(root, "-f", _LL_YML, "stop", "vllm", "sglang")
    log.append(o + e)
    c2, o2, e2 = await compose_exec.compose_inherit_env(
        root, "-f", _LL_YML, "rm", "-f", "vllm", "sglang"
    )
    log.append(o2 + e2)
    return 0 if c == 0 else c


async def _detect_engine(root: Path, log: list[str]) -> str | None:
    proc = await asyncio.create_subprocess_exec(
        "docker",
        "compose",
        "--project-directory",
        str(root),
        "-f",
        _LL_YML,
        "ps",
        "--status",
        "running",
        "--format",
        "{{.Service}}",
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=None,
    )
    out_b, _ = await proc.communicate()
    text = out_b.decode("utf-8", errors="replace")
    for line in text.splitlines():
        s = line.strip().lower()
        if s == "vllm":
            log.append("[restart] detected vllm")
            return "vllm"
        if s == "sglang":
            log.append("[restart] detected sglang")
            return "sglang"
    return None


async def _native_llm_restart(args: dict[str, Any], log: list[str]) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    engine = await _detect_engine(root, log)
    if not engine:
        log.append("[restart] no running engine")
        return 1
    merged = sync_merged_flat()
    preset = str(args.get("preset", ""))
    tp = args.get("tp")
    tp_i = int(tp) if tp is not None else None
    port_s = merged.get("LLM_API_PORT", "8111" if engine == "vllm" else "8222")
    port_i = int(port_s)
    up_args = {"engine": engine, "preset": preset, "port": port_i, "tp": tp_i}
    return await _native_llm_up(up_args, log)


async def _monitoring_bootstrap(root: Path, env_file: Path, log: list[str]) -> None:
    bootstrap_dir = root / "data" / "monitoring" / ".bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)

    async def _one(svc: str, marker_name: str) -> None:
        marker = bootstrap_dir / marker_name
        if marker.is_file():
            log.append(f"[bootstrap] skip {svc} (done)")
            return
        c, o, e = await compose_exec.compose_monitoring(
            root, env_file, "-f", _MON_YML, "--profile", "bootstrap", "rm", "-f", "-s", "-v", svc
        )
        if o.strip():
            log.append(o.strip())
        if e.strip():
            log.append(e.strip())
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
        log.append(o.strip())
        if e.strip():
            log.append(e.strip())
        if c != 0:
            raise RuntimeError(f"bootstrap {svc} failed exit={c}")
        c2, o2, e2 = await compose_exec.compose_monitoring(
            root, env_file, "-f", _MON_YML, "--profile", "bootstrap", "rm", "-f", "-s", "-v", svc
        )
        if o2.strip():
            log.append(o2.strip())
        if e2.strip():
            log.append(e2.strip())
        marker.touch()

    await _one("minio-bucket-init", "minio-bucket-init.done")
    await _one("litellm-pg-init", "litellm-pg-init.done")


async def _native_monitoring_up(log: list[str]) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    write_langfuse_litellm_env(
        root,
        {k: merged[k] for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY") if k in merged},
    )
    _mkdir_data_dirs(root, merged, log)
    await _ensure_config_files_async(root, log)
    env_file = _write_tmp_monitoring_env(root, merged)
    try:
        await compose_exec.ensure_slgpu_network(log)
        await _monitoring_bootstrap(root, env_file, log)
        c, o, e = await compose_exec.compose_monitoring(root, env_file, "-f", _MON_YML, "up", "-d")
        log.append(o.strip())
        if e.strip():
            log.append(e.strip())
        return 0 if c == 0 else c
    finally:
        env_file.unlink(missing_ok=True)


async def _native_monitoring_down(log: list[str]) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    env_file = _write_tmp_monitoring_env(root, merged)
    try:
        c, o, e = await compose_exec.compose_monitoring(root, env_file, "-f", _MON_YML, "down")
        log.append(o + e)
        return 0 if c == 0 else c
    finally:
        env_file.unlink(missing_ok=True)


async def _native_monitoring_restart(log: list[str]) -> int:
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
    await _ensure_config_files_async(root, log)
    env_file = _write_tmp_monitoring_env(root, merged)
    try:
        await compose_exec.ensure_slgpu_network(log)
        c, o, e = await compose_exec.compose_monitoring(
            root, env_file, "-f", _MON_YML, "up", "-d", "--force-recreate"
        )
        log.append(o + e)
        return 0 if c == 0 else c
    finally:
        env_file.unlink(missing_ok=True)


def _id_from_image(client: docker.DockerClient, image: str, log: list[str]) -> tuple[str, str]:
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
        log.append(f"[fix-perms] id_from {image}: {exc}")
    return "999", "999"


def _chown_dir(client: docker.DockerClient, host_path: Path, uid: str, gid: str, log: list[str]) -> None:
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
        log.append(f"[fix-perms] chown {host_path}: {exc}")


async def _native_fix_perms(log: list[str]) -> int:
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

    gimg = merged.get("SLGPU_GRAFANA_IMAGE", "grafana/grafana:latest")
    pimg = merged.get("SLGPU_PROMETHEUS_IMAGE", "prom/prometheus:latest")
    limg = merged.get("SLGPU_LOKI_IMAGE", "grafana/loki:2.9.8")
    pgimg = merged.get("SLGPU_LANGFUSE_POSTGRES_IMAGE", "postgres:17")
    minioimg = merged.get("SLGPU_MINIO_IMAGE", "minio/minio:latest")
    redisimg = merged.get("SLGPU_LANGFUSE_REDIS_IMAGE", "redis:7")

    def run_sync() -> None:
        client = docker.from_env()
        gu, gg = _id_from_image(client, gimg, log)
        pu, pg = _id_from_image(client, pimg, log)
        lu, lg = _id_from_image(client, limg, log)
        if lu == "999":
            lu, lg = "10001", "10001"
        pg_u, pg_g = _id_from_image(client, pgimg, log)
        ru, rg = _id_from_image(client, redisimg, log)
        mu, mg = _id_from_image(client, minioimg, log)

        _chown_dir(client, gdir, gu, gg, log)
        _chown_dir(client, pdir, pu, pg, log)
        _chown_dir(client, ldir, lu, lg, log)
        _chown_dir(client, ptdir, "0", "0", log)
        _chown_dir(client, lf_p, pg_u, pg_g, log)
        _chown_dir(client, lf_c, "101", "101", log)
        _chown_dir(client, lf_cl, "101", "101", log)
        _chown_dir(client, lf_m, mu, mg, log)
        _chown_dir(client, lf_r, ru, rg, log)

    await asyncio.to_thread(run_sync)
    log.append("[fix-perms] done")
    return 0


async def _native_model_pull(args: dict[str, Any], log: list[str]) -> int:
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

    def run_dl() -> None:
        snapshot_download(
            repo_id=hf_id,
            local_dir=str(target),
            local_dir_use_symlinks=False,
            revision=revision,
            token=token or None,
        )

    log.append(f"[pull] {hf_id} -> {target}")
    try:
        await asyncio.to_thread(run_dl)
    except Exception as exc:  # noqa: BLE001
        log.append(f"[pull] failed: {exc}")
        return 1
    return 0


async def _native_bench_scenario(args: dict[str, Any], log: list[str]) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    engine = str(args.get("engine", "vllm"))
    preset = str(args.get("preset", ""))
    rounds = int(args.get("rounds", 1))
    warmup = int(args.get("warmup_requests", 3))
    m = _merge_llm(root, merged, preset, engine, None, None)
    from datetime import datetime as dt

    ts = dt.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = root / "data" / "bench" / "results" / engine / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    host = "vllm" if engine == "vllm" else "sglang"
    internal_port = m.get("LLM_API_PORT", "8111" if engine == "vllm" else "8222")
    base_url = f"http://{host}:{internal_port}/v1"
    env = os.environ.copy()
    env["MAX_MODEL_LEN"] = m.get("MAX_MODEL_LEN", "32768")
    if m.get("SLGPU_SERVED_MODEL_NAME"):
        env["BENCH_MODEL_NAME"] = m["SLGPU_SERVED_MODEL_NAME"]
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
    log.append(f"[bench] scenario -> {out_dir}")
    code = await compose_exec.run_subprocess_logged(argv, root, env, log)
    return code


async def _native_bench_load(args: dict[str, Any], log: list[str]) -> int:
    settings = get_settings()
    root = settings.slgpu_root
    merged = sync_merged_flat()
    engine = str(args.get("engine", "vllm"))
    preset = str(args.get("preset", ""))
    m = _merge_llm(root, merged, preset, engine, None, None)
    from datetime import datetime as dt

    ts = dt.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = root / "data" / "bench" / "results" / engine / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    host = "vllm" if engine == "vllm" else "sglang"
    internal_port = m.get("LLM_API_PORT", "8111" if engine == "vllm" else "8222")
    base_url = f"http://{host}:{internal_port}/v1"
    env = os.environ.copy()
    env["MAX_MODEL_LEN"] = m.get("MAX_MODEL_LEN", "32768")
    if m.get("SLGPU_SERVED_MODEL_NAME"):
        env["BENCH_MODEL_NAME"] = m["SLGPU_SERVED_MODEL_NAME"]
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
    log.append(f"[bench] load -> {out_dir}")
    return await compose_exec.run_subprocess_logged(argv, root, env, log)
