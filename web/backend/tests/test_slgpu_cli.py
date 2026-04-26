"""Argv / kind for stack operations (native docker compose; empty argv)."""

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


def test_cmd_pull_native():
    cmd = cmd_pull(_root(), "qwen3.6-35b-a3b")
    assert cmd.argv == []
    assert cmd.kind == "native.model.pull"
    assert cmd.scope == "model"


def test_cmd_pull_with_hf_id_and_revision():
    cmd = cmd_pull(_root(), "Qwen/Qwen3.6-35B-A3B", revision="main")
    assert cmd.argv == []
    assert cmd.kind == "native.model.pull"


def test_cmd_pull_rejects_injection():
    with pytest.raises(ValidationError):
        cmd_pull(_root(), "Qwen/Qwen; rm -rf /")


def test_cmd_up_native():
    cmd = cmd_up(_root(), "vllm", "qwen3.6-35b-a3b")
    assert cmd.argv == []
    assert cmd.kind == "native.llm.up"
    assert cmd.scope == "engine"
    assert cmd.resource == "runtime"


def test_cmd_up_with_port_and_tp_still_native():
    cmd = cmd_up(_root(), "sglang", "deepseek-v4-pro", port=8222, tp=8)
    assert cmd.argv == []
    assert cmd.kind == "native.llm.up"


def test_cmd_up_rejects_bad_engine():
    with pytest.raises(ValidationError):
        cmd_up(_root(), "trtllm", "demo")


def test_cmd_down_native():
    assert cmd_down(_root()).argv == []
    assert cmd_down(_root()).kind == "native.llm.down"
    assert cmd_down(_root()).resource == "runtime"
    assert cmd_down(_root(), include_monitoring=True).kind == "native.llm.down"


def test_cmd_restart_native():
    cmd = cmd_restart(_root(), "qwen3.6-35b-a3b", tp=4)
    assert cmd.argv == []
    assert cmd.kind == "native.llm.restart"
    assert cmd.resource == "runtime"


@pytest.mark.parametrize("action", ["up", "down", "restart", "fix-perms"])
def test_cmd_monitoring_native(action: str):
    cmd = cmd_monitoring(_root(), action)
    assert cmd.argv == []
    assert cmd.kind == f"native.monitoring.{action}"
    assert cmd.scope == "monitoring"
    assert cmd.resource == "stack"


def test_cmd_monitoring_rejects_unknown():
    with pytest.raises(ValueError):
        cmd_monitoring(_root(), "nuke")
