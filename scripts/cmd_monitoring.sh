#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Мониторинг (dcgm-exporter, node-exporter, Prometheus, Grafana) — отдельно от движка vLLM/SGLang.

Один раз на хост (или после reboot, если не включён restart: unless-stopped):
  ./slgpu monitoring up

Остановить только стек мониторинга (модель не трогает):
  ./slgpu monitoring down

Перезапуск контейнеров мониторинга:
  ./slgpu monitoring restart

Конфиг: docker-compose.monitoring.yml, сеть \`slgpu\` — общая с docker-compose.yml (Prometheus → vllm:8111 / sglang:8222).

Переменные портов и ретенции — main.env (как раньше).

EOF
}

SUB="${1:-}"
shift || true

case "${SUB}" in
  up)
    slgpu_ensure_slgpu_network
    slgpu_load_server_env
    echo "Поднимаю мониторинг (slgpu-monitoring)…"
    docker compose -f docker-compose.monitoring.yml --env-file main.env up -d
    echo "Проверка: Prometheus /targets (по умолч. http://127.0.0.1:9090/targets, см. PROMETHEUS_BIND в main.env) · Grafana: GRAFANA_PORT"
    ;;
  down)
    echo "Останавливаю мониторинг…"
    docker compose -f docker-compose.monitoring.yml down
    echo "Готово."
    ;;
  restart)
    slgpu_ensure_slgpu_network
    slgpu_load_server_env
    echo "Перезапуск мониторинга…"
    docker compose -f docker-compose.monitoring.yml --env-file main.env up -d --force-recreate
    echo "Готово."
    ;;
  -h|--help|help)
    usage
    ;;
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
