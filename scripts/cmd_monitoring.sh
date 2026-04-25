#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Мониторинг: dcgm-exporter, node-exporter, Prometheus, Grafana, **Loki**, **Promtail**, **Langfuse** (UI + self-host БД/окно трейсинга), **LiteLLM** (шлюз OpenAI → vLLM) — отдельно от движка vLLM/SGLang. Логи: **Grafana → Explore → Loki** (источник в provisioning). Langfuse: \`http://<хост>:\$LANGFUSE_PORT\` (по умолч. 3001), LiteLLM: порт LITELLM_PORT (по умолч. 4000); вызовы LiteLLM — см. `configs/monitoring/litellm/config.yaml` (часто **devllm** = `SLGPU_SERVED_MODEL_NAME`).

Один раз на хост (или после reboot, если не включён restart: unless-stopped):
  ./slgpu monitoring up

Остановить только стек мониторинга (модель не трогает):
  ./slgpu monitoring down

Перезапуск контейнеров мониторинга:
  ./slgpu monitoring restart

Права на каталоги данных (bind mount: Grafana, Prometheus, **Loki**, **Promtail**/positions): по uid:gid **из образов** (рекомендуется до up или при ошибках):
  ./slgpu monitoring fix-perms
  (см. scripts/monitoring_fix_permissions.sh, main.env: GRAFANA_DATA_DIR, PROMETHEUS_DATA_DIR, LOKI_DATA_DIR, PROMTAIL_DATA_DIR, LANGFUSE_*_DATA_DIR)

Конфиг: `docker/docker-compose.monitoring.yml`, сеть \`slgpu\` — общая с `docker/docker-compose.llm.yml` (Prometheus → vllm:8111 / sglang:8222).

Переменные портов и ретенции — main.env (как раньше).

EOF
}

SUB="${1:-}"
shift || true

slgpu_ensure_monitoring_bind_config_files() {
  slgpu_ensure_config_yaml_is_file \
    "${ROOT}/configs/monitoring/loki/loki-config.yaml" \
    "configs/monitoring/loki/loki-config.yaml"
  slgpu_ensure_config_yaml_is_file \
    "${ROOT}/configs/monitoring/promtail/promtail-config.yml" \
    "configs/monitoring/promtail/promtail-config.yml"
  slgpu_ensure_config_yaml_is_file \
    "${ROOT}/configs/monitoring/prometheus/prometheus.yml" \
    "configs/monitoring/prometheus/prometheus.yml"
  slgpu_ensure_config_yaml_is_file \
    "${ROOT}/configs/monitoring/prometheus/prometheus-alerts.yml" \
    "configs/monitoring/prometheus/prometheus-alerts.yml"
}

slgpu_ensure_langfuse_litellm_secrets() {
  local s="${ROOT}/configs/secrets/langfuse-litellm.env"
  local ex="${ROOT}/configs/secrets/langfuse-litellm.env.example"
  if [[ ! -f "${s}" ]]; then
    if [[ -f "${ex}" ]]; then
      cp "${ex}" "${s}"
      echo "Создан ${s} из примера — при необходимости вставьте LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY (Langfuse → Project → API keys)."
    else
      echo "Предупреждение: нет ${ex}, не могу создать ${s}" >&2
    fi
  fi
}

case "${SUB}" in
  up)
    slgpu_ensure_slgpu_network
    slgpu_ensure_langfuse_litellm_secrets
    slgpu_load_server_env
    slgpu_ensure_data_dirs
    slgpu_ensure_monitoring_bind_config_files
    echo "Поднимаю мониторинг (slgpu-monitoring)…"
    slgpu_docker_compose -f docker/docker-compose.monitoring.yml --env-file main.env up -d
    echo "Проверка: Prometheus /targets (http://<хост>:9090/targets) · Grafana: GRAFANA_PORT · Loki: Explore → Loki · Langfuse: :${LANGFUSE_PORT:-3001} · LiteLLM: :${LITELLM_PORT:-4000} (vLLM: LLM_API_PORT → configs/monitoring/litellm/config.yaml, devllm = SLGPU_SERVED_MODEL_NAME)"
    ;;
  down)
    echo "Останавливаю мониторинг…"
    slgpu_docker_compose -f docker/docker-compose.monitoring.yml down
    echo "Готово."
    ;;
  restart)
    slgpu_ensure_slgpu_network
    slgpu_ensure_langfuse_litellm_secrets
    slgpu_load_server_env
    slgpu_ensure_monitoring_bind_config_files
    echo "Перезапуск мониторинга…"
    slgpu_docker_compose -f docker/docker-compose.monitoring.yml --env-file main.env up -d --force-recreate
    echo "Готово."
    ;;
  fix-perms|fix_permissions)
    exec bash "${ROOT}/scripts/monitoring_fix_permissions.sh"
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
