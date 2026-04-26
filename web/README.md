# Develonica.LLM

Web control plane поверх существующего CLI [`./slgpu`](../slgpu) и Docker-стека
проекта [`slgpu`](../README.md). Содержит:

- Реестр моделей Hugging Face по фактическим папкам `MODELS_DIR/<org>/<repo>`:
  регистрация, изменение revision/notes, удаление записи или локальной папки весов,
  инициируемые загрузки.
- CRUD пресетов с двусторонней синхронизацией с
  [`data/presets/*.env`](../data/presets/) (`PRESETS_DIR` в `main.env`).
  Параметры пресета редактируются через строки `ключ/значение` с подсказками
  типовых runtime-переменных, без ручного JSON.
- Управление инференсом vLLM/SGLang через `./slgpu up|down|restart`.
  Runtime/Dashboard показывают текущий engine, запрошенный пресет, HF ID модели и TP;
  Runtime также показывает автообновляемый хвост логов контейнера модели и активную job
  запуска/рестарта/остановки, пока кнопки заблокированы.
- Управление и наблюдение мониторинг-стека (`./slgpu monitoring …`).
- Состояние и базовые маршруты LiteLLM Proxy.
- Настройки публичного адреса сервера для корректных ссылок на Grafana,
  Prometheus, Langfuse и LiteLLM Admin UI из браузера пользователя; на той же
  странице — запуск `monitoring fix-perms` (права на bind-mount каталогов стека).
- Журнал всех CLI-операций с stdout/stderr tail.

Контракт и границы ответственности зафиксированы в
[`CONTRACT.md`](CONTRACT.md). Без согласования с этим документом ничего не
менять.

## Стек

- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + aiosqlite + Alembic +
  `docker` SDK + httpx.
