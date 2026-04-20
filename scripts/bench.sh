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

Пресеты (configs/models/<name>.env):
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

ENGINE=""
MODEL_SLUG="${MODEL:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    vllm|sglang) ENGINE="$1"; shift ;;
    -m|--model) MODEL_SLUG="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "${ENGINE}" ]]; then
  usage >&2
  exit 1
fi

slgpu_load_env "${MODEL_SLUG}"

case "${ENGINE}" in
  vllm) BASE="http://127.0.0.1:8111/v1" ;;
  sglang) BASE="http://127.0.0.1:8222/v1" ;;
esac

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
