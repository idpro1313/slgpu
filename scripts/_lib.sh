#!/usr/bin/env bash
# Общие функции для slgpu (source из scripts/cmd_*.sh).
# ВНИМАНИЕ: не вызывать set -e здесь — его задают вызывающие скрипты.

slgpu_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

slgpu_list_presets() {
  local root
  root="$(slgpu_root)"
  if [[ -d "${root}/configs/models" ]]; then
    (cd "${root}/configs/models" && ls -1 *.env 2>/dev/null | sed 's/\.env$//' | sort) || true
  fi
}

# Только корневой .env (пути, мониторинг). Без пресета.
slgpu_load_server_env() {
  local root
  root="$(slgpu_root)"
  if [[ ! -f "${root}/.env" ]]; then
    echo "Нет файла .env — скопируйте: cp .env.example .env" >&2
    return 1
  fi
  set -a
  # shellcheck disable=SC1091
  source "${root}/.env"
  set +a
}

# .env + обязательный пресет configs/models/<slug>.env (bench, status и т.д.).
slgpu_load_env() {
  local preset="${1:-}"
  local root
  root="$(slgpu_root)"

  if [[ -z "${preset}" ]]; then
    echo "Укажите пресет: -m <slug> (файл configs/models/<slug>.env)" >&2
    echo "Доступные пресеты:" >&2
    slgpu_list_presets | sed 's/^/  /' >&2 || true
    return 1
  fi

  if [[ ! -f "${root}/.env" ]]; then
    echo "Нет файла .env — скопируйте: cp .env.example .env" >&2
    return 1
  fi

  set -a
  # shellcheck disable=SC1091
  source "${root}/.env"

  local f="${root}/configs/models/${preset}.env"
  if [[ ! -f "${f}" ]]; then
    echo "Пресет не найден: ${f}" >&2
    echo "Доступные пресеты:" >&2
    local presets
    presets="$(slgpu_list_presets)"
    if [[ -n "${presets}" ]]; then
      echo "${presets}" | sed 's/^/  /' >&2
    else
      echo "  (нет файлов в configs/models/)" >&2
    fi
    set +a
    return 1
  fi
  echo "Загружен пресет модели: ${preset}  (${f#${root}/})"
  # shellcheck disable=SC1090
  source "${f}"
  set +a

  : "${MODEL_ID:?MODEL_ID не задан в пресете ${preset}.env}"
}

# Для docker compose: .env → configs/<engine>/<engine>.env → пресет (обязателен).
# $1 — слаг пресета, $2 — vllm | sglang.
slgpu_load_compose_env() {
  local preset="${1:-}"
  local engine="${2:?укажите vllm или sglang}"
  local root
  root="$(slgpu_root)"

  if [[ -z "${preset}" ]]; then
    echo "Укажите пресет: -m <slug>" >&2
    return 1
  fi

  if [[ ! -f "${root}/.env" ]]; then
    echo "Нет файла .env — скопируйте: cp .env.example .env" >&2
    return 1
  fi

  case "${engine}" in
    vllm|sglang) ;;
    *) echo "slgpu_load_compose_env: ожидается vllm|sglang, получено: ${engine}" >&2; return 1 ;;
  esac

  local eng_file="${root}/configs/${engine}/${engine}.env"
  if [[ ! -f "${eng_file}" ]]; then
    echo "Нет файла движка: ${eng_file}" >&2
    return 1
  fi

  set -a
  # shellcheck disable=SC1091
  source "${root}/.env"
  # shellcheck disable=SC1090
  source "${eng_file}"

  local f="${root}/configs/models/${preset}.env"
  if [[ ! -f "${f}" ]]; then
    echo "Пресет не найден: ${f}" >&2
    set +a
    return 1
  fi
  echo "Загружен пресет модели: ${preset}  (${f#${root}/})"
  # shellcheck disable=SC1090
  source "${f}"
  set +a

  : "${MODEL_ID:?MODEL_ID не задан в пресете ${preset}.env}"
}

# Hugging Face repo id → slug для имени пресета (basename, lower, _ → -).
slgpu_hf_id_to_slug() {
  local id="$1"
  local base="${id##*/}"
  echo "${base,,}" | tr '_' '-'
}

