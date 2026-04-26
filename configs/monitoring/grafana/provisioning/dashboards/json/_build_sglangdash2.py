"""vllmdash2.json -> sglangdash2-slgpu.json (SGLang метрики, provisioning prometheus)."""
import json
from pathlib import Path

HERE = Path(__file__).parent
# Эталон vLLM V2 вне auto-provisioning: ../templates/vllmdash2.json
SRC = HERE.parents[2] / "templates" / "vllmdash2.json"
DST = HERE / "sglangdash2-slgpu.json"

SEL = 'job="sglang",instance=~"$instance",model_name=~"$model_name"'

# Точные expr из vllmdash2 (после json.load), -> sglang
EXACT = {
    '(sum(rate(vllm:request_success_total{finished_reason=~"stop|length", model_name="$model_name"}[5m])) / clamp_min(sum(rate(vllm:request_success_total{model_name="$model_name"}[5m])), 0.001)) * 100': f"(1 - (sum(rate(sglang:num_aborted_requests_total{{{SEL}}}[5m])) / clamp_min(sum(rate(sglang:num_requests_total{{{SEL}}}[5m])), 0.001))) * 100",
    'sum(vllm:num_requests_running{model_name="$model_name"}) + sum(vllm:num_requests_waiting{model_name="$model_name"})': f"sum(sglang:num_running_reqs{{{SEL}}}) + sum(sglang:num_queue_reqs{{{SEL}}})",
    'clamp_max((sum(vllm:num_requests_running{model_name="$model_name"}) + 0.001) / (sum(vllm:num_requests_running{model_name="$model_name"}) + sum(vllm:num_requests_waiting{model_name="$model_name"}) + 0.001), 1)': f"clamp_max((sum(sglang:num_running_reqs{{{SEL}}}) + 0.001) / (sum(sglang:num_running_reqs{{{SEL}}}) + sum(sglang:num_queue_reqs{{{SEL}}}) + 0.001), 1)",
    'histogram_quantile(0.99, sum(rate(vllm:time_to_first_token_seconds_bucket{model_name="$model_name"}[5m])) by (le))': f"histogram_quantile(0.99, sum(rate(sglang:time_to_first_token_seconds_bucket{{{SEL}}}[5m])) by (le))",
    'sum(rate(vllm:num_preemptions_total{model_name="$model_name"}[5m]))': f"sum(rate(sglang:num_retracted_requests_total{{{SEL}}}[5m]))",
    'histogram_quantile(0.99, sum by(le) (rate(vllm:e2e_request_latency_seconds_bucket{model_name="$model_name"}[$__rate_interval])))': f"histogram_quantile(0.99, sum by(le) (rate(sglang:e2e_request_latency_seconds_bucket{{{SEL}}}[$__rate_interval])))",
    'histogram_quantile(0.95, sum by(le) (rate(vllm:e2e_request_latency_seconds_bucket{model_name="$model_name"}[$__rate_interval])))': f"histogram_quantile(0.95, sum by(le) (rate(sglang:e2e_request_latency_seconds_bucket{{{SEL}}}[$__rate_interval])))",
    'histogram_quantile(0.5, sum by(le) (rate(vllm:e2e_request_latency_seconds_bucket{model_name="$model_name"}[$__rate_interval])))': f"histogram_quantile(0.5, sum by(le) (rate(sglang:e2e_request_latency_seconds_bucket{{{SEL}}}[$__rate_interval])))",
    'rate(vllm:request_prefill_time_seconds_sum{model_name="$model_name"}[5m]) / clamp_min(rate(vllm:request_prefill_time_seconds_count{model_name="$model_name"}[5m]), 0.001)': f"rate(sglang:time_to_first_token_seconds_sum{{{SEL}}}[5m]) / clamp_min(rate(sglang:time_to_first_token_seconds_count{{{SEL}}}[5m]), 0.001)",
    'rate(vllm:request_decode_time_seconds_sum{model_name="$model_name"}[5m]) / clamp_min(rate(vllm:request_decode_time_seconds_count{model_name="$model_name"}[5m]), 0.001)': f"rate(sglang:inter_token_latency_seconds_sum{{{SEL}}}[5m]) / clamp_min(rate(sglang:inter_token_latency_seconds_count{{{SEL}}}[5m]), 0.001)",
    'histogram_quantile(0.99, sum by(le) (rate(vllm:time_to_first_token_seconds_bucket{model_name="$model_name"}[$__rate_interval])))': f"histogram_quantile(0.99, sum by(le) (rate(sglang:time_to_first_token_seconds_bucket{{{SEL}}}[$__rate_interval])))",
    'histogram_quantile(0.99, sum by(le) (rate(vllm:request_time_per_output_token_seconds_bucket{model_name="$model_name"}[$__rate_interval])))': f"histogram_quantile(0.99, sum by(le) (rate(sglang:inter_token_latency_seconds_bucket{{{SEL}}}[$__rate_interval])))",
    'sum(rate(vllm:prompt_tokens_total{model_name="$model_name"}[$__rate_interval]))': f"sum(rate(sglang:prompt_tokens_total{{{SEL}}}[$__rate_interval]))",
    'sum(rate(vllm:generation_tokens_total{model_name="$model_name"}[$__rate_interval]))': f"sum(rate(sglang:generation_tokens_total{{{SEL}}}[$__rate_interval]))",
    'sum(rate(vllm:prompt_tokens_total{model_name="$model_name"}[5m])) / clamp_min(sum(rate(vllm:generation_tokens_total{model_name="$model_name"}[5m])), 0.001)': f"sum(rate(sglang:prompt_tokens_total{{{SEL}}}[5m])) / clamp_min(sum(rate(sglang:generation_tokens_total{{{SEL}}}[5m])), 0.001)",
    '(1 - (sum(rate(vllm:request_prefill_kv_computed_tokens_sum{model_name="$model_name"}[5m])) / clamp_min(sum(rate(vllm:prompt_tokens_total{model_name="$model_name"}[5m])), 1))) * 100': f"(sum(rate(sglang:cached_tokens_total{{{SEL}}}[5m])) / clamp_min(sum(rate(sglang:prompt_tokens_total{{{SEL}}}[5m])), 1)) * 100",
    'sum by(le) (increase(vllm:request_prompt_tokens_bucket{model_name="$model_name"}[$__rate_interval]))': f"sum by(le) (increase(sglang:prompt_tokens_histogram_bucket{{{SEL}}}[$__rate_interval]))",
    'histogram_quantile(0.99, sum by(le) (rate(vllm:request_queue_time_seconds_bucket{model_name="$model_name"}[$__rate_interval])))': f"histogram_quantile(0.99, sum by(le) (rate(sglang:queue_time_seconds_bucket{{{SEL}}}[$__rate_interval])))",
    'histogram_quantile(0.5, sum by(le) (rate(vllm:request_queue_time_seconds_bucket{model_name="$model_name"}[$__rate_interval])))': f"histogram_quantile(0.5, sum by(le) (rate(sglang:queue_time_seconds_bucket{{{SEL}}}[$__rate_interval])))",
    'vllm:kv_cache_usage_perc{model_name="$model_name"}': f"sglang:token_usage{{{SEL}}}",
    'sum(rate(vllm:prefix_cache_hits_total{model_name="$model_name"}[5m])) / clamp_min(sum(rate(vllm:prefix_cache_queries_total{model_name="$model_name"}[5m])), 1)': f"sglang:cache_hit_rate{{{SEL}}}",
    'vllm:num_requests_running{model_name="$model_name"}': f"sglang:num_running_reqs{{{SEL}}}",
    'vllm:num_requests_waiting{model_name="$model_name"}': f"sglang:num_queue_reqs{{{SEL}}}",
    'vllm:num_requests_swapped{model_name="$model_name"}': f"sglang:num_retracted_reqs{{{SEL}}}",
    "rate(python_gc_collections_total[5m])": f"rate(python_gc_collections_total{{{SEL}}}[5m])",
    "process_resident_memory_bytes": f"process_resident_memory_bytes{{{SEL}}}",
    'sum by(finished_reason) (increase(vllm:request_success_total{model_name="$model_name"}[$__range]))': f"sum(increase(sglang:num_aborted_requests_total{{{SEL}}}[$__range]))",
    'sum(rate(vllm:e2e_request_latency_seconds_count{model_name="$model_name"}[5m]))': f"sum(rate(sglang:e2e_request_latency_seconds_count{{{SEL}}}[5m]))",
    'sum(rate(vllm:request_success_total{model_name="$model_name"}[5m]))': f"sum(rate(sglang:num_requests_total{{{SEL}}}[5m])) - sum(rate(sglang:num_aborted_requests_total{{{SEL}}}[5m]))",
}


