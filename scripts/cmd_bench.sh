#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  ./slgpu bench <vllm|sglang> -m|--model <preset> [-h|--help]

Пресеты (configs/models/<name>.env):
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

ENGINE=""
MODEL_SLUG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    vllm|sglang) ENGINE="$1"; shift ;;
    -m|--model) MODEL_SLUG="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

# Авто-определение engine из docker compose, если не указан
if [[ -z "${ENGINE}" ]]; then
  ENGINE="$(slgpu_detect_running_engine)" || true
  if [[ -z "${ENGINE}" ]]; then
    echo "[BENCH] Не удалось автоопределить движок: ни vllm, ни sglang не запущены." >&2
    echo "[BENCH] Укажите явно: ./slgpu bench <vllm|sglang> -m <preset>" >&2
    exit 1
  fi
  echo "[BENCH] Авто-определён движок: ${ENGINE}"
fi

if [[ -z "${MODEL_SLUG}" ]]; then
  echo "[BENCH] ОШИБКА: не указан пресет (флаг -m <preset>)" >&2
  usage >&2
  exit 1
fi

slgpu_load_env "${MODEL_SLUG}"

# Проверка соответствия запущенного engine + model
slgpu_validate_running_config "${ENGINE}" "${MODEL_SLUG}" "${MODEL_ID}" || exit 1

BASE="http://127.0.0.1:8111/v1"

TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/bench/results/${ENGINE}/${TS}"
mkdir -p "${OUT}"

echo "Бенч: engine=${ENGINE} base=${BASE} model=${BENCH_MODEL_NAME:-${MODEL_ID}}"
echo "MAX_MODEL_LEN=${MAX_MODEL_LEN:-<unset>}"
echo "Результаты: ${OUT}"

python3 "${ROOT}/scripts/bench_openai.py" \
  --base-url "${BASE}" \
  --engine "${ENGINE}" \
  --output-dir "${OUT}"

echo "${OUT}" > "${ROOT}/bench/results/.last_${ENGINE}"
echo "Готово. summary: ${OUT}/summary.json"