# По HF id угадываем парсеры (vLLM). Вывод: две строки reasoning<TAB>tool.
slgpu_guess_parsers() {
  local id="$1"
  local r="" t=""
  case "${id}" in
    *Thinking*|*-thinking*)
      r="qwen3-thinking"
      t="hermes"
      ;;
    Qwen/Qwen3*|Qwen/Qwen3.6*|Qwen3.6*)
      r="qwen3"
      t="hermes"
      ;;
    deepseek-ai/DeepSeek-R1*|DeepSeek-R1*)
      r="deepseek_r1"
      t="pythonic"
      ;;
    meta-llama/Llama-3*|Llama-3*)
      r=""
      t="llama3_json"
      ;;
    moonshotai/Kimi*|*/Kimi-K2*)
      r="kimi_k2"
      t="kimi_k2"
      ;;
    MiniMaxAI/MiniMax*)
      r="minimax_m2"
      t="minimax_m2"
      ;;
    zai-org/GLM*)
      r="glm45"
      t="glm45"
      ;;
    openai/gpt-oss*)
      r="openai_gptoss"
      t="openai"
      ;;
    *)
      r=""
      t=""
      ;;
  esac
  printf '%s\t%s' "${r}" "${t}"
}

# По HF id — дефолтный MAX_MODEL_LEN для ./slgpu pull без --max-len (токены).
# 262144 = 256k; для моделей с меньшим заявленным окном — меньше (см. README).
slgpu_guess_max_model_len() {
  local id="$1"
  case "${id}" in
    Qwen/Qwen3.6*|Qwen3.6*)
      echo 262144
      ;;
    Qwen/Qwen3-30B*|Qwen3-30B*)
      # HF: нативно 32k; с YaRN валидировано до 131072 — не 262144 без отдельной настройки rope.
      echo 131072
      ;;
    zai-org/GLM*)
      # max_position_embeddings в config.json; ~200k заявленного окна
      echo 202752
      ;;
    openai/gpt-oss*)
      echo 131072
      ;;
    *)
      echo 262144
      ;;
  esac
}

# Записать configs/models/<slug>.env
# Аргументы: slug hf_id revision max_len tp kv_dtype gpu_mem sglang_mem batch reason tool [mm_encoder_tp_mode]
slgpu_gen_preset_file() {
  local root out slug hf_id revision max_len tp kv gpu sgl batch reason tool mm_enc ts
  root="$(slgpu_root)"
  slug="$1"
  hf_id="$2"
  revision="$3"
  max_len="$4"
  tp="$5"
  kv="$6"
  gpu="$7"
  sgl="$8"
  batch="$9"
  reason="${10}"
  tool="${11}"
  mm_enc="${12:-}"
  ts="$(date -Iseconds 2>/dev/null || date)"
  out="${root}/configs/models/${slug}.env"

  {
    echo "# Auto-generated by ./slgpu pull ${hf_id} @ ${ts}"
    echo "# Семантика полей: см. комментарии в configs/models/qwen3.6-35b-a3b.env и docs к движкам."
    echo ""
    echo "# Для чего: Hugging Face id весов (каталог скачивания и имя сервера в API)."
    echo "# Варианты: \`org/model\`; сейвится из аргумента pull."
    echo "MODEL_ID=${hf_id}"
    echo "# Для чего: зафиксировать ревизию ветки."
    echo "# Варианты: тег, SHA; пусто — по умолчанию с pull."
    echo "MODEL_REVISION=${revision}"
    echo "# Для чего: макс. контекст (токены) для vLLM/SGLang."
    echo "# Варианты: ≤ лимита модели; снижайте при OOM."
    echo "MAX_MODEL_LEN=${max_len}"
    echo "# Для чего: тип KV cache."
    echo "# Варианты: fp8, fp8_e4m3 (часто), auto — уточните в карточке HF и в доке движка."
    echo "KV_CACHE_DTYPE=${kv}"
    echo "# Для чего: vLLM --gpu-memory-utilization."
    echo "# Варианты: 0.85–0.95; снижать при OOM."
    echo "GPU_MEM_UTIL=${gpu}"
    echo "# Для чего: SGLang --mem-fraction-static."
    echo "# Варианты: 0.85–0.92; снижать при OOM / нестабильном graph capture."
    echo "SGLANG_MEM_FRACTION_STATIC=${sgl}"
    echo "# Для чего: vLLM chunked prefill; имя SLGPU_* (не VLLM_*) для 0.19+."
    echo "# Варианты: 4096, 8192, 16384."
    echo "SLGPU_MAX_NUM_BATCHED_TOKENS=${batch}"
    echo "# Для чего: tensor parallel (число GPU одной реплики)."
    echo "# Варианты: совпадать с device_ids в docker-compose; 1/2/4/8/…"
    echo "TP=${tp}"
    echo "# Для чего: парсер reasoning/think-тегов."
    echo "# Варианты: угадан по семейству; проверьте в доке vLLM/SGLang и при смене модели."
    echo "REASONING_PARSER=${reason}"
    echo "# Для чего: парсер tool/function calling."
    echo "# Варианты: пусто или hermes/…; см. configs/models/README.md."
    echo "TOOL_CALL_PARSER=${tool}"
    if [[ -n "${mm_enc}" ]]; then
      echo "# Для чего: vLLM --mm-encoder-tp-mode (модальности, Kimi/мультимодель)."
      echo "# Варианты: data и др. по релизу vLLM; только для vLLM."
      echo "MM_ENCODER_TP_MODE=${mm_enc}"
    fi
    echo "# Для чего: фиктивное имя модели в бенчмарке (пусто — из /v1/models)."
    echo "# Варианты: пусто или ID строки для отчёта."
    echo "BENCH_MODEL_NAME="
    if [[ -z "${reason}" && -z "${tool}" ]]; then
      echo ""
      echo "# TODO: уточните REASONING_PARSER и TOOL_CALL_PARSER вручную — см. configs/models/README.md"
    fi
  } >"${out}"
  echo "${out}"
}

