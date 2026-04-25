#!/usr/bin/env bash
# Web control plane (slgpu-web): `docker/docker-compose.web.yml`, корень проекта = корень репо.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# Хостовый абсолютный путь репо. Web bind-mount’ит репо по этому же пути (docker/docker-compose.web.yml),
# чтобы команды из веб-контейнера (например `slgpu monitoring up`) отдавали docker daemon корректные
# хостовые пути для bind-маунтов конфигов и скриптов monitoring-стека.
export SLGPU_HOST_REPO="${ROOT}"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<'EOF'
Web UI (FastAPI + React) для управления slgpu: `./slgpu web up` из корня репозитория.

Сеть: внешняя `slgpu` (сначала `docker compose -f docker/docker-compose.llm.yml` или любой up, создавший сеть).

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
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file main.env up -d --build
    echo "slgpu-web: ${WEB_BIND:-0.0.0.0}:${WEB_PORT:-8089} → локально http://127.0.0.1:${WEB_PORT:-8089}/  ·  с других машин: http://<IP>:${WEB_PORT:-8089}/ (закрыть снаружи: WEB_BIND=127.0.0.1 в main.env)"
    ;;
  down)
    echo "Останавливаю slgpu-web…"
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file main.env down
    echo "Готово."
    ;;
  restart)
    slgpu_ensure_slgpu_network
    slgpu_load_server_env
    echo "Перезапуск slgpu-web…"
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file main.env up -d --build --force-recreate
    echo "Готово."
    ;;
  logs)
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file main.env logs -f --tail=200
    ;;
  build)
    slgpu_load_server_env
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file main.env build
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
