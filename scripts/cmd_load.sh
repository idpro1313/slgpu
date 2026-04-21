#!/usr/bin/env bash
set -euo pipefail

# FILE: scripts/cmd_load.sh
# VERSION: 1.0.1
# START_MODULE_CONTRACT
#   PURPOSE: Обёртка для длительного нагрузочного теста bench_load.py.
#   SCOPE: Загрузка env, валидация аргументов, проверка API, запуск bench_load.py.
#   DEPENDS: M-LIB (env loading), M-LOAD (bench_load.py)
#   LINKS: grace/knowledge-graph/knowledge-graph.xml -> M-LOAD
# END_MODULE_CONTRACT
#
# START_MODULE_MAP
#   cmd_load.sh      - обёртка запуска bench_load.py с предflight-проверкой API
# END_MODULE_MAP

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  ./slgpu load <vllm|sglang> -m|--model <preset> [опции]

Опции:
  -u, --users <N>         Целевое число виртуальных пользователей (default: 250)
  -d, --duration <SEC>    Длительность steady фазы, сек (default: 900)
  --ramp-up <SEC>         Длительность ramp-up, сек (default: 120)
  --ramp-down <SEC>       Длительность ramp-down, сек (default: 60)
  --think-time <MIN,MAX>  Задержка между запросами пользователя, ms (default: 2000,5000)
  --max-prompt <TOKENS>   Макс длина prompt (default: 512)
  --max-output <TOKENS>   Макс длина output (default: 256)
  --report-interval <SEC> Интервал записи метрик CSV (default: 5)
  --warmup <N>            Число warmup запросов перед тестом (default: 3)
  --burst                 Burst-режим: максимальная нагрузка без пауз между запросами
  -h, --help              Эта справка

Примеры:
  # Стандарт: 250 пользователей, 15 мин steady, 2 мин ramp-up
  ./slgpu load vllm -m qwen3.6-35b-a3b

  # 300 пользователей, 20 мин steady
  ./slgpu load vllm -m qwen3.6-35b-a3b --users 300 --duration 1200

  # Быстрый тест: 50 пользователей, 2 мин
  ./slgpu load vllm -m qwen3.6-35b-a3b --users 50 --duration 120 --ramp-up 30 --ramp-down 30
EOF
}

ENGINE=""
MODEL_SLUG=""
USERS=250
DURATION=900
RAMP_UP=120
RAMP_DOWN=60
THINK_TIME="2000,5000"
MAX_PROMPT=512
MAX_OUTPUT=256
REPORT_INTERVAL=5
WARMUP=3

while [[ $# -gt 0 ]]; do
  case "$1" in
    vllm|sglang) ENGINE="$1"; shift ;;
    -m|--model) MODEL_SLUG="${2:?}"; shift 2 ;;
    -u|--users) USERS="${2:?}"; shift 2 ;;
    -d|--duration) DURATION="${2:?}"; shift 2 ;;
    --ramp-up) RAMP_UP="${2:?}"; shift 2 ;;
    --ramp-down) RAMP_DOWN="${2:?}"; shift 2 ;;
    --think-time) THINK_TIME="${2:?}"; shift 2 ;;
    --max-prompt) MAX_PROMPT="${2:?}"; shift 2 ;;
    --max-output) MAX_OUTPUT="${2:?}"; shift 2 ;;
    --report-interval) REPORT_INTERVAL="${2:?}"; shift 2 ;;
    --warmup) WARMUP="${2:?}"; shift 2 ;;
    --burst) BURST="--burst"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

# Авто-определение engine из docker compose, если не указан
if [[ -z "${ENGINE}" ]]; then
  ENGINE="$(slgpu_detect_running_engine)" || true
  if [[ -z "${ENGINE}" ]]; then
    echo "[LOAD] Не удалось автоопределить движок: ни vllm, ни sglang не запущены." >&2
    echo "[LOAD] Укажите явно: ./slgpu load <vllm|sglang> -m <preset>" >&2
    exit 1
  fi
  echo "[LOAD] Авто-определён движок: ${ENGINE}"
fi

if [[ -z "${MODEL_SLUG}" ]]; then
  echo "[LOAD] ОШИБКА: не указан пресет (флаг -m <preset>)" >&2
  usage >&2
  exit 1
fi

slgpu_load_env "${MODEL_SLUG}"

# Проверка соответствия запущенного engine
slgpu_validate_running_config "${ENGINE}" "${MODEL_SLUG}" || exit 1

BASE="http://127.0.0.1:8111/v1"

# Предflight-проверка API
echo "[LOAD] Проверка API ${BASE}/models ..."
if ! curl -sf "${BASE}/models" >/dev/null 2>&1; then
  echo "[LOAD] ОШИБКА: API не отвечает на ${BASE}/models" >&2
  echo "[LOAD] Убедитесь, что движок запущен: ./slgpu up ${ENGINE} -m ${MODEL_SLUG}" >&2
  exit 1
fi
echo "[LOAD] API доступен."

TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/bench/results/${ENGINE}/${TS}"
mkdir -p "${OUT}"

if [[ -n "${BURST}" ]]; then
  echo "LOAD: engine=${ENGINE} users=${USERS} duration=${DURATION}s base=${BASE} model=${BENCH_MODEL_NAME:-${MODEL_ID}}"
  echo "  ramp_up=${RAMP_UP}s steady=${DURATION}s ramp_down=${RAMP_DOWN}s burst=ON"
else
  echo "LOAD: engine=${ENGINE} users=${USERS} duration=${DURATION}s base=${BASE} model=${BENCH_MODEL_NAME:-${MODEL_ID}}"
  echo "  ramp_up=${RAMP_UP}s steady=${DURATION}s ramp_down=${RAMP_DOWN}s think_time=${THINK_TIME}ms"
fi
echo "Результаты: ${OUT}"

python3 "${ROOT}/scripts/bench_load.py" \
  --base-url "${BASE}" \
  --engine "${ENGINE}" \
  --output-dir "${OUT}" \
  --users "${USERS}" \
  --duration "${DURATION}" \
  --ramp-up "${RAMP_UP}" \
  --ramp-down "${RAMP_DOWN}" \
  --think-time "${THINK_TIME}" \
  --max-prompt-tokens "${MAX_PROMPT}" \
  --max-output-tokens "${MAX_OUTPUT}" \
  --report-interval "${REPORT_INTERVAL}" \
  --warmup-requests "${WARMUP}" \
  ${BURST}

echo "Готово. summary: ${OUT}/summary.json"
