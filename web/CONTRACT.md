# Контракт `web/` — Develonica.LLM

> Этот документ — единый источник правды для границ ответственности
> web-приложения внутри проекта `slgpu`. Любое расхождение между кодом
> и контрактом — баг, и фикс начинается отсюда.

## 1. Назначение

Web-приложение **Develonica.LLM** (`slgpu-web`) — control plane поверх Docker Compose / Docker API
([`docker/docker-compose.llm.yml`](../docker/docker-compose.llm.yml),
[`docker/docker-compose.monitoring.yml`](../docker/docker-compose.monitoring.yml)); опционально bash CLI
[`./slgpu`](../slgpu) на хосте для ручных сценариев. Оно
выполняет задачи из ТЗ пользователя:

1. Скачивание моделей с Hugging Face по ID, контроль процесса,
   повторная докачка, журнал.
2. CRUD пресетов запуска (несколько пресетов на одну модель,
   привязка к GPU и переменным `.env` для serve; **движок** в БД не хранится).
3. Запуск/остановка/рестарт vLLM или SGLang с выбранным пресетом и
   просмотр их фактического состояния.
4. Управление и контроль стека мониторинга (Prometheus, Grafana, Loki,
   Promtail, DCGM, Node Exporter, Langfuse).
5. Управление и контроль LiteLLM Proxy — единой OpenAI-совместимой
   точки доступа к моделям.
6. Отображение актуальной версии проекта и копирайта в общем footer.

