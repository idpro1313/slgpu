# Контракт `web/` — Develonica.LLM

> Этот документ — единый источник правды для границ ответственности
> web-приложения внутри проекта `slgpu`. Любое расхождение между кодом
> и контрактом — баг, и фикс начинается отсюда.

## 1. Назначение

Web-приложение **Develonica.LLM** (`slgpu-web`) — control plane поверх Docker Compose / Docker API
([`docker/docker-compose.llm.yml`](../docker/docker-compose.llm.yml),
[`docker/docker-compose.monitoring.yml`](../docker/docker-compose.monitoring.yml),
[`docker/docker-compose.proxy.yml`](../docker/docker-compose.proxy.yml)); на хосте — только bootstrap CLI
[`./slgpu web`](../slgpu). Оно
выполняет задачи из ТЗ пользователя:

1. Скачивание моделей с Hugging Face по ID, контроль процесса,
   повторная докачка, журнал.
2. CRUD пресетов запуска (несколько пресетов на одну модель,
   привязка к GPU и переменным `.env` для serve; **движок** в БД не хранится).
3. Запуск/остановка/рестарт vLLM или SGLang с выбранным пресетом и
   просмотр их фактического состояния.
4. Управление и контроль стека мониторинга (Prometheus, Grafana, Loki,
   Promtail, DCGM, Node Exporter).
5. Управление и контроль стека **proxy** (Langfuse, LiteLLM) — трейсинг и единая OpenAI-совместимая точка доступа к моделям.
6. Отображение актуальной версии проекта и копирайта в общем footer.

