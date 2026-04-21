#!/usr/bin/env python3
"""
Длительный нагрузочный тест с эмуляцией 200-300 виртуальных пользователей.
Фазы: ramp-up -> steady -> ramp-down.
Сбор time-series метрик (throughput, TTFT, latency, error rate).
Только стандартная библиотека.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import queue
import random
import ssl
import string
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple


# START_MODULE_CONTRACT
#   PURPOSE: Длительный нагрузочный тест с эмуляцией виртуальных пользователей через
#            фазы ramp-up/steady/ramp-down, сбором time-series метрик производительности.
#   SCOPE: HTTP streaming-запросы к /v1/chat/completions, CSV time-series, JSON summary, per-user JSONL.
#   DEPENDS: M-LIB (env loading), M-UP (running engine API)
#   LINKS: grace/knowledge-graph/knowledge-graph.xml -> M-LOAD
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   run_load_test      - основной entry point для длительного бенча
#   _stream_chat       - один streaming-запрос к API
#   _build_prompt      - генерация pseudo-случайного prompt заданной длины
#   _percentile        - расчёт перцентиля
#   MetricCollector    - поток-сборщик метрик каждые N секунд
#   UserWorker         - поток виртуального пользователя
# END_MODULE_MAP


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


def _stream_chat(
    base_url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    timeout: float = 600.0,
) -> Tuple[float, float, int, Optional[str]]:
    """
    Возвращает (ttft_s, total_s, output_tokens_est, error).
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
                payload_txt = line[len("data:"):].strip()
                try:
                    chunk = json.loads(payload_txt)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    if ttft is None:
                        ttft = time.perf_counter()
                    out_chunks += 1
        t1 = time.perf_counter()
        if ttft is None:
            return -1.0, t1 - t0, 0, "no_content"
        return ttft - t0, t1 - t0, max(out_chunks, 1), None
    except Exception as e:
        err_str = repr(e)
        print(f"[ERROR][_stream_chat] {err_str}", flush=True)
        return -1.0, time.perf_counter() - t0, 0, err_str


@dataclass
class RequestResult:
    ts_start: float
    ts_end: float
    ttft_s: float
    total_s: float
    out_tokens: int
    error: Optional[str]


@dataclass
class WindowMetrics:
    timestamp: float
    phase: str
    active_users: int
    requests_total: int = 0
    requests_ok: int = 0
    requests_err: int = 0
    ttft_p50_ms: float = float("nan")
    ttft_p95_ms: float = float("nan")
    latency_p50_ms: float = float("nan")
    latency_p95_ms: float = float("nan")
    throughput_rps: float = float("nan")
    tokens_per_sec: float = float("nan")
    error_rate: float = float("nan")
    prompt_tokens: int = 0
    output_tokens: int = 0


@dataclass
class UserState:
    uid: int
    active: bool = False
    results: List[RequestResult] = field(default_factory=list)
    total_requests: int = 0
    ok_requests: int = 0
    err_requests: int = 0


@dataclass
class LoadTestSummary:
    engine: str
    base_url: str
    model: str
    users: int
    ramp_up_sec: int
    steady_sec: int
    ramp_down_sec: int
    total_duration_sec: float
    total_requests: int
    ok_requests: int
    err_requests: int
    ttft_p50_ms: float
    ttft_p95_ms: float
    latency_p50_ms: float
    latency_p95_ms: float
    throughput_rps: float
    tokens_per_sec: float
    error_rate: float
    phases_summary: Dict[str, Any]
    timestamp: str


class MetricCollector:
    """Поток-сборщик метрик каждые report_interval секунд."""

    def __init__(self, report_interval: float, output_dir: str):
        self.report_interval = report_interval
        self.output_dir = output_dir
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._metrics: List[WindowMetrics] = []

    @property
    def metrics(self) -> List[WindowMetrics]:
        with self._lock:
            return list(self._metrics)

    @property
    def csv_path(self) -> str:
        return os.path.join(self.output_dir, "time_series.csv")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "phase", "active_users", "requests_total",
                "requests_ok", "requests_err", "throughput_rps",
                "ttft_p50_ms", "ttft_p95_ms", "latency_p50_ms", "latency_p95_ms",
                "tokens_per_sec", "error_rate",
            ])
            while not self._stop_event.wait(timeout=self.report_interval):
                wm = self._collect_current_window()
                with self._lock:
                    self._metrics.append(wm)
                writer.writerow([
                    f"{wm.timestamp:.3f}", wm.phase, wm.active_users,
                    wm.requests_total, wm.requests_ok, wm.requests_err,
                    f"{wm.throughput_rps:.3f}",
                    f"{wm.ttft_p50_ms:.3f}", f"{wm.ttft_p95_ms:.3f}",
                    f"{wm.latency_p50_ms:.3f}", f"{wm.latency_p95_ms:.3f}",
                    f"{wm.tokens_per_sec:.3f}", f"{wm.error_rate:.4f}",
                ])
                f.flush()

    def _collect_current_window(self) -> WindowMetrics:
        # Этот метод будет переопределён извне для доступа к общим данным.
        return WindowMetrics(timestamp=time.time(), phase="unknown", active_users=0)


