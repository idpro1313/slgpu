#!/usr/bin/env bash
# Универсальный entrypoint: vLLM или SGLang по SLGPU_ENGINE=vllm|sglang.
# Env: БД (`stack_params` + пресет) → backend (`llm_env.py`) собирает плоский dict и передаёт docker-py при старте слота. Монтируется в контейнер LLM-слота как /etc/slgpu/serve.sh.
# Имена vLLM-флагов — без префикса SLGPU_ (SERVED_MODEL_NAME, MAX_NUM_BATCHED_TOKENS, …); устаревший SLGPU_* читается как fallback.
set -euo pipefail

# Если задана маска GPU Docker, число записей (индексы или UUID через запятую) — источник истины для TP,
# иначе пресетный TP=8 на узле с двумя GPU даёт ParallelConfig: world size > available GPUs.
slgpu_resolve_tp_from_visible_gpus() {
  local tp_env nv_trim nv_clean want n oldifs
  tp_env="${1:-8}"
  if [[ -z "${NVIDIA_VISIBLE_DEVICES:-}" ]]; then
    printf '%s' "${tp_env}"
    return 0
  fi
  nv_trim="${NVIDIA_VISIBLE_DEVICES#"${NVIDIA_VISIBLE_DEVICES%%[![:space:]]*}"}"
  nv_trim="${nv_trim%"${nv_trim##*[![:space:]]}"}"
  case "${nv_trim}" in
    '' | all | none | void)
      printf '%s' "${tp_env}"
      return 0
      ;;
  esac
  nv_clean="${nv_trim// /}"
  want=0
  oldifs="${IFS}"
  IFS=','
  for n in ${nv_clean}; do
    [[ -z "${n}" ]] && continue
    ((want += 1))
  done
  IFS="${oldifs}"
  if ((want < 1)); then
    printf '%s' "${tp_env}"
    return 0
  fi
  if [[ "${tp_env}" =~ ^[0-9]+$ ]] && ((10#tp_env != want)); then
    echo "[slgpu][serve.sh][BLOCK_TP_VISIBLE] TP ${tp_env} → ${want} (NVIDIA_VISIBLE_DEVICES=${nv_trim})" >&2
  fi
  printf '%s' "${want}"
}

slgpu_run_vllm() {
  local MODEL_PATH SERVED_NAME HOST PORT TP GPU_MEM MAX_LEN KV BATCH TOOL REASON DISABLE_CAR PREFIX_CACHE \
    TRUST CR_PREFILL AUTO_TOOL BS MAXSEQ AB TM DPS cmd
  MODEL_PATH="${SLGPU_MODEL_ROOT:-/models}/${MODEL_ID}"
  # Имя в OpenAI API (/v1/models, choice.model). Пусто/не задано → MODEL_ID; задайте devllm для фиксированного имени.
  SERVED_NAME="${SERVED_MODEL_NAME:-${SLGPU_SERVED_MODEL_NAME:-$MODEL_ID}}"
  HOST="${LLM_API_BIND:-${SLGPU_VLLM_HOST:-0.0.0.0}}"
  PORT="${LLM_API_PORT:-${SLGPU_VLLM_PORT:-8111}}"
  TP="${TP:-8}"
  TP="$(slgpu_resolve_tp_from_visible_gpus "${TP}")"
  GPU_MEM="${GPU_MEM_UTIL:-0.92}"
  MAX_LEN="${MAX_MODEL_LEN:-32768}"
  KV="${KV_CACHE_DTYPE:-fp8_e4m3}"
  BATCH="${MAX_NUM_BATCHED_TOKENS:-${SLGPU_MAX_NUM_BATCHED_TOKENS:-${VLLM_MAX_NUM_BATCHED_TOKENS:-8192}}}"
  TOOL="${TOOL_CALL_PARSER:-hermes}"
  REASON="${REASONING_PARSER:-qwen3}"
  DISABLE_CAR="${DISABLE_CUSTOM_ALL_REDUCE:-${SLGPU_DISABLE_CUSTOM_ALL_REDUCE:-1}}"
  PREFIX_CACHE="${ENABLE_PREFIX_CACHING:-${SLGPU_ENABLE_PREFIX_CACHING:-1}}"
  TRUST="${TRUST_REMOTE_CODE:-${SLGPU_VLLM_TRUST_REMOTE_CODE:-1}}"
  CR_PREFILL="${ENABLE_CHUNKED_PREFILL:-${SLGPU_VLLM_ENABLE_CHUNKED_PREFILL:-1}}"
  AUTO_TOOL="${ENABLE_AUTO_TOOL_CHOICE:-${SLGPU_VLLM_ENABLE_AUTO_TOOL_CHOICE:-1}}"
  BS="${BLOCK_SIZE:-${SLGPU_VLLM_BLOCK_SIZE:-}}"
  MAXSEQ="${MAX_NUM_SEQS:-${SLGPU_VLLM_MAX_NUM_SEQS:-}}"
  AB="${ATTENTION_BACKEND:-${SLGPU_VLLM_ATTENTION_BACKEND:-}}"
  TM="${TOKENIZER_MODE:-${SLGPU_VLLM_TOKENIZER_MODE:-}}"
  DPS="${DATA_PARALLEL_SIZE:-${SLGPU_VLLM_DATA_PARALLEL_SIZE:-}}"

  cmd=(
    vllm serve "${MODEL_PATH}"
    --served-model-name "${SERVED_NAME}"
    --host "${HOST}"
    --port "${PORT}"
    --tensor-parallel-size "${TP}"
    --gpu-memory-utilization "${GPU_MEM}"
    --max-model-len "${MAX_LEN}"
  )
  if [[ -n "${BS}" ]] && [[ "${BS}" =~ ^[1-9][0-9]*$ ]]; then
    cmd+=(--block-size "${BS}")
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
  if [[ -n "${MAXSEQ}" ]] && [[ "${MAXSEQ}" =~ ^[1-9][0-9]*$ ]]; then
    cmd+=(--max-num-seqs "${MAXSEQ}")
  fi
  if [[ -n "${AB}" ]]; then
    cmd+=(--attention-backend "${AB}")
  fi
  if [[ -n "${TM}" ]]; then
    cmd+=(--tokenizer-mode "${TM}")
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
  if [[ -n "${COMPILATION_CONFIG:-${SLGPU_VLLM_COMPILATION_CONFIG:-}}" ]]; then
    cmd+=(--compilation-config "${COMPILATION_CONFIG:-$SLGPU_VLLM_COMPILATION_CONFIG}")
  fi
  if [[ "${ENFORCE_EAGER:-${SLGPU_VLLM_ENFORCE_EAGER:-0}}" == "1" ]]; then
    cmd+=(--enforce-eager)
  fi
  if [[ -n "${SPECULATIVE_CONFIG:-${SLGPU_VLLM_SPECULATIVE_CONFIG:-}}" ]]; then
    cmd+=(--speculative-config "${SPECULATIVE_CONFIG:-$SLGPU_VLLM_SPECULATIVE_CONFIG}")
  fi
  if [[ "${ENABLE_EXPERT_PARALLEL:-${SLGPU_ENABLE_EXPERT_PARALLEL:-0}}" == "1" ]]; then
    cmd+=(--enable-expert-parallel)
  fi
  if [[ -n "${DPS}" ]] && [[ "${DPS}" =~ ^[1-9][0-9]*$ ]]; then
    cmd+=(--data-parallel-size "${DPS}")
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
  SERVED_NAME="${SERVED_MODEL_NAME:-${SLGPU_SERVED_MODEL_NAME:-$MODEL_ID}}"
  HOST="${LLM_API_BIND:-0.0.0.0}"
  PORT="${LLM_API_PORT_SGLANG:-8222}"
  TP="${TP:-8}"
  TP="$(slgpu_resolve_tp_from_visible_gpus "${TP}")"
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