Визуальный стиль фронтенда следует live CSS сайта
[`develonica.ru`](https://develonica.ru/): `IBM Plex Sans` как основной шрифт,
`Finlandica` для заголовков и числовых акцентов, фирменный голубой `#59AFFF`,
тёмно-голубой hover/active `#0A5AA4`, светло-голубые градиенты
`#F7FBFF`/`#E2EDF8`, белая sticky-шапка, подчёркнутая навигация и контролы с
radius порядка **8–14px** (компактный макет: меньше отступов и кегль в `globals.css`). Favicon остаётся в LLM-тематике, но использует ту же синюю
палитру.

Страница **Настройки**: публичный IP/DNS (`settings.public_access.server_host`), импорт стека из
**`configs/main.env`** — **только** шаблон для **`POST /api/v1/app-config/install`** (UI «Импорт настроек»). Backend больше **не** сидит БД автоматически: при пустой `stack_params` пользователь обязан явно нажать «Импорт». Источник правды в рантайме — SQLite (**`stack_params`**, без кодовых дефолтов; реестр в `app/services/stack_registry.py`; правка в UI). Минимум для bootstrap web на хосте — **`configs/bootstrap.env`** (`./slgpu web up --env-file configs/bootstrap.env`). Fallback для ссылок: **`WEB_PUBLIC_HOST`** в стеке. Внутренние health-probe: `WEB_MONITORING_HTTP_HOST` / `WEB_LLM_HTTP_HOST`. Порты, имена сервисов / контейнеров / сети, compose project-name — из **слитого** стека (только БД); конфиги мониторинга — из `*.tmpl` в `${WEB_DATA_DIR}/.slgpu/monitoring/` (`render_monitoring_configs`). Runtime LLM: `http://${VLLM_SERVICE_NAME}:${VLLM_PORT}` / `http://${SGLANG_SERVICE_NAME}:${SGLANG_LISTEN_PORT}` (DNS алиасы из стека).

### HTTP 409 `missing_stack_params`

Если для операции не хватает обязательных ключей стека в SQLite, API отвечает **409** с JSON:

- **`error`**: `missing_stack_params`
- **`scope`**: одно из значений `StackScope` (например `llm_slot`, `monitoring_up`, `proxy_up`, …) — см. `app/services/stack_registry.py`
- **`keys`**: список имён отсутствующих ключей
- **`detail`**: человеко читаемое пояснение (рус.)

Полный перечень ключей, групп, `allow_empty` и `required_for` — в **`GET /api/v1/app-config/stack`** (поле **`registry`**) и в **`STACK_KEY_REGISTRY`**.

## 2. Границы ответственности

### Источники правды (НЕ дублируем в БД приложения)

| Сущность | Источник правды |
|---|---|
| Веса моделей на диске | `${MODELS_DIR}` (по умолчанию **`./data/models`**, см. `data/README.md`); удаление весов из UI разрешено только внутри этого каталога |
| Параметры движка для запуска | Плоский стек в SQLite (**`stack_params`** только из БД в `sync_merged_flat`); импорт — **`POST /app-config/install`** из `configs/main.env` + пресеты с диска в таблицу `presets`. Автоседа при пустой БД нет (5.2.0). UI «Настройки» (5.2.1) показывает все ключи реестра с описанием и подсвечивает красным незаполненные обязательные. **С 5.2.2** порядок и группы строк в UI приведены 1-в-1 к разделам `configs/main.env` (1..8): сеть/web/пути/образы/инференс/мониторинг/прокси/секреты; внутри группы порядок = порядок `_STACK_KEY_REGISTRY` (он же — порядок секций main.env), без алфавитной сортировки. Чекбокс «секрет» больше не перекидывает строку в группу «Секреты» — секрет остаётся в своём смысловом разделе. **С 5.2.3** для is_secret-ключей фронт читает маску `data.secrets[key] === "***"` от `mask_secrets()`: если значение в БД задано — поле «Значение» показывает placeholder `••••••••` с подписью «секрет: значение задано в БД (скрыто)» и **не** подсвечивается красным; пустой ввод при PATCH трактуется бекендом как «не менять» (см. `buildStackPatch` на фронте: `if (v) secrets[r.k] = v`). |
| Состояние контейнеров | Docker daemon (через socket) |
| Метрики и серии | Prometheus TSDB |
| Логи контейнеров | Loki / `docker logs` |
| Трейсы LLM-вызовов | Langfuse |
| Маршруты `model -> api_base` LiteLLM | БД `litellm` (Postgres в compose **proxy**, тот же сервис, что и у Langfuse) |

### Что хранит SQLite приложения

| Таблица | Назначение |
|---|---|
| `models` | Кэш реестра HF-моделей: id, revision, slug, локальный путь, статус скачивания, размер, последняя ошибка, attempts. Источник правды для весов — папки `${MODELS_DIR}/<org>/<repo>`. `GET /models` и **`POST /models/sync`** подмешивают/обновляют записи по сканированию `MODELS_DIR`. В **`GET /models`** и **`GET /models/{id}`** вложенное поле **`pull_progress`** (активная `Job` `native.model.pull` по `resource` = `hf_id`): `job_id`, `status`, `progress` (0..1 при наличии tqdm от `huggingface_hub`), `message` — для отображения хода загрузки в списке моделей. UI: правка revision/notes, **удаление из реестра** (в т.ч. в строке таблицы) и, отдельно, удаление локальной папки весов внутри `MODELS_DIR` при явном подтверждении. |
| `presets` | Декларация пресета в БД (имя, HF ID, parameters JSON, …). Источник правды — **БД**; одноразовый seed с диска — при **`POST /app-config/install`** (`data/presets/*.env`). **`POST /presets/sync`** / **`import-templates`** сняты в v5.0.0. **UI:** CRUD, клон; **выгрузка в `.env`** — **`POST /presets/{id}/export`**. |
| `engine_slots` | Слот инференса: `slot_key` (уник.), `engine`, `preset_name`, `hf_id`, `tp`, `gpu_indices` (CSV физ. GPU), `host_api_port`, `internal_api_port` (8111/8222), `container_id`/`container_name`, `desired_status` / `observed_status`, `extra`. При `POST /runtime/slots` строка создаётся сразу со статусом **`requested`** (бронь GPU/порта), job переводит в `running` / `failed`. Таблица **`runs` удалена в 4.0.0** (миграция startup: `DROP TABLE runs` на SQLite). Запуск/остановка — **`native.slot.*`** (docker-py), см. §3. |
| `services` | Состояние сервисов мониторинга и LiteLLM по последнему опросу. |
| `jobs` | Долгие операции CLI: команда, статус, exit code, stdout/stderr tail, correlation id, инициатор. Пока job **running** для **`native.*`** периодически обновляются **`stdout_tail`** и **`message`** (последняя значимая строка), в т.ч. линии **stream docker pull** при **`native.slot.up`** (до старта контейнера). |
| `audit_events` | Действия: при `jobs.submit` — запись **с** `correlation_id` (дублирует job для трассировки). Отдельно — **только UI** (`correlation_id IS NULL`): пресеты, модель в реестре, настройки public-access. Лента «Задачи» строится из `GET /activity`: `jobs` + UI-`audit` без дубля CLI-строк. |
| `settings` | Ключ `public_access`: JSON с **`server_host`** (для ссылок в UI) и опциональным **`litellm_api_key`** (тот же смысл, что **`LITELLM_MASTER_KEY`** у прокси; в ответах API **не** возвращается, только флаг **`litellm_api_key_set`**). Плюс **`cfg.meta`**, унаследованные пустые **`cfg.stack`** / **`cfg.secrets`**. |
| `stack_params` | Плоский стек: `param_key`, `param_value`, `is_secret` (секреты маскируются в `GET /app-config/stack`). |
| `app_log_event` | Журнал приложения (UI «Логи»): `level`, `logger_name`, `event_kind`, `message`, при HTTP — `http_method`, `http_path`, `status_code`, `duration_ms`, `request_id`, усечённый `exc_summary`, `log_extra`. Пишется из `DbLogHandler` → очередь → фоновый батч INSERT. Не путать с `audit_events`. |

Footer приложения показывает версию из `/healthz`; backend читает её из
корневого `VERSION`, чтобы UI не расходился с SemVer проекта. Копирайт:
`Igor Yatsishen, Develonica`.

## 3. Операции

### Фоновые задачи стека (`jobs.kind` = `native.*`)

| kind | Назначение |
|---|---|
| `native.model.pull` | Скачать веса через `huggingface_hub.snapshot_download` (`HF_TOKEN` из слитого стека). |
| `native.slot.up` / `down` / `restart` | Управление одним слотом: `args.slot_key`, `engine`, `preset` (имя в таблице `presets`), `gpu_indices` (list int), `host_api_port`, опционально `tp`. **Удалено в 4.0.0:** `native.llm.*`. **v5.0.0:** нет host `./slgpu` для LLM — только web/native jobs. |
| `native.monitoring.up` / `down` / `restart` | Стек метрик (`docker-compose.monitoring.yml`) + стек **proxy** (Langfuse + LiteLLM, `docker-compose.proxy.yml` после monitoring). |
| `native.monitoring.fix-perms` | Права на data-dir через docker-py + helper-образ. |
| `native.proxy.up` / `down` / `restart` | Только [`docker/docker-compose.proxy.yml`](../docker/docker-compose.proxy.yml) (Langfuse + LiteLLM). Тот же lock, что и monitoring: `("monitoring", "stack")`. |
| `native.bench.scenario` / `native.bench.load` | Subprocess `scripts/bench_openai.py` / `bench_load.py`, вывод в `data/bench/results/`. |

`CliCommand.argv` для **native.*** **пустой**; параметры в **`Job.args`**. **v5.0.0:** для jobs поддерживается только **`native.*`**; устаревший subprocess `./slgpu` снят.

API (все публичные ручки под префиксом **`/api/v1`**): `GET /api/v1/dashboard` — метрики БД, runtime, пробы сервисов и объект **`host`** (ОС/ядро/архитектура, hostname, CPU, RAM, диск по `WEB_SLGPU_ROOT`, NVIDIA+CUDA). Железо **хоста**: при доступном Docker socket backend делает `docker run` с bind-mount хостовых `/proc` и `/etc` (образ `WEB_DOCKER_HOST_PROBE_IMAGE`, по умолчанию `busybox`) и отдельный запуск **`nvidia-smi`** в образе `WEB_NVIDIA_SMI_DOCKER_IMAGE` с `device_requests` GPU (нужен **NVIDIA Container Toolkit** на сервере). Без Docker или при сбое — чтение из namespace процесса web и локальный `nvidia-smi`. Конфиг приложения: `GET/PATCH /api/v1/app-config/stack`, `POST /api/v1/app-config/install`, `GET /api/v1/app-config/status`. Бенчмарк: `GET /api/v1/bench/runs`, `GET /api/v1/bench/runs/{engine}/{ts}/summary`, `POST /api/v1/bench/scenario`, `POST /api/v1/bench/load`; в UI результаты прогона — модалка по `summary.json`. Страница подставляет **движок** и **slug пресета** из `GET /api/v1/runtime/snapshot`, когда в snapshot есть активный запуск с известным пресетом.

Зависимости образа web: `docker` (socket), `huggingface_hub` (pull), `docker compose` на хосте репо — для LLM/monitoring up (см. `app/services/compose_exec.py`).

**Inference (UI), 4.0.0:** только мультислотный путь: `POST /api/v1/runtime/slots`, `POST /api/v1/runtime/slots/{key}/down` (опционально **`?force=1`** — принудительная остановка: отмена job по `resource=slot:{key}`, `docker stop` по слоту, снятие lock без ожидания долгого `native.slot.up`; ответ `JobAccepted` с `forced: true`), `…/restart`, `GET /api/v1/runtime/snapshot`, `GET /api/v1/runtime/slots`, `GET /api/v1/runtime/slots/{key}/logs?tail=1..2000` (хвост строк контейнера слота). **Удалено:** `POST /api/v1/runtime/up|down|restart`, `GET /api/v1/runtime/logs` (без `slot_key`). Для слота `default` укажите `slot_key: "default"` в теле `POST /slots`. **Live GPU:** `GET /api/v1/gpu/state` (nvidia-smi + процессы с полем `slot_key` по `docker top`), `GET /api/v1/gpu/availability?tp=N` (занятость по `engine_slots` **и** по процессам на GPU без записи в БД — `slot_key: external` в `busy[]`).

### Docker API

- **UI «Docker» (логи), read-only (4.1.0+):** `GET /api/v1/docker/containers?scope=slgpu|all` — список контейнеров на хосте (`slgpu` — фильтр по префиксу/compose/лейблу `com.develonica.slgpu.*`). `GET /api/v1/docker/containers/{name_or_id}/logs?tail=1..5000` — tail stdout+stderr. **`GET /api/v1/docker/engine-events?since_sec=..&limit=..`** — хвост событий Docker Engine (`/events`, pull/start/die…). **`GET /api/v1/docker/daemon-log?lines=..`** — best-effort лог **dockerd** через `journalctl` (в контейнере без journal хоста может быть пусто). Страница `/docker-logs` в SPA. При недоступном socket — `docker_available: false` в списке, `503` на `…/logs` и `…/engine-events`.
- **UI «Логи» (журнал slgpu-web), read-only (5.1+):** **`GET /api/v1/app-logs/events`** — список структурированных событий из таблицы **`app_log_event`** (фильтры: `level`, `event_kind` (CSV), `path_prefix`, `q`, `since` ISO, курсор `before_id`, `limit` 1..1000). **Опционально** JSON в файл: **`${WEB_DATA_DIR}/.slgpu/app.log`** только при **`WEB_LOG_FILE_ENABLED=true`** (Loki/дебаг). `DbLogHandler` дублирует поток `logging` (stdout) в БД. Middleware: `X-Request-ID`, `extra` с `path`/`status`/`request_id` для `app.http`. Пропуск access: `GET /healthz`, `/assets/*`, фавиконки, **`/api/v1/app-logs/events`**. **`uvicorn.access`** → WARNING. Страница SPA: **`/app-logs`**. Секреты в поля `log_extra` не кладутся; тела HTTP не пишутся.
- **Чтение (внутр.):** список контейнеров по `com.docker.compose.project`, атрибуты, хвост логов; слоты — по `com.develonica.slgpu.slot` / имени `slgpu-{engine}-{slot_key}`.
- **Запись:** `native.monitoring.fix-perms` (chown через ephemeral контейнер); **LLM-слоты** — `docker run` / stop через **docker-py** (`app.services.slot_runtime`); стек мониторинга — `docker compose` из web.

### HTTP-проверки

- `GET ${WEB_LLM_HTTP_HOST}:${LLM_API_PORT}/v1/models` и при необходимости
  `http://vllm:<порт>` / `http://sglang:<порт>` — реальный список id и `/metrics` (значения из БД, без YAML-дефолтов).
- `GET http://127.0.0.1:${PROMETHEUS_PORT}/-/healthy` и `/api/v1/query`.
- `GET http://127.0.0.1:${GRAFANA_PORT}/api/health`.
- `GET http://${WEB_MONITORING_HTTP_HOST}:${LITELLM_PORT}/health/*` (страница LiteLLM).

## 4. Безопасность

- Секреты стека хранятся в **`stack_params`** с `is_secret=true`; в API отдаются **маскированными** (`***`). Пользователь может обновить значение через `PATCH /app-config/stack` (не отправляйте `***` как новое значение). В теле `stack` значение **`null`** удаляет ключ; в `secrets` — **`null`** удаляет секрет (после `merge_partial_secrets`).
- Один mutating job на scope+resource (**in-process lock** в job-runner, не PostgreSQL advisory): **слоты** — `("engine", "slot:{slot_key}")`; **monitoring и отдельный proxy LiteLLM** — `("monitoring", "stack")` (нельзя параллелить `native.monitoring.*` и `native.proxy.*`); model pull — `("model", hf_id)`; bench — `("bench", …)`. **4.0.0:** `native.llm.*` и lock `("engine", "runtime")` **удалены**.
- Mutations, **не** порождающие CLI-job, пишут `audit_events` с `correlation_id IS NULL` (см. `app.services.ui_audit`). Команды через `jobs.submit` дополнительно пишут audit **с** `correlation_id`; в ленте `GET /activity` для таких команд показывается только строка `jobs` (лог, exit).
- Корневой запуск не нужен. Контейнер web-приложения работает от
  не-root пользователя; для CLI он `exec`-ает в slgpu-репозиторий через
  bind-mount.

## 5. Развёртывание

- Подъём **с хоста (Linux VM) из корня репозитория:** **`./slgpu web up`** — `docker compose -f docker/docker-compose.web.yml --env-file **configs/bootstrap.env**`. Остановка: **`./slgpu web down`**. Импорт в БД: **`POST /api/v1/app-config/install`** из UI (контейнер должен слушать HTTP). Bootstrap — [`configs/bootstrap.env`](../configs/bootstrap.env) (минимальный набор: `SLGPU_HOST_REPO`, `WEB_DATA_DIR`, `MODELS_DIR`, `WEB_BIND/PORT`, сетевые имена). Шаблон стека для импорта — [`configs/main.env`](../configs/main.env).
- Сборка образа: [`docker/Dockerfile.web`](../docker/Dockerfile.web) (context = каталог `web/`).
- Один контейнер `slgpu-web`. Внутри: FastAPI (uvicorn) + статика
  собранного React в одном бинаре. Backend отдаёт `/api/*` и фронт
  как fallback.
- БД: SQLite в `/data/slgpu-web.db`, путь приходит из `WEB_DATABASE_URL`,
  по умолчанию `sqlite+aiosqlite:////data/slgpu-web.db`.
- Bind mounts:
  - репозиторий slgpu → **тот же абсолютный путь, что и на хосте**
    (`SLGPU_HOST_REPO`, экспортируется из [`scripts/cmd_web.sh`](../scripts/cmd_web.sh) как `$(pwd)`).
    `WEB_SLGPU_ROOT` тоже = `SLGPU_HOST_REPO`. Это нужно, чтобы команды,
    которые web запускает в стек мониторинга (`docker compose -f docker/docker-compose.monitoring.yml up`),
    отдавали docker daemon **хостовые** пути для bind-маунтов конфигов
    и скриптов; иначе daemon при отсутствующем source создаёт пустые
    каталоги (Loki/Prometheus/`minio-bucket-init` падают).
    `working_dir` в compose **не задаём** — uvicorn должен стартовать из
    `WORKDIR /srv/app` ([`docker/Dockerfile.web`](../docker/Dockerfile.web)),
    где лежит пакет `app/`; для CLI-вызовов backend сам выставляет
    `cwd=settings.slgpu_root` в `jobs` (только `native.*`);
  - локальный диск под БД → `/data`;
  - **веса HF** с хоста: `${MODELS_DIR}` (из `stack_params` после install). Target в контейнере
    — `${SLGPU_HOST_REPO}/data/models` (тот же абсолютный путь, что
    разрешает CLI на хосте). Права **rw** (pull и скан). Страница моделей
    перечисляет именно фактические каталоги `${MODELS_DIR}/<org>/<repo>`, а
    не список пресетов;
  - `/var/run/docker.sock` → `/var/run/docker.sock` (read-only).
- Данные **метрик и логов** (Prometheus, Grafana, Loki и т.д.) вынесены в
  `docker/docker-compose.monitoring.yml`; **Langfuse** (и связанные тома) — в
  `docker/docker-compose.proxy.yml`. В web-контейнер **не** монтируются: UI опрашивает по HTTP / Docker API.
- Снимок стека для `docker compose` (monitoring/proxy): **`${WEB_DATA_DIR}/.slgpu/compose-service.env`**; web пишет **строго из БД** (`sync_merged_flat` → `write_compose_service_env_file`). `docker compose` с очищенным env процесса; в YAML **нет** `${VAR:-...}`. Корень **`<repo>/.slgpu`** не используется.
- Entrypoint образа (`web/docker-entrypoint.sh`): PID 1 кратко под root,
  `chown` на смонтированные `/data`, `${WEB_SLGPU_ROOT}/data/models` и
  `${WEB_SLGPU_ROOT}/data/presets` и **`${WEB_SLGPU_ROOT}/data/web`** (в т.ч. `.slgpu`) под UID приложения (10001);
  сокет Docker при монтировании часто `root:docker` (660) — создаётся/используется
  группа с GID, совпадающим с `stat` сокета, в неё добавляется `slgpuweb`, затем
  `tini` (PID 1) → entrypoint → `runuser` (uvicorn), группа = GID `docker.sock`
  (доступ к API Docker без `PermissionError` на сокете).
- Сеть: подключение к существующей `slgpu` (external) для опционального
  доступа к именам сервисов.
- Имена стеков Compose для **опроса Docker** (`com.docker.compose.project`) читаются из
  `stack_params`: `WEB_COMPOSE_PROJECT_INFER`, `WEB_COMPOSE_PROJECT_MONITORING`,
  `WEB_COMPOSE_PROJECT_PROXY`.
- **DSN SQLite (sync read):** путь к файлу БД для `sync_merged_flat` / read-only `sqlite3` разбирается через **SQLAlchemy `make_url`** (URL вида `sqlite+aiosqlite:////data/slgpu-web.db` — абсолютный путь в Unix; старый regex, обрезавший ведущий `/`, **не** используется).
- **Наблюдаемость:** `configure_logging(…, log_file_enabled=…)` — **StreamHandler** (JSON в stdout) + **`DbLogHandler`** (очередь → SQLite `app_log_event`) + **RotatingFileHandler** в **`${WEB_DATA_DIR}/.slgpu/app.log`** только если **`WEB_LOG_FILE_ENABLED=true`**. `start_writer` / `stop_writer` в **startup** / **shutdown** приложения. `PRAGMA journal_mode=WAL` на SQLite при **init_db**. `uvicorn*`, `fastapi`, `starlette`, `app`, `httpx` — propagate, **`uvicorn.access`** — WARNING. Якоря: `[runtime][…]`, `[app][http][BLOCK_API_REQUEST]`, …
  `WEB_LOG_LEVEL=DEBUG` включает, в частности, отсутствие контейнера по
  лейблам `com.docker.compose.project` / `…service` (`get_by_service`).
- **Поиск контейнеров в Docker:** помимо точного фильтра по лейблам — нормализация
  (`-`/`_`, регистр) и имя в стиле Compose v2 (`<project>-<service>-N`) / v1
  (`<project>_<service>_N`), если Portainer/стек отдаёт нестандартные лейблы;
  дополнительно — по жёстким `container_name`: **`slgpu-<service>`** (инференс),
  **`slgpu-monitoring-<service>`** (метрики/логи), **`slgpu-proxy-<service>`** (Langfuse, LiteLLM, Postgres proxy-стека и т.д.).

## 6. Совместимость

- Windows-машина — только разработка. Все эксплуатационные команды
  выполняются на Linux VM с Docker и драйвером NVIDIA.
- Корневые [`docker/docker-compose.llm.yml`](../docker/docker-compose.llm.yml),
  [`docker/docker-compose.monitoring.yml`](../docker/docker-compose.monitoring.yml) и
  [`docker/docker-compose.proxy.yml`](../docker/docker-compose.proxy.yml) (Langfuse + LiteLLM) задают
  стабильные **`container_name`** (`slgpu-*` / `slgpu-monitoring-*` / `slgpu-proxy-*`); конфиги
  метрик/логов (Prometheus, Grafana, Loki, …) — в
  [`configs/monitoring/`](../configs/monitoring/).
  web-приложение — [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml).

## 7. Журнал изменений контракта

Любое изменение этого файла обязано сопровождаться записью в
[`docs/HISTORY.md`](../docs/HISTORY.md) и поднятием версии в
[`VERSION`](../VERSION).
