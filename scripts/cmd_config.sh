#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  ./slgpu config <vllm|sglang> -m|--model <preset> [-h|--help]

Печатает переменные окружения после слияния: .env + configs/<engine>/<engine>.env + пресет.

Пресеты:
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

ENGINE=""
PRESET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    vllm|sglang) ENGINE="$1"; shift ;;
    -m|--model) PRESET="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "${ENGINE}" || -z "${PRESET}" ]]; then
  usage >&2
  exit 1
fi

slgpu_load_compose_env "${PRESET}" "${ENGINE}"

echo "=== Effective env (engine=${ENGINE}, preset=${PRESET}) ==="
env | sort | grep -E '^(MODEL_|MAX_|TP|KV_|GPU_|SLGPU_|MM_ENCODER_|VLLM_MEM|VLLM_LOGGING|VLLM_MEMORY|VLLM_USE|VLLM_|SGLANG_|REASONING_|TOOL_|BENCH_|PYTORCH_|NCCL_)' || true