def walk_replace_expr(x, missing):
    if isinstance(x, dict):
        if "expr" in x and isinstance(x["expr"], str):
            e = x["expr"]
            if e in EXACT:
                x["expr"] = EXACT[e]
            else:
                missing.add(e)
        if x.get("type") == "prometheus" and "uid" in x:
            x["uid"] = "prometheus"
        for v in x.values():
            walk_replace_expr(v, missing)
    elif isinstance(x, list):
        for i in x:
            walk_replace_expr(i, missing)


d = json.loads(SRC.read_text(encoding="utf-8"))
d.pop("__inputs", None)
d.pop("__requires", None)
d.pop("id", None)
d["description"] = "SGLang: обзор (разметка vLLM Monitoring V2, метрики sglang:*)"
d["title"] = "SGLang Monitoring (from vLLM V2, slgpu)"
d["uid"] = "sglangdash2-slgpu"
d["tags"] = ["sglang", "inference", "llm", "slgpu"]
d["gnetId"] = None

missing = set()
walk_replace_expr(d, missing)
if missing:
    for m in sorted(missing):
        print("MISSING", repr(m)[:200])

# templating
d["templating"] = {
    "list": [
        {
            "current": {},
            "datasource": {"type": "prometheus", "uid": "prometheus"},
            "definition": 'label_values(up{job="sglang"}, instance)',
            "includeAll": False,
            "label": "instance",
            "name": "instance",
            "options": [],
            "query": {
                "qryType": 1,
                "query": 'label_values(up{job="sglang"}, instance)',
                "refId": "PrometheusVariableQueryEditor-VariableQuery",
            },
            "refresh": 1,
            "regex": "",
            "type": "query",
        },
        {
            "current": {},
            "datasource": {"type": "prometheus", "uid": "prometheus"},
            "definition": 'label_values(sglang:generation_tokens_total{job="sglang",instance=~"$instance"}, model_name)',
            "includeAll": False,
            "label": "Model",
            "name": "model_name",
            "options": [],
            "query": {
                "qryType": 1,
                "query": 'label_values(sglang:generation_tokens_total{job="sglang",instance=~"$instance"}, model_name)',
                "refId": "PrometheusVariableQueryEditor-VariableQuery",
            },
            "refresh": 1,
            "regex": "",
            "type": "query",
        },
    ]
}

