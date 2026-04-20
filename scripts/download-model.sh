#!/usr/bin/env bash
# Скачивает модель в ${MODELS_DIR}/${MODEL_ID} (реальные файлы в каталоге, без симлинков в ~/.cache/huggingface).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  $0 [-m|--model <preset>] [-h|--help]

Скачивает модель, указанную в пресете configs/models/<preset>.env,
либо (если -m не задан) в .env.

Пресеты:
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

MODEL_SLUG="${MODEL:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--model) MODEL_SLUG="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Неизвестный аргумент: $1" >&2; usage >&2; exit 1 ;;
  esac
done

slgpu_load_env "${MODEL_SLUG}"

MODELS_DIR="${MODELS_DIR:-/opt/models}"

if [[ -n "${HF_TOKEN:-}" ]]; then
  export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"
  export HF_TOKEN="${HF_TOKEN}"
fi

if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "Предупреждение: HF_TOKEN пуст — приватные репо не скачаются." >&2
fi

TARGET="${MODELS_DIR}/${MODEL_ID}"
mkdir -p "$(dirname "${TARGET}")"

echo "Каталог: ${TARGET}"
echo "Репозиторий: ${MODEL_ID} revision=${MODEL_REVISION:-<default>}"

REV_ARGS=()
if [[ -n "${MODEL_REVISION:-}" ]]; then
  REV_ARGS=(--revision "${MODEL_REVISION}")
fi

export HF_HUB_ENABLE_HF_TRANSFER=1

run_hf() {
  echo "Используется: hf download (актуальный Hugging Face CLI)"
  local extra=()
  if hf download --help 2>/dev/null | grep -q 'local-dir-use-symlinks'; then
    extra=(--local-dir-use-symlinks false)
  fi
  hf download "${MODEL_ID}" \
    "${REV_ARGS[@]}" \
    --local-dir "${TARGET}" \
    "${extra[@]}"
}

run_legacy_cli() {
  echo "Используется: huggingface-cli download (устарело; обновите: pip install -U 'huggingface_hub[cli]')"
  huggingface-cli download "${MODEL_ID}" \
    "${REV_ARGS[@]}" \
    --local-dir "${TARGET}" \
    --local-dir-use-symlinks False
}

if command -v hf >/dev/null 2>&1; then
  run_hf
elif command -v huggingface-cli >/dev/null 2>&1; then
  run_legacy_cli
else
  cat <<'EOF' >&2
Не найден ни «hf», ни «huggingface-cli».

Установите актуальный CLI:
  pip install -U "huggingface_hub[cli]"

Проверка: hf download --help
EOF
  exit 1
fi

echo "Готово: ${TARGET}"
