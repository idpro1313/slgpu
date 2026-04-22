#!/usr/bin/env bash
# Запуск SGLang launch_server. Параметры — из env (.env, sglang.env, пресет).
set -euo pipefail

: "${MODEL_ID:?MODEL_ID не задан (корневой .env или пресет модели)}"

MODEL_PATH="/models/${MODEL_ID}"
HOST="${SGLANG_LISTEN_HOST:-0.0.0.0}"
PORT="${SGLANG_LISTEN_PORT:-8222}"
TP="${TP:-8}"
MEM_FRAC="${SGLANG_MEM_FRACTION_STATIC:-0.90}"
MAX_LEN="${MAX_MODEL_LEN:-32768}"
KV="${KV_CACHE_DTYPE:-fp8_e4m3}"
REASON="${REASONING_PARSER:-qwen3}"
TOOL="${TOOL_CALL_PARSER:-}"
# 0|no|false: не передавать --enable-torch-compile (см. подсказку SGLang при «Capture cuda graph failed»).
SGL_TORCH="${SGLANG_ENABLE_TORCH_COMPILE:-1}"
# 1: добавить --disable-cuda-graph (сильно бьёт по скорости; крайняя мера).
SGL_NO_CG="${SGLANG_DISABLE_CUDA_GRAPH:-0}"
# 1: --disable-custom-all-reduce (NCCL); при RuntimeError в custom_all_reduce / get_graph_buffer_ipc_meta.
SGL_NO_CAR="${SGLANG_DISABLE_CUSTOM_ALL_REDUCE:-0}"
# 1: /metrics с sglang:* (Grafana «SGLang Dashboard»); без этого панели часто пустые.
SGL_METRICS="${SGLANG_ENABLE_METRICS:-1}"
SGL_MFU="${SGLANG_ENABLE_MFU_METRICS:-0}"

cmd=(
  python3 -m sglang.launch_server
  --model-path "${MODEL_PATH}"
  --trust-remote-code
  --served-model-name "${MODEL_ID}"
  --tp "${TP}"
  --host "${HOST}"
  --port "${PORT}"
  --mem-fraction-static "${MEM_FRAC}"
  --context-length "${MAX_LEN}"
  --kv-cache-dtype "${KV}"
  --reasoning-parser "${REASON}"
)
if [[ "${SGL_METRICS}" == "1" ]]; then
  cmd+=(--enable-metrics)
fi
if [[ "${SGL_MFU}" == "1" ]]; then
  cmd+=(--enable-mfu-metrics)
fi
if [[ "${SGL_NO_CAR}" == "1" ]]; then
  cmd+=(--disable-custom-all-reduce)
fi
# Опции CUDA graph: порядок не критичен, флаги из оф. подсказки SGLang.
if [[ -n "${SGLANG_CUDA_GRAPH_MAX_BS:-}" ]]; then
  cmd+=(--cuda-graph-max-bs "${SGLANG_CUDA_GRAPH_MAX_BS}")
fi
if [[ "${SGL_NO_CG}" == "1" ]]; then
  cmd+=(--disable-cuda-graph)
fi
case "${SGL_TORCH}" in
  0|no|NO|false|False) ;;
  *) cmd+=(--enable-torch-compile) ;;
esac
if [[ -n "${TOOL}" ]]; then
  cmd+=(--tool-call-parser "${TOOL}")
fi
exec "${cmd[@]}"
