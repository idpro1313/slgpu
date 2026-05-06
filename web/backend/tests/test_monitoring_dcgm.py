"""MONITORING_DCGM, monitoring_dcgm_wanted и хелперы HOST_GPU / образ nvidia-smi."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.services.stack_config import (
    host_gpu_docker_probe_enabled,
    monitoring_dcgm_wanted,
    nvidia_smi_docker_image_for_stack,
)


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


def test_host_gpu_docker_probe_default_on() -> None:
    assert host_gpu_docker_probe_enabled({}) is True
    assert host_gpu_docker_probe_enabled({"HOST_GPU_DOCKER_PROBE": "on"}) is True


def test_host_gpu_docker_probe_off_variants() -> None:
    for v in ("off", "false", "0", "no", "disabled", "OFF"):
        assert host_gpu_docker_probe_enabled({"HOST_GPU_DOCKER_PROBE": v}) is False


@patch("app.core.config.get_settings")
def test_nvidia_smi_docker_image_fallback(mock_settings) -> None:
    mock_settings.return_value.nvidia_smi_docker_image = "fallback/nvidia:test"
    assert nvidia_smi_docker_image_for_stack({}) == "fallback/nvidia:test"


def test_nvidia_smi_docker_image_from_merged() -> None:
    assert (
        nvidia_smi_docker_image_for_stack(
            {"NVIDIA_SMI_DOCKER_IMAGE": "  registry/cuda:tag  "}
        )
        == "registry/cuda:tag"
    )
