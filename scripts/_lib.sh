#!/usr/bin/env bash
# Общие функции для slgpu (source из scripts/cmd_*.sh).
# ВНИМАНИЕ: не вызывать set -e здесь — его задают вызывающие скрипты.
#
# v5.2.5:
#   - host-bash отвечает ТОЛЬКО за bootstrap контейнера slgpu-web
#     (`./slgpu web up|down|restart|logs`). LLM-слоты, monitoring, proxy,
#     bench, fix-perms — backend native.* jobs, без host-bash.
#   - источник переменных bash — `configs/bootstrap.env` (минимальный набор);
#     `configs/main.env` ИСКЛЮЧИТЕЛЬНО шаблон импорта в БД через UI
#     (POST /api/v1/app-config/install).

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
