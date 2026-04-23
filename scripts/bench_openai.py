#!/usr/bin/env python3
"""
Нагрузочный прогон против OpenAI-совместимого /v1/chat/completions (streaming).
Только стандартная библиотека. Длина prompt в символах ~ 4 * prompt_tokens (грубая оценка).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import ssl
import string
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple


def _percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return d0 + d1


def _build_prompt(target_chars: int) -> str:
    # Псевдослучайный текст, чтобы не сжимался идеально компрессией HTTP.
    rng = random.Random(42)
    alphabet = string.ascii_letters + string.digits + " "
    parts: List[str] = []
    cur = 0
    while cur < target_chars:
        chunk_len = min(4096, target_chars - cur)
        parts.append("".join(rng.choice(alphabet) for _ in range(chunk_len)))
        cur += chunk_len
    return "".join(parts)[:target_chars]


def _get_models(base_url: str) -> List[str]:
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, method="GET")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=30.0, context=ctx) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    return [m["id"] for m in data.get("data", [])]


def _resolve_model(base_url: str, override: Optional[str]) -> str:
    if override and override.strip():
        return override.strip()
    models = _get_models(base_url)
    if not models:
        raise RuntimeError("Пустой список моделей от /v1/models")
    return models[0]


def _classify_exception(e: BaseException) -> str:
    """Короткий стабильный код ошибки вместо repr(e).

    Возвращает одну из форм:
      HTTPError:<code>, URLError:<reason>, TimeoutError, ClassName:<short-msg>
    """
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTPError:{e.code}"
    if isinstance(e, urllib.error.URLError):
        reason = getattr(e, "reason", e)
        reason_name = type(reason).__name__ if not isinstance(reason, str) else reason
        return f"URLError:{reason_name}"
    if isinstance(e, TimeoutError):
        return "TimeoutError"
    msg = str(e).splitlines()[0][:80] if str(e) else ""
    name = type(e).__name__
    return f"{name}:{msg}" if msg else name


def _delta_stream_started(delta: Dict[str, Any]) -> bool:
    """Первый чанк, с которого считаем TTFT (совместимо с vLLM и reasoning-моделями).

    vLLM может слать служебные чанки с ``content: ""``; ключ ``content`` при этом уже есть.
    Kimi и др. могут отдавать текст только в ``reasoning_content`` / ``reasoning``.
    """
    if not delta:
        return False
    if "content" in delta:
        return True
    if "reasoning_content" in delta:
        return True
    if "reasoning" in delta:
        return True
    return False


def _delta_text_chunk_count(delta: Dict[str, Any]) -> int:
    """Сколько «выходных» чанков учесть (не более 1 на SSE-кадр, как раньше по content)."""
    content = delta.get("content")
    if isinstance(content, str) and content:
        return 1
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                t = part.get("text")
                if isinstance(t, str) and t:
                    return 1
    for key in ("reasoning_content", "reasoning"):
        v = delta.get(key)
        if isinstance(v, str) and v:
            return 1
    return 0


def _stream_chat(
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    timeout: float = 600.0,
) -> Tuple[float, float, int, Optional[str]]:
    """
    Возвращает (ttft_s, total_s, output_tokens_est, error).
    output_tokens_est: по числу чанков с непустым текстом (content / list[text] / reasoning_*).
    error: короткий код ошибки (HTTP N / no_content / HTTPError:N / URLError:<reason> / <ClassName>[:msg])
           или None при успехе.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.6,
        "stream": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = ssl.create_default_context()
    t0 = time.perf_counter()
    ttft: Optional[float] = None
    out_chunks = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            if resp.getcode() != 200:
                return -1.0, -1.0, 0, f"HTTP {resp.getcode()}"
            # SSE поток
            while True:
                line = resp.readline()
                if not line:
                    break
                line = line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line == "data: [DONE]":
                    break
                if not line.startswith("data:"):
                    continue
                payload_txt = line[len("data:") :].strip()
                try:
                    chunk = json.loads(payload_txt)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                if not isinstance(delta, dict):
                    continue
                if ttft is None and _delta_stream_started(delta):
                    ttft = time.perf_counter()
                out_chunks += _delta_text_chunk_count(delta)
        t1 = time.perf_counter()
        if ttft is None:
            return -1.0, t1 - t0, 0, "no_content"
        return ttft - t0, t1 - t0, max(out_chunks, 1), None
    except Exception as e:  # noqa: BLE001
        return -1.0, time.perf_counter() - t0, 0, _classify_exception(e)


@dataclass
class ScenarioResult:
    name: str
    concurrency: int
    prompt_chars: int
    max_tokens: int
    rounds: int
    ttft_s_p50: Optional[float]
    ttft_s_p95: Optional[float]
    total_s_mean: Optional[float]
    out_tokens_mean: Optional[float]
    rps: float
    errors: int
    error_code: Optional[str] = None
    errors_breakdown: Dict[str, int] = field(default_factory=dict)


