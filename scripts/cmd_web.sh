#!/usr/bin/env bash
# Web control plane (slgpu-web): тот же compose, что `web/docker-compose.yml`, с корнем проекта = корень репо.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<'EOF'
Web UI (FastAPI + React) для управления slgpu: `./slgpu web up` из корня репозитория.

Сеть: внешняя `slgpu` (сначала `docker compose -f docker-compose.yml` или любой up, создавший сеть).

Переменные: `main.env` (порты LLM, monitoring, `MODELS_DIR`, `WEB_DATA_DIR` и т.д.).

Использование:
  ./slgpu web up|down|restart|logs|build
  ./slgpu web -h

Тома по умолчанию (см. `data/README.md`):
  - WEB_DATA_DIR  → ./data/web  (SQLite)
  - MODELS_DIR    → ./data/models
EOF
}

SUB="${1:-}"
shift || true

case "${SUB}" in
  up)
    slgpu_ensure_slgpu_network
    slgpu_load_server_env
    slgpu_ensure_data_dirs
    echo "Поднимаю slgpu-web…"
    slgpu_docker_compose -f web/docker-compose.yml --env-file main.env up -d --build
    echo "UI: http://${WEB_BIND:-127.0.0.1}:${WEB_PORT:-8089}/  (WEB_BIND, WEB_PORT в main.env или окружении)"
    ;;
  down)
    echo "Останавливаю slgpu-web…"
    slgpu_docker_compose -f web/docker-compose.yml --env-file main.env down
    echo "Готово."
    ;;
  restart)
    slgpu_ensure_slgpu_network
    slgpu_load_server_env
    echo "Перезапуск slgpu-web…"
    slgpu_docker_compose -f web/docker-compose.yml --env-file main.env up -d --build --force-recreate
    echo "Готово."
    ;;
  logs)
    slgpu_docker_compose -f web/docker-compose.yml --env-file main.env logs -f --tail=200
    ;;
  build)
    slgpu_load_server_env
    slgpu_docker_compose -f web/docker-compose.yml --env-file main.env build
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
