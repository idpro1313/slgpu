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

# После -m|--model нет имени (или следующий токен — флаг): подсказка + список пресетов в stderr.
slgpu_fail_if_missing_preset_arg() {
  local opt="$1"
  echo "Опция ${opt} требует имя пресета (файл configs/models/<name>.env)." >&2
  echo "Доступные пресеты:" >&2
  local list
  list="$(slgpu_list_presets)"
  if [[ -n "${list}" ]]; then
    echo "${list}" | sed 's/^/  /' >&2
  else
    echo "  (нет файлов *.env в configs/models/)" >&2
  fi
}

# Дефолты репозитория: `main.env` в корне (если есть), до движка и пресетов.
slgpu_source_main_env() {
  local root
  root="$(slgpu_root)"
  local f="${root}/main.env"
  if [[ -f "${f}" ]]; then
    # shellcheck disable=SC1091
    source "${f}"
  fi
}

# `main.env` (пути, мониторинг). Без пресета.
slgpu_load_server_env() {
  set -a
  slgpu_source_main_env
  set +a
}

# main.env + обязательный пресет configs/models/<slug>.env (bench, load, …).
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

  set -a
  slgpu_source_main_env

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

# Для docker compose: main.env → пресет (обязателен).
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

  case "${engine}" in
    vllm|sglang) ;;
    *) echo "slgpu_load_compose_env: ожидается vllm|sglang, получено: ${engine}" >&2; return 1 ;;
  esac

  set -a
  slgpu_source_main_env

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
