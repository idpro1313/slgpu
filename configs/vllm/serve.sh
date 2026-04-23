#!/usr/bin/env bash
# Запуск vLLM OpenAI-сервера внутри контейнера. Флаги — из env (.env, vllm.env, пресет). HF-токен не используется (модель с диска).
# Служебные переменные listen/batch — SLGPU_* (см. vllm.env), чтобы vLLM 0.19+ не предупреждал о «Unknown VLLM_*».
set -euo pipefail

: "${MODEL_ID:?MODEL_ID не задан (корневой .env или пресет модели)}"

MODEL_PATH="/models/${MODEL_ID}"
HOST="${SLGPU_VLLM_HOST:-0.0.0.0}"
PORT="${SLGPU_VLLM_PORT:-8111}"
TP="${TP:-8}"
GPU_MEM="${GPU_MEM_UTIL:-0.92}"
MAX_LEN="${MAX_MODEL_LEN:-32768}"
KV="${KV_CACHE_DTYPE:-fp8_e4m3}"
BATCH="${SLGPU_MAX_NUM_BATCHED_TOKENS:-8192}"
TOOL="${TOOL_CALL_PARSER:-hermes}"
REASON="${REASONING_PARSER:-qwen3}"
# 1 (по умолчанию) = --disable-custom-all-reduce (NCCL, стабильно). 0 = custom all-reduce (быстрее на части GPU, но на vLLM 0.19 + Qwen3.6 бывает custom_all_reduce.cuh invalid argument при graph capture).
DISABLE_CAR="${SLGPU_DISABLE_CUSTOM_ALL_REDUCE:-1}"
# 1 = --enable-prefix-caching. 0 = --no-enable-prefix-caching (в vLLM 0.19+ prefix cache по умолчанию ВКЛ, просто «не передавать --enable» не отключает).
PREFIX_CACHE="${SLGPU_ENABLE_PREFIX_CACHING:-1}"

cmd=(
  vllm serve "${MODEL_PATH}"
  --served-model-name "${MODEL_ID}"
  --host "${HOST}"
  --port "${PORT}"
  --tensor-parallel-size "${TP}"
  --gpu-memory-utilization "${GPU_MEM}"
  --max-model-len "${MAX_LEN}"
  --trust-remote-code
)
if [[ "${DISABLE_CAR}" == "1" ]]; then
  cmd+=(--disable-custom-all-reduce)
fi
cmd+=(
  --kv-cache-dtype "${KV}"
  --enable-chunked-prefill
  --max-num-batched-tokens "${BATCH}"
  --tool-call-parser "${TOOL}"
  --enable-auto-tool-choice
  --reasoning-parser "${REASON}"
)
# Рецепт GLM-5.1 (FP8): --chat-template-content-format string, см. vllm-project/recipes GLM/GLM5.md
if [[ -n "${CHAT_TEMPLATE_CONTENT_FORMAT:-}" ]]; then
  cmd+=(--chat-template-content-format "${CHAT_TEMPLATE_CONTENT_FORMAT}")
fi
if [[ -n "${MM_ENCODER_TP_MODE:-}" ]]; then
  cmd+=(--mm-encoder-tp-mode "${MM_ENCODER_TP_MODE}")
fi
if [[ "${PREFIX_CACHE}" == "1" ]]; then
  cmd+=(--enable-prefix-caching)
else
  cmd+=(--no-enable-prefix-caching)
fi
exec "${cmd[@]}"
