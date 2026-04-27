#!/usr/bin/env bash
# Web control plane: `docker/docker-compose.web.yml`, корень проекта = корень репо.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export SLGPU_HOST_REPO="${ROOT}"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<'EOF'
Web UI (FastAPI + React) для slgpu: `./slgpu web` из корня репозитория.

Сеть: внешняя `slgpu` (создаётся этим скриптом при `web up`).

Переменные: **обязателен** `configs/main.env` (bootstrap: WEB_PORT, WEB_BIND, WEB_DATA_DIR, MODELS_DIR, SLGPU_HOST_REPO, …).
Импорт в SQLite: из UI (POST /api/v1/app-config/install) — только из `configs/main.env`, без configs/secrets.

Использование:
  ./slgpu web up|down|restart|logs
  ./slgpu web -h
EOF
}

SUB="${1:-}"
shift || true

case "${SUB}" in
  up)
    slgpu_require_docker
    slgpu_ensure_slgpu_network
    slgpu_load_server_env
    slgpu_ensure_data_dirs
    _web_env="$(slgpu_web_compose_env_file)"
    echo "Поднимаю slgpu-web… (env-file: ${_web_env#"${ROOT}"/})"
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file "${_web_env}" up -d --build
    echo "slgpu-web: ${WEB_BIND}:${WEB_PORT} — см. WEB_* в configs/main.env"
    ;;
  down)
    _web_env="$(slgpu_web_compose_env_file)"
    echo "Останавливаю slgpu-web… (env-file: ${_web_env#"${ROOT}"/})"
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file "${_web_env}" down
    echo "Готово."
    ;;
  restart)
    slgpu_require_docker
    slgpu_ensure_slgpu_network
    slgpu_load_server_env
    _web_env="$(slgpu_web_compose_env_file)"
    echo "Перезапуск slgpu-web… (env-file: ${_web_env#"${ROOT}"/})"
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file "${_web_env}" up -d --build --force-recreate
    echo "Готово."
    ;;
  logs)
    slgpu_require_docker
    _web_env="$(slgpu_web_compose_env_file)"
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file "${_web_env}" logs -f --tail=200
    ;;
  -h|--help|help) usage ;;
  "")
    usage >&2
    exit 1
    ;;
  *)
    echo "Неизвестная подкоманда: ${SUB}" >&2
    usage >&2
    exit 1
    ;;
esac
