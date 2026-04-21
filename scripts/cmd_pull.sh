#!/usr/bin/env bash
# Скачивание модели: HF id (org/name) с автогенерацией пресета или существующий пресет.
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

HF id содержит «/» (например Qwen/Qwen3.6-35B-A3B) — создаётся configs/models/<slug>.env и скачиваются веса.
Имя без «/» — существующий пресет configs/models/<name>.env.

Опции:
  --slug NAME           явный slug файла пресета (вместо авто из basename HF id)
  --force               перезаписать существующий пресет (HF-режим)
  --keep                не перезаписывать пресет; только hf download (пресет уже есть)
  --revision REV        MODEL_REVISION
  --max-len N           MAX_MODEL_LEN (по умолчанию 131072)
  --tp N                TP (по умолчанию 4)
  --kv-dtype X          KV_CACHE_DTYPE (по умолчанию fp8_e4m3)
  --gpu-mem F           GPU_MEM_UTIL (по умолчанию 0.92)
  --sglang-mem F        SGLANG_MEM_FRACTION_STATIC (по умолчанию 0.90)
  --batch N             VLLM_MAX_NUM_BATCHED_TOKENS (по умолчанию 8192)
  --reasoning-parser X  переопределить авто
  --tool-call-parser Y  переопределить авто
  -h, --help            эта справка

Требуется команда «hf» (pip install -U "huggingface_hub[cli]").
Токен: configs/secrets/hf.env (HF_TOKEN) — опционально.

Пресеты:
$(slgpu_list_presets | sed 's/^/  /')
EOF
}

TARGET=""
FORCE=0
KEEP=0
SLUG=""
REVISION=""
MAX_LEN="131072"
TP="4"
KV="fp8_e4m3"
GPU="0.92"
SGL="0.90"
BATCH="8192"
REASON_O=""
TOOL_O=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -m|--model) TARGET="${2:?}"; shift 2 ;;
    --slug) SLUG="${2:?}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --keep) KEEP=1; shift ;;
    --revision) REVISION="${2:?}"; shift 2 ;;
    --max-len) MAX_LEN="${2:?}"; shift 2 ;;
    --tp) TP="${2:?}"; shift 2 ;;
    --kv-dtype) KV="${2:?}"; shift 2 ;;
    --gpu-mem) GPU="${2:?}"; shift 2 ;;
    --sglang-mem) SGL="${2:?}"; shift 2 ;;
    --batch) BATCH="${2:?}"; shift 2 ;;
    --reasoning-parser) REASON_O="${2:?}"; shift 2 ;;
    --tool-call-parser) TOOL_O="${2:?}"; shift 2 ;;
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

if is_hf_id "${TARGET}"; then
  HF_ID="${TARGET}"
  slug="${SLUG:-$(slgpu_hf_id_to_slug "${HF_ID}")}"
  preset_file="${ROOT}/configs/models/${slug}.env"

  if [[ "${KEEP}" -eq 1 && ! -f "${preset_file}" ]]; then
    echo "Нет пресета ${preset_file} — нельзя использовать --keep без существующего файла." >&2
    exit 1
  fi

  if [[ -f "${preset_file}" ]]; then
    if [[ "${KEEP}" -eq 1 ]]; then
      echo "Пресет существует, --keep: не перезаписываю ${preset_file}"
      slgpu_load_env "${slug}"
      do_hf_download
      du_out="$(du -sh "${MODELS_DIR}/${MODEL_ID}" 2>/dev/null | awk '{print $1}' || echo "?")"
      echo ""
      echo "Пресет: configs/models/${slug}.env"
      echo "Модель: ${MODELS_DIR}/${MODEL_ID} (${du_out})"
      echo "Запуск: ./slgpu up vllm -m ${slug}"
      exit 0
    fi
    if [[ "${FORCE}" -ne 1 ]]; then
      echo "Пресет уже существует: ${preset_file}" >&2
      echo "Используйте --force для перезаписи, --slug для другого имени, или --keep только для скачивания." >&2
      exit 1
    fi
  fi

  line="$(slgpu_guess_parsers "${HF_ID}")"
  reason="${line%%$'\t'*}"
  tool="${line#*$'\t'}"
  [[ -n "${REASON_O}" ]] && reason="${REASON_O}"
  [[ -n "${TOOL_O}" ]] && tool="${TOOL_O}"

  slgpu_gen_preset_file "${slug}" "${HF_ID}" "${REVISION}" "${MAX_LEN}" "${TP}" "${KV}" "${GPU}" "${SGL}" "${BATCH}" "${reason}" "${tool}" >/dev/null
  echo "Создан пресет: configs/models/${slug}.env"

  slgpu_load_env "${slug}"
  do_hf_download
else
  slgpu_load_env "${TARGET}"
  do_hf_download
  slug="${TARGET}"
fi

du_out="$(du -sh "${MODELS_DIR}/${MODEL_ID}" 2>/dev/null | awk '{print $1}' || echo "?")"
echo ""
echo "Пресет: configs/models/${slug}.env"
echo "Модель: ${MODELS_DIR}/${MODEL_ID} (${du_out})"
echo "Запуск: ./slgpu up vllm -m ${slug}"
