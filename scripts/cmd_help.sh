#!/usr/bin/env bash
set -euo pipefail
cat <<'EOF'
slgpu 5.x — управление LLM-стендом через Web UI (slgpu-web).

На хосте остаётся только bootstrap контейнера web:
  ./slgpu web up|down|restart|logs

Файлы конфигурации (host-side):
  configs/bootstrap.env  — минимальный набор для compose web (`./slgpu web up --env-file …`).
  configs/main.env       — шаблон ИМПОРТА в БД (Web UI → «Настройки» → «Импорт» / API
                           POST /api/v1/app-config/install). Backend этот файл
                           автоматически НЕ читает.

Полная документация: README.md
EOF