# панельные подписи
for p in d.get("panels", []):
    if p.get("type") == "row":
        continue
    pid = p.get("id")
    if pid == 101:
        p["title"] = "Non-abort %"
        p["description"] = "100 * (1 - aborted/requests) по rate за 5m."
    elif pid == 105:
        p["title"] = "Retraction rate"
        p["description"] = "Аналог preemption: rate(sglang:num_retracted_requests_total)."
    elif pid == 202:
        p["title"] = "TTFT vs inter-token (avg)"
        p["description"] = (
            "Средний TTFT и средняя inter-token latency. "
            "Аналог prefill/decode vLLM, не идентичен стадиям движка."
        )
        for t in p.get("targets", []):
            if t.get("refId") == "A":
                t["legendFormat"] = "TTFT avg"
            if t.get("refId") == "B":
                t["legendFormat"] = "Inter-token avg"
        for o in p.get("fieldConfig", {}).get("overrides", []):
            m = o.get("matcher", {})
            if m.get("options") == "Prefill":
                m["options"] = "TTFT avg"
            if m.get("options") == "Decode":
                m["options"] = "Inter-token avg"
    elif pid == 303:
        p["title"] = "Cached prompt share %"
    elif pid == 401:
        p["title"] = "Token usage (KV pool)"
        p["description"] = "sglang:token_usage (0–1), аналог использования пула."
    elif pid == 403:
        p["title"] = "Scheduler state (SGLang)"
        p["description"] = "Running, queue, retracted (вместо vLLM swapped)."
        for t in p.get("targets", []):
            if t.get("refId") == "C":
                t["legendFormat"] = "Retracted"
    elif pid == 502:
        p["title"] = "Aborted vs non-aborted (range)"
        p["description"] = (
            "SGLang не отдаёт finished_reason в Prometheus. "
            "Срез: aborted и остаток за выбранный диапазон."
        )
        p["targets"] = [
            {
                "datasource": {"type": "prometheus", "uid": "prometheus"},
                "expr": f"sum(increase(sglang:num_aborted_requests_total{{{SEL}}}[$__range]))",
                "legendFormat": "aborted",
                "refId": "A",
            },
            {
                "datasource": {"type": "prometheus", "uid": "prometheus"},
                "expr": f"clamp_min(sum(increase(sglang:num_requests_total{{{SEL}}}[$__range])) - sum(increase(sglang:num_aborted_requests_total{{{SEL}}}[$__range])), 0)",
                "legendFormat": "non_aborted",
                "refId": "B",
            },
        ]
        p["fieldConfig"]["overrides"] = [
            {
                "matcher": {"id": "byName", "options": "aborted"},
                "properties": [{"id": "color", "value": {"fixedColor": "red", "mode": "fixed"}}],
            },
            {
                "matcher": {"id": "byName", "options": "non_aborted"},
                "properties": [{"id": "color", "value": {"fixedColor": "green", "mode": "fixed"}}],
            },
        ]
    elif pid == 503:
        p["title"] = "Req/s: e2e completions vs not-aborted"
        p["description"] = "e2e_request_latency_seconds_count и num_requests - num_aborted (rate)."


DST.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Wrote", DST, "expr missing:", len(missing))
