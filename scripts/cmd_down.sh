#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) ALL=1; shift ;;
    -h|--help)
      cat <<EOF
Использование:
  ./slgpu down              # остановить vllm и sglang (docker-compose.yml)
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
  docker compose -f docker-compose.yml stop 2>/dev/null || true
  docker compose -f docker-compose.monitoring.yml stop 2>/dev/null || true
else
  echo "Останавливаю vllm и sglang…"
  docker compose -f docker-compose.yml stop vllm sglang 2>/dev/null || true
  docker compose -f docker-compose.yml rm -f vllm sglang 2>/dev/null || true
fi
echo "Готово."
