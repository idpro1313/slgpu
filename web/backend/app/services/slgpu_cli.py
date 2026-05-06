"""Дескрипторы заданий стека: ``kind`` = ``native.*`` (docker compose / docker-py) или ``web.log_report.generate`` (Loki + LLM HTTP для сводки), либо legacy ``argv`` → ``bash ./slgpu``.

Web UI ставит **``native.*``** и **``web.log_report.generate``** с пустым ``argv``; данные стека — из БД (см. ``stack_config`` / ``write_compose_service_env_file``).
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


_PROXY_ACTIONS = frozenset({"up", "down", "restart"})


def cmd_proxy(_slgpu_root: Path, action: str) -> CliCommand:
    """Только `docker/docker-compose.proxy.yml` (LiteLLM), тот же lock `monitoring`/`stack`, что и полный monitoring up."""
    if action not in _PROXY_ACTIONS:
        raise ValueError(
            f"proxy action must be one of {sorted(_PROXY_ACTIONS)}, got {action!r}"
        )
    return CliCommand(
        kind=f"native.proxy.{action}",
        argv=[],
        scope="monitoring",
        resource="stack",
        summary=f"proxy {action}",
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


def cmd_log_report(*, report_id: int) -> CliCommand:
    """Фоновая генерация сводного отчёта по логам Loki + LiteLLM (web-only job)."""

    if not isinstance(report_id, int) or report_id < 1:
        raise ValidationError("report_id must be a positive integer")
    return CliCommand(
        kind="web.log_report.generate",
        argv=[],
        scope="log_report",
        resource=f"report:{report_id}",
        summary=f"log report #{report_id}",
    )
