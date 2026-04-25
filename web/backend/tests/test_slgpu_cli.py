"""Argv generators for the ./slgpu CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.security import ValidationError
from app.services.slgpu_cli import (
    cmd_down,
    cmd_monitoring,
    cmd_pull,
    cmd_restart,
    cmd_up,
)


def _root() -> Path:
    return Path("/srv/slgpu")


def test_cmd_pull_with_slug():
    cmd = cmd_pull(_root(), "qwen3.6-35b-a3b")
    assert cmd.argv == ["/srv/slgpu/slgpu", "pull", "qwen3.6-35b-a3b"]
    assert cmd.kind == "cli.pull"
    assert cmd.scope == "model"


def test_cmd_pull_with_hf_id_and_revision():
    cmd = cmd_pull(_root(), "Qwen/Qwen3.6-35B-A3B", revision="main")
    assert cmd.argv == [
        "/srv/slgpu/slgpu",
        "pull",
        "Qwen/Qwen3.6-35B-A3B",
        "--revision",
        "main",
    ]


def test_cmd_pull_rejects_injection():
    with pytest.raises(ValidationError):
        cmd_pull(_root(), "Qwen/Qwen; rm -rf /")


def test_cmd_up_minimal():
    cmd = cmd_up(_root(), "vllm", "qwen3.6-35b-a3b")
    assert cmd.argv == [
        "/srv/slgpu/slgpu",
        "up",
        "vllm",
        "-m",
        "qwen3.6-35b-a3b",
    ]


def test_cmd_up_with_port_and_tp():
    cmd = cmd_up(_root(), "sglang", "deepseek-v4-pro", port=8222, tp=8)
    assert cmd.argv[-4:] == ["-p", "8222", "--tp", "8"]


def test_cmd_up_rejects_bad_engine():
    with pytest.raises(ValidationError):
        cmd_up(_root(), "trtllm", "demo")


def test_cmd_down_optionally_includes_monitoring():
    assert cmd_down(_root()).argv == ["/srv/slgpu/slgpu", "down"]
    assert cmd_down(_root(), include_monitoring=True).argv == [
        "/srv/slgpu/slgpu",
        "down",
        "--all",
    ]


def test_cmd_restart_argv():
    cmd = cmd_restart(_root(), "qwen3.6-35b-a3b", tp=4)
    assert cmd.argv == [
        "/srv/slgpu/slgpu",
        "restart",
        "-m",
        "qwen3.6-35b-a3b",
        "--tp",
        "4",
    ]


@pytest.mark.parametrize("action", ["up", "down", "restart", "fix-perms"])
def test_cmd_monitoring_allowlist(action: str):
    cmd = cmd_monitoring(_root(), action)
    assert cmd.argv == ["/srv/slgpu/slgpu", "monitoring", action]
    assert cmd.kind == f"cli.monitoring.{action}"


def test_cmd_monitoring_rejects_unknown():
    with pytest.raises(ValueError):
        cmd_monitoring(_root(), "nuke")
