"""MONITORING_DCGM и helper monitoring_dcgm_wanted (подъём мониторинга без GPU)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.stack_config import monitoring_dcgm_wanted


def test_monitoring_dcgm_off_never_wants() -> None:
    m = {"MONITORING_DCGM": "off"}
    assert monitoring_dcgm_wanted(m, Path("/tmp")) is False


def test_monitoring_dcgm_on_without_host_probe() -> None:
    m = {"MONITORING_DCGM": "on"}
    assert monitoring_dcgm_wanted(m, Path("/tmp")) is True


@patch("app.services.host_info.collect_host_info")
def test_monitoring_dcgm_auto_false_without_gpu(mock_collect) -> None:
    mock_collect.return_value = {"nvidia": {"smi_available": False, "gpus": []}}
    assert monitoring_dcgm_wanted({"MONITORING_DCGM": "auto"}, Path("/tmp")) is False
    mock_collect.assert_called_once()


@patch("app.services.host_info.collect_host_info")
def test_monitoring_dcgm_auto_true_with_gpu(mock_collect) -> None:
    mock_collect.return_value = {"nvidia": {"smi_available": True, "gpus": [{"index": 0}]}}
    assert monitoring_dcgm_wanted({"MONITORING_DCGM": "auto"}, Path("/tmp")) is True


@patch("app.services.host_info.collect_host_info")
def test_monitoring_dcgm_missing_key_defaults_to_auto(mock_collect) -> None:
    mock_collect.return_value = {"nvidia": {"smi_available": True, "gpus": [{"index": 0}]}}
    assert monitoring_dcgm_wanted({}, Path("/tmp")) is True
