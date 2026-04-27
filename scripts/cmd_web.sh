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

Переменные: `main.env` **опционален** для up/down/… (если нет — `docker/web-compose.defaults.env` + дефолты в YAML). Для **`./slgpu web install`** импорт в SQLite — из `main.env` (должен быть в корне); до этого достаточно `web up` без файла.

Использование:
  ./slgpu web up|down|restart|logs|build|install
  ./slgpu web -h

Подкоманда install вызывает HTTP API уже запущенного slgpu-web: сначала ./slgpu web up, затем install.

Тома по умолчанию (см. `data/README.md`):
  - WEB_DATA_DIR  → ./data/web  (SQLite)
  - MODELS_DIR    → ./data/models
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
    echo "slgpu-web: ${WEB_BIND:-0.0.0.0}:${WEB_PORT:-8089} → локально http://127.0.0.1:${WEB_PORT:-8089}/  ·  с других машин: http://<IP>:${WEB_PORT:-8089}/ (закрыть снаружи: WEB_BIND=127.0.0.1 в main.env или export перед up)"
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
  build)
    slgpu_require_docker
    slgpu_load_server_env
    _web_env="$(slgpu_web_compose_env_file)"
    slgpu_docker_compose -f docker/docker-compose.web.yml --env-file "${_web_env}" build
    ;;
  install)
    slgpu_require_docker
    slgpu_load_server_env
    _port="${WEB_PORT:-8089}"
    _bind="${WEB_BIND:-0.0.0.0}"
    if [[ "${_bind}" == "0.0.0.0" ]]; then
      _curl_host="127.0.0.1"
    else
      _curl_host="${_bind}"
    fi
    _running=""
    if docker inspect -f '{{.State.Running}}' slgpu-web 2>/dev/null | grep -qx true; then
      _running=1
    fi
    if [[ -z "${_running}" ]]; then
      echo "[web install] Ошибка: контейнер slgpu-web не запущен (на ${_curl_host}:${_port} некому отвечать)." >&2
      echo "[web install] Сначала: ./slgpu web up   затем снова: ./slgpu web install" >&2
      exit 1
    fi
    _url_host="http://${_curl_host}:${_port}/api/v1/app-config/install"
    _url_in="http://127.0.0.1:8000/api/v1/app-config/install"
    echo "[web install] POST ${_url_host} …"
    if curl -sfS --connect-timeout 5 -X POST "${_url_host}" \
      -H "Content-Type: application/json" \
      -d '{"force":false}' | cat; then
      :
    else
      echo "[web install] Запрос к хосту не прошёл, пробую изнутри контейнера slgpu-web (${_url_in})…" >&2
      docker exec slgpu-web curl -sfS --connect-timeout 5 -X POST "${_url_in}" \
        -H "Content-Type: application/json" \
        -d '{"force":false}' | cat
    fi
    echo ""
    echo "Готово. Повтор с перезаписью: curl ... -d '{\"force\":true}'"
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