# Определить, запущен ли vllm или sglang (stdout: vllm|sglang или пусто).
slgpu_detect_running_engine() {
  local root
  root="$(slgpu_root)"
  cd "${root}" || return 1
  if docker compose ps --status running --services 2>/dev/null | grep -qx 'vllm'; then
    echo vllm
    return 0
  fi
  if docker compose ps --status running --services 2>/dev/null | grep -qx 'sglang'; then
    echo sglang
    return 0
  fi
  return 1
}

# Список «0,1,…,N-1» для NVIDIA_VISIBLE_DEVICES (согласовано с tensor parallel).
slgpu_nvidia_visible_from_tp() {
  local t="${1:?}" i s=""
  for ((i = 0; i < t; i++)); do
    s+="${s:+,}$i"
  done
  echo "$s"
}

# База OpenAI API: http://127.0.0.1:<порт>/v1 для запущенного движка (порт с хоста из docker compose).
# $1: vllm|sglang. Внутри контейнера: vLLM 8111, SGLang 8222.
slgpu_openai_base_url() {
  local e="${1:?укажите vllm или sglang}"
  local root in_p mapped host_port
  root="$(slgpu_root)"
  cd "${root}" || return 1
  case "${e}" in
    vllm) in_p=8111 ;;
    sglang) in_p=8222 ;;
    *) echo "slgpu_openai_base_url: ожидается vllm|sglang" >&2; return 1 ;;
  esac
  mapped="$(docker compose port "${e}" "${in_p}" 2>/dev/null | head -1 || true)"
  host_port=""
  if [[ -n "${mapped}" ]] && [[ "${mapped}" =~ :([0-9]+)$ ]]; then
    host_port="${BASH_REMATCH[1]}"
  fi
  if [[ -z "${host_port}" ]]; then
    if [[ "${e}" == sglang ]]; then
      host_port=8222
    else
      host_port=8111
    fi
  fi
  echo "http://127.0.0.1:${host_port}/v1"
}

# Проверить соответствие запущенного движка.
# $1 = engine (vllm|sglang)
slgpu_validate_running_config() {
  local engine="${1:-}"

  local running_engine
  running_engine="$(slgpu_detect_running_engine)" || true

  if [[ -z "${running_engine}" ]]; then
    echo "[VALIDATE] ОШИБКА: ни vllm, ни sglang не запущены. Сначала: ./slgpu up ${engine}" >&2
    return 1
  fi

  if [[ "${running_engine}" != "${engine}" ]]; then
    echo "[VALIDATE] ОШИБКА: запущен ${running_engine}, а бенч для ${engine}. Сначала: ./slgpu down && ./slgpu up ${engine}" >&2
    return 1
  fi

  echo "[VALIDATE] OK: engine=${running_engine}"
  return 0
}