class LoadTestRunner:
    """Оркестратор длительного бенча с фазами."""

    def __init__(
        self,
        base_url: str,
        model: str,
        engine: str,
        output_dir: str,
        users: int = 250,
        ramp_up_sec: int = 120,
        steady_sec: int = 900,
        ramp_down_sec: int = 60,
        think_time_ms: Tuple[int, int] = (2000, 5000),
        max_prompt_tokens: int = 512,
        max_output_tokens: int = 256,
        report_interval: float = 5.0,
    ):
        self.base_url = base_url
        self.model = model
        self.engine = engine
        self.output_dir = output_dir
        self.users = users
        self.ramp_up_sec = ramp_up_sec
        self.steady_sec = steady_sec
        self.ramp_down_sec = ramp_down_sec
        self.think_time_ms = think_time_ms
        self.max_prompt_tokens = max_prompt_tokens
        self.max_output_tokens = max_output_tokens
        self.report_interval = report_interval

        self._prompt_chars = max(32, int(max_prompt_tokens * 4))
        self._users: List[UserState] = [UserState(uid=i) for i in range(users)]
        self._active_count = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._phase = "idle"
        self._phase_start_time = 0.0
        self._collector: Optional[MetricCollector] = None
        self._total_requests_since_start = 0
        self._ok_requests_since_start = 0
        self._err_requests_since_start = 0
        self._last_report_time = 0.0
        self._snapshot_total = 0
        self._snapshot_ok = 0
        self._snapshot_err = 0

    def _current_phase(self, elapsed: float) -> str:
        if elapsed < self.ramp_up_sec:
            return "ramp_up"
        if elapsed < self.ramp_up_sec + self.steady_sec:
            return "steady"
        if elapsed < self.ramp_up_sec + self.steady_sec + self.ramp_down_sec:
            return "ramp_down"
        return "done"

    def _target_active_users(self, phase: str, elapsed: float) -> int:
        if phase == "ramp_up":
            frac = elapsed / self.ramp_up_sec if self.ramp_up_sec > 0 else 1.0
            return max(1, int(self.users * min(1.0, frac)))
        if phase == "steady":
            return self.users
        if phase == "ramp_down":
            steady_end = self.ramp_up_sec + self.steady_sec
            frac = (elapsed - steady_end) / self.ramp_down_sec if self.ramp_down_sec > 0 else 1.0
            return max(0, int(self.users * max(0.0, 1.0 - frac)))
        return 0

    def _user_worker(self, user: UserState) -> None:
        rng = random.Random(user.uid + 12345)
        while not self._stop_event.is_set():
            with self._lock:
                active = user.active
            if not active:
                time.sleep(0.5)
                continue

            think = rng.randint(self.think_time_ms[0], self.think_time_ms[1]) / 1000.0
            time.sleep(think)

            if self._stop_event.is_set():
                break

            prompt = _build_prompt(self._prompt_chars)
            ts_start = time.perf_counter()
            ttft_s, total_s, out_toks, err = _stream_chat(
                self.base_url, self.model, prompt, self.max_output_tokens
            )
            ts_end = time.perf_counter()

            res = RequestResult(
                ts_start=ts_start, ts_end=ts_end,
                ttft_s=ttft_s, total_s=total_s,
                out_tokens=out_toks, error=err,
            )

            with self._lock:
                user.results.append(res)
                user.total_requests += 1
                if err:
                    user.err_requests += 1
                else:
                    user.ok_requests += 1
                self._total_requests_since_start += 1
                if err:
                    self._err_requests_since_start += 1
                else:
                    self._ok_requests_since_start += 1

    def _phase_controller(self) -> None:
        """Контроллер: переключает фазы и включает/выключает пользователей."""
        t0 = time.perf_counter()
        self._phase_start_time = t0
        while not self._stop_event.is_set():
            elapsed = time.perf_counter() - t0
            phase = self._current_phase(elapsed)
            self._phase = phase
            target = self._target_active_users(phase, elapsed)
            with self._lock:
                self._active_count = target
                for i in range(self.users):
                    self._users[i].active = i < target
            if phase == "done":
                self._stop_event.set()
                break
            time.sleep(0.5)

    def _collect_window(self) -> WindowMetrics:
        now = time.perf_counter()
        with self._lock:
            phase = self._phase
            active = self._active_count
        ttfts: List[float] = []
        totals: List[float] = []
        total_tokens = 0
        total_reqs = 0
        ok_reqs = 0
        err_reqs = 0
        with self._lock:
            for u in self._users:
                for r in u.results:
                    total_reqs += 1
                    if r.error:
                        err_reqs += 1
                    else:
                        ok_reqs += 1
                        if r.ttft_s >= 0:
                            ttfts.append(r.ttft_s * 1000)
                        if r.total_s >= 0:
                            totals.append(r.total_s * 1000)
                        total_tokens += r.out_tokens
            total_since_last = self._total_requests_since_start - self._snapshot_total
            ok_since_last = self._ok_requests_since_start - self._snapshot_ok
            err_since_last = self._err_requests_since_start - self._snapshot_err
            self._snapshot_total = self._total_requests_since_start
            self._snapshot_ok = self._ok_requests_since_start
            self._snapshot_err = self._err_requests_since_start

        interval = now - self._last_report_time if self._last_report_time > 0 else self.report_interval
        self._last_report_time = now
        rps = total_since_last / interval if interval > 0 else float("nan")
        tps = total_tokens / interval if interval > 0 else float("nan")
        st_ttft = sorted(ttfts)
        st_total = sorted(totals)
        return WindowMetrics(
            timestamp=now,
            phase=phase,
            active_users=active,
            requests_total=total_reqs,
            requests_ok=ok_reqs,
            requests_err=err_reqs,
            throughput_rps=rps,
            ttft_p50_ms=_percentile(st_ttft, 50),
            ttft_p95_ms=_percentile(st_ttft, 95),
            latency_p50_ms=_percentile(st_total, 50),
            latency_p95_ms=_percentile(st_total, 95),
            tokens_per_sec=tps,
            error_rate=err_reqs / total_reqs if total_reqs > 0 else 0.0,
        )

    def run(self) -> LoadTestSummary:
        print(f"[LOAD] Запуск: users={self.users}, ramp_up={self.ramp_up_sec}s, "
              f"steady={self.steady_sec}s, ramp_down={self.ramp_down_sec}s", flush=True)

        os.makedirs(self.output_dir, exist_ok=True)

        self._collector = MetricCollector(self.report_interval, self.output_dir)
        self._collector._collect_current_window = self._collect_window  # type: ignore
        self._collector.start()

        phase_thread = threading.Thread(target=self._phase_controller, daemon=True)
        phase_thread.start()

        t0 = time.perf_counter()
        user_threads: List[threading.Thread] = []
        for u in self._users:
            t = threading.Thread(target=self._user_worker, args=(u,), daemon=True)
            t.start()
            user_threads.append(t)

        # Ждём завершения фаз
        phase_thread.join(timeout=self.ramp_up_sec + self.steady_sec + self.ramp_down_sec + 30)

        total_duration = time.perf_counter() - t0

        # Выключаем сборщика
        self._collector.stop()

        # Даём пользователям завершить текущие запросы
        time.sleep(2.0)
        self._stop_event.set()
        for t in user_threads:
            t.join(timeout=10.0)

        summary = self._build_summary(total_duration)
        self._write_outputs(summary)
        return summary

    def _build_summary(self, total_duration: float) -> LoadTestSummary:
        all_ttft: List[float] = []
        all_total: List[float] = []
        total_tokens = 0
        total_reqs = 0
        ok_reqs = 0
        err_reqs = 0
        phase_stats: Dict[str, Dict[str, Any]] = {}

        for u in self._users:
            for r in u.results:
                total_reqs += 1
                if r.error:
                    err_reqs += 1
                else:
                    ok_reqs += 1
                    if r.ttft_s >= 0:
                        all_ttft.append(r.ttft_s * 1000)
                    if r.total_s >= 0:
                        all_total.append(r.total_s * 1000)
                    total_tokens += r.out_tokens

        st_ttft = sorted(all_ttft)
        st_total = sorted(all_total)

        return LoadTestSummary(
            engine=self.engine,
            base_url=self.base_url,
            model=self.model,
            users=self.users,
            ramp_up_sec=self.ramp_up_sec,
            steady_sec=self.steady_sec,
            ramp_down_sec=self.ramp_down_sec,
            total_duration_sec=total_duration,
            total_requests=total_reqs,
            ok_requests=ok_reqs,
            err_requests=err_reqs,
            ttft_p50_ms=_percentile(st_ttft, 50),
            ttft_p95_ms=_percentile(st_ttft, 95),
            latency_p50_ms=_percentile(st_total, 50),
            latency_p95_ms=_percentile(st_total, 95),
            throughput_rps=total_reqs / total_duration if total_duration > 0 else float("nan"),
            tokens_per_sec=total_tokens / total_duration if total_duration > 0 else float("nan"),
            error_rate=err_reqs / total_reqs if total_reqs > 0 else 0.0,
            phases_summary=phase_stats,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def _write_outputs(self, summary: LoadTestSummary) -> None:
        # JSON summary
        with open(os.path.join(self.output_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(asdict(summary), f, indent=2, ensure_ascii=False)

        # Per-user JSONL
        with open(os.path.join(self.output_dir, "users.jsonl"), "w", encoding="utf-8") as f:
            for u in self._users:
                f.write(json.dumps({
                    "uid": u.uid,
                    "total_requests": u.total_requests,
                    "ok_requests": u.ok_requests,
                    "err_requests": u.err_requests,
                    "results": [
                        {
                            "ts_start": r.ts_start,
                            "ttft_ms": round(r.ttft_s * 1000, 3) if r.ttft_s >= 0 else None,
                            "total_ms": round(r.total_s * 1000, 3) if r.total_s >= 0 else None,
                            "out_tokens": r.out_tokens,
                            "error": r.error,
                        }
                        for r in u.results
                    ],
                }, ensure_ascii=False) + "\n")

        # CSV time-series уже записан MetricCollector
        print(f"[LOAD] Результаты: {self.output_dir}", flush=True)
        print(f"[LOAD] summary: {os.path.join(self.output_dir, 'summary.json')}", flush=True)
        print(f"[LOAD] time-series: {self._collector.csv_path}", flush=True)
        print(f"[LOAD] per-user: {os.path.join(self.output_dir, 'users.jsonl')}", flush=True)


def main() -> None:
    # START_CHANGE_SUMMARY
    #   LAST_CHANGE: v1.1.0 - Создан bench_load.py для длительных нагрузочных тестов 200-300 пользователей.
    # END_CHANGE_SUMMARY

    ap = argparse.ArgumentParser(
        description="Длительный нагрузочный тест с эмуляцией виртуальных пользователей."
    )
    ap.add_argument("--base-url", required=True, help="URL OpenAI API (с /v1)")
    ap.add_argument("--engine", required=True, help="Подпись движка (vllm/sglang)")
    ap.add_argument("--output-dir", required=True, help="Каталог для результатов")
    ap.add_argument("--users", type=int, default=250, help="Целевое число виртуальных пользователей")
    ap.add_argument("--duration", type=int, default=900, help="Длительность steady фазы (сек)")
    ap.add_argument("--ramp-up", type=int, default=120, help="Длительность ramp-up (сек)")
    ap.add_argument("--ramp-down", type=int, default=60, help="Длительность ramp-down (сек)")
    ap.add_argument("--think-time", type=str, default="2000,5000",
                    help="Задержка между запросами пользователя 'min,max' (ms)")
    ap.add_argument("--max-prompt-tokens", type=int, default=512, help="Макс длина prompt (токенов)")
    ap.add_argument("--max-output-tokens", type=int, default=256, help="Макс длина output (токенов)")
    ap.add_argument("--report-interval", type=float, default=5.0,
                    help="Интервал записи метрик в CSV (сек)")
    ap.add_argument("--warmup-requests", type=int, default=3,
                    help="Число warmup запросов перед измерениями")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"

    bench_name = os.environ.get("BENCH_MODEL_NAME")
    model = _resolve_model(base, bench_name.strip() if bench_name else None)

    # Warmup с проверкой
    for i in range(args.warmup_requests):
        p = _build_prompt(512)
        ttft_s, total_s, out_toks, err = _stream_chat(base, model, p, 16)
        if err:
            print(f"[warmup] {i + 1}/{args.warmup_requests} FAILED: {err}", flush=True)
        else:
            print(f"[warmup] {i + 1}/{args.warmup_requests} OK (ttft={ttft_s:.3f}s, total={total_s:.3f}s)", flush=True)

    think_parts = args.think_time.split(",")
    think_min = int(think_parts[0].strip())
    think_max = int(think_parts[1].strip()) if len(think_parts) > 1 else think_min

    runner = LoadTestRunner(
        base_url=base,
        model=model,
        engine=args.engine,
        output_dir=args.output_dir,
        users=args.users,
        ramp_up_sec=args.ramp_up,
        steady_sec=args.duration,
        ramp_down_sec=args.ramp_down,
        think_time_ms=(think_min, think_max),
        max_prompt_tokens=args.max_prompt_tokens,
        max_output_tokens=args.max_output_tokens,
        report_interval=args.report_interval,
    )
    runner.run()


if __name__ == "__main__":
    main()
