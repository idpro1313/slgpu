#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  ./slgpu up [<vllm|sglang>] [-m|--model <пресет>] [-p|--port <порт>] [--tp <N>] [-h|--help]

  Без аргументов (нужен TTY): сначала выбор движка (vLLM / SGLang), затем выбор пресета из списка *.env в PRESETS_DIR (см. main.env, по умолчанию data/presets).
  Можно указать только движок — тогда запросят пресет. Только -m <пресет> без движка — запросят движок.

  -p, --port   порт API на хосте (vLLM: по умолчанию 8111; SGLang: 8222)
  --tp <N>     tensor parallel на этот запуск (переопределяет TP из пресета; по умолчанию — из файла, иначе 8 в serve.sh)

Примеры:
  ./slgpu up vllm -m qwen3.6-35b-a3b
  ./slgpu up vllm -m qwen3.6-35b-a3b --tp 4
  ./slgpu up vllm -m qwen3.6-35b-a3b -p 8222
  ./slgpu up sglang -m qwen3-30b-a3b --tp 4

Пресеты (каталог PRESETS_DIR, по умолчанию data/presets/<name>.env):
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

MODE=""
MODEL_SLUG=""
API_PORT=""
PORT_GIVEN=0
TP_OVERRIDE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    vllm|sglang) MODE="$1"; shift ;;
    -m|--model)
      if [[ -z "${2:-}" || "${2}" == -* ]]; then
        slgpu_fail_if_missing_preset_arg "$1"
        exit 1
      fi
      MODEL_SLUG="${2}"
      shift 2
      ;;
    -p|--port)
      if [[ -z "${2:-}" || "${2:-}" == -* ]]; then
        echo "Опция $1 требует номер порта (1–65535)" >&2
        usage >&2
        exit 1
      fi
      PORT_GIVEN=1
      API_PORT="${2}"
      shift 2
      ;;
    --tp)
      if [[ -z "${2:-}" || "${2:-}" == -* ]]; then
        echo "Опция --tp требует целое число ≥1 (tensor parallel, например 4 или 8)" >&2
        usage >&2
        exit 1
      fi
      TP_OVERRIDE="${2}"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "${MODE}" ]]; then
  if ! MODE="$(slgpu_interactive_choose_engine)"; then
    usage >&2
    exit 1
  fi
fi

if [[ -z "${MODEL_SLUG}" ]]; then
  if ! MODEL_SLUG="$(slgpu_interactive_choose_preset)"; then
    exit 1
  fi
fi

if [[ "${PORT_GIVEN}" != "1" ]]; then
  if [[ "${MODE}" == sglang ]]; then
    API_PORT=8222
  else
    API_PORT=8111
  fi
fi

if ! [[ "${API_PORT}" =~ ^[0-9]+$ ]] || (( API_PORT < 1 || API_PORT > 65535 )); then
  echo "Некорректный порт API: ${API_PORT} (нужен 1–65535)" >&2
  exit 1
fi

slgpu_load_compose_env "${MODEL_SLUG}" "${MODE}"
export LLM_API_PORT="${API_PORT}"

if [[ -n "${TP_OVERRIDE}" ]]; then
  if ! [[ "${TP_OVERRIDE}" =~ ^[1-9][0-9]*$ ]] || (( TP_OVERRIDE > 128 )); then
    echo "Некорректный --tp: ${TP_OVERRIDE} (нужно целое 1…128; согласуйте с числом GPU на хосте)" >&2
    exit 1
  fi
  export TP="${TP_OVERRIDE}"
  tp_src="--tp"
else
  : "${TP:=8}"
  tp_src="пресет"
fi
export TP
# Согласовать Docker с TP: в контейнере видны GPU 0..TP-1 (маска: NVIDIA_VISIBLE_DEVICES). Переопределение: SLGPU_NVIDIA_VISIBLE_DEVICES=2,3 в main.env или export
if [[ -n "${SLGPU_NVIDIA_VISIBLE_DEVICES:-}" ]]; then
  export NVIDIA_VISIBLE_DEVICES="${SLGPU_NVIDIA_VISIBLE_DEVICES}"
else
  export NVIDIA_VISIBLE_DEVICES="$(slgpu_nvidia_visible_from_tp "${TP}")"
fi

echo "Модель: ${MODEL_ID}  TP=${TP} (${tp_src})  NVIDIA_VISIBLE_DEVICES=${NVIDIA_VISIBLE_DEVICES}  (MAX_MODEL_LEN=${MAX_MODEL_LEN:-<default>}, KV=${KV_CACHE_DTYPE:-<default>}, reasoning=${REASONING_PARSER:-<off>})"

