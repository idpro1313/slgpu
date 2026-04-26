"""Allowlist for stack operations (native docker compose / jobs).

Legacy argv-shaped ``CliCommand`` is kept for tests and optional CLI fallback;
web uses ``native.*`` kinds with empty ``argv``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.security import (
    validate_engine,
    validate_port,
    validate_revision,
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


def cmd_up(
    slgpu_root: Path,
    engine: str,
    preset: str,
    port: int | None = None,
    tp: int | None = None,
) -> CliCommand:
    engine = validate_engine(engine)
    preset = validate_slug(preset)
    if port is not None:
        validate_port(port)
    if tp is not None:
        validate_tp(tp)
    return CliCommand(
        kind="native.llm.up",
        argv=[],
        scope="engine",
        resource="runtime",
        summary=f"up {engine} -m {preset}",
    )


def cmd_down(slgpu_root: Path, include_monitoring: bool = False) -> CliCommand:
    return CliCommand(
        kind="native.llm.down",
        argv=[],
        scope="engine",
        resource="runtime",
        summary="down" + (" --all" if include_monitoring else ""),
    )


def cmd_restart(slgpu_root: Path, preset: str, tp: int | None = None) -> CliCommand:
    preset = validate_slug(preset)
    if tp is not None:
        validate_tp(tp)
    return CliCommand(
        kind="native.llm.restart",
        argv=[],
        scope="engine",
        resource="runtime",
        summary=f"restart -m {preset}",
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
