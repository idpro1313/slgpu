#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  $0 <vllm|sglang> [-m|--model <preset>] [-h|--help]

Примеры:
  $0 vllm                          # TP=4, все GPU; модель из .env
  $0 sglang -m qwen3-30b-a3b       # пресет переопределяет MODEL_ID, MAX_MODEL_LEN и т.д.
  MODEL=llama-3.1-70b-instruct $0 sglang

Доступные пресеты (configs/models/<name>.env):
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

MODE=""
MODEL_SLUG="${MODEL:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    vllm|sglang) MODE="$1"; shift ;;
    -m|--model) MODEL_SLUG="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "${MODE}" ]]; then
  usage >&2
  exit 1
fi

slgpu_load_env "${MODEL_SLUG}"
echo "Модель: ${MODEL_ID}  (MAX_MODEL_LEN=${MAX_MODEL_LEN:-<default>}, KV=${KV_CACHE_DTYPE:-<default>}, reasoning=${REASONING_PARSER:-<off>})"

echo "Останавливаю vllm/sglang (если были)…"
docker compose stop vllm sglang 2>/dev/null || true
docker compose rm -f vllm sglang 2>/dev/null || true

echo "Поднимаю мониторинг…"
docker compose up -d dcgm-exporter node-exporter prometheus grafana

API_PORT=8111

case "${MODE}" in
  vllm)
    echo "Поднимаю vLLM (TP=${TP:-4}, все GPU), API :${API_PORT}…"
    docker compose --profile vllm up -d
    ;;
  sglang)
    echo "Поднимаю SGLang (TP=${TP:-4}, все GPU), API :${API_PORT}…"
    docker compose --profile sglang up -d
    ;;
esac

echo "Ожидание готовности http://127.0.0.1:${API_PORT}/v1/models …"
ok=0
for _ in $(seq 1 180); do
  if curl -sf "http://127.0.0.1:${API_PORT}/v1/models" >/dev/null; then
    echo "API http://127.0.0.1:${API_PORT}/v1/models отвечает."
    curl -s "http://127.0.0.1:${API_PORT}/v1/models" | head -c 400 || true
    echo
    ok=1
    break
  fi
  sleep 5
done
if [[ "${ok}" != "1" ]]; then
  echo "Таймаут ожидания API на :${API_PORT}. Логи: docker compose logs -f ${MODE}" >&2
  exit 1
fi
