#!/usr/bin/env bash
# Общие функции для slgpu (source из scripts/cmd_*.sh).
# ВНИМАНИЕ: не вызывать set -e здесь — его задают вызывающие скрипты.
#
# v5.2.0:
#   - host-bash отвечает только за bootstrap web-контейнера и за
#     `./slgpu monitoring fix-perms`. Остальной стек (LLM-слоты,
#     monitoring, proxy) поднимается из slgpu-web через `native.*` jobs.
#   - источник переменных bash — `configs/bootstrap.env` (минимальный набор);
#     `configs/main.env` ИСКЛЮЧИТЕЛЬНО шаблон для импорта в БД через UI.

slgpu_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

# Загрузить `configs/bootstrap.env` в текущий shell (set -a для compose).
# Используется `cmd_web.sh` перед `docker compose --env-file …`.
slgpu_source_bootstrap_env() {
  local root f
  root="$(slgpu_root)"
  f="${root}/configs/bootstrap.env"
  if [[ ! -f "${f}" ]]; then
    echo "Ошибка: требуется ${f} (файл должен лежать в репозитории; не редактируйте main.env)." >&2
    return 1
  fi
  set -a
  # shellcheck disable=SC1091
  source "${f}"
  set +a
}

# Env-файл для `docker compose -f docker/docker-compose.web.yml`.
slgpu_web_compose_env_file() {
  local root f
  root="$(slgpu_root)"
  f="${root}/configs/bootstrap.env"
  if [[ ! -f "${f}" ]]; then
    echo "Ошибка: требуется ${f} (минимальный bootstrap для slgpu-web)." >&2
    exit 1
  fi
  echo "${f}"
}

# stdout: абсолютный путь к каталогу пресетов *.env (PRESETS_DIR из bootstrap.env или data/presets).
slgpu_presets_dir() {
  local root p
  root="$(slgpu_root)"
  p=""
  if [[ -f "${root}/configs/bootstrap.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${root}/configs/bootstrap.env" 2>/dev/null
    set +a
  fi
  p="${PRESETS_DIR:-./data/presets}"
  case "${p}" in
    ./*) echo "${root}/${p#./}" ;;
    /*) echo "${p}" ;;
    *) echo "${root}/${p}" ;;
  esac
}

# Общая Docker-сеть slgpu (видно из `docker/docker-compose.*.yml`).
# Имя сети — из `${SLGPU_NETWORK_NAME}` (bootstrap.env); проект — `${WEB_COMPOSE_PROJECT_INFER}`.
# Раньше «голый» `docker network create` без меток ломал docker compose v2 (incorrect label).
slgpu_ensure_slgpu_network() {
  local want_net proj lbl_net lbl_proj
  want_net="${SLGPU_NETWORK_NAME:-slgpu}"
  proj="${WEB_COMPOSE_PROJECT_INFER:-slgpu}"
  if docker network inspect "${want_net}" &>/dev/null; then
    lbl_net="$(docker network inspect "${want_net}" -f '{{index .Labels "com.docker.compose.network"}}' 2>/dev/null | tr -d '\r' || true)"
    lbl_proj="$(docker network inspect "${want_net}" -f '{{index .Labels "com.docker.compose.project"}}' 2>/dev/null | tr -d '\r' || true)"
    if [[ "${lbl_net}" != "${want_net}" || "${lbl_proj}" != "${proj}" ]]; then
      echo "Сеть ${want_net} уже есть, но создана не через docker compose (нет меток com.docker.compose.*)." >&2
      echo "Починка: остановите все контейнеры стека и удалите сеть:" >&2
      echo "  docker network rm ${want_net}" >&2
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
  echo "Опция ${opt} требует имя пресета (файл data/presets/<name>.env или PRESETS_DIR в bootstrap.env)." >&2
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
    echo "Интерактивный выбор невозможен: нет TTY. Поднимите слот движка в Develonica.LLM (Web UI)." >&2
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
    echo "Нет пресетов: добавьте *.env в ${pdir#${root}/} (см. PRESETS_DIR в bootstrap.env)" >&2
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

# Hugging Face repo id → slug для имени пресета (basename, lower, _ → -).
slgpu_hf_id_to_slug() {
  local id="$1"
  local base="${id##*/}"
  echo "${base,,}" | tr '_' '-'
}

# Список «0,1,…,N-1» для NVIDIA_VISIBLE_DEVICES (согласовано с tensor parallel).
slgpu_nvidia_visible_from_tp() {
  local t="${1:?}" i s=""
  for ((i = 0; i < t; i++)); do
    s+="${s:+,}$i"
  done
  echo "$s"
}

# Проверка CLI перед любыми вызовами `docker compose` (диагностика на «голой» VM).
slgpu_require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "slgpu: не найдена команда «docker». Установите Docker Engine и Compose v2." >&2
    exit 1
  fi
}

# Унифицированный `docker compose`: project directory = корень репо (тома и `bootstrap.env` с путями `./data/...`).
slgpu_docker_compose() {
  local _here _root
  _here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  _root="$(cd "${_here}/.." && pwd)"
  (cd "${_root}" && docker compose --project-directory "${_root}" "$@")
}

# Создать ./data/* каталоги для bind mount slgpu-web (MODELS_DIR, PRESETS_DIR, WEB_DATA_DIR).
# Источник путей — `configs/bootstrap.env`. Без файла — минимальные `./data/{web,models,presets,bench/results}`.
slgpu_ensure_data_dirs() {
  local root _p
  root="$(slgpu_root)"
  if [[ -f "${root}/configs/bootstrap.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${root}/configs/bootstrap.env"
    set +a
  fi
  for _p in \
    "${MODELS_DIR:-./data/models}" \
    "${PRESETS_DIR:-./data/presets}" \
    "${WEB_DATA_DIR:-./data/web}"; do
    case "${_p}" in
      /*) mkdir -p "${_p}" ;;
      ./*) mkdir -p "${root}/${_p#./}" ;;
      *) mkdir -p "${root}/${_p}" ;;
    esac
  done
  mkdir -p "${root}/data/bench/results"
}

# Если bind-монт в Docker указывал на отсутствующий файл, Docker мог создать каталог с тем же именем → Loki/Promtail: «is a directory».
# $1 — абсолютный путь к ожидаемому файлу; $2 — путь для «git checkout» от корня репо.
slgpu_ensure_config_yaml_is_file() {
  local abs="${1:?}"
  local gitrel="${2:?}"
  local root
  root="$(slgpu_root)"
  if [[ -d "${abs}" ]]; then
    echo "Исправление: ${abs#${root}/} — каталог вместо файла; удаляю и восстанавливаю из git…" >&2
    rm -rf "${abs}"
  fi
  if [[ -f "${abs}" ]]; then
    return 0
  fi
  if command -v git &>/dev/null && (cd "${root}" && git rev-parse --is-inside-work-tree &>/dev/null); then
    if (cd "${root}" && git checkout -- "${gitrel}" 2>/dev/null); then
      echo "Восстановлено: ${gitrel}" >&2
    fi
  fi
  if [[ ! -f "${abs}" ]]; then
    echo "Ошибка: нет файла ${abs#${root}/}. Скопируйте из репозитория или: git checkout ${gitrel}" >&2
    return 1
  fi
  return 0
}
