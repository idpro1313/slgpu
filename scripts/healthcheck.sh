#!/usr/bin/env bash
set -euo pipefail

ENGINE="${1:?Использование: $0 vllm|sglang}"

case "${ENGINE}" in
  vllm) PORT=8111 ;;
  sglang) PORT=8222 ;;
  *)
    echo "Неизвестный движок: ${ENGINE}" >&2
    exit 1
    ;;
esac

curl -sf "http://127.0.0.1:${PORT}/v1/models" | head -c 800
echo
