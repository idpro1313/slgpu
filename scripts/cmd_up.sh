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

# Для docker compose: явно передаём LLM_API_PORT/LLM_API_BIND, чтобы подстановка в
# docker-compose.yml не взяла устаревшее значение из корневого .env без учёта -p.
compose_llm_env() {
  env LLM_API_PORT="${API_PORT}" LLM_API_BIND="${LLM_API_BIND:-0.0.0.0}" "$@"
}

echo "Останавливаю vllm/sglang (если были)…"
compose_llm_env docker compose stop vllm sglang 2>/dev/null || true
compose_llm_env docker compose rm -f vllm sglang 2>/dev/null || true

echo "Поднимаю мониторинг…"
docker compose up -d dcgm-exporter node-exporter prometheus grafana

case "${MODE}" in
  vllm)
    echo "Поднимаю vLLM (TP=${TP:-8}, все GPU), API :${API_PORT}…"
    compose_llm_env docker compose --profile vllm up -d
    ;;
  sglang)
    echo "Поднимаю SGLang (TP=${TP:-8}, все GPU), API :${API_PORT}…"
    compose_llm_env docker compose --profile sglang up -d
    ;;
esac

sleep 2
mapped="$(compose_llm_env docker compose port "${MODE}" 8111 2>/dev/null | head -1 || true)"
if [[ -n "${mapped}" ]]; then
  echo "Проброс порта 8111 (внутри контейнера) → хост: ${mapped}"
  if [[ "${mapped}" =~ :([0-9]+)$ ]]; then
    if [[ "${BASH_REMATCH[1]}" != "${API_PORT}" ]]; then
      echo "ВНИМАНИЕ: ожидаемый порт хоста -p ${API_PORT}, compose сообщает :${BASH_REMATCH[1]}. Проверьте LLM_API_PORT в .env и повторите up." >&2
    fi
  fi
else
  echo "Не удалось получить проброс порта (сервис ещё стартует или контейнер не в сети)." >&2
fi

# До 30 минут: тяжёлые MoE/медленный диск могут не уложиться в 15 минут.
: "${SLGPU_UP_READY_ATTEMPTS:=360}"
echo "Ожидание готовности http://127.0.0.1:${API_PORT}/v1/models … (до $((SLGPU_UP_READY_ATTEMPTS * 5 / 60)) мин, шаг 5 с; SLGPU_UP_READY_ATTEMPTS при необходимости) …"
ok=0
for _ in $(seq 1 "${SLGPU_UP_READY_ATTEMPTS}"); do
  if curl -sf --connect-timeout 3 --max-time 20 "http://127.0.0.1:${API_PORT}/v1/models" >/dev/null; then
    echo "API http://127.0.0.1:${API_PORT}/v1/models отвечает."
    curl -s --connect-timeout 3 --max-time 20 "http://127.0.0.1:${API_PORT}/v1/models" | head -c 400 || true
    echo
    ok=1
    break
  fi
  sleep 5
done
if [[ "${ok}" != "1" ]]; then
  echo "Таймаут ожидания API на :${API_PORT}. Логи: docker compose logs -f ${MODE}" >&2
  echo "=== docker compose port ${MODE} 8111 ===" >&2
  compose_llm_env docker compose port "${MODE}" 8111 2>&1 >&2 || true
  echo "=== docker compose ps (фрагмент) ===" >&2
  docker compose ps 2>&1 | head -n 20 >&2
  exit 1
fi
