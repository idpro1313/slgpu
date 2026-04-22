#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

echo "=== docker compose ps ==="
docker compose ps -a || true

echo ""
ENGINE="$(slgpu_detect_running_engine)" || true
if [[ -n "${ENGINE}" ]]; then
  API_BASE="$(slgpu_openai_base_url "${ENGINE}")"
  echo "=== API ${API_BASE}/models (engine=${ENGINE}) ==="
  if curl -sf --max-time 3 "${API_BASE}/models" >/dev/null 2>&1; then
    curl -s --max-time 5 "${API_BASE}/models" | head -c 1200 || true
    echo
  else
    echo "(нет ответа — движок ещё стартует или сбой)"
  fi
else
  echo "=== API /v1/models (в compose не running vllm/sglang — пробую 8111 и 8222) ==="
  ok=0
  for p in 8111 8222; do
    if curl -sf --max-time 3 "http://127.0.0.1:${p}/v1/models" >/dev/null 2>&1; then
      curl -s --max-time 5 "http://127.0.0.1:${p}/v1/models" | head -c 1200 || true
      echo
      ok=1
      break
    fi
  done
  if [[ "${ok}" != "1" ]]; then
    echo "(нет ответа на :8111 / :8222)"
  fi
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
