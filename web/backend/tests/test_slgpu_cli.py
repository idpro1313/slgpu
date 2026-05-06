"""Argv / kind for stack operations (native docker compose; empty argv)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.security import ValidationError
from app.services.slgpu_cli import (
    cmd_log_export,
    cmd_log_report,
    cmd_monitoring,
    cmd_proxy,
    cmd_pull,
    cmd_slot_down,
    cmd_slot_up,
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


def test_cmd_slot_up_native():
    cmd = cmd_slot_up(
        slot_key="a1",
        engine="vllm",
        preset="qwen3.6-35b-a3b",
        host_api_port=8111,
        gpu_indices=[0, 1, 2, 3, 4, 5, 6, 7],
    )
    assert cmd.argv == []
    assert cmd.kind == "native.slot.up"
    assert cmd.scope == "engine"
    assert cmd.resource == "slot:a1"


def test_cmd_slot_up_rejects_bad_engine():
    with pytest.raises(ValidationError):
        cmd_slot_up(
            slot_key="a1",
            engine="trtllm",
            preset="qwen3.6-35b-a3b",
            host_api_port=8111,
            gpu_indices=[0, 1, 2, 3, 4, 5, 6, 7],
        )


def test_cmd_slot_down_native():
    cmd = cmd_slot_down(slot_key="a1")
    assert cmd.argv == []
    assert cmd.kind == "native.slot.down"
    assert cmd.resource == "slot:a1"


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


@pytest.mark.parametrize("action", ["up", "down", "restart"])
def test_cmd_proxy_native(action: str):
    cmd = cmd_proxy(_root(), action)
    assert cmd.argv == []
    assert cmd.kind == f"native.proxy.{action}"
    assert cmd.scope == "monitoring"
    assert cmd.resource == "stack"


def test_cmd_log_report_web_job():
    cmd = cmd_log_report(report_id=42)
    assert cmd.argv == []
    assert cmd.kind == "web.log_report.generate"
    assert cmd.scope == "log_report"
    assert cmd.resource == "report:42"


def test_cmd_log_report_rejects_bad_id():
    with pytest.raises(ValidationError):
        cmd_log_report(report_id=0)


def test_cmd_log_export_web_job():
    cmd = cmd_log_export(export_id=7)
    assert cmd.argv == []
    assert cmd.kind == "web.log_export.generate"
    assert cmd.scope == "log_export"
    assert cmd.resource == "export:7"


def test_cmd_log_export_rejects_bad_id():
    with pytest.raises(ValidationError):
        cmd_log_export(export_id=0)
