#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENGINE="${1:?Использование: $0 vllm|sglang}"

case "${ENGINE}" in
  vllm|sglang) ;;
  *)
    echo "Неизвестный движок: ${ENGINE} (ожидается vllm или sglang)" >&2
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

echo "Поднимаю мониторинг + профиль ${ENGINE}…"
docker compose up -d dcgm-exporter prometheus grafana
docker compose --profile "${ENGINE}" up -d

case "${ENGINE}" in
  vllm) PORT=8111 ;;
  sglang) PORT=8222 ;;
esac

echo "Ожидание готовности http://127.0.0.1:${PORT}/v1/models …"
for _ in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:${PORT}/v1/models" >/dev/null; then
    echo "Сервис отвечает."
    curl -s "http://127.0.0.1:${PORT}/v1/models" | head -c 400 || true
    echo
    exit 0
  fi
  sleep 5
done

echo "Таймаут ожидания API. Логи: docker compose logs -f ${ENGINE}" >&2
exit 1