# Подстановка ${VAR} в docker-compose.llm.yml: у Docker Compose переменные **shell** процесса
# `docker compose` имеют приоритет над отдельными KEY=value в обёртке `env … docker compose`.
# slgpu-web (и любой родитель с export из main.env) тогда перебивает пресет → в логе vLLM остаются
# 32768 / hermes / 0.92. Пишем снимок после source и вызываем compose под `env -i` + `--env-file`.
# Не дублируйте MAX_MODEL_LEN/GPU_MEM_UTIL/парсеры в корневом `.env` проекта — см. docker/README.md.
SLGPU_LLM_COMPOSE_INTERP_ENV=""
slgpu_cleanup_llm_interp_env() {
  if [[ -n "${SLGPU_LLM_COMPOSE_INTERP_ENV}" && -f "${SLGPU_LLM_COMPOSE_INTERP_ENV}" ]]; then
    rm -f "${SLGPU_LLM_COMPOSE_INTERP_ENV}"
  fi
}
trap slgpu_cleanup_llm_interp_env EXIT
SLGPU_LLM_COMPOSE_INTERP_ENV="$(mktemp "${TMPDIR:-/tmp}/slgpu-compose-interp.XXXXXX.env")"
slgpu_write_llm_compose_interp_env "${SLGPU_LLM_COMPOSE_INTERP_ENV}"

compose_llm_env() {
  env -i \
    "PATH=${PATH:-/usr/sbin:/usr/bin:/sbin:/bin}" \
    "HOME=${HOME:-/root}" \
    "USER=${USER:-root}" \
    "DOCKER_HOST=${DOCKER_HOST:-}" \
    "DOCKER_CONTEXT=${DOCKER_CONTEXT:-}" \
    "SSH_AUTH_SOCK=${SSH_AUTH_SOCK:-}" \
    "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}" \
    "TMPDIR=${TMPDIR:-/tmp}" \
    "LANG=${LANG:-C.UTF-8}" \
    docker compose \
      --project-directory "${ROOT}" \
      --env-file "${SLGPU_LLM_COMPOSE_INTERP_ENV}" \
      "$@"
}

slgpu_ensure_slgpu_network
slgpu_ensure_data_dirs

echo "Останавливаю vllm/sglang (если были)…"
compose_llm_env -f docker/docker-compose.llm.yml stop vllm sglang 2>/dev/null || true
compose_llm_env -f docker/docker-compose.llm.yml rm -f vllm sglang 2>/dev/null || true

case "${MODE}" in
  vllm)
    echo "Поднимаю vLLM (TP=${TP:-8}, GPU ${NVIDIA_VISIBLE_DEVICES}), API :${API_PORT}…"
    compose_llm_env -f docker/docker-compose.llm.yml --profile vllm up -d
    ;;
  sglang)
    echo "Поднимаю SGLang (TP=${TP:-8}, GPU ${NVIDIA_VISIBLE_DEVICES}), API :${API_PORT}…"
    compose_llm_env -f docker/docker-compose.llm.yml --profile sglang up -d
    ;;
esac

sleep 2
# Внутри контейнера: vLLM 8111, SGLang 8222 (см. docker-compose, SGLANG_LISTEN_PORT).
llm_in_port=8111
[[ "${MODE}" == sglang ]] && llm_in_port=8222
mapped="$(compose_llm_env -f docker/docker-compose.llm.yml port "${MODE}" "${llm_in_port}" 2>/dev/null | head -1 || true)"
if [[ -n "${mapped}" ]]; then
  echo "Проброс порта ${llm_in_port} (внутри контейнера) → хост: ${mapped}"
  if [[ "${mapped}" =~ :([0-9]+)$ ]]; then
    if [[ "${BASH_REMATCH[1]}" != "${API_PORT}" ]]; then
      echo "ВНИМАНИЕ: ожидаемый порт хоста -p ${API_PORT}, compose сообщает :${BASH_REMATCH[1]}. Проверьте LLM_API_PORT (main.env / export) и повторите up." >&2
    fi
  fi
else
  echo "Не удалось получить проброс порта (сервис ещё стартует или контейнер не в сети)." >&2
fi

echo ""
echo "Готовность модели: curl -s http://127.0.0.1:${API_PORT}/v1/models  ·  логи: cd <корень репо> && docker compose -f docker/docker-compose.llm.yml logs -f ${MODE}"
echo "Мониторинг: ./slgpu monitoring up  ·  web UI: ./slgpu web up  ·  ./slgpu help"
