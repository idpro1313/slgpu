#!/usr/bin/env bash
# Общие функции для скриптов slgpu.
# Использование:
#   . "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
#   slgpu_load_env "${MODEL_SLUG:-}"
# ВНИМАНИЕ: этот файл только подключается через source и не устанавливает set -e сам.
# Опции шелла задают вызывающие скрипты.

slgpu_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd
}

slgpu_list_presets() {
  local root
  root="$(slgpu_root)"
  if [[ -d "${root}/configs/models" ]]; then
    (cd "${root}/configs/models" && ls -1 *.env 2>/dev/null | sed 's/\.env$//' | sort) || true
  fi
}

# Экспортирует переменные из .env, затем опционально — из configs/models/<slug>.env.
# Пресет переопределяет значения .env для указанной модели.
# Аргумент $1 либо переменная окружения MODEL задают слаг (имя файла без .env).
slgpu_load_env() {
  local preset="${1:-${MODEL:-}}"
  local root
  root="$(slgpu_root)"

  if [[ ! -f "${root}/.env" ]]; then
    echo "Нет файла .env — скопируйте: cp .env.example .env" >&2
    return 1
  fi

  set -a
  # shellcheck disable=SC1091
  source "${root}/.env"

  if [[ -n "${preset}" ]]; then
    local f="${root}/configs/models/${preset}.env"
    if [[ ! -f "${f}" ]]; then
      echo "Пресет не найден: ${f}" >&2
      echo "Доступные пресеты:" >&2
      local presets
      presets="$(slgpu_list_presets)"
      if [[ -n "${presets}" ]]; then
        echo "${presets}" | sed 's/^/  /' >&2
      else
        echo "  (нет файлов в configs/models/)" >&2
      fi
      set +a
      return 1
    fi
    echo "Загружен пресет модели: ${preset}  (${f#${root}/})"
    # shellcheck disable=SC1090
    source "${f}"
  fi
  set +a

  : "${MODEL_ID:?MODEL_ID не задан (в .env или пресете)}"
}