def _run_scenario(
    base_url: str,
    model: str,
    name: str,
    concurrency: int,
    prompt_tokens_est: int,
    max_tokens: int,
    rounds: int,
) -> ScenarioResult:
    prompt_chars = max(32, int(prompt_tokens_est * 4))
    ttfts: List[float] = []
    totals: List[float] = []
    outs: List[float] = []
    error_codes: List[str] = []
    wall_total = 0.0
    ok_requests = 0

    def one_call(_: int) -> Tuple[float, float, int, Optional[str]]:
        prompt = _build_prompt(prompt_chars)
        return _stream_chat(base_url, model, prompt, max_tokens)

    for _ in range(rounds):
        t_batch0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = [ex.submit(one_call, i) for i in range(concurrency)]
            for fut in as_completed(futures):
                ttft, total, out_toks, err = fut.result()
                if err:
                    error_codes.append(err)
                    continue
                if ttft >= 0:
                    ttfts.append(ttft)
                    ok_requests += 1
                    totals.append(total)
                    outs.append(float(out_toks))
        t_batch1 = time.perf_counter()
        wall_total += max(1e-9, t_batch1 - t_batch0)

    rps = ok_requests / wall_total if wall_total > 0 else 0.0

    st = sorted(ttfts)
    breakdown: Dict[str, int] = dict(Counter(error_codes))
    top_code: Optional[str] = (
        Counter(error_codes).most_common(1)[0][0] if error_codes else None
    )
    return ScenarioResult(
        name=name,
        concurrency=concurrency,
        prompt_chars=prompt_chars,
        max_tokens=max_tokens,
        rounds=rounds,
        ttft_s_p50=_percentile(st, 50) if ttfts else None,
        ttft_s_p95=_percentile(st, 95) if ttfts else None,
        total_s_mean=(sum(totals) / len(totals)) if totals else None,
        out_tokens_mean=(sum(outs) / len(outs)) if outs else None,
        rps=rps,
        errors=len(error_codes),
        error_code=top_code,
        errors_breakdown=breakdown,
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Нагрузочный бенч против OpenAI API. Параметры ниже задают только клиент бенча; движок настраивается через main.env, пресет и compose."
    )
    ap.add_argument(
        "--base-url",
        required=True,
        help=(
            "Для чего: корневой URL OpenAI-совместимого API (должен оканчиваться на /v1). "
            "Варианты: например http://127.0.0.1:8111/v1 (vLLM) или :8222 (SGLang по умолчанию в slgpu); или URL с тем же путём за прокси."
        ),
    )
    ap.add_argument(
        "--engine",
        required=True,
        help=(
            "Для чего: подпись движка в summary.json и каталогах результатов. "
            "Варианты: строка `vllm` или `sglang` (логическое имя прогона, на сам сервер не влияет)."
        ),
    )
    ap.add_argument(
        "--output-dir",
        required=True,
        help=(
            "Для чего: каталог для JSON по сценариям и summary.json. Варианты: любой существующий/создаваемый путь на диске."
        ),
    )
    ap.add_argument(
        "--rounds",
        type=int,
        default=1,
        help=(
            "Для чего: сколько раз прогнать всю матрицу сценариев подряд. "
            "Варианты: целое ≥1; больше — стабильнее средние, дольше время бенча."
        ),
    )
    ap.add_argument(
        "--warmup-requests",
        type=int,
        default=3,
        help=(
            "Для чего: число коротких запросов перед измерениями (прогрев кэшей/GPU). "
            "Варианты: целое ≥0; 0 — без прогрева."
        ),
    )
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    base = args.base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"

    bench_name = os.environ.get("BENCH_MODEL_NAME")
    model = _resolve_model(base, bench_name.strip() if bench_name else None)

    # Прогрев
    for i in range(args.warmup_requests):
        p = _build_prompt(512)
        _stream_chat(base, model, p, 16)

    raw_scenarios: List[Tuple[str, int, int, int]] = []
    for conc in (1, 8, 32, 128):
        raw_scenarios.extend(
            [
                (f"p512_o256_c{conc}", conc, 512, 256),
                (f"p2048_o512_c{conc}", conc, 2048, 512),
                (f"p8192_o1024_c{conc}", conc, 8192, 1024),
                (f"p512_o2048_c{conc}", conc, 512, 2048),
            ]
        )

    # Уважаем серверный MAX_MODEL_LEN: prompt + max_tokens + safety <= MAX_MODEL_LEN
    safety = 64
    max_model_len_env = os.environ.get("MAX_MODEL_LEN", "").strip()
    try:
        max_model_len = int(max_model_len_env) if max_model_len_env else 0
    except ValueError:
        max_model_len = 0

    scenarios: List[Tuple[str, int, int, int]] = []
    for name, conc, ptoks, mtoks in raw_scenarios:
        if max_model_len and (ptoks + mtoks + safety) > max_model_len:
            new_mtoks = max(64, max_model_len - ptoks - safety)
            print(
                f"[skip-resize] {name}: prompt({ptoks})+out({mtoks})+safety({safety}) > MAX_MODEL_LEN({max_model_len}); out → {new_mtoks}",
                flush=True,
            )
            mtoks = new_mtoks
            if (ptoks + safety) >= max_model_len:
                print(f"[skip] {name}: prompt сам превышает окно — пропуск", flush=True)
                continue
        scenarios.append((name, conc, ptoks, mtoks))

    results: List[Dict[str, Any]] = []
    for name, conc, ptoks, mtoks in scenarios:
        print(f"=== {name} (out={mtoks}) ===", flush=True)
        sr = _run_scenario(base, model, name, conc, ptoks, mtoks, rounds=args.rounds)
        results.append(asdict(sr))
        with open(os.path.join(args.output_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump(asdict(sr), f, indent=2)

    summary = {
        "engine": args.engine,
        "base_url": base,
        "model": model,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scenarios": results,
    }
    with open(os.path.join(args.output_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
