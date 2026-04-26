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
`main.env` в SQLite (`cfg.stack`, `cfg.secrets`, `cfg.meta`), правка плоских ключей и секретов (секреты в API маскируются). Этот host используется только для ссылок в браузере. Внутренние health-probe используют `WEB_MONITORING_HTTP_HOST`; порты Prometheus/Grafana/Langfuse/LiteLLM и имена compose-проектов читаются из **слитого** стека (БД + дефолты), не только из `WEB_*` env. Снимок runtime ходит к API движка через `WEB_LLM_HTTP_HOST` и `http://vllm:<LLM_API_PORT>` / `http://sglang:<порт>` (порты из стека).

## 2. Границы ответственности

### Источники правды (НЕ дублируем в БД приложения)

| Сущность | Источник правды |
|---|---|
| Веса моделей на диске | `${MODELS_DIR}` (по умолчанию **`./data/models`**, см. `data/README.md`); удаление весов из UI разрешено только внутри этого каталога |
| Параметры движка для запуска | Плоский стек в SQLite (`cfg.stack` + `cfg.secrets`), синхронизируемый с `main.env` при install; пресеты — `data/presets/<slug>.env` (`PRESETS_DIR` из стека) |
| Состояние контейнеров | Docker daemon (через socket) |
| Метрики и серии | Prometheus TSDB |
| Логи контейнеров | Loki / `docker logs` |
| Трейсы LLM-вызовов | Langfuse |
| Маршруты `model -> api_base` LiteLLM | БД `litellm` (Postgres из monitoring) |

### Что хранит SQLite приложения

| Таблица | Назначение |
|---|---|
| `models` | Кэш реестра HF-моделей: id, revision, slug, локальный путь, статус скачивания, размер, последняя ошибка, attempts. Источник правды для весов — папки `${MODELS_DIR}/<org>/<repo>`. `GET /models` и **`POST /models/sync`** подмешивают/обновляют записи по сканированию `MODELS_DIR`. UI: правка revision/notes, **удаление из реестра** (в т.ч. в строке таблицы) и, отдельно, удаление локальной папки весов внутри `MODELS_DIR` при явном подтверждении. |
| `presets` | Декларация пресета в БД (имя, HF ID, model_id, параметры key/value для `.env`, GPU mask, путь к синхронизированному `.env`). **Движок** (vLLM/SGLang) в пресете **не** хранится: выбор — при запуске (`./slgpu up …`, страница Inference). Экспорт в `data/presets/<slug>.env` не добавляет `SLGPU_ENGINE`. UI: просмотр, параметрическое редактирование, удаление; запись в файл — отдельный экспорт; удаление `.env` — отдельная подтверждаемая операция. |
| `runs` | Желаемое и фактическое состояние запуска (engine, preset, HF ID в `extra`, port, TP, started_at). Runtime snapshot показывает последний активный запуск, чтобы UI явно видел запрошенные модель и пресет. |
| `services` | Состояние сервисов мониторинга и LiteLLM по последнему опросу. |
| `jobs` | Долгие операции CLI: команда, статус, exit code, stdout/stderr tail, correlation id, инициатор. |
| `audit_events` | Действия: при `jobs.submit` — запись **с** `correlation_id` (дублирует job для трассировки). Отдельно — **только UI** (`correlation_id IS NULL`): пресеты, модель в реестре, настройки public-access. Лента «Задачи» строится из `GET /activity`: `jobs` + UI-`audit` без дубля CLI-строк. |
| `settings` | Публичный host (`public_access`), плюс ключи **`cfg.stack`**, **`cfg.secrets`**, **`cfg.meta`** (установка из файлов, маскирование секретов в API). |

Footer приложения показывает версию из `/healthz`; backend читает её из
корневого `VERSION`, чтобы UI не расходился с SemVer проекта. Копирайт:
`Igor Yatsishen, Develonica`.

## 3. Операции

### Фоновые задачи стека (`jobs.kind` = `native.*`)

| kind | Назначение |
|---|---|
| `native.model.pull` | Скачать веса через `huggingface_hub.snapshot_download` (`HF_TOKEN` из слитого стека). |
| `native.llm.up` | `docker compose` LLM-стек, env из БД + пресет. |
| `native.llm.down` / `native.llm.restart` | Остановка / пересоздание LLM-стека. |
| `native.monitoring.up` / `down` / `restart` | Стек мониторинга. |
| `native.monitoring.fix-perms` | Права на data-dir через docker-py + helper-образ. |
| `native.bench.scenario` / `native.bench.load` | Subprocess `scripts/bench_openai.py` / `bench_load.py`, вывод в `data/bench/results/`. |

`CliCommand.argv` для этих операций **пустой**; параметры в `Job.args`. Унаследованный путь с subprocess `./slgpu` не используется для стека.

API: `GET/PATCH /app-config/stack`, `POST /app-config/install`, `GET /app-config/status`; бенчмарк: `GET /bench/runs`, `GET /bench/report.md`, `POST /bench/scenario`, `POST /bench/load`.

Зависимости образа web: `docker` (socket), `huggingface_hub` (pull), `docker compose` на хосте репо — для LLM/monitoring up (см. `app/services/compose_exec.py`).

### Docker API

- **Чтение:** список контейнеров по `com.docker.compose.project`, атрибуты, хвост логов.
- **Запись:** `native.monitoring.fix-perms` (chown через ephemeral контейнер); LLM/monitoring up/down — через `docker compose`, не через произвольный `docker run` из UI.

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

- Секреты стека хранятся в **`cfg.secrets`** (SQLite); в API отдаются **маскированными** (`***`). Пользователь может обновить значение через `PATCH /app-config/stack` (не отправляйте `***` как новое значение).
- Один mutating job на стек одновременно (advisory lock в БД на
  `(scope, resource)`: runtime-команды используют `("engine", "runtime")`,
  monitoring-команды — `("monitoring", "stack")`). UI показывает активную
  job и блокирует повторные конфликтующие кнопки до завершения.
- Mutations, **не** порождающие CLI-job, пишут `audit_events` с `correlation_id IS NULL` (см. `app.services.ui_audit`). Команды через `jobs.submit` дополнительно пишут audit **с** `correlation_id`; в ленте `GET /activity` для таких команд показывается только строка `jobs` (лог, exit).
- Корневой запуск не нужен. Контейнер web-приложения работает от
  не-root пользователя; для CLI он `exec`-ает в slgpu-репозиторий через
  bind-mount.

## 5. Развёртывание

- Подъём **с хоста (Linux VM) из корня репозитория:** **`./slgpu web up`** (обёртка над
  `docker compose -f docker/docker-compose.web.yml --env-file main.env` с
  `--project-directory` = корень репо; см. `scripts/cmd_web.sh`). Остановка:
  **`./slgpu web down`**. После первого старта: **`./slgpu web install`** или UI / `POST /app-config/install` — импорт `main.env` в БД. Переменные `WEB_DATA_DIR`, `MODELS_DIR`, `WEB_BIND`, `WEB_PORT` —
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
  `LogRecord` должен давать ровно одну строку. `configure_logging()` заменяет
  handlers у `root`, `app`, `httpx`, `uvicorn*` и отключает `propagate`, чтобы
  не получать дубли вроде `INFO INFO ... ts=... logger=... msg=...`. В сообщениях
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
