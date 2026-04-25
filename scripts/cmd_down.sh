#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

ALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) ALL=1; shift ;;
    -h|--help)
      cat <<EOF
Использование:
  ./slgpu down              # остановить vllm и sglang (docker/docker-compose.yml)
  ./slgpu down --all        # остановить движок и стек мониторинга
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
  echo "Останавливаю vllm, sglang и мониторинг…"
  slgpu_docker_compose -f docker/docker-compose.yml stop 2>/dev/null || true
  slgpu_docker_compose -f docker/docker-compose.monitoring.yml stop 2>/dev/null || true
else
  echo "Останавливаю vllm и sglang…"
  slgpu_docker_compose -f docker/docker-compose.yml stop vllm sglang 2>/dev/null || true
  slgpu_docker_compose -f docker/docker-compose.yml rm -f vllm sglang 2>/dev/null || true
fi
echo "Готово."
