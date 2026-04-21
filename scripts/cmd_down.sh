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
  ./slgpu down              # остановить и удалить контейнеры vllm и sglang
  ./slgpu down --all        # остановить все сервисы compose (включая мониторинг)
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
  echo "Останавливаю все сервисы slgpu…"
  docker compose stop
else
  echo "Останавливаю vllm и sglang…"
  docker compose stop vllm sglang 2>/dev/null || true
  docker compose rm -f vllm sglang 2>/dev/null || true
fi
echo "Готово."
