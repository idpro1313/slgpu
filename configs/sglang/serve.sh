#!/usr/bin/env bash
# Запуск SGLang launch_server. Параметры — из env (.env, sglang.env, пресет).
set -euo pipefail

: "${MODEL_ID:?MODEL_ID не задан (корневой .env или пресет модели)}"

MODEL_PATH="/models/${MODEL_ID}"
HOST="${SGLANG_LISTEN_HOST:-0.0.0.0}"
PORT="${SGLANG_LISTEN_PORT:-8111}"
TP="${TP:-4}"
MEM_FRAC="${SGLANG_MEM_FRACTION_STATIC:-0.90}"
MAX_LEN="${MAX_MODEL_LEN:-32768}"
KV="${KV_CACHE_DTYPE:-fp8_e4m3}"
REASON="${REASONING_PARSER:-qwen3}"

exec python3 -m sglang.launch_server \
  --model-path "${MODEL_PATH}" \
  --trust-remote-code \
  --served-model-name "${MODEL_ID}" \
  --tp "${TP}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --mem-fraction-static "${MEM_FRAC}" \
  --context-length "${MAX_LEN}" \
  --enable-torch-compile \
  --kv-cache-dtype "${KV}" \
  --reasoning-parser "${REASON}"
