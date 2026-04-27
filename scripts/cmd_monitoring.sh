#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Мониторинг: dcgm-exporter, node-exporter, Prometheus, Grafana, **Loki**, **Promtail**, **Langfuse** (UI + self-host БД) — `docker/docker-compose.monitoring.yml` (проект **slgpu-monitoring**). **LiteLLM** (OpenAI → vLLM) — в отдельном compose **`docker/docker-compose.proxy.yml`**, проект **slgpu-proxy**; сеть `slgpu` та же. Логи: **Grafana → Explore → Loki**. Langfuse: `http://<хост>:$LANGFUSE_PORT` (по умолч. 3001), LiteLLM: LITELLM_PORT (по умолч. 4000); модели/маршруты — `configs/monitoring/litellm/config.yaml` и /ui (часто **devllm** = `SERVED_MODEL_NAME`).

Один раз на хост (или после reboot, если не включён restart: unless-stopped):
  ./slgpu monitoring up
  (первый up на новом сервере: bootstrap MinIO + БД litellm в postgres, затем monitoring + **proxy (LiteLLM)**)

Остановить только стек мониторинга (модель не трогает):
  ./slgpu monitoring down

Перезапуск контейнеров мониторинга:
  ./slgpu monitoring restart

Принудительно повторить одноразовый bootstrap:
  ./slgpu monitoring bootstrap
  SLGPU_MONITORING_BOOTSTRAP_FORCE=1 ./slgpu monitoring bootstrap

Права на каталоги данных (bind mount: Grafana, Prometheus, **Loki**, **Promtail**/positions): по uid:gid **из образов** (рекомендуется до up или при ошибках):
  ./slgpu monitoring fix-perms
  (см. scripts/monitoring_fix_permissions.sh, main.env: GRAFANA_DATA_DIR, PROMETHEUS_DATA_DIR, LOKI_DATA_DIR, PROMTAIL_DATA_DIR, LANGFUSE_*_DATA_DIR)

Конфиг: `docker/docker-compose.monitoring.yml` + `docker/docker-compose.proxy.yml` (LiteLLM); сеть `slgpu` — общая с `docker/docker-compose.llm.yml`.

Порты/секреты: при наличии **`main.env`** — копируется в **`.slgpu/compose-service.env`** перед compose; иначе используется уже записанный снимок (например из slgpu-web из БД) или **`docker/web-compose.defaults.env`**.

EOF
}

SUB="${1:-}"
shift || true

slgpu_ensure_monitoring_bind_config_files() {
  # YAML конфиги (одиночные bind в compose).
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
  # Скрипты-entrypoint (одиночные bind). Если из-за рассогласования путей
  # docker daemon когда-либо создал на их месте пустые каталоги — лечим заранее.
  slgpu_ensure_config_yaml_is_file \
    "${ROOT}/configs/monitoring/langfuse/minio-bucket-init.sh" \
    "configs/monitoring/langfuse/minio-bucket-init.sh"
  slgpu_ensure_config_yaml_is_file \
    "${ROOT}/configs/monitoring/litellm/init-litellm-db.sh" \
    "configs/monitoring/litellm/init-litellm-db.sh"
  slgpu_ensure_config_yaml_is_file \
    "${ROOT}/configs/monitoring/litellm/litellm-entrypoint.sh" \
    "configs/monitoring/litellm/litellm-entrypoint.sh"
  slgpu_ensure_config_yaml_is_file \
    "${ROOT}/configs/monitoring/litellm/config.yaml" \
    "configs/monitoring/litellm/config.yaml"
}

slgpu_ensure_langfuse_litellm_secrets() {
  # С compose: data/web/… (см. docker-compose.monitoring.yml). Устаревший configs/secrets/ — только с хоста вручную.
  local s="${ROOT}/data/web/secrets/langfuse-litellm.env"
  local ex="${ROOT}/configs/secrets/langfuse-litellm.env.example"
  if [[ ! -f "${s}" ]]; then
    if [[ -f "${ex}" ]]; then
      mkdir -p "$(dirname "${s}")"
      cp "${ex}" "${s}"
      echo "Создан ${s} из примера — при необходимости вставьте LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY (Langfuse → Project → API keys)."
    else
      echo "Предупреждение: нет ${ex}, не могу создать ${s}" >&2
    fi
  fi
}

slgpu_monitoring_bootstrap_dir() {
  echo "${ROOT}/data/monitoring/.bootstrap"
}