Визуальный стиль фронтенда следует live CSS сайта
[`develonica.ru`](https://develonica.ru/): `IBM Plex Sans` как основной шрифт,
`Finlandica` для заголовков и числовых акцентов, фирменный голубой `#59AFFF`,
тёмно-голубой hover/active `#0A5AA4`, светло-голубые градиенты
`#F7FBFF`/`#E2EDF8`, белая sticky-шапка, подчёркнутая навигация и контролы с
radius `10px`. Favicon остаётся в LLM-тематике, но использует ту же синюю
палитру.

Страница **Настройки**: публичный IP/DNS (`settings.public_access.server_host`), импорт стека из
`main.env` в SQLite (**таблица `stack_params`** — одна строка на переменную; **`cfg.meta`** — установка; унаследованные ключи **`cfg.stack`** / **`cfg.secrets`** в `settings` после миграции остаются пустыми `{}`), правка ключей в UI таблицей (секреты в API маскируются). Этот host используется только для ссылок в браузере. Внутренние health-probe используют `WEB_MONITORING_HTTP_HOST`; порты Prometheus/Grafana/Langfuse/LiteLLM и имена compose-проектов читаются из **слитого** стека (БД + дефолты), не только из `WEB_*` env. Снимок runtime ходит к API движка через `WEB_LLM_HTTP_HOST` и `http://vllm:<LLM_API_PORT>` / `http://sglang:<порт>` (порты из стека).

## 2. Границы ответственности

### Источники правды (НЕ дублируем в БД приложения)

| Сущность | Источник правды |
|---|---|
| Веса моделей на диске | `${MODELS_DIR}` (по умолчанию **`./data/models`**, см. `data/README.md`); удаление весов из UI разрешено только внутри этого каталога |
| Параметры движка для запуска | Плоский стек в SQLite (**`stack_params`** + слияние с кодовыми дефолтами в `sync_merged_flat`), синхронизируемый с `main.env` при install; пресеты — `data/presets/<slug>.env` (`PRESETS_DIR` из стека) |
| Состояние контейнеров | Docker daemon (через socket) |
| Метрики и серии | Prometheus TSDB |
| Логи контейнеров | Loki / `docker logs` |
| Трейсы LLM-вызовов | Langfuse |
| Маршруты `model -> api_base` LiteLLM | БД `litellm` (Postgres из monitoring) |

### Что хранит SQLite приложения

| Таблица | Назначение |
|---|---|
| `models` | Кэш реестра HF-моделей: id, revision, slug, локальный путь, статус скачивания, размер, последняя ошибка, attempts. Источник правды для весов — папки `${MODELS_DIR}/<org>/<repo>`. `GET /models` и **`POST /models/sync`** подмешивают/обновляют записи по сканированию `MODELS_DIR`. В **`GET /models`** и **`GET /models/{id}`** вложенное поле **`pull_progress`** (активная `Job` `native.model.pull` по `resource` = `hf_id`): `job_id`, `status`, `progress` (0..1 при наличии tqdm от `huggingface_hub`), `message` — для отображения хода загрузки в списке моделей. UI: правка revision/notes, **удаление из реестра** (в т.ч. в строке таблицы) и, отдельно, удаление локальной папки весов внутри `MODELS_DIR` при явном подтверждении. |
| `presets` | Декларация пресета в БД (имя, HF ID, model_id, параметры key/value для `.env`, GPU mask, путь к синхронизированному `.env`). **Движок** (vLLM/SGLang) в пресете **не** хранится: выбор — при запуске (`./slgpu up …`, страница Inference). Экспорт в `data/presets/<slug>.env` не добавляет `SLGPU_ENGINE`. **`POST /api/v1/presets/import-templates`** копирует эталонные `*.env` из **`examples/presets`** репозитория в `PRESETS_DIR` **без перезаписи** уже существующих файлов, затем выполняет импорт в БД (как **`POST /presets/sync`**). UI: просмотр, параметрическое редактирование, удаление; запись в файл — отдельный экспорт; удаление `.env` — отдельная подтверждаемая операция. |
| `runs` | Желаемое и фактическое состояние запуска (engine, preset, HF ID в `extra`, port, TP, `gpu_mask`, started_at). Используется для истории/совместимости; активный **мультислот** — таблица `engine_slots`. |
| `engine_slots` | Слот инференса: `slot_key` (уник.), `engine`, `preset_name`, `hf_id`, `tp`, `gpu_indices` (CSV физ. GPU), `host_api_port`, `internal_api_port` (8111/8222), `container_id`/`container_name`, `desired_status` / `observed_status`, `extra`. Запуск/остановка — **`native.slot.*`** (docker-py, не compose), см. §3. |
| `services` | Состояние сервисов мониторинга и LiteLLM по последнему опросу. |
| `jobs` | Долгие операции CLI: команда, статус, exit code, stdout/stderr tail, correlation id, инициатор. |
| `audit_events` | Действия: при `jobs.submit` — запись **с** `correlation_id` (дублирует job для трассировки). Отдельно — **только UI** (`correlation_id IS NULL`): пресеты, модель в реестре, настройки public-access. Лента «Задачи» строится из `GET /activity`: `jobs` + UI-`audit` без дубля CLI-строк. |
| `settings` | Публичный host (`public_access`), **`cfg.meta`**, плюс унаследованные пустые **`cfg.stack`** / **`cfg.secrets`** после миграции. |
| `stack_params` | Плоский стек: `param_key`, `param_value`, `is_secret` (секреты маскируются в `GET /app-config/stack`). |

Footer приложения показывает версию из `/healthz`; backend читает её из
корневого `VERSION`, чтобы UI не расходился с SemVer проекта. Копирайт:
`Igor Yatsishen, Develonica`.

## 3. Операции

### Фоновые задачи стека (`jobs.kind` = `native.*`)

| kind | Назначение |
|---|---|
| `native.model.pull` | Скачать веса через `huggingface_hub.snapshot_download` (`HF_TOKEN` из слитого стека). |
| `native.llm.up` | Тонкая обёртка: `native.slot.up` с `slot_key=default` (docker-py, контейнер `slgpu-vllm` / `slgpu-sglang`). |
| `native.llm.down` / `native.llm.restart` | `down` — остановка всех слотов LLM (по БД + legacy compose-имена); `restart` — пересоздание слота `default`. |
| `native.slot.up` / `down` / `restart` | Управление одним слотом: `args.slot_key`, `engine`, `preset`, `gpu_indices` (list int), `host_api_port`, опционально `tp`. Локи jobs: `("engine", "slot:{slot_key}")` — разные слоты не блокируют друг друга. |
| `native.monitoring.up` / `down` / `restart` | Стек мониторинга. |
| `native.monitoring.fix-perms` | Права на data-dir через docker-py + helper-образ. |
| `native.bench.scenario` / `native.bench.load` | Subprocess `scripts/bench_openai.py` / `bench_load.py`, вывод в `data/bench/results/`. |

`CliCommand.argv` для этих операций **пустой**; параметры в `Job.args`. Унаследованный путь с subprocess `./slgpu` не используется для стека.

API: `GET /api/v1/dashboard` — метрики БД, runtime, пробы сервисов и объект **`host`** (ОС/ядро/архитектура, hostname, CPU, RAM, диск по `WEB_SLGPU_ROOT`, NVIDIA+CUDA). Железо **хоста**: при доступном Docker socket backend делает `docker run` с bind-mount хостовых `/proc` и `/etc` (образ `WEB_DOCKER_HOST_PROBE_IMAGE`, по умолчанию `busybox`) и отдельный запуск **`nvidia-smi`** в образе `WEB_NVIDIA_SMI_DOCKER_IMAGE` с `device_requests` GPU (нужен **NVIDIA Container Toolkit** на сервере). Без Docker или при сбое — чтение из namespace процесса web и локальный `nvidia-smi`. `GET/PATCH /app-config/stack`, `POST /app-config/install`, `GET /app-config/status`; бенчмарк: `GET /bench/runs`, `GET /bench/runs/{engine}/{ts}/summary`, `POST /bench/scenario`, `POST /bench/load`; в UI результаты прогона — модалка по `summary.json`. Страница подставляет **движок** и **slug пресета** из `GET /runtime/snapshot`, когда в snapshot есть активный запуск с известным пресетом.

Зависимости образа web: `docker` (socket), `huggingface_hub` (pull), `docker compose` на хосте репо — для LLM/monitoring up (см. `app/services/compose_exec.py`).

### Docker API

- **Чтение:** список контейнеров по `com.docker.compose.project`, атрибуты, хвост логов; слоты — по `com.develonica.slgpu.slot` / имени `slgpu-{engine}-{slot_key}`.
- **Запись:** `native.monitoring.fix-perms` (chown через ephemeral контейнер); **LLM-слоты** — `docker run` / stop через **docker-py** (`app.services.slot_runtime`); стек мониторинга — `docker compose`. Ручной `./slgpu up` с хоста по-прежнему использует `docker/docker-compose.llm.yml`.

### HTTP-проверки

- `GET ${WEB_LLM_HTTP_HOST:-host.docker.internal}:${LLM_API_PORT}/v1/models` и, при
  необходимости, `http://vllm:8111` / `http://sglang:8222` — реальный список
  обслуживаемых id и проверка `/metrics` (из контейнера `slgpu-web` не
  `127.0.0.1:порт` на публикованный порт движка).
- `GET http://127.0.0.1:${PROMETHEUS_PORT}/-/healthy` и `/api/v1/query`.
- `GET http://127.0.0.1:${GRAFANA_PORT}/api/health`.
- `GET http://${WEB_MONITORING_HTTP_HOST:-host.docker.internal}:${LITELLM_PORT}/health/*` (страница
  LiteLLM в slgpu-web, не `127.0.0.1` из контейнера).

## 4. Безопасность

- Секреты стека хранятся в **`stack_params`** с `is_secret=true`; в API отдаются **маскированными** (`***`). Пользователь может обновить значение через `PATCH /app-config/stack` (не отправляйте `***` как новое значение). В теле `stack` значение **`null`** удаляет ключ; в `secrets` — **`null`** удаляет секрет (после `merge_partial_secrets`).
- Один mutating job на стек одновременно (advisory lock в БД на
  `(scope, resource)`: **legacy** runtime `native.llm.*` — `("engine", "runtime")`; **слоты** — `("engine", "slot:{slot_key}")`; monitoring — `("monitoring", "stack")`. UI показывает активную
  job и блокирует повторные конфликтующие кнопки до завершения.
- Mutations, **не** порождающие CLI-job, пишут `audit_events` с `correlation_id IS NULL` (см. `app.services.ui_audit`). Команды через `jobs.submit` дополнительно пишут audit **с** `correlation_id`; в ленте `GET /activity` для таких команд показывается только строка `jobs` (лог, exit).
- Корневой запуск не нужен. Контейнер web-приложения работает от
  не-root пользователя; для CLI он `exec`-ает в slgpu-репозиторий через
  bind-mount.

## 5. Развёртывание

- Подъём **с хоста (Linux VM) из корня репозитория:** **`./slgpu web up`** (обёртка над
  `docker compose -f docker/docker-compose.web.yml --env-file main.env` с
  `--project-directory` = корень репо; см. `scripts/cmd_web.sh`). Остановка:
  **`./slgpu web down`**. Импорт стека: только пока контейнер слушает HTTP — **`./slgpu web up`**, затем **`./slgpu web install`** (или UI / `POST /api/v1/app-config/install`). Переменные `WEB_DATA_DIR`, `MODELS_DIR`, `WEB_BIND`, `WEB_PORT` —
  в [`main.env`](../main.env). Публикация на хосте: по умолчанию **`WEB_BIND=0.0.0.0`** (доступ извне на `WEB_PORT`); только с localhost — **`WEB_BIND=127.0.0.1`**.
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
    `cwd=settings.slgpu_root` в `app/services/jobs.py`;
  - локальный диск под БД → `/data`;
  - **веса HF** с хоста: `${MODELS_DIR}` (должно совпадать с `MODELS_DIR` в
    `main.env`, по умолчанию **`./data/models`**). Target в контейнере
    — `${SLGPU_HOST_REPO}/data/models` (тот же абсолютный путь, что
    разрешает CLI на хосте). Права **rw** (pull и скан). Страница моделей
    перечисляет именно фактические каталоги `${MODELS_DIR}/<org>/<repo>`, а
    не список пресетов;
  - `/var/run/docker.sock` → `/var/run/docker.sock` (read-only).
- Данные **мониторинга** (Prometheus, Grafana, Loki, Langfuse и т.д.) вынесены в
  отдельный `docker/docker-compose.monitoring.yml` и **не** монтируются в web-контейнер:
  UI опрашивает их по HTTP/ Docker API, не по путям на диске.
- Entrypoint образа (`web/docker-entrypoint.sh`): PID 1 кратко под root,
  `chown` на смонтированные `/data`, `${WEB_SLGPU_ROOT}/data/models` и
  `${WEB_SLGPU_ROOT}/data/presets` под UID приложения (10001);
  сокет Docker при монтировании часто `root:docker` (660) — создаётся/используется
  группа с GID, совпадающим с `stat` сокета, в неё добавляется `slgpuweb`, затем
  `tini` (PID 1) → entrypoint → `runuser` (uvicorn), группа = GID `docker.sock`
  (доступ к API Docker без `PermissionError` на сокете).
- Сеть: подключение к существующей `slgpu` (external) для опционального
  доступа к именам сервисов.
- Имена стеков Compose для **опроса Docker** (`com.docker.compose.project`):
  по умолчанию `slgpu` (инференс) и `slgpu-monitoring` (мониторинг); при
  другом `COMPOSE_PROJECT_NAME` задайте `WEB_COMPOSE_PROJECT_INFER` и
  `WEB_COMPOSE_PROJECT_MONITORING` (см. `main.env` в корне репо).
- **Наблюдаемость:** логи в **stdout** в JSON (`app.core.logging`); один
  `LogRecord` — одна строка. `configure_logging()` оставляет **единственный** handler
  на **root**, снимает handlers с `app`, `httpx`, `httpcore`, `h11`, `uvicorn*`,
  `fastapi`, `starlette` и включает у них `propagate`, чтобы не было дублей
  (`INFO INFO …` в Loki). Повторный вызов в `startup` сбрасывает handler'ы, которые
  добавил uvicorn после импорта приложения. В сообщениях
  якоря вроде `[runtime][snapshot][BLOCK_RESOLVE]`, `[monitoring][probe_all]`, `[api][dashboard]`.
  `WEB_LOG_LEVEL=DEBUG` включает, в частности, отсутствие контейнера по
  лейблам `com.docker.compose.project` / `…service` (`get_by_service`).
- **Поиск контейнеров в Docker:** помимо точного фильтра по лейблам — нормализация
  (`-`/`_`, регистр) и имя в стиле Compose v2 (`<project>-<service>-N`) / v1
  (`<project>_<service>_N`), если Portainer/стек отдаёт нестандартные лейблы;
  дополнительно — по жёстким `container_name` из репозитория: **`slgpu-<service>`**
  (инференс) и **`slgpu-monitoring-<service>`** (стек мониторинга), если
  `COMPOSE_PROJECT_NAME` не совпадает с ожидаемым.

## 6. Совместимость

- Windows-машина — только разработка. Все эксплуатационные команды
  выполняются на Linux VM с Docker и драйвером NVIDIA.
- Корневые [`docker/docker-compose.llm.yml`](../docker/docker-compose.llm.yml) и
  [`docker/docker-compose.monitoring.yml`](../docker/docker-compose.monitoring.yml) задают
  стабильные **`container_name`** (префиксы `slgpu-` / `slgpu-monitoring-`); конфиги
  стека мониторинга (Prometheus, Grafana, Loki, …) — в
  [`configs/monitoring/`](../configs/monitoring/).
  web-приложение поднимается отдельным [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml).

## 7. Журнал изменений контракта

Любое изменение этого файла обязано сопровождаться записью в
[`docs/HISTORY.md`](../docs/HISTORY.md) и поднятием версии в
[`VERSION`](../VERSION).
