#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

echo "=== docker compose ps ==="
docker compose ps -a || true

echo ""
echo "=== API :8111 /v1/models (если отвечает) ==="
if curl -sf --max-time 3 "http://127.0.0.1:8111/v1/models" >/dev/null 2>&1; then
  curl -s --max-time 5 "http://127.0.0.1:8111/v1/models" | head -c 1200 || true
  echo
else
  echo "(нет ответа на 127.0.0.1:8111 — движок не поднят или ещё стартует)"
fi

echo ""
echo "=== nvidia-smi (кратко) ==="
if command -v nvidia-smi &>/dev/null; then
  nvidia-smi --query-gpu=index,name,memory.total,memory.used,temperature.gpu --format=csv,noheader 2>/dev/null || nvidia-smi | head -n 20
else
  echo "nvidia-smi не найден"
fi

echo ""
echo "Подсказка: ./slgpu config vllm -m <preset> — полный список переменных для запуска."
