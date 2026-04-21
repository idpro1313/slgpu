#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  ./slgpu ab -m|--model <preset> [-h|--help]

Последовательность: up vllm → bench vllm → down (только LLM) → up sglang → bench sglang → compare.

Пресеты:
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

PRESET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--model) PRESET="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "${PRESET}" ]]; then
  usage >&2
  exit 1
fi

echo "=== A/B: vLLM затем SGLang, пресет=${PRESET} ==="
bash "${ROOT}/scripts/cmd_up.sh" vllm -m "${PRESET}"
bash "${ROOT}/scripts/cmd_bench.sh" vllm -m "${PRESET}"
bash "${ROOT}/scripts/cmd_down.sh"
bash "${ROOT}/scripts/cmd_up.sh" sglang -m "${PRESET}"
bash "${ROOT}/scripts/cmd_bench.sh" sglang -m "${PRESET}"
python3 "${ROOT}/scripts/compare.py"
echo "Готово. См. bench/report.md"
