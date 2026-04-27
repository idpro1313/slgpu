#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

slgpu_require_docker

ALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) ALL=1; shift ;;
    -h|--help)
      cat <<EOF
Использование:
  ./slgpu down              # остановить vllm и sglang (docker/docker-compose.llm.yml)
  ./slgpu down --all        # остановить движок, мониторинг и slgpu-web (docker-compose.web.yml)
EOF
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "${ALL}" -eq 1 ]]; then
  echo "Останавливаю vllm, sglang, proxy (LiteLLM), мониторинг и slgpu-web…"
  _web_env="$(slgpu_web_compose_env_file)"
  slgpu_docker_compose -f docker/docker-compose.llm.yml stop 2>/dev/null || true
  slgpu_docker_compose -f docker/docker-compose.proxy.yml --env-file main.env stop 2>/dev/null || true
  slgpu_docker_compose -f docker/docker-compose.monitoring.yml stop 2>/dev/null || true
  slgpu_docker_compose -f docker/docker-compose.web.yml --env-file "${_web_env}" stop 2>/dev/null || true
else
  echo "Останавливаю vllm и sglang…"
  slgpu_docker_compose -f docker/docker-compose.llm.yml stop vllm sglang 2>/dev/null || true
  slgpu_docker_compose -f docker/docker-compose.llm.yml rm -f vllm sglang 2>/dev/null || true
fi
echo "Готово."
