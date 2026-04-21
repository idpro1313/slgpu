#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<EOF
Использование:
  ./slgpu logs [SERVICE] [-- docker-compose logs args...]

SERVICE: vllm | sglang | prometheus | grafana | dcgm-exporter | node-exporter
Без SERVICE — логи того LLM-сервиса, который сейчас running (vllm или sglang).

Примеры:
  ./slgpu logs vllm -f
  ./slgpu logs --tail=50 prometheus
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

SERVICE="${1:-}"
if [[ -n "${SERVICE}" && "${SERVICE}" != -* ]]; then
  shift
else
  SERVICE=""
fi

if [[ -z "${SERVICE}" ]]; then
  if docker compose ps --status running --services 2>/dev/null | grep -qx 'vllm'; then
    exec docker compose logs -f --tail=200 vllm "$@"
  elif docker compose ps --status running --services 2>/dev/null | grep -qx 'sglang'; then
    exec docker compose logs -f --tail=200 sglang "$@"
  else
    echo "Ни vllm, ни sglang не запущены. Укажите сервис, например: ./slgpu logs prometheus -f" >&2
    exit 1
  fi
fi

exec docker compose logs -f --tail=200 "${SERVICE}" "$@"
