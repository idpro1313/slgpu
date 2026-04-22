#!/usr/bin/env python3
"""Сравнивает последние summary.json vLLM и SGLang и пишет bench/report.md."""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _latest_summary(engine: str) -> Optional[Path]:
    pattern = str(_root() / "bench" / "results" / engine / "*" / "summary.json")
    paths = glob.glob(pattern)
    if not paths:
        return None
    paths.sort(key=lambda p: os.path.getmtime(p))
    return Path(paths[-1])


def _load(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _index_scenarios(summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in summary.get("scenarios", []):
        name = row.get("name")
        if isinstance(name, str):
            out[name] = row
    return out


def _fmt(x: Any, err_code: Optional[str] = None) -> str:
    if x is None:
        return f"err:{err_code}" if err_code else "—"
    if isinstance(x, float):
        if x != x:  # NaN — legacy (старые summary.json)
            return f"err:{err_code}" if err_code else "nan"
        return f"{x:.4f}"
    return str(x)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vllm", type=Path, help="Путь к summary.json vLLM (по умолчанию — самый новый)")
    ap.add_argument("--sglang", type=Path, help="Путь к summary.json SGLang (по умолчанию — самый новый)")
    args = ap.parse_args()

    v_path = args.vllm or _latest_summary("vllm")
    s_path = args.sglang or _latest_summary("sglang")

    report_path = _root() / "bench" / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("# A/B отчёт vLLM vs SGLang\n")
    lines.append(f"- vLLM summary: `{v_path or '—'}`\n")
    lines.append(f"- SGLang summary: `{s_path or '—'}`\n")

    if not v_path or not s_path:
        lines.append("\n**Недостаточно данных**: нужны оба файла `summary.json`.\n")
        lines.append("Запустите `./slgpu bench vllm -m <preset>` и `./slgpu bench sglang -m <preset>`.\n")
        report_path.write_text("".join(lines), encoding="utf-8")
        print(f"Записано {report_path} (частично)")
        return

    v = _load(v_path)
    s = _load(s_path)
    iv = _index_scenarios(v)
    is_ = _index_scenarios(s)
    names = sorted(set(iv) & set(is_))

    lines.append("\n## Сводка по сценариям\n")
    lines.append(
        "| Сценарий | vLLM TTFT p50 (s) | SGLang TTFT p50 (s) | vLLM TTFT p95 | SGLang TTFT p95 | vLLM RPS | SGLang RPS | Δ RPS (S/v) |\n"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|\n"
    )

    for name in names:
        rv, rs = iv[name], is_[name]
        tv50, sv50 = rv.get("ttft_s_p50"), rs.get("ttft_s_p50")
        tv95, sv95 = rv.get("ttft_s_p95"), rs.get("ttft_s_p95")
        rpv, rps = rv.get("rps"), rs.get("rps")
        ev, es = rv.get("error_code"), rs.get("error_code")
        ratio = ""
        if isinstance(rpv, (int, float)) and isinstance(rps, (int, float)) and rpv == rpv and rps == rps and rpv > 0:
            ratio = f"{(rps / rpv):.3f}"
        lines.append(
            f"| `{name}` | {_fmt(tv50, ev)} | {_fmt(sv50, es)} | {_fmt(tv95, ev)} | {_fmt(sv95, es)} "
            f"| {_fmt(rpv, ev)} | {_fmt(rps, es)} | {ratio} |\n"
        )

    lines.append("\n## Модели в прогонах\n")
    lines.append(f"- vLLM model: `{v.get('model')}` @ `{v.get('base_url')}`\n")
    lines.append(f"- SGLang model: `{s.get('model')}` @ `{s.get('base_url')}`\n")

    report_path.write_text("".join(lines), encoding="utf-8")
    print(f"Записано {report_path}")


if __name__ == "__main__":
    main()
