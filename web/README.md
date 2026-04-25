# slgpu-web

Web control plane поверх существующего CLI [`./slgpu`](../slgpu) и Docker-стека
проекта [`slgpu`](../README.md). Содержит:

- Реестр моделей Hugging Face и инициируемые загрузки.
- CRUD пресетов с двусторонней синхронизацией с
  [`data/presets/*.env`](../data/presets/) (`PRESETS_DIR` в `main.env`).
- Управление инференсом vLLM/SGLang через `./slgpu up|down|restart`.
- Управление и наблюдение мониторинг-стека (`./slgpu monitoring …`).
- Состояние и базовые маршруты LiteLLM Proxy.
- Журнал всех CLI-операций с stdout/stderr tail.

Контракт и границы ответственности зафиксированы в
[`CONTRACT.md`](CONTRACT.md). Без согласования с этим документом ничего не
менять.

## Стек

- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + aiosqlite + Alembic +
  `docker` SDK + httpx.
- **Frontend**: React 18 + Vite + TypeScript + React Router + TanStack Query.
  Стиль — лёгкий enterprise по мотивам [`develonica.ru`](https://develonica.ru/):
  тёмная панель навигации, крупные градиентные карточки, аккуратная
  типографика.
- **Контейнер**: один образ. Backend отдаёт `/api/v1/*` и собранную React
  статику.
- **БД**: SQLite, путь приходит из переменной `WEB_DATABASE_URL`,
  по умолчанию `/data/slgpu-web.db`. Папка `/data` всегда bind-mount.
- **Веса моделей**: `MODELS_DIR` с хоста (см. `../main.env`, по умолчанию **`../data/models`**)
  — тот же путь **в** контейнере, `rw` (скан, `./slgpu pull` из job runner). Остальные
  данные стека (рост контейнеров, мониторинг) — отдельные bind в корневых compose,
  в web-образ они не дублируются.

## Структура

```text
web/
├── CONTRACT.md
├── docker-entrypoint.sh  # в образ; инструкции сборки — `../docker/Dockerfile.web` (context = этот каталог)
├── data/                 # SQLite на хосте (bind mount → /data в контейнере)
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/v1/        # роутеры FastAPI
│   │   ├── core/          # конфигурация, логирование, валидация аргументов
│   │   ├── db/            # SQLAlchemy base и session
│   │   ├── models/        # таблицы models, presets, runs, services, jobs, audit, settings
│   │   ├── schemas/       # Pydantic модели для API
│   │   ├── services/      # CLI runner, Docker inspect, HF, LiteLLM, monitoring, env_files
│   │   └── workers/
│   └── tests/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── app/App.tsx
        ├── api/           # типизированный fetch-клиент
        ├── components/
        ├── pages/         # Dashboard, Models, Presets, Runtime, Monitoring, LiteLLM, Jobs
        └── styles/globals.css
```

## Запуск

> Для эксплуатации требуется Linux VM с Docker, NVIDIA-драйвером и уже
> работающим стендом slgpu. На Windows-машине разработки запускать
> только сборку фронтенда и unit-тесты backend.

**Рекомендуемо (из корня репозитория):** подъём согласован с `../main.env` и каталогом **`../data/`**:

```bash
cd /path/to/slgpu
# при необходимости отредактируйте main.env: WEB_DATA_DIR, MODELS_DIR, WEB_BIND, WEB_PORT
./slgpu web up
```

Скрипт [`../scripts/cmd_web.sh`](../scripts/cmd_web.sh) вызывает
`docker compose` с `project directory` = корень репо (тома `./data/web`, `./data/models`).

**Вариант вручную (из корня репо):** подставьте те же переменные, что и `./slgpu web up` — `docker compose -f docker/docker-compose.web.yml --project-directory . --env-file main.env up --build -d`. Пути в compose рассчитаны на корень репозитория.

После старта UI: `http://${WEB_BIND:-127.0.0.1}:${WEB_PORT:-8089}/` (см. `../main.env`).

## API

Все ручки версионированы под `/api/v1`. Подробное описание выдаёт
`/docs` (FastAPI Swagger UI), краткий список:

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/healthz` | liveness + версия |
| GET | `/api/v1/dashboard` | сводка для главной страницы |
| GET/POST | `/api/v1/models` | список и регистрация HF моделей |
| POST | `/api/v1/models/{id}/pull` | `slgpu pull` через job runner |
| GET/POST | `/api/v1/presets` | пресеты |
| POST | `/api/v1/presets/sync` | импорт `data/presets/*.env` (или `PRESETS_DIR`) в БД |
| POST | `/api/v1/presets/{id}/export` | экспорт пресета в файл |
| POST | `/api/v1/runtime/up\|down\|restart` | управление движком |
| GET | `/api/v1/runtime/snapshot` | состояние движка |
| GET | `/api/v1/monitoring/services` | состояние сервисов |
| POST | `/api/v1/monitoring/action` | `slgpu monitoring up\|down\|restart\|fix-perms` |
| GET | `/api/v1/litellm/health\|info\|models` | LiteLLM proxy |
| GET | `/api/v1/jobs` | журнал задач |

## Безопасность

- Любой аргумент, идущий в shell, проходит через
  [`app.core.security`](backend/app/core/security.py) с whitelist-регулярками.
- Команды формируются ТОЛЬКО в [`app.services.slgpu_cli`](backend/app/services/slgpu_cli.py)
  и исполняются через `asyncio.create_subprocess_exec(*argv)`, без shell.
- На каждый mutating job ставится in-memory advisory lock на
  `(scope, resource)` — повторный `up` или `pull` той же модели вернёт `409`.
- Секреты HF/Grafana/LiteLLM/Langfuse в БД не пишутся; UI показывает
  лишь наличие/отсутствие.

## Тесты

```bash
cd web/backend
pip install -e .[dev]
pytest
```

```bash
cd web/frontend
npm install
npm run typecheck
```

Дополнительная статическая проверка для compose-файла:

```bash
docker compose -f docker/docker-compose.web.yml config
```