slgpu_monitoring_run_bootstrap_service() {
  local svc="$1"
  local marker="$2"
  local dir
  dir="$(slgpu_monitoring_bootstrap_dir)"
  mkdir -p "${dir}"

  if [[ -f "${marker}" && "${SLGPU_MONITORING_BOOTSTRAP_FORCE:-0}" != "1" ]]; then
    echo "Bootstrap ${svc}: уже выполнен (${marker#${ROOT}/})."
    return 0
  fi

  echo "Bootstrap ${svc}: одноразовый запуск…"
  slgpu_ensure_compose_service_env
  _ce="$(slgpu_compose_service_env_basename)"
  slgpu_docker_compose -f docker/docker-compose.monitoring.yml --env-file "${_ce}" --profile bootstrap rm -f -s -v "${svc}" >/dev/null 2>&1 || true
  slgpu_docker_compose -f docker/docker-compose.monitoring.yml --env-file "${_ce}" --profile bootstrap up --abort-on-container-exit --exit-code-from "${svc}" "${svc}"
  slgpu_docker_compose -f docker/docker-compose.monitoring.yml --env-file "${_ce}" --profile bootstrap rm -f -s -v "${svc}" >/dev/null 2>&1 || true
  touch "${marker}"
  echo "Bootstrap ${svc}: готово."
}

slgpu_monitoring_bootstrap_once() {
  local dir
  dir="$(slgpu_monitoring_bootstrap_dir)"
  mkdir -p "${dir}"
  slgpu_monitoring_run_bootstrap_service "minio-bucket-init" "${dir}/minio-bucket-init.done"
  slgpu_monitoring_run_bootstrap_service "litellm-pg-init" "${dir}/litellm-pg-init.done"
}

case "${SUB}" in
  up)
    slgpu_require_docker
    slgpu_ensure_slgpu_network
    slgpu_ensure_langfuse_litellm_secrets
    slgpu_load_server_env
    slgpu_ensure_data_dirs
    slgpu_ensure_compose_service_env
    _ce="$(slgpu_compose_service_env_basename)"
    slgpu_ensure_monitoring_bind_config_files
    slgpu_monitoring_bootstrap_once
    echo "Поднимаю мониторинг (slgpu-monitoring)…"
    slgpu_docker_compose -f docker/docker-compose.monitoring.yml --env-file "${_ce}" up -d --remove-orphans
    echo "Поднимаю LiteLLM (slgpu-proxy)…"
    slgpu_docker_compose -f docker/docker-compose.proxy.yml --env-file "${_ce}" up -d
    echo "Проверка: Prometheus /targets (http://<хост>:9090/targets) · Grafana: GRAFANA_PORT · Loki: Explore → Loki · Langfuse: :${LANGFUSE_PORT:-3001} · LiteLLM: :${LITELLM_PORT:-4000} (vLLM: LLM_API_PORT → configs/monitoring/litellm/config.yaml, devllm = SERVED_MODEL_NAME)"
    ;;
  down)
    slgpu_require_docker
    slgpu_ensure_compose_service_env
    _ce="$(slgpu_compose_service_env_basename)"
    echo "Останавливаю LiteLLM (slgpu-proxy)…"
    slgpu_docker_compose -f docker/docker-compose.proxy.yml --env-file "${_ce}" down 2>/dev/null || true
    echo "Останавливаю мониторинг (slgpu-monitoring)…"
    slgpu_docker_compose -f docker/docker-compose.monitoring.yml --env-file "${_ce}" down
    echo "Готово."
    ;;
  restart)
    slgpu_require_docker
    slgpu_ensure_slgpu_network
    slgpu_ensure_langfuse_litellm_secrets
    slgpu_load_server_env
    slgpu_ensure_compose_service_env
    _ce="$(slgpu_compose_service_env_basename)"
    slgpu_ensure_monitoring_bind_config_files
    echo "Перезапуск мониторинга…"
    slgpu_docker_compose -f docker/docker-compose.monitoring.yml --env-file "${_ce}" up -d --force-recreate --remove-orphans
    echo "Перезапуск LiteLLM (slgpu-proxy)…"
    slgpu_docker_compose -f docker/docker-compose.proxy.yml --env-file "${_ce}" up -d --force-recreate
    echo "Готово."
    ;;
  bootstrap)
    slgpu_require_docker
    slgpu_ensure_slgpu_network
    slgpu_ensure_langfuse_litellm_secrets
    slgpu_load_server_env
    slgpu_ensure_data_dirs
    slgpu_ensure_compose_service_env
    slgpu_ensure_monitoring_bind_config_files
    SLGPU_MONITORING_BOOTSTRAP_FORCE="${SLGPU_MONITORING_BOOTSTRAP_FORCE:-1}" slgpu_monitoring_bootstrap_once
    echo "Bootstrap готов."
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
