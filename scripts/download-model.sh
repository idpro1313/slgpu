#!/usr/bin/env bash
# Скачивает модель в ${MODELS_DIR}/${MODEL_ID} (реальные файлы в каталоге, без симлинков в ~/.cache/huggingface).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Создайте .env из .env.example: cp .env.example .env" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${MODEL_ID:?Задайте MODEL_ID в .env}"
MODELS_DIR="${MODELS_DIR:-/opt/models}"

# Hub принимает оба имени; в .env у нас HF_TOKEN
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
  # С --local-dir служебные метаданные Hub лежат внутри TARGET (см. доку hf download), а не в ~/.cache.
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
  # или в venv проекта; после установки доступна команда: hf

Проверка: hf download --help
EOF
  exit 1
fi

echo "Готово: ${TARGET}"
