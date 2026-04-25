"""Whitelist coverage for the CLI argument validators."""

from __future__ import annotations

import pytest

from app.core.security import (
    ValidationError,
    validate_engine,
    validate_hf_id,
    validate_port,
    validate_revision,
    validate_slug,
    validate_slug_or_hf_id,
    validate_tp,
)


def test_engine_allows_known_values():
    assert validate_engine("vllm") == "vllm"
    assert validate_engine("sglang") == "sglang"


def test_engine_rejects_unknown():
    with pytest.raises(ValidationError):
        validate_engine("trtllm")


@pytest.mark.parametrize(
    "value",
    [
        "qwen3.6-35b-a3b",
        "deepseek-v4-pro",
        "minimax-m2",
        "ds-r1",
    ],
)
def test_slug_accepts_valid_names(value: str):
    assert validate_slug(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "Qwen/Qwen3.6-35B-A3B",
        "../escape",
        "with spaces",
        "semi;colon",
        "ampers&and",
        "$injection",
    ],
)
def test_slug_rejects_unsafe(value: str):
    with pytest.raises(ValidationError):
        validate_slug(value)


@pytest.mark.parametrize(
    "value",
    [
        "Qwen/Qwen3.6-35B-A3B",
        "deepseek-ai/DeepSeek-V3",
        "meta-llama/Llama-4-70B",
    ],
)
def test_hf_id_accepts(value: str):
    assert validate_hf_id(value) == value


@pytest.mark.parametrize("value", ["nope", "/nope", "Qwen/", "Qwen Qwen3", "x;y/z"])
def test_hf_id_rejects(value: str):
    with pytest.raises(ValidationError):
        validate_hf_id(value)


def test_slug_or_hf_id_routes_correctly():
    assert validate_slug_or_hf_id("Qwen/Qwen3.6-35B-A3B")
    assert validate_slug_or_hf_id("qwen3.6-35b-a3b")


def test_port_range():
    assert validate_port(1) == 1
    assert validate_port(65535) == 65535
    with pytest.raises(ValidationError):
        validate_port(0)
    with pytest.raises(ValidationError):
        validate_port(70000)


def test_tp_range():
    assert validate_tp(8) == 8
    with pytest.raises(ValidationError):
        validate_tp(0)
    with pytest.raises(ValidationError):
        validate_tp(200)


def test_revision_rejects_unsafe():
    assert validate_revision("main") == "main"
    assert validate_revision("v1.0.0")
    with pytest.raises(ValidationError):
        validate_revision("v1 ; rm -rf /")
