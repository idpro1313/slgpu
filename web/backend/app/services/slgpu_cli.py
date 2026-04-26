"""Allowlist for stack operations (native docker compose / jobs).

Legacy argv-shaped ``CliCommand`` is kept for tests and optional CLI fallback;
web uses ``native.*`` kinds with empty ``argv``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.security import (
    ValidationError,
    validate_engine,
    validate_port,
    validate_revision,
    validate_slot_key,
    validate_slug,
    validate_slug_or_hf_id,
    validate_tp,
)


@dataclass(frozen=True)
class CliCommand:
    kind: str
    argv: list[str]
    scope: str
    resource: str | None = None
    summary: str | None = None


def cmd_pull(slgpu_root: Path, target: str, revision: str | None = None) -> CliCommand:
    target = validate_slug_or_hf_id(target)
    if revision:
        validate_revision(revision)
    return CliCommand(
        kind="native.model.pull",
        argv=[],
        scope="model",
        resource=target,
        summary=f"pull {target}" + (f"@{revision}" if revision else ""),
        # hf_id passed via job extra_args
    )


def cmd_slot_up(
    *,
    slot_key: str,
    engine: str,
    preset: str,
    host_api_port: int,
    gpu_indices: list[int],
    tp: int | None = None,
) -> CliCommand:
    engine = validate_engine(engine)
    slot_key = validate_slot_key(slot_key)
    validate_slug(preset)
    validate_port(host_api_port)
    if not gpu_indices or not all(isinstance(i, int) and i >= 0 for i in gpu_indices):
        raise ValidationError("gpu_indices must be a non-empty list of non-negative int")
    if tp is not None:
        validate_tp(tp)
    return CliCommand(
        kind="native.slot.up",
        argv=[],
        scope="engine",
        resource=f"slot:{slot_key}",
        summary=f"slot up {slot_key} {engine} -m {preset} gpus={gpu_indices}",
    )


def cmd_slot_down(*, slot_key: str) -> CliCommand:
    slot_key = validate_slot_key(slot_key)
    return CliCommand(
        kind="native.slot.down",
        argv=[],
        scope="engine",
        resource=f"slot:{slot_key}",
        summary=f"slot down {slot_key}",
    )


def cmd_slot_restart(
    *,
    slot_key: str,
    preset: str,
    host_api_port: int | None = None,
    tp: int | None = None,
    gpu_indices: list[int] | None = None,
) -> CliCommand:
    slot_key = validate_slot_key(slot_key)
    validate_slug(preset)
    if host_api_port is not None:
        validate_port(host_api_port)
    if tp is not None:
        validate_tp(tp)
    if gpu_indices is not None and (
        not gpu_indices or not all(isinstance(i, int) and i >= 0 for i in gpu_indices)
    ):
        raise ValidationError("gpu_indices must be a non-empty list of non-negative int")
    return CliCommand(
        kind="native.slot.restart",
        argv=[],
        scope="engine",
        resource=f"slot:{slot_key}",
        summary=f"slot restart {slot_key} -m {preset}",
    )


_MONITORING_ACTIONS = frozenset({"up", "down", "restart", "fix-perms"})


def cmd_monitoring(slgpu_root: Path, action: str) -> CliCommand:
    if action not in _MONITORING_ACTIONS:
        raise ValueError(
            f"monitoring action must be one of {sorted(_MONITORING_ACTIONS)}, got {action!r}"
        )
    return CliCommand(
        kind=f"native.monitoring.{action}",
        argv=[],
        scope="monitoring",
        resource="stack",
        summary=f"monitoring {action}",
    )


def cmd_bench_scenario(
    slgpu_root: Path,
    *,
    engine: str,
    preset: str,
    rounds: int = 1,
    warmup_requests: int = 3,
) -> CliCommand:
    engine = validate_engine(engine)
    preset = validate_slug(preset)
    return CliCommand(
        kind="native.bench.scenario",
        argv=[],
        scope="bench",
        resource="scenario",
        summary=f"bench scenario {engine}/{preset}",
    )


def cmd_bench_load(_slgpu_root: Path) -> CliCommand:
    return CliCommand(
        kind="native.bench.load",
        argv=[],
        scope="bench",
        resource="load",
        summary="bench load",
    )
