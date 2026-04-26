"""Start/stop vLLM/SGLang inference via docker-py (multi-slot), no LLM compose for web."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import docker
from docker.errors import NotFound
from docker.types import DeviceRequest, LogConfig

from app.services.compose_exec import ensure_slgpu_network
from app.services.gpu_state import invalidate_gpu_state_cache
from app.services.llm_env import container_env_for_engine, merge_llm_stack_env
from app.services.stack_config import sync_merged_flat

logger = logging.getLogger(__name__)

_LABEL_SLOT = "com.develonica.slgpu.slot"
_LABEL_ENGINE = "com.develonica.slgpu.engine"
_LABEL_PRESET = "com.develonica.slgpu.preset"

SGLANG_DEFAULT_IMAGE = "lmsysorg/sglang:latest"
VLLM_DEFAULT_IMAGE = "vllm/vllm-openai:v0.19.1-cu130"
SGLANG_KERNEL_VOLUME = "slgpu-sglang-kernel-cache-web"


def slot_container_name(engine: str, slot_key: str) -> str:
    if slot_key == "default":
        return f"slgpu-{engine}"
    return f"slgpu-{engine}-{slot_key}"


def internal_api_port_for(engine: str) -> int:
    return 8111 if engine == "vllm" else 8222


def resolve_image(engine: str, merged: dict[str, str]) -> str:
    if engine == "vllm":
        return str(merged.get("VLLM_DOCKER_IMAGE") or VLLM_DEFAULT_IMAGE)
    return str(merged.get("SGLANG_DOCKER_IMAGE") or SGLANG_DEFAULT_IMAGE)


def _resolve_path(root: Path, p: str) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    if p.startswith("./"):
        return (root / p[2:]).resolve()
    return (root / p).resolve()


def _stop_container_by_name(client: docker.DockerClient, name: str, log: list[str]) -> None:
    try:
        c = client.containers.get(name)
        c.stop(timeout=20)
        c.remove()
        log.append(f"[slot] removed {name}")
    except NotFound:
        pass
    except docker.errors.DockerException as exc:
        log.append(f"[slot] stop {name}: {exc}")


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
) -> dict[str, Any]:
    """Start one slot; returns ``{ok, container_id, container_name, error}``."""
    from asyncio import to_thread

    err_net: list[str] = []
    await ensure_slgpu_network(err_net)
    for line in err_net:
        log.append(line)
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
) -> dict[str, Any]:
    cname = slot_container_name(engine, slot_key)
    merged0 = sync_merged_flat()
    merged = merge_llm_stack_env(
        root,
        dict(merged0),
        preset,
        engine,
        None,
        tp,
        gpu_indices,
    )
    image = resolve_image(engine, merged)
    env = container_env_for_engine(merged, engine)
    client = docker.from_env()
    try:
        client.ping()
    except docker.errors.DockerException as exc:
        return {"ok": False, "error": f"docker: {exc}", "container_id": None, "container_name": cname}

    _stop_container_by_name(client, cname, log)

    models = _resolve_path(root, str(merged.get("MODELS_DIR", "./data/models")))
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

    internal = internal_api_port_for(engine)
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
        _stop_container_by_name(client, cname, log)
        return {"ok": False, "error": f"network slgpu: {exc}", "container_id": None, "container_name": cname}
    except docker.errors.DockerException as exc:
        log.append(f"[slot] network connect warning: {exc}")
    short = f"{cid[:12]}…" if cid else "?"
    log.append(f"[slot] up {cname} id={short} image={image!r} port={host_api_port} gpus={gpu_indices}")
    invalidate_gpu_state_cache()
    from app.services.gpu_availability import invalidate_host_gpu_cache

    invalidate_host_gpu_cache()
    return {
        "ok": True,
        "error": None,
        "container_id": cid,
        "container_name": cname,
    }


def stop_slot_sync(cname: str, log: list[str]) -> int:
    client = docker.from_env()
    _stop_container_by_name(client, cname, log)
    invalidate_gpu_state_cache()
    from app.services.gpu_availability import invalidate_host_gpu_cache

    invalidate_host_gpu_cache()
    return 0


def stop_containers_for_slot_key_sync(slot_key: str, log: list[str]) -> int:
    """Stop all containers with ``com.develonica.slgpu.slot`` label; fallback to name patterns."""
    client = docker.from_env()
    if not _ping(client, log):
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
                log.append(f"[slot] removed labeled {c.name or c.id[:12]}")
            except docker.errors.DockerException as exc:
                log.append(f"[slot] remove {c.name}: {exc}")
    except docker.errors.DockerException as exc:
        log.append(f"[slot] list: {exc}")
    for eng in ("vllm", "sglang"):
        cname = slot_container_name(eng, slot_key)
        _stop_container_by_name(client, cname, log)
    invalidate_gpu_state_cache()
    from app.services.gpu_availability import invalidate_host_gpu_cache

    invalidate_host_gpu_cache()
    return 0


def _ping(client: docker.DockerClient, log: list[str]) -> bool:
    try:
        client.ping()
        return True
    except docker.errors.DockerException as exc:
        log.append(f"[slot] docker: {exc}")
        return False
