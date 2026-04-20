#!/usr/bin/env bash
# Скачивает модель в ${MODELS_DIR}/${MODEL_ID} (реальные файлы, без симлинков в ~/.cache).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Создайте .env из .env.example: cp .env.example .env" >&2
  exit 1
fi

if ! command -v huggingface-cli >/dev/null 2>&1; then
  echo "Установите CLI: pip install -U 'huggingface_hub[cli]'" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${MODEL_ID:?Задайте MODEL_ID в .env}"
MODELS_DIR="${MODELS_DIR:-/opt/models}"

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

HF_HUB_ENABLE_HF_TRANSFER=1 huggingface-cli download "${MODEL_ID}" \
  "${REV_ARGS[@]}" \
  --local-dir "${TARGET}" \
  --local-dir-use-symlinks False

echo "Готово: ${TARGET}"
