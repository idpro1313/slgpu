# Контракт `web/` — slgpu Control Plane

> Этот документ — единый источник правды для границ ответственности
> web-приложения внутри проекта `slgpu`. Любое расхождение между кодом
> и контрактом — баг, и фикс начинается отсюда.

## 1. Назначение

Web-приложение `slgpu-web` — control plane поверх существующего bash CLI
[`./slgpu`](../slgpu) и Docker-стека ([`docker-compose.yml`](../docker-compose.yml),
[`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml)). Оно
выполняет пять задач из ТЗ пользователя:

1. Скачивание моделей с Hugging Face по ID, контроль процесса,
   повторная докачка, журнал.
2. CRUD пресетов запуска (несколько пресетов на одну модель,
   привязка к GPU и параметрам движка).
3. Запуск/остановка/рестарт vLLM или SGLang с выбранным пресетом и
   просмотр их фактического состояния.
4. Управление и контроль стека мониторинга (Prometheus, Grafana, Loki,
   Promtail, DCGM, Node Exporter, Langfuse).
5. Управление и контроль LiteLLM Proxy — единой OpenAI-совместимой
   точки доступа к моделям.

## 2. Границы ответственности

### Источники правды (НЕ дублируем в БД приложения)

| Сущность | Источник правды |
|---|---|
| Веса моделей на диске | `${MODELS_DIR}` (по умолчанию `/opt/models`) |
| Параметры движка для запуска | `main.env` + `configs/models/<slug>.env` |
| Состояние контейнеров | Docker daemon (через socket) |
| Метрики и серии | Prometheus TSDB |
| Логи контейнеров | Loki / `docker logs` |
| Трейсы LLM-вызовов | Langfuse |
| Маршруты `model -> api_base` LiteLLM | БД `litellm` (Postgres из monitoring) |

### Что хранит SQLite приложения

| Таблица | Назначение |
|---|---|
| `models` | Реестр HF-моделей: id, revision, slug, локальный путь, статус скачивания, размер, последняя ошибка, attempts. |
| `presets` | Декларация пресета в БД (имя, движок, model_id, параметры JSON, GPU mask, путь к синхронизированному `.env`). |
| `runs` | Желаемое и фактическое состояние запуска (engine, preset, port, TP, started_at). |
| `services` | Состояние сервисов мониторинга и LiteLLM по последнему опросу. |
| `jobs` | Долгие операции CLI: команда, статус, exit code, stdout/stderr tail, correlation id, инициатор. |
| `audit_events` | Действия пользователей в UI (mutations). |
| `settings` | Пути проекта, фичефлаги, видимые URL для UI. |

## 3. Операции

### CLI Allowlist (только эти команды разрешены приложению)

| ID | Команда | Назначение |
|---|---|---|
| `cli.pull` | `./slgpu pull <slug-or-hf-id> [--revision REV]` | Скачать модель. |
| `cli.up` | `./slgpu up <vllm\|sglang> -m <slug> [-p PORT] [--tp N]` | Поднять движок. |
| `cli.down` | `./slgpu down [--all]` | Остановить движок (опц. с мониторингом). |
| `cli.restart` | `./slgpu restart -m <slug> [--tp N]` | Перезапуск с новым пресетом без смены движка. |
| `cli.monitoring.up` | `./slgpu monitoring up` | Поднять мониторинг. |
| `cli.monitoring.down` | `./slgpu monitoring down` | Остановить мониторинг. |
| `cli.monitoring.restart` | `./slgpu monitoring restart` | Пересоздать мониторинг. |
| `cli.monitoring.fix-perms` | `./slgpu monitoring fix-perms` | Починить права на bind-mount каталоги. |

Любая команда вне списка отвергается раньше, чем дойдёт до shell.
Аргументы валидируются регулярными выражениями: slug, hf-id, port,
TP, revision. `shell=False` всегда.

### Docker API (read-only)

Приложение использует Docker socket только для чтения:

- `containers.list({"label": "com.docker.compose.project=slgpu"})`,
  `+slgpu-monitoring`;
- `container.attrs` (статус, ports, restart count);
- `container.logs(tail=N, since=...)` — стрим в UI и в `jobs.stderr_tail`.

Mutations контейнеров идут только через CLI allowlist.

### HTTP-проверки

- `GET http://127.0.0.1:${LLM_API_PORT}/v1/models` — реальный список
  моделей у движка.
- `GET http://127.0.0.1:${PROMETHEUS_PORT}/-/healthy` и `/api/v1/query`.
- `GET http://127.0.0.1:${GRAFANA_PORT}/api/health`.
- `GET http://127.0.0.1:${LITELLM_PORT}/health`.

## 4. Безопасность

- Hugging Face / Grafana / Langfuse / LiteLLM секреты **не пишутся в
  БД и не показываются в UI**. UI показывает только наличие/отсутствие
  и путь к секретному файлу.
- Один mutating job на стек одновременно (advisory lock в БД на
  `(scope, resource)`, например `("engine", "vllm")`).
- Все mutating-эндпоинты пишут запись в `audit_events`.
- Корневой запуск не нужен. Контейнер web-приложения работает от
  не-root пользователя; для CLI он `exec`-ает в slgpu-репозиторий через
  bind-mount.

## 5. Развёртывание

- Один контейнер `slgpu-web`. Внутри: FastAPI (uvicorn) + статика
  собранного React в одном бинаре. Backend отдаёт `/api/*` и фронт
  как fallback.
- БД: SQLite в `/data/slgpu-web.db`, путь приходит из `WEB_DATABASE_URL`,
  по умолчанию `sqlite+aiosqlite:////data/slgpu-web.db`.
- Bind mounts:
  - репозиторий slgpu → `/slgpu` (для CLI и чтения `configs/models/*.env`,
    `main.env`);
  - локальный диск под БД → `/data`;
  - `/var/run/docker.sock` → `/var/run/docker.sock` (read-only).
- Entrypoint образа (`web/docker-entrypoint.sh`): PID 1 кратко под root,
  `chown` на смонтированный `/data` под UID приложения (10001), затем uvicorn
  не от root (чтобы SQLite на bind-mount не упирался в «root-only» каталог).
- Сеть: подключение к существующей `slgpu` (external) для опционального
  доступа к именам сервисов.

## 6. Совместимость

- Windows-машина — только разработка. Все эксплуатационные команды
  выполняются на Linux VM с Docker и драйвером NVIDIA.
- Корневые `docker-compose.yml` и `docker-compose.monitoring.yml` не
  изменяются. Web-приложение поднимается отдельным
  [`web/docker-compose.yml`](docker-compose.yml).

## 7. Журнал изменений контракта

Любое изменение этого файла обязано сопровождаться записью в
[`docs/HISTORY.md`](../docs/HISTORY.md) и поднятием версии в
[`VERSION`](../VERSION).
