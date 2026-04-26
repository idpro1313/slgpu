"""Allowlist for `./slgpu` invocations.

This module is the only place in the backend that builds argv for the
slgpu CLI. The strict separation guarantees:

- nothing from request bodies ever reaches the shell as an interpreted
  string;
- every command that mutates the stack is logged with its exact argv;
- unit tests can assert the argv shape without a real Docker daemon.
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


def _root_cli(slgpu_root: Path) -> str:
    return str(slgpu_root / "slgpu")


def cmd_pull(slgpu_root: Path, target: str, revision: str | None = None) -> CliCommand:
    target = validate_slug_or_hf_id(target)
    argv = [_root_cli(slgpu_root), "pull", target]
    if revision:
        argv += ["--revision", validate_revision(revision)]
    return CliCommand(
        kind="cli.pull",
        argv=argv,
        scope="model",
        resource=target,
        summary=f"slgpu pull {target}",
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
    argv = [_root_cli(slgpu_root), "up", engine, "-m", preset]
    if port is not None:
        argv += ["-p", str(validate_port(port))]
    if tp is not None:
        argv += ["--tp", str(validate_tp(tp))]
    return CliCommand(
        kind="cli.up",
        argv=argv,
        scope="engine",
        resource="runtime",
        summary=f"slgpu up {engine} -m {preset}",
    )


def cmd_down(slgpu_root: Path, include_monitoring: bool = False) -> CliCommand:
    argv = [_root_cli(slgpu_root), "down"]
    if include_monitoring:
        argv.append("--all")
    return CliCommand(
        kind="cli.down",
        argv=argv,
        scope="engine",
        resource="runtime",
        summary="slgpu down" + (" --all" if include_monitoring else ""),
    )


def cmd_restart(slgpu_root: Path, preset: str, tp: int | None = None) -> CliCommand:
    preset = validate_slug(preset)
    argv = [_root_cli(slgpu_root), "restart", "-m", preset]
    if tp is not None:
        argv += ["--tp", str(validate_tp(tp))]
    return CliCommand(
        kind="cli.restart",
        argv=argv,
        scope="engine",
        resource="runtime",
        summary=f"slgpu restart -m {preset}",
    )


_MONITORING_ACTIONS = frozenset({"up", "down", "restart", "fix-perms"})


def cmd_monitoring(slgpu_root: Path, action: str) -> CliCommand:
    if action not in _MONITORING_ACTIONS:
        raise ValueError(
            f"monitoring action must be one of {sorted(_MONITORING_ACTIONS)}, got {action!r}"
        )
    argv = [_root_cli(slgpu_root), "monitoring", action]
    return CliCommand(
        kind=f"cli.monitoring.{action}",
        argv=argv,
        scope="monitoring",
        resource="stack",
        summary=f"slgpu monitoring {action}",
    )
