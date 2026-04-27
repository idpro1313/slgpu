#!/usr/bin/env bash
set -euo pipefail
cat <<'EOF'
slgpu 5.x — управление LLM-стендом через Web UI (slgpu-web).

На хосте остаётся только bootstrap контейнера:
  ./slgpu web up|down|restart|logs

Требуется файл `configs/main.env` (см. репозиторий). Импорт стека в SQLite — из UI: Настройки → установка, или API `POST /api/v1/app-config/install` после `web up`.

Полная документация: README.md
EOF
