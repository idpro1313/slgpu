#!/usr/bin/env bash
# Скачивание модели: hf download в MODELS_DIR по полям пресета или по HF id.
# Файл пресета не создаётся — задавайте configs/models/<slug>.env вручную (см. README).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "${ROOT}/scripts/_lib.sh"

usage() {
  cat <<EOF
Использование:
  ./slgpu pull <HF_ID|preset> [опции]
  ./slgpu pull -m <HF_ID|preset> [опции]

HF id с «/» (например Qwen/Qwen3.6-35B-A3B): веса в \${MODELS_DIR}/<HF_ID>.
  Если существует configs/models/<slug>.env (slug = имя репозитария, нижний регистр, _ → -),
  подгружаются MODEL_ID, MODEL_REVISION и т.д.
  Если пресета нет — скачивание только по HF id; для ./slgpu up создайте .env вручную.

Аргумент без «/» — имя существующего пресета configs/models/<name>.env.

Опции:
  --revision REV   ревизия HF; при загрузке по пресету переопределяет MODEL_REVISION
  -h, --help       эта справка

Требуется «hf» (pip install -U "huggingface_hub[cli]").
Токен: configs/secrets/hf.env (HF_TOKEN) — опционально.

Пресеты:
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

TARGET=""
REVISION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -m|--model) TARGET="${2:?}"; shift 2 ;;
    --revision) REVISION="${2:?}"; shift 2 ;;
    -*)
      echo "Неизвестная опция: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -n "${TARGET}" ]]; then
        echo "Лишний аргумент: $1" >&2
        usage >&2
        exit 1
      fi
      TARGET="$1"
      shift
      ;;
  esac
done

if [[ -z "${TARGET}" ]]; then
  usage >&2
  exit 1
fi

slgpu_load_server_env

HF_ENV="${ROOT}/configs/secrets/hf.env"
if [[ -f "${HF_ENV}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${HF_ENV}"
  set +a
fi

if [[ -n "${HF_TOKEN:-}" ]]; then
  export HUGGING_FACE_HUB_TOKEN="${HF_TOKEN}"
  export HF_TOKEN="${HF_TOKEN}"
fi

if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "Предупреждение: HF_TOKEN пуст — приватные репо не скачаются." >&2
fi

MODELS_DIR="${MODELS_DIR:-/opt/models}"

if ! command -v hf >/dev/null 2>&1; then
  cat <<'EOF' >&2
Не найдена команда «hf».

Установите Hugging Face CLI:
  pip install -U "huggingface_hub[cli]"

Проверка: hf download --help
EOF
  exit 1
fi

do_hf_download() {
  local target="${MODELS_DIR}/${MODEL_ID}"
  mkdir -p "$(dirname "${target}")"
  echo "Каталог: ${target}"
  echo "Репозиторий: ${MODEL_ID} revision=${MODEL_REVISION:-<default>}"
  REV_ARGS=()
  if [[ -n "${MODEL_REVISION:-}" ]]; then
    REV_ARGS=(--revision "${MODEL_REVISION}")
  fi
  export HF_HUB_ENABLE_HF_TRANSFER=1
  echo "Используется: hf download"
  local extra=()
  if hf download --help 2>/dev/null | grep -q 'local-dir-use-symlinks'; then
    extra=(--local-dir-use-symlinks false)
  fi
  hf download "${MODEL_ID}" \
    "${REV_ARGS[@]}" \
    --local-dir "${target}" \
    "${extra[@]}"
}

is_hf_id() {
  [[ "$1" == */* ]]
}

have_preset=1
slug=""

if is_hf_id "${TARGET}"; then
  HF_ID="${TARGET}"
  slug="$(slgpu_hf_id_to_slug "${HF_ID}")"
  preset_file="${ROOT}/configs/models/${slug}.env"

  if [[ -f "${preset_file}" ]]; then
    slgpu_load_env "${slug}"
    if [[ -n "${REVISION}" ]]; then
      export MODEL_REVISION="${REVISION}"
    fi
    do_hf_download
  else
    export MODEL_ID="${HF_ID}"
    export MODEL_REVISION="${REVISION:-}"
    do_hf_download
    have_preset=0
    echo "" >&2
    echo "Пресет отсутствует: configs/models/${slug}.env" >&2
    echo "Создайте его вручную (см. configs/models/README.md), MODEL_ID=${HF_ID}." >&2
  fi
else
  slgpu_load_env "${TARGET}"
  if [[ -n "${REVISION}" ]]; then
    export MODEL_REVISION="${REVISION}"
  fi
  do_hf_download
  slug="${TARGET}"
fi

du_out="$(du -sh "${MODELS_DIR}/${MODEL_ID}" 2>/dev/null | awk '{print $1}' || echo "?")"
echo ""
if [[ "${have_preset}" == "1" ]]; then
  echo "Пресет: configs/models/${slug}.env"
else
  echo "Пресет: (ожидается) configs/models/${slug}.env"
fi
echo "Модель: ${MODELS_DIR}/${MODEL_ID} (${du_out})"
if [[ "${have_preset}" == "1" ]]; then
  echo "Запуск: ./slgpu up vllm -m ${slug}"
else
  echo "Запуск: после создания пресета — ./slgpu up vllm -m ${slug}"
fi
