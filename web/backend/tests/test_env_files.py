"""Round-trip parsing of slgpu preset .env files."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.env_files import (
    hf_id_to_slug,
    parse_env_text,
    render_env_text,
    write_preset_file,
)


def test_parse_env_text_handles_comments_and_quotes():
    raw = (
        "# header\n"
        "MODEL_ID=Qwen/Qwen3.6-35B-A3B\n"
        "MAX_MODEL_LEN=262144\n"
        'TOOL_CALL_PARSER="qwen3_xml"\n'
        "EMPTY=\n"
        "  KV_CACHE_DTYPE = fp8_e4m3 \n"
        "# trailing comment\n"
    )
    parsed = parse_env_text(raw)
    assert parsed["MODEL_ID"] == "Qwen/Qwen3.6-35B-A3B"
    assert parsed["MAX_MODEL_LEN"] == "262144"
    assert parsed["TOOL_CALL_PARSER"] == "qwen3_xml"
    assert parsed["KV_CACHE_DTYPE"] == "fp8_e4m3"
    assert parsed["EMPTY"] == ""


def test_render_env_text_groups_keys():
    rendered = render_env_text(
        {
            "MODEL_ID": "Qwen/Qwen3.6-35B-A3B",
            "MAX_MODEL_LEN": "262144",
            "TP": "8",
            "TOOL_CALL_PARSER": "qwen3_xml",
            "TORCH_FLOAT32_MATMUL_PRECISION": "high",
            "VLLM_USE_V1": "1",
            "EXTRA_FLAG": "1",
        },
        header="auto-generated",
    )
    assert "# auto-generated" in rendered
    assert "MODEL_ID=Qwen/Qwen3.6-35B-A3B" in rendered
    assert "MAX_MODEL_LEN=262144" in rendered
    assert "TORCH_FLOAT32_MATMUL_PRECISION=high" in rendered
    assert "VLLM_USE_V1=1" in rendered
    assert rendered.endswith("\n")


def test_render_env_text_quotes_when_whitespace():
    rendered = render_env_text({"NOTE": "hello world"})
    assert 'NOTE="hello world"' in rendered


@pytest.mark.parametrize(
    ("hf_id", "expected"),
    [
        ("Qwen/Qwen3.6-35B-A3B", "qwen3.6-35b-a3b"),
        ("deepseek-ai/DeepSeek_V3", "deepseek-v3"),
        ("just-name", "just-name"),
    ],
)
def test_hf_id_to_slug(hf_id: str, expected: str):
    assert hf_id_to_slug(hf_id) == expected


def test_write_preset_file_round_trips(tmp_path: Path):
    target = write_preset_file(
        tmp_path,
        "demo-preset",
        {"MODEL_ID": "Qwen/Qwen3.6-35B-A3B", "TP": "8", "MAX_MODEL_LEN": "262144"},
    )
    text = target.read_text(encoding="utf-8")
    parsed = parse_env_text(text)
    assert parsed["MODEL_ID"] == "Qwen/Qwen3.6-35B-A3B"
    assert parsed["TP"] == "8"
    assert parsed["MAX_MODEL_LEN"] == "262144"
