#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  ./slgpu up <vllm|sglang> -m|--model <preset> [-p|--port <порт>] [-h|--help]

  -p, --port   порт API на хосте (по умолчанию 8111)

Примеры:
  ./slgpu up vllm -m qwen3.6-35b-a3b
  ./slgpu up vllm -m qwen3.6-35b-a3b -p 8222
  ./slgpu up sglang -m qwen3-30b-a3b

Пресеты (configs/models/<name>.env):
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

MODE=""
MODEL_SLUG=""
API_PORT=8111
while [[ $# -gt 0 ]]; do
  case "$1" in
    vllm|sglang) MODE="$1"; shift ;;
    -m|--model) MODEL_SLUG="${2:?}"; shift 2 ;;
    -p|--port)
      if [[ -z "${2:-}" || "${2:-}" == -* ]]; then
        echo "Опция $1 требует номер порта (1–65535)" >&2
        usage >&2
        exit 1
      fi
      API_PORT="${2}"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "${MODE}" ]]; then
  usage >&2
  exit 1
fi

if ! [[ "${API_PORT}" =~ ^[0-9]+$ ]] || (( API_PORT < 1 || API_PORT > 65535 )); then
  echo "Некорректный порт API: ${API_PORT} (нужен 1–65535)" >&2
  exit 1
fi

slgpu_load_compose_env "${MODEL_SLUG}" "${MODE}"
export LLM_API_PORT="${API_PORT}"
echo "Модель: ${MODEL_ID}  (MAX_MODEL_LEN=${MAX_MODEL_LEN:-<default>}, KV=${KV_CACHE_DTYPE:-<default>}, reasoning=${REASONING_PARSER:-<off>})"

echo "Останавливаю vllm/sglang (если были)…"
docker compose stop vllm sglang 2>/dev/null || true
docker compose rm -f vllm sglang 2>/dev/null || true

echo "Поднимаю мониторинг…"
docker compose up -d dcgm-exporter node-exporter prometheus grafana

case "${MODE}" in
  vllm)
    echo "Поднимаю vLLM (TP=${TP:-8}, все GPU), API :${API_PORT}…"
    docker compose --profile vllm up -d
    ;;
  sglang)
    echo "Поднимаю SGLang (TP=${TP:-8}, все GPU), API :${API_PORT}…"
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
