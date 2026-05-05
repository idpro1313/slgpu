"""Алиасы vLLM data-parallel (preset / merge)."""

from __future__ import annotations

from app.services.env_key_aliases import PRESET_ONLY_KEYS, apply_vllm_aliases_to_merged


def test_vllm_data_parallel_size_is_preset_only() -> None:
    assert "DATA_PARALLEL_SIZE" in PRESET_ONLY_KEYS


def test_apply_vllm_aliases_vllm_data_parallel_size_canonicalizes() -> None:
    merged = {"VLLM_DATA_PARALLEL_SIZE": "4"}
    apply_vllm_aliases_to_merged(merged)
    assert merged["DATA_PARALLEL_SIZE"] == "4"


def test_legacy_slgpu_vllm_data_parallel_still_aliases() -> None:
    merged = {"SLGPU_VLLM_DATA_PARALLEL_SIZE": "2"}
    apply_vllm_aliases_to_merged(merged)
    assert merged["DATA_PARALLEL_SIZE"] == "2"

