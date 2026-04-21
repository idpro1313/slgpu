#!/usr/bin/env bash
set -euo pipefail

ENGINE="${1:?Использование: $0 vllm|sglang}"

case "${ENGINE}" in
  vllm|sglang) ;;
  *)
    echo "Неизвестный движок: ${ENGINE}" >&2
    exit 1
    ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

PORT=8111
curl -sf "http://127.0.0.1:${PORT}/v1/models" | head -c 800
echo
