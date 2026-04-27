"""Start/stop vLLM/SGLang inference via docker-py (multi-slot), no LLM compose for web."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import docker
from docker.errors import NotFound
from docker.utils import parse_repository_tag
from docker.types import DeviceRequest, LogConfig

from app.services.job_log import append_job_log

from app.services.compose_exec import ensure_slgpu_network
from app.services.gpu_state import invalidate_gpu_state_cache
from app.services.llm_env import container_env_for_engine, merge_llm_stack_env
from app.services.stack_config import sync_merged_flat
from app.services.stack_errors import MissingStackParams

logger = logging.getLogger(__name__)

_LABEL_SLOT = "com.develonica.slgpu.slot"
_LABEL_ENGINE = "com.develonica.slgpu.engine"
_LABEL_PRESET = "com.develonica.slgpu.preset"

SGLANG_KERNEL_VOLUME = "slgpu-sglang-kernel-cache-web"


def slot_container_name(engine: str, slot_key: str) -> str:
    if slot_key == "default":
        return f"slgpu-{engine}"
    return f"slgpu-{engine}-{slot_key}"


def internal_api_port_for(engine: str, merged: dict[str, str]) -> int:
    if engine == "vllm":
        return int(merged["VLLM_PORT"])
    return int(merged["SGLANG_LISTEN_PORT"])


def resolve_image(engine: str, merged: dict[str, str]) -> str:
    if engine == "vllm":
        return str(merged["VLLM_DOCKER_IMAGE"])
    return str(merged["SGLANG_DOCKER_IMAGE"])


def _resolve_path(root: Path, p: str) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    if p.startswith("./"):
        return (root / p[2:]).resolve()
    return (root / p).resolve()


def _stop_container_by_name(
    client: docker.DockerClient, name: str, log: list[str], log_lock: threading.Lock | None
) -> None:
    try:
        c = client.containers.get(name)
        c.stop(timeout=20)
        c.remove()
        append_job_log(log, log_lock, f"[slot] removed {name}")
    except NotFound:
        pass
    except docker.errors.DockerException as exc:
        append_job_log(log, log_lock, f"[slot] stop {name}: {exc}")


def _docker_pull_with_log(
    client: docker.DockerClient, image: str, log: list[str], log_lock: threading.Lock | None
) -> None:
    """Stream ``docker pull`` into job log (``containers.run`` does not show layer progress)."""

    try:
        repository, tag = parse_repository_tag(image)
    except (TypeError, ValueError):
        repository, tag = image, None
    append_job_log(log, log_lock, f"[slot] docker pull: {image}")
    try:
        stream = client.api.pull(
            repository, tag=tag or "latest", stream=True, decode=True
        )
    except (docker.errors.DockerException, TypeError) as exc:
        append_job_log(log, log_lock, f"[docker] pull init: {exc}")
        return
    try:
        for chunk in stream:
            if not chunk or not isinstance(chunk, dict):
                continue
            st = (chunk.get("status") or "").strip()
            layer_id = (chunk.get("id") or "")[:12]
            prog = chunk.get("progress")
            if isinstance(prog, str) and prog.strip():
                line = f"{st} {layer_id} {prog.strip()}".strip()
            else:
                pd = chunk.get("progressDetail")
                if isinstance(pd, dict) and pd.get("total") and pd.get("current") is not None:
                    line = f"{st} {layer_id} {pd.get('current')}/{pd.get('total')}"
                else:
                    line = f"{st} {layer_id}".strip() if (st or layer_id) else ""
            if line:
                append_job_log(log, log_lock, f"[docker] {line[:500]}")
    except (docker.errors.DockerException, OSError) as exc:
        append_job_log(log, log_lock, f"[docker] pull: {str(exc)[:1000]}")


def _ensure_named_volume(client: docker.DockerClient, name: str) -> None:
    try:
        client.volumes.get(name)
    except NotFound:
        client.volumes.create(name=name, labels={_LABEL_SLOT: "volume"})


async def run_slot_docker(
    *,
    root: Path,
    slot_key: str,
    engine: str,
    preset: str,
    host_api_port: int,
    gpu_indices: list[int],
    tp: int | None,
    log: list[str],
    log_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    """Start one slot; returns ``{ok, container_id, container_name, error}``."""
    from asyncio import to_thread

    await ensure_slgpu_network(log, log_lock=log_lock)
    return await to_thread(
        _run_slot_sync,
        root,
        slot_key,
        engine,
        preset,
        host_api_port,
        gpu_indices,
        tp,
        log,
        log_lock,
    )


def _run_slot_sync(
    root: Path,
    slot_key: str,
    engine: str,
    preset: str,
    host_api_port: int,
    gpu_indices: list[int],
    tp: int | None,
    log: list[str],
    log_lock: threading.Lock | None,
) -> dict[str, Any]:
    cname = slot_container_name(engine, slot_key)
    merged0 = sync_merged_flat()
    try:
        merged = merge_llm_stack_env(
            root,
            dict(merged0),
            preset,
            engine,
            None,
            tp,
            gpu_indices,
        )
    except MissingStackParams as exc:
        return {
            "ok": False,
            "error": f"missing stack/preset keys ({exc.scope}): {', '.join(exc.keys)}",
            "container_id": None,
            "container_name": cname,
        }
    image = resolve_image(engine, merged)
    env = container_env_for_engine(merged, engine)
    with docker.from_env() as client:
        try:
            client.ping()
        except docker.errors.DockerException as exc:
            return {"ok": False, "error": f"docker: {exc}", "container_id": None, "container_name": cname}

        _stop_container_by_name(client, cname, log, log_lock)

        models = _resolve_path(root, str(merged["MODELS_DIR"]))
        serve = (root / "scripts" / "serve.sh").resolve()
        if not serve.is_file():
            return {"ok": False, "error": f"missing {serve}", "container_id": None, "container_name": cname}

        vols: dict[str, dict[str, str]] = {
            str(models): {"bind": "/models", "mode": "ro"},
            str(serve): {"bind": "/etc/slgpu/serve.sh", "mode": "ro"},
        }
        if engine == "sglang":
            _ensure_named_volume(client, SGLANG_KERNEL_VOLUME)
            vols[SGLANG_KERNEL_VOLUME] = {"bind": "/var/cache/slgpu-kernels", "mode": "rw"}

        internal = internal_api_port_for(engine, merged)
        port_key = f"{internal}/tcp"
        dr = [DeviceRequest(device_ids=[str(i) for i in gpu_indices], capabilities=[["gpu"]])]
        labels = {
            _LABEL_SLOT: slot_key,
            _LABEL_ENGINE: engine,
            _LABEL_PRESET: preset,
        }
        if slot_key == "default":
            aliases = [engine]
        else:
            aliases = [f"{engine}-{slot_key}"]

        _docker_pull_with_log(client, image, log, log_lock)

        log_config = LogConfig(type="json-file", config={"max-size": "100m", "max-file": "5"})
        try:
            container = client.containers.run(
                image,
                name=cname,
                detach=True,
                environment=env,
                ports={port_key: host_api_port},
                volumes=vols,
                shm_size="32g",
                ipc_mode="host",
                device_requests=dr,
                entrypoint=["/bin/bash"],
                command=["/etc/slgpu/serve.sh"],
                labels=labels,
                log_config=log_config,
                restart_policy={"Name": "unless-stopped"},
            )
        except docker.errors.DockerException as exc:
            logger.exception(
                "[slot_runtime][_run_slot_sync][BLOCK_FAIL] cname=%s err=%s",
                cname,
                str(exc)[:300],
            )
            return {"ok": False, "error": str(exc)[:800], "container_id": None, "container_name": cname}

        cid = container.id or ""
        # Connect to slgpu with DNS aliases
        try:
            net = client.networks.get("slgpu")
            net.connect(container, aliases=aliases)
        except NotFound as exc:
            _stop_container_by_name(client, cname, log, log_lock)
            return {
                "ok": False,
                "error": f"network slgpu: {exc}",
                "container_id": None,
                "container_name": cname,
            }
        except docker.errors.DockerException as exc:
            append_job_log(log, log_lock, f"[slot] network connect warning: {exc}")
        short = f"{cid[:12]}…" if cid else "?"
        append_job_log(
            log,
            log_lock,
            f"[slot] up {cname} id={short} image={image!r} port={host_api_port} gpus={gpu_indices}",
        )
    invalidate_gpu_state_cache()
    from app.services.gpu_availability import invalidate_host_gpu_cache

    invalidate_host_gpu_cache()
    return {
        "ok": True,
        "error": None,
        "container_id": cid,
        "container_name": cname,
    }


def stop_slot_sync(cname: str, log: list[str], log_lock: threading.Lock | None = None) -> int:
    with docker.from_env() as client:
        _stop_container_by_name(client, cname, log, log_lock)
    invalidate_gpu_state_cache()
    from app.services.gpu_availability import invalidate_host_gpu_cache

    invalidate_host_gpu_cache()
    return 0


def stop_containers_for_slot_key_sync(
    slot_key: str, log: list[str], log_lock: threading.Lock | None = None
) -> int:
    """Stop all containers with ``com.develonica.slgpu.slot`` label; fallback to name patterns."""
    with docker.from_env() as client:
        if not _ping(client, log, log_lock):
            return 1
        label = f"{_LABEL_SLOT}={slot_key}"
        try:
            for c in client.containers.list(all=True, filters={"label": [label]}):
                try:
                    c.stop(timeout=20)
                    c.remove()
                    logger.info(
                        "[slot_runtime][stop_containers_for_slot_key_sync][BLOCK_REMOVED] name=%s",
                        c.name,
                    )
                    append_job_log(
                        log, log_lock, f"[slot] removed labeled {c.name or c.id[:12]}"
                    )
                except docker.errors.DockerException as exc:
                    append_job_log(log, log_lock, f"[slot] remove {c.name}: {exc}")
        except docker.errors.DockerException as exc:
            append_job_log(log, log_lock, f"[slot] list: {exc}")
        for eng in ("vllm", "sglang"):
            cname = slot_container_name(eng, slot_key)
            _stop_container_by_name(client, cname, log, log_lock)
    invalidate_gpu_state_cache()
    from app.services.gpu_availability import invalidate_host_gpu_cache

    invalidate_host_gpu_cache()
    return 0


def _ping(client: docker.DockerClient, log: list[str], log_lock: threading.Lock | None) -> bool:
    try:
        client.ping()
        return True
    except docker.errors.DockerException as exc:
        append_job_log(log, log_lock, f"[slot] docker: {exc}")
        return False
