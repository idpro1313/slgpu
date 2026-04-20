#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENGINE="${1:?Использование: $0 vllm|sglang}"

# Если есть .env — экспортируем, чтобы python-бенч видел MAX_MODEL_LEN и т.п.
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

case "${ENGINE}" in
  vllm) BASE="http://127.0.0.1:8111/v1" ;;
  sglang) BASE="http://127.0.0.1:8222/v1" ;;
  *)
    echo "Неизвестный движок: ${ENGINE}" >&2
    exit 1
    ;;
esac

TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ROOT}/bench/results/${ENGINE}/${TS}"
mkdir -p "${OUT}"

echo "Бенч: engine=${ENGINE} base=${BASE}"
echo "Результаты: ${OUT}"

python3 "${ROOT}/scripts/bench_openai.py" \
  --base-url "${BASE}" \
  --engine "${ENGINE}" \
  --output-dir "${OUT}"

echo "${OUT}" > "${ROOT}/bench/results/.last_${ENGINE}"
echo "Готово. summary: ${OUT}/summary.json"
