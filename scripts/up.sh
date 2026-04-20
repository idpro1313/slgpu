#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:?Использование: $0 vllm|sglang|both}"

case "${MODE}" in
  vllm|sglang|both) ;;
  *)
    echo "Неизвестный режим: ${MODE} (ожидается vllm | sglang | both)" >&2
    exit 1
    ;;
esac

if [[ ! -f .env ]]; then
  echo "Нет файла .env — скопируйте: cp .env.example .env" >&2
  exit 1
fi

echo "Останавливаю vllm/sglang (если были)…"
docker compose stop vllm sglang 2>/dev/null || true
docker compose rm -f vllm sglang 2>/dev/null || true

echo "Поднимаю мониторинг…"
docker compose up -d dcgm-exporter prometheus grafana

case "${MODE}" in
  vllm)
    echo "Поднимаю vLLM (TP=${TP:-4}, все GPU)…"
    docker compose --profile vllm up -d
    PORTS=(8111)
    ;;
  sglang)
    echo "Поднимаю SGLang (TP=${TP:-4}, все GPU)…"
    docker compose --profile sglang up -d
    PORTS=(8222)
    ;;
  both)
    export TP="${TP:-2}"
    echo "Co-run: vLLM (GPU 0,1) + SGLang (GPU 2,3), TP=${TP}…"
    docker compose \
      -f docker-compose.yml \
      -f docker-compose.both.yml \
      --profile vllm --profile sglang up -d
    PORTS=(8111 8222)
    ;;
esac

for PORT in "${PORTS[@]}"; do
  echo "Ожидание готовности http://127.0.0.1:${PORT}/v1/models …"
  ok=0
  for _ in $(seq 1 180); do
    if curl -sf "http://127.0.0.1:${PORT}/v1/models" >/dev/null; then
      echo "Сервис на :${PORT} отвечает."
      curl -s "http://127.0.0.1:${PORT}/v1/models" | head -c 400 || true
      echo
      ok=1
      break
    fi
    sleep 5
  done
  if [[ "${ok}" != "1" ]]; then
    echo "Таймаут ожидания API на :${PORT}. Логи: docker compose logs -f (vllm|sglang)" >&2
    exit 1
  fi
done
