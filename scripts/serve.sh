#!/usr/bin/env bash
# Универсальный entrypoint: vLLM или SGLang по SLGPU_ENGINE=vllm|sglang.
# Env: main.env → пресет (через compose + ./slgpu up). Монтируется в контейнер как /etc/slgpu/serve.sh.
set -euo pipefail

slgpu_run_vllm() {
  # Служебные listen/batch — SLGPU_* (см. main.env), чтобы vLLM 0.19+ не предупреждало о «Unknown VLLM_*».
  local MODEL_PATH SERVED_NAME HOST PORT TP GPU_MEM MAX_LEN KV BATCH TOOL REASON DISABLE_CAR PREFIX_CACHE \
    TRUST CR_PREFILL AUTO_TOOL cmd
  MODEL_PATH="${SLGPU_MODEL_ROOT:-/models}/${MODEL_ID}"
  # Имя в OpenAI API (/v1/models, choice.model). Пусто/не задано → MODEL_ID; задайте devllm для фиксированного имени.
  SERVED_NAME="${SLGPU_SERVED_MODEL_NAME:-$MODEL_ID}"
  HOST="${SLGPU_VLLM_HOST:-0.0.0.0}"
  PORT="${SLGPU_VLLM_PORT:-8111}"
  TP="${TP:-8}"
  GPU_MEM="${GPU_MEM_UTIL:-0.92}"
  MAX_LEN="${MAX_MODEL_LEN:-32768}"
  KV="${KV_CACHE_DTYPE:-fp8_e4m3}"
  BATCH="${SLGPU_MAX_NUM_BATCHED_TOKENS:-8192}"
  TOOL="${TOOL_CALL_PARSER:-hermes}"
  REASON="${REASONING_PARSER:-qwen3}"
  DISABLE_CAR="${SLGPU_DISABLE_CUSTOM_ALL_REDUCE:-1}"
  PREFIX_CACHE="${SLGPU_ENABLE_PREFIX_CACHING:-1}"
  TRUST="${SLGPU_VLLM_TRUST_REMOTE_CODE:-1}"
  CR_PREFILL="${SLGPU_VLLM_ENABLE_CHUNKED_PREFILL:-1}"
  AUTO_TOOL="${SLGPU_VLLM_ENABLE_AUTO_TOOL_CHOICE:-1}"

  cmd=(
    vllm serve "${MODEL_PATH}"
    --served-model-name "${SERVED_NAME}"
    --host "${HOST}"
    --port "${PORT}"
    --tensor-parallel-size "${TP}"
    --gpu-memory-utilization "${GPU_MEM}"
    --max-model-len "${MAX_LEN}"
  )
  if [[ -n "${SLGPU_VLLM_BLOCK_SIZE:-}" ]] && [[ "${SLGPU_VLLM_BLOCK_SIZE}" =~ ^[1-9][0-9]*$ ]]; then
    cmd+=(--block-size "${SLGPU_VLLM_BLOCK_SIZE}")
  fi
  if [[ "${TRUST}" == "1" ]]; then
    cmd+=(--trust-remote-code)
  fi
  if [[ "${DISABLE_CAR}" == "1" ]]; then
    cmd+=(--disable-custom-all-reduce)
  fi
  cmd+=(
    --kv-cache-dtype "${KV}"
    --max-num-batched-tokens "${BATCH}"
    --tool-call-parser "${TOOL}"
    --reasoning-parser "${REASON}"
  )
  if [[ -n "${SLGPU_VLLM_MAX_NUM_SEQS:-}" ]] && [[ "${SLGPU_VLLM_MAX_NUM_SEQS}" =~ ^[1-9][0-9]*$ ]]; then
    cmd+=(--max-num-seqs "${SLGPU_VLLM_MAX_NUM_SEQS}")
  fi
  if [[ -n "${SLGPU_VLLM_ATTENTION_BACKEND:-}" ]]; then
    cmd+=(--attention-backend "${SLGPU_VLLM_ATTENTION_BACKEND}")
  fi
  if [[ -n "${SLGPU_VLLM_TOKENIZER_MODE:-}" ]]; then
    cmd+=(--tokenizer-mode "${SLGPU_VLLM_TOKENIZER_MODE}")
  fi
  if [[ "${CR_PREFILL}" == "1" ]]; then
    cmd+=(--enable-chunked-prefill)
  fi
  if [[ "${AUTO_TOOL}" == "1" ]]; then
    cmd+=(--enable-auto-tool-choice)
  fi
  if [[ -n "${CHAT_TEMPLATE_CONTENT_FORMAT:-}" ]]; then
    cmd+=(--chat-template-content-format "${CHAT_TEMPLATE_CONTENT_FORMAT}")
  fi
  if [[ -n "${SLGPU_VLLM_COMPILATION_CONFIG:-}" ]]; then
    cmd+=(--compilation-config "${SLGPU_VLLM_COMPILATION_CONFIG}")
  fi
  if [[ -n "${SLGPU_VLLM_SPECULATIVE_CONFIG:-}" ]]; then
    cmd+=(--speculative-config "${SLGPU_VLLM_SPECULATIVE_CONFIG}")
  fi
  if [[ "${SLGPU_ENABLE_EXPERT_PARALLEL:-0}" == "1" ]]; then
    cmd+=(--enable-expert-parallel)
  fi
  if [[ -n "${SLGPU_VLLM_DATA_PARALLEL_SIZE:-}" ]] && [[ "${SLGPU_VLLM_DATA_PARALLEL_SIZE}" =~ ^[1-9][0-9]*$ ]]; then
    cmd+=(--data-parallel-size "${SLGPU_VLLM_DATA_PARALLEL_SIZE}")
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
}

