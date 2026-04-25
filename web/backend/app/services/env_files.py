"""Read and write `configs/models/<slug>.env` preset files.

The format is intentionally minimal: lines like `KEY=VALUE`, with
comments starting at `#`. Values are NOT shell-quoted because the
existing slgpu CLI sources these files directly with `set -a` and
`source`, and we want to remain byte-compatible with what already
ships in the repository.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.core.security import validate_slug

_VAR_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


@dataclass
class EnvFile:
    slug: str
    path: Path
    values: dict[str, str]
    raw: str

    @property
    def hf_id(self) -> str | None:
        return self.values.get("MODEL_ID")


def parse_env_text(text: str) -> dict[str, str]:
    """Parse a slgpu preset .env text into a dict.

    Strips inline comments only when they follow whitespace, to avoid
    eating literal `#` inside values that are quoted JSON strings.
    """

    out: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _VAR_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'") and len(value) >= 2:
            value = value[1:-1]
        out[key] = value
    return out


def parse_env_file(path: Path) -> EnvFile:
    raw = path.read_text(encoding="utf-8")
    return EnvFile(
        slug=path.stem,
        path=path,
        values=parse_env_text(raw),
        raw=raw,
    )


def list_preset_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*.env") if p.is_file())


def load_all_presets(directory: Path) -> Iterable[EnvFile]:
    for path in list_preset_files(directory):
        try:
            yield parse_env_file(path)
        except OSError:
            continue


def render_env_text(values: dict[str, str], header: str | None = None) -> str:
    """Render a dict back into the slgpu preset .env format.

    Order is stable and grouped: identity, runtime, vLLM-only, SGLang-only,
    everything else. Values containing whitespace are quoted with
    double quotes; existing quotes are escaped with a backslash.
    """

    lines: list[str] = []
    if header:
        for header_line in header.splitlines():
            lines.append(f"# {header_line}".rstrip())
        lines.append("")

    groups: list[tuple[str, list[str]]] = [
        ("Identity", ["VLLM_DOCKER_IMAGE", "MODEL_ID", "MODEL_REVISION", "SLGPU_SERVED_MODEL_NAME"]),
        ("Runtime", ["MAX_MODEL_LEN", "TP", "KV_CACHE_DTYPE", "GPU_MEM_UTIL"]),
        (
            "vLLM",
            [
                "SLGPU_MAX_NUM_BATCHED_TOKENS",
                "SLGPU_VLLM_MAX_NUM_SEQS",
                "SLGPU_VLLM_BLOCK_SIZE",
                "SLGPU_DISABLE_CUSTOM_ALL_REDUCE",
                "SLGPU_ENABLE_PREFIX_CACHING",
                "SLGPU_ENABLE_EXPERT_PARALLEL",
                "SLGPU_VLLM_DATA_PARALLEL_SIZE",
                "SLGPU_VLLM_ATTENTION_BACKEND",
                "SLGPU_VLLM_TOKENIZER_MODE",
                "SLGPU_VLLM_COMPILATION_CONFIG",
                "SLGPU_VLLM_ENFORCE_EAGER",
                "SLGPU_VLLM_SPECULATIVE_CONFIG",
                "MM_ENCODER_TP_MODE",
                "TOOL_CALL_PARSER",
                "REASONING_PARSER",
                "CHAT_TEMPLATE_CONTENT_FORMAT",
                "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS",
            ],
        ),
        (
            "SGLang",
            [
                "SGLANG_MEM_FRACTION_STATIC",
                "SGLANG_CUDA_GRAPH_MAX_BS",
                "SGLANG_ENABLE_TORCH_COMPILE",
                "SGLANG_DISABLE_CUDA_GRAPH",
                "SGLANG_DISABLE_CUSTOM_ALL_REDUCE",
            ],
        ),
        ("Bench", ["BENCH_MODEL_NAME"]),
    ]

    seen: set[str] = set()
    for title, keys in groups:
        present = [(k, values[k]) for k in keys if k in values and values[k] != ""]
        if not present:
            continue
        lines.append(f"# --- {title} ---")
        for key, value in present:
            lines.append(_render_pair(key, value))
            seen.add(key)
        lines.append("")

    extras = sorted(k for k in values if k not in seen and values[k] != "")
    if extras:
        lines.append("# --- Extra ---")
        for key in extras:
            lines.append(_render_pair(key, values[key]))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_pair(key: str, value: str) -> str:
    if value == "":
        return f"{key}="
    needs_quote = any(ch.isspace() for ch in value) or "#" in value
    if needs_quote:
        escaped = value.replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={value}"


def write_preset_file(directory: Path, slug: str, values: dict[str, str], header: str | None = None) -> Path:
    validate_slug(slug)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{slug}.env"
    target.write_text(render_env_text(values, header=header), encoding="utf-8")
    return target


def hf_id_to_slug(hf_id: str) -> str:
    """Mirror of `slgpu_hf_id_to_slug` in scripts/_lib.sh.

    Lowercase the HF repo name, replace underscores with dashes, drop
    the org prefix.
    """

    if "/" in hf_id:
        _, repo = hf_id.split("/", 1)
    else:
        repo = hf_id
    return repo.lower().replace("_", "-")
