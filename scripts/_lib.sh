#!/usr/bin/env bash
# Общие функции для slgpu (source из scripts/cmd_*.sh).
# ВНИМАНИЕ: не вызывать set -e здесь — его задают вызывающие скрипты.

slgpu_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

# stdout: абсолютный путь к каталогу пресетов *.env (PRESETS_DIR в main.env или data/presets).
slgpu_presets_dir() {
  local root p
  root="$(slgpu_root)"
  p=""
  if [[ -f "${root}/main.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${root}/main.env" 2>/dev/null
    set +a
  fi
  p="${PRESETS_DIR:-./data/presets}"
  case "${p}" in
    ./*) echo "${root}/${p#./}" ;;
    /*) echo "${p}" ;;
    *) echo "${root}/${p}" ;;
  esac
}

# Общая сеть vLLM/SGLang ↔ Prometheus/DCGM/… (см. docker/docker-compose.llm.yml, docker/docker-compose.monitoring.yml).
# Раньше: «голый» `docker network create slgpu` без меток — docker compose v2 ожидает
# com.docker.compose.project / com.docker.compose.network и падает с
# "network ... has incorrect label com.docker.compose.network set to \"\"".
slgpu_ensure_slgpu_network() {
  local want_net proj lbl_net lbl_proj
  want_net="slgpu"
  proj="slgpu"
  if docker network inspect "${want_net}" &>/dev/null; then
    lbl_net="$(docker network inspect "${want_net}" -f '{{index .Labels "com.docker.compose.network"}}' 2>/dev/null | tr -d '\r' || true)"
    lbl_proj="$(docker network inspect "${want_net}" -f '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null | tr -d '\r' || true)"
    if [[ "${lbl_net}" != "${want_net}" || "${lbl_proj}" != "${proj}" ]]; then
      echo "Сеть ${want_net} уже есть, но создана не через «этот» docker compose (нет меток com.docker.compose.*)." >&2
      echo "Починка: остановить контейнеры, удалить сеть, поднять заново:" >&2
      echo "  cd $(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd) && docker compose -f docker/docker-compose.llm.yml down && docker network rm ${want_net}" >&2
      echo "  (если slgpu-monitoring: также docker compose -f docker/docker-compose.monitoring.yml down)" >&2
      return 1
    fi
    return 0
  fi
  docker network create --driver bridge \
    --label "com.docker.compose.project=${proj}" \
    --label "com.docker.compose.network=${want_net}" \
    "${want_net}"
}

slgpu_list_presets() {
  local pdir
  pdir="$(slgpu_presets_dir)"
  if [[ -d "${pdir}" ]]; then
    (cd "${pdir}" && ls -1 *.env 2>/dev/null | sed 's/\.env$//' | sort) || true
  fi
}

# После -m|--model нет имени (или следующий токен — флаг): подсказка + список пресетов в stderr.
slgpu_fail_if_missing_preset_arg() {
  local opt="$1"
  echo "Опция ${opt} требует имя пресета (файл data/presets/<name>.env или PRESETS_DIR в main.env)." >&2
  echo "Доступные пресеты:" >&2
  local list
  list="$(slgpu_list_presets)"
  if [[ -n "${list}" ]]; then
    echo "${list}" | sed 's/^/  /' >&2
  else
    echo "  (нет файлов *.env в каталоге пресетов)" >&2
  fi
}

# Интерактив: выбор vllm | sglang. В stdout печатается одно слово. Код != 0 — TTY нет / отмена.
slgpu_interactive_choose_engine() {
  local choice
  if ! [[ -r /dev/tty ]]; then
    echo "Интерактивный выбор невозможен: нет TTY. Укажите явно: ./slgpu up <vllm|sglang> -m <пресет>" >&2
    return 1
  fi
  while true; do
    echo "" >&2
    echo "Выберите движок инференса:" >&2
    echo "  1) vLLM" >&2
    echo "  2) SGLang" >&2
    read -r -p "Введите номер (1 или 2) либо vllm / sglang: " choice </dev/tty || return 1
    choice="${choice//[[:space:]]/}"
    case "${choice}" in
      1|vllm|VLLM) echo vllm; return 0 ;;
      2|sglang|SGLang) echo sglang; return 0 ;;
      v|V) echo vllm; return 0 ;;
      s|S) echo sglang; return 0 ;;
      q|Q|exit) echo "Отмена." >&2; return 1 ;;
      *) echo "Введите 1, 2, vllm или sglang (или q — выход)." >&2 ;;
    esac
  done
}

# Интерактив: выбор пресета по списку *.env в PRESETS_DIR. В stdout — slug. Код != 0 — TTY нет / нет пресетов.
slgpu_interactive_choose_preset() {
  local pres line i pick root pdir
  root="$(slgpu_root)"
  pdir="$(slgpu_presets_dir)"
  pres=()
  while IFS= read -r line; do
    [[ -n "${line}" ]] && pres+=("$line")
  done < <(slgpu_list_presets)
  if [[ ${#pres[@]} -eq 0 ]]; then
    echo "Нет пресетов: добавьте *.env в ${pdir#${root}/} (см. PRESETS_DIR в main.env)" >&2
    return 1
  fi
  if ! [[ -r /dev/tty ]]; then
    echo "Интерактивный выбор невозможен: нет TTY. Укажите: -m <пресет>" >&2
    return 1
  fi
  echo "" >&2
  echo "Доступные пресеты:" >&2
  for i in "${!pres[@]}"; do
    echo "  $((i + 1))) ${pres[i]}" >&2
  done
  while true; do
    read -r -p "Введите номер списка или имя пресета: " pick </dev/tty || return 1
    pick="${pick//[$'\t\r\n']/}"
    [[ -z "${pick}" ]] && { echo "Пустой ввод; повторите или q — выход." >&2; continue; }
    [[ "${pick}" == "q" || "${pick}" == "Q" ]] && { echo "Отмена." >&2; return 1; }
    if [[ "${pick}" =~ ^[0-9]+$ ]]; then
      if (( pick >= 1 && pick <= ${#pres[@]} )); then
        echo "${pres[$((pick - 1))]}"
        return 0
      fi
      echo "Номер от 1 до ${#pres[@]}." >&2
      continue
    fi
    if [[ -f "${pdir}/${pick}.env" ]]; then
      echo "${pick}"
      return 0
    fi
    echo "Пресет не найден: ${pdir}/${pick}.env" >&2
  done
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

# main.env + обязательный пресет <PRESETS_DIR>/<slug>.env (bench, load, …).
slgpu_load_env() {
  local preset="${1:-}"
  local root pdir
  root="$(slgpu_root)"
  pdir="$(slgpu_presets_dir)"

  if [[ -z "${preset}" ]]; then
    echo "Укажите пресет: -m <slug> (файл в каталоге пресетов, см. PRESETS_DIR в main.env)" >&2
    echo "Доступные пресеты:" >&2
    slgpu_list_presets | sed 's/^/  /' >&2 || true
    return 1
  fi

  set -a
  slgpu_source_main_env

  local f="${pdir}/${preset}.env"
  if [[ ! -f "${f}" ]]; then
    echo "Пресет не найден: ${f}" >&2
    echo "Доступные пресеты:" >&2
    local presets
    presets="$(slgpu_list_presets)"
    if [[ -n "${presets}" ]]; then
      echo "${presets}" | sed 's/^/  /' >&2
    else
      echo "  (нет файлов в каталоге пресетов)" >&2
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
  local root pdir
  root="$(slgpu_root)"
  pdir="$(slgpu_presets_dir)"

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

  local f="${pdir}/${preset}.env"
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
  if slgpu_docker_compose -f docker/docker-compose.llm.yml ps --status running --services 2>/dev/null | grep -qx 'vllm'; then
    echo vllm
    return 0
  fi
  if slgpu_docker_compose -f docker/docker-compose.llm.yml ps --status running --services 2>/dev/null | grep -qx 'sglang'; then
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
  mapped="$(slgpu_docker_compose -f docker/docker-compose.llm.yml port "${e}" "${in_p}" 2>/dev/null | head -1 || true)"
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

# Унифицированный `docker compose`: project directory = корень репо (тома и `main.env` с путями `./data/...`).
slgpu_docker_compose() {
  local _here _root
  _here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _root="$(cd "${_here}/.." && pwd)"
  (cd "${_root}" && docker compose --project-directory "${_root}" "$@")
}

# Создать каталоги для относительных путей из main.env (./data/…), если файла нет — no-op.
slgpu_ensure_data_dirs() {
  local root _p
  root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [[ ! -f "${root}/main.env" ]]; then
    return 0
  fi
  set -a
  # shellcheck disable=SC1091
  source "${root}/main.env"
  set +a
  for _p in \
    "${MODELS_DIR:-}" \
    "${PRESETS_DIR:-}" \
    "${WEB_DATA_DIR:-}" \
    "${PROMETHEUS_DATA_DIR:-}" \
    "${GRAFANA_DATA_DIR:-}" \
    "${LOKI_DATA_DIR:-}" \
    "${PROMTAIL_DATA_DIR:-}" \
    "${LANGFUSE_POSTGRES_DATA_DIR:-}" \
    "${LANGFUSE_CLICKHOUSE_DATA_DIR:-}" \
    "${LANGFUSE_CLICKHOUSE_LOGS_DIR:-}" \
    "${LANGFUSE_MINIO_DATA_DIR:-}" \
    "${LANGFUSE_REDIS_DATA_DIR:-}"; do
    if [[ -n "${_p}" && "${_p}" == ./* ]]; then
      mkdir -p "${root}/${_p#./}"
    fi
  done
}
