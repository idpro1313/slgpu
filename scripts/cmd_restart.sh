#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  ./slgpu restart -m|--model <preset> [-h|--help]

Перезапускает тот же движок (vllm или sglang), который сейчас в статусе running.
Если ни один не запущен — используйте ./slgpu up <vllm|sglang> -m <preset>.

Пресеты:
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

MODEL_SLUG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--model) MODEL_SLUG="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ -z "${MODEL_SLUG}" ]]; then
  usage >&2
  exit 1
fi

engine="$(slgpu_detect_running_engine || true)"
if [[ -z "${engine}" ]]; then
  echo "Нет запущенного vllm/sglang. Запустите: ./slgpu up vllm -m ${MODEL_SLUG}  или  ./slgpu up sglang -m ${MODEL_SLUG}" >&2
  exit 1
fi

echo "Перезапуск: engine=${engine}, preset=${MODEL_SLUG}"
exec bash "${ROOT}/scripts/cmd_up.sh" "${engine}" -m "${MODEL_SLUG}"