slgpu_run_sglang() {
  local MODEL_PATH SERVED_NAME HOST PORT TP MEM_FRAC MAX_LEN KV REASON TOOL SGL_TORCH SGL_NO_CG SGL_NO_CAR SGL_METRICS SGL_MFU cmd
  MODEL_PATH="${SLGPU_MODEL_ROOT:-/models}/${MODEL_ID}"
  SERVED_NAME="${SLGPU_SERVED_MODEL_NAME:-$MODEL_ID}"
  HOST="${SGLANG_LISTEN_HOST:-0.0.0.0}"
  PORT="${SGLANG_LISTEN_PORT:-8222}"
  TP="${TP:-8}"
  MEM_FRAC="${SGLANG_MEM_FRACTION_STATIC:-0.90}"
  MAX_LEN="${MAX_MODEL_LEN:-32768}"
  KV="${KV_CACHE_DTYPE:-fp8_e4m3}"
  REASON="${REASONING_PARSER:-qwen3}"
  TOOL="${TOOL_CALL_PARSER:-}"
  SGL_TORCH="${SGLANG_ENABLE_TORCH_COMPILE:-1}"
  SGL_NO_CG="${SGLANG_DISABLE_CUDA_GRAPH:-0}"
  SGL_NO_CAR="${SGLANG_DISABLE_CUSTOM_ALL_REDUCE:-0}"
  SGL_METRICS="${SGLANG_ENABLE_METRICS:-1}"
  SGL_MFU="${SGLANG_ENABLE_MFU_METRICS:-0}"
  SGL_TRUST="${SGLANG_TRUST_REMOTE_CODE:-1}"

  cmd=(
    python3 -m sglang.launch_server
    --model-path "${MODEL_PATH}"
    --served-model-name "${SERVED_NAME}"
    --tp "${TP}"
    --host "${HOST}"
    --port "${PORT}"
    --mem-fraction-static "${MEM_FRAC}"
    --context-length "${MAX_LEN}"
    --kv-cache-dtype "${KV}"
    --reasoning-parser "${REASON}"
  )
  if [[ "${SGL_TRUST}" == "1" ]]; then
    cmd+=(--trust-remote-code)
  fi
  if [[ "${SGL_METRICS}" == "1" ]]; then
    cmd+=(--enable-metrics)
  fi
  if [[ "${SGL_MFU}" == "1" ]]; then
    cmd+=(--enable-mfu-metrics)
  fi
  if [[ "${SGL_NO_CAR}" == "1" ]]; then
    cmd+=(--disable-custom-all-reduce)
  fi
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
}

: "${MODEL_ID:?MODEL_ID не задан (main.env / пресет модели)}"
: "${SLGPU_ENGINE:?SLGPU_ENGINE не задан: ожидается vllm или sglang}"

case "${SLGPU_ENGINE}" in
  vllm) slgpu_run_vllm ;;
  sglang) slgpu_run_sglang ;;
  *)
    echo "SLGPU_ENGINE=${SLGPU_ENGINE} — ожидается vllm или sglang" >&2
    exit 1
    ;;
esac