- **Frontend**: React 18 + Vite + TypeScript + React Router + TanStack Query.
  Приложение называется **Develonica.LLM**. Стиль синхронизирован с live CSS
  [`develonica.ru`](https://develonica.ru/): `IBM Plex Sans` как основной
  шрифт, `Finlandica` для акцентов, голубая палитра `#59AFFF`/`#0A5AA4`,
  светло-голубые градиенты `#F7FBFF`/`#E2EDF8`, белая sticky-шапка,
  подчёркнутая навигация и контролы с radius `10px`.
- **Контейнер**: один образ. Backend отдаёт `/api/v1/*` и собранную React
  статику.
- **БД**: SQLite, путь приходит из переменной `WEB_DATABASE_URL`,
  по умолчанию `/data/slgpu-web.db`. Папка `/data` всегда bind-mount.
- **Версия UI**: footer читает `/healthz`, backend берёт номер из корневого
  [`VERSION`](../VERSION), единственного источника версии проекта.
- **Веса моделей**: `MODELS_DIR` с хоста (см. `../main.env`, по умолчанию **`../data/models`**)
  → `${SLGPU_HOST_REPO}/data/models` в контейнере (тот же абсолютный путь, что разрешает CLI на хосте), `rw`
  (скан, `./slgpu pull` из job runner). Страница **Модели** синхронизируется с реальными каталогами
  `${MODELS_DIR}/<org>/<repo>`; пресеты используются для запуска, но не являются источником списка
  скачанных моделей. Остальные данные стека (рост контейнеров, мониторинг) —
  отдельные bind в корневых compose, в web-образ они не дублируются.

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
        ├── pages/         # Dashboard, Models, Presets, Runtime, Monitoring, LiteLLM, Jobs, Settings
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
`docker compose` с `project directory` = корень репо и **экспортирует `SLGPU_HOST_REPO=$(pwd)`** —
этот **же абсолютный хостовой путь** монтируется в контейнере и задаётся как `WEB_SLGPU_ROOT`.
`working_dir` для контейнера в compose **не задаётся**: uvicorn должен стартовать из
`WORKDIR /srv/app` ([`../docker/Dockerfile.web`](../docker/Dockerfile.web)), где лежит пакет `app/`,
иначе будет `ModuleNotFoundError: No module named 'app'`. Для CLI-вызовов backend сам выставляет
`cwd=settings.slgpu_root` в `app/services/jobs.py`.
Тома: `./data/web` → `/data`; **`MODELS_DIR` с хоста** → **`${SLGPU_HOST_REPO}/data/models`** (тот же абсолютный
путь, что и в CLI на хосте; см. [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml)).
Entrypoint web-контейнера стартует от root, создаёт и chown’ит `/data`,
`${WEB_SLGPU_ROOT}/data/models` и `${WEB_SLGPU_ROOT}/data/presets`, затем
переходит на пользователя `slgpuweb` (uid 10001). Это нужно, чтобы `./slgpu pull`
из UI мог создавать `${MODELS_DIR}/<org>/<repo>`.

**Зачем совпадение путей:** когда web запускает `./slgpu monitoring up`, `docker compose` внутри
контейнера разрешает относительные bind-маунты от `cwd` и отдаёт docker daemon **строки путей**, которые
daemon трактует как **хостовые**. Если бы внутри web репо лежало в `/slgpu`, а на хосте — в `/srv/slgpu`,
daemon не нашёл бы файлы по `/slgpu/...` и создал бы пустые каталоги (типичные ошибки: Prometheus mount
«not a directory», `minio-bucket-init` exit 126, Loki «is a directory»).

**Зависимости в образе для CLI-задач:**
- `huggingface_hub[cli]` (команда `hf`) и `hf_transfer` ставятся в [`../docker/Dockerfile.web`](../docker/Dockerfile.web);
  без них `slgpu pull` из web падает с `Не найдена команда «hf»`. В образе также есть
  writable `/home/slgpuweb`, а `HF_HOME=/data/huggingface`; [`../scripts/cmd_pull.sh`](../scripts/cmd_pull.sh)
  переводит `MODELS_DIR=./data/models` в абсолютный путь и при отсутствующем/wrong `$HOME`
  использует writable `WEB_DATA_DIR`, чтобы `hf download` не писал в недоступный `/home/slgpuweb`;
  перед `hf download --local-dir` создаётся каталог модели.
- `monitoring fix-perms` использует короткоживущий root-контейнер (`docker run --rm -u 0:0`,
  образ из переменной **`SLGPU_FIXPERMS_HELPER_IMAGE`**, по умолчанию `alpine:latest`)
  для `mkdir`/`chown`. `sudo` **не нужен** ни на хосте, ни внутри web.

**Вариант вручную (из корня репо):** `SLGPU_HOST_REPO="$(pwd)" docker compose -f docker/docker-compose.web.yml --project-directory . --env-file main.env up --build -d`. Без `SLGPU_HOST_REPO` compose уйдёт в fallback `.:/slgpu` (старая схема — с известной проблемой mount-маунтов из web).

По умолчанию **слушает на всех интерфейсах** (`WEB_BIND=0.0.0.0` в `../main.env`): `http://127.0.0.1:8089/` с того же хоста или `http://<IP>:8089/` из сети. Только localhost: `WEB_BIND=127.0.0.1`.

Страница **Мониторинг** опрашивает Prometheus/Grafana/Langfuse/LiteLLM по HTTP: с хоста это `127.0.0.1`, **из контейнера slgpu-web** — **`host.docker.internal`** (задано в `docker/docker-compose.web.yml` как `WEB_MONITORING_HTTP_HOST`), иначе пробы попадали бы в сам контейнер web, а не в стек на хосте. Это внутренний адрес только для health-probe. Ссылки, которые открывает браузер, строятся по публичному host из страницы **Настройки** (`/settings`); если он не задан, используется hostname текущего запроса к Develonica.LLM.

**Инференс-пробы** (`/v1/models`, `/metrics` к vLLM/SGLang) из backend используют `WEB_LLM_HTTP_HOST` (в compose тоже `host.docker.internal`) и при необходимости прямой DNS сервиса `http://vllm:8111` / `http://sglang:8222` в сети `slgpu`, потому что `127.0.0.1` внутри web — не хост с опубликованным портом движка.

**LiteLLM** (`GET /api/v1/litellm/health` и `…/models`) ходит к тому же хосту, что и пробы мониторинга: `WEB_MONITORING_HTTP_HOST` + `WEB_LITELLM_PORT` (порт из `main.env` / compose).

## API

Все ручки версионированы под `/api/v1`. Подробное описание выдаёт
`/docs` (FastAPI Swagger UI), краткий список:

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/healthz` | liveness + версия |
| GET | `/api/v1/dashboard` | сводка для главной страницы |
| GET/POST | `/api/v1/models` | список HF моделей по `MODELS_DIR/<org>/<repo>` и регистрация HF моделей |
| PATCH/DELETE | `/api/v1/models/{id}` | изменение revision/notes, удаление записи или локальных весов |
| POST | `/api/v1/models/{id}/pull` | `slgpu pull` через job runner |
| GET/POST | `/api/v1/presets` | список и создание пресетов |
| GET/PATCH/DELETE | `/api/v1/presets/{id}` | просмотр, параметрическое редактирование и удаление пресета |
| POST | `/api/v1/presets/sync` | импорт `data/presets/*.env` (или `PRESETS_DIR`) в БД |
| POST | `/api/v1/presets/{id}/export` | экспорт пресета в файл |
| POST | `/api/v1/runtime/up\|down\|restart` | управление движком |
| GET | `/api/v1/runtime/snapshot` | состояние движка, запрошенный пресет/HF ID/TP и served models |
| GET | `/api/v1/runtime/logs` | хвост stdout/stderr текущего контейнера vLLM/SGLang |
| GET | `/api/v1/monitoring/services` | состояние сервисов |
| POST | `/api/v1/monitoring/action` | `slgpu monitoring up\|down\|restart\|fix-perms` |
| GET | `/api/v1/litellm/health\|info\|models` | LiteLLM proxy |
| GET | `/api/v1/jobs` | только CLI-задачи (лог, exit) |
| GET | `/api/v1/activity` | **объединённая** лента: `jobs` + UI-действия (`audit_events` с `correlation_id IS NULL`); страница «Задачи» в UI |
| GET/PATCH | `/api/v1/settings/public-access` | публичный host сервера и итоговые UI-ссылки |

## Безопасность

- Любой аргумент, идущий в shell, проходит через
  [`app.core.security`](backend/app/core/security.py) с whitelist-регулярками.
- Команды формируются ТОЛЬКО в [`app.services.slgpu_cli`](backend/app/services/slgpu_cli.py)
  и исполняются через `asyncio.create_subprocess_exec(*argv)`, без shell.
- На каждый mutating job ставится in-memory advisory lock на
  `(scope, resource)` — runtime-команды лочатся на `("engine", "runtime")`,
  monitoring-команды на `("monitoring", "stack")`; повторный конфликтующий клик
  в UI блокируется, а прямой повторный запрос вернёт `409`.
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
