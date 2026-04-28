# slgpu

Репозиторий **стенда для сравнения LLM-инференса** на Linux-сервере с GPU: два движка (**vLLM** и **SGLang**) в Docker, общий локальный кэш моделей, OpenAI-совместимый HTTP API, нагрузочный бенчмарк, **Prometheus + Grafana Loki (логи) + Promtail + Langfuse (трейсинг) + LiteLLM Proxy (шлюз) + NVIDIA DCGM Exporter** (см. [§3](#3-сервисы-и-порты), [`configs/monitoring/README.md`](configs/monitoring/README.md)).

> **Версия 6.1.0:** страница **«Пресеты»** — **загрузка пресета из `.env`-файла** в SQLite (`POST /api/v1/presets/import-env`, конфликт имени без перезаписи — **409**). **6.0.11:** `native.slot.*` / `slot_runtime` — **`contextlib.closing(docker.from_env())`** вместо `with docker.from_env()`, чтобы не зависеть от поддержки контекстного протокола в установленном **docker-py**. **6.0.10:** из провиженинга Grafana убран дашборд **«slgpu overview»**. Шаблон Loki с **`compactor.delete_request_store: filesystem`** при **`retention_enabled`** (иначе Loki 3: *delete-request-store should be configured when retention is enabled*); ранее убран **`chunk_store_config.max_look_back_period`** — в **Loki 3** это поле недопустимо; глубина запросов — **`limits_config.max_query_lookback`**. В «Настройки» можно **показывать секреты из БД в явном виде** (`GET /api/v1/app-config/stack?reveal_secrets=true`, см. **`web/CONTRACT.md`**). На хосте — только bootstrap web: **`./slgpu help`** и **`./slgpu web up|down|restart|logs|build|install`**. Стек в рантайме — **SQLite** (`stack_params`); стартовый импорт — **`POST /api/v1/app-config/install`** читает **`configs/main.env`** (теперь это **только** шаблон импорта, backend больше не сидит БД автоматически — нажмите «Импорт настроек» в UI). Минимальный bootstrap для `./slgpu web up` — **`configs/bootstrap.env`**. **Страница «Настройки» отсортирована и сгруппирована строго по разделам `configs/main.env` (1..8): «Сеть Docker и compose-проекты», «Web UI», «Пути на хосте», «Образы Docker», «Инференс», «Мониторинг», «Прокси», «Секреты приложения»; внутри группы ключи идут в порядке `main.env` (без алфавитной сортировки).** Незаполненные обязательные параметры подсвечиваются **красным**, в третьей колонке — описание и список сценариев, в которых ключ обязателен (источник — `STACK_KEY_REGISTRY` через `GET /api/v1/app-config/stack` поле `registry`). **6.0.2:** в «Инференс» не дублируются строки для listen внутри контейнеров (**`VLLM_*`/`SGLANG_LISTEN_*`**); задаются только **`LLM_API_BIND`** и хост-порты LLM, внутренние параметры подставляются backend при merge. **5.2.3:** для уже заданных в БД секретов в поле «Значение» показывается маска `••••••••` (с подписью «значение задано в БД (скрыто)»), и такие строки больше не подсвечиваются красным — пустое поле value трактуется как «не менять». **5.2.4:** на странице «Стек мониторинга» отображаются только сервисы стека monitoring (Prometheus, Grafana, Loki, Promtail, DCGM, Node Exporter); карточки **Langfuse** и **LiteLLM Proxy** переехали на страницу «LiteLLM Proxy» (они относятся к compose-стеку **`slgpu-proxy`**, а не к monitoring). **5.2.6:** образ **`docker/Dockerfile.web`** — в репозитории `web/frontend/package-lock.json`, в контейнерной сборке frontend используется **`npm ci`** (вместо `npm install`); на стадии Python включён **кэш pip** (BuildKit `--mount=type=cache,target=/root/.cache/pip`) и убрано дублирование `pip install` — см. [web/README.md](web/README.md) (раздел «Тесты»). **5.2.7:** `native.monitoring.up` / `render_monitoring_configs` — в [`configs/monitoring/promtail/promtail-config.yml.tmpl`](configs/monitoring/promtail/promtail-config.yml.tmpl) путь с regex-группой записан как `$$1` (после рендера в YAML — `$1` для Promtail); сырой `$1` ломал `string.Template` («Invalid placeholder… line 23»). **5.2.8:** [`docker/docker-compose.monitoring.yml`](docker/docker-compose.monitoring.yml) — у **Grafana** убран единый bind всего `provisioning` с `:ro` + отдельный файл `datasource.yml` (у runc: «read-only file system» при nested mount). Вместо этого монтируются только `dashboards` / `alerting` / `plugins` из репо и сгенерированный `datasource.yml` из `WEB_DATA_DIR` (см. [configs/monitoring/README.md](configs/monitoring/README.md), абзац «Grafana: provisioning»). **5.2.9:** в [`configs/main.env`](configs/main.env) по умолчанию **`LANGFUSE_REDIS_IMAGE=redis:8-alpine`** (чтение RDB v12+); при ошибке «Can't handle RDB format version» и предупреждении `vm.overcommit_memory` см. [configs/monitoring/README.md](configs/monitoring/README.md) (раздел про Redis). **5.2.10:** обновлены дефолты **образов мониторинга** в `main.env` (node-exporter **v1.11.1**, DCGM **4.5.2-4.8.1**, `SLGPU_BENCH_CHOWN_IMAGE` — **alpine:3.21.7**). **6.0.0 (MAJOR):** дефолты **Loki 3.7.1**, **Prometheus v3.11.3**, **Grafana 13.0.1**, **Promtail 3.6.10** + новый шаблон **Loki 3** (`loki-config.yaml.tmpl`, TSDB/v13); ломает совместимость с данными **Loki 2** в `LOKI_DATA_DIR` без миграции — см. [configs/monitoring/README.md](configs/monitoring/README.md). Старые host-команды **`./slgpu` `up|pull|monitoring|bench|load|prepare`** **удалены** — вместо них jobs **`native.*`** в **slgpu-web** (см. [`web/CONTRACT.md`](web/CONTRACT.md), [`docs/HISTORY.md`](docs/HISTORY.md)).

Целевая конфигурация при разработке: **8× NVIDIA H200**. **Tensor parallel по умолчанию `TP=8`**: в пресетах в БД и в [`serve.sh`](scripts/serve.sh). GPU-маска — **`NVIDIA_VISIBLE_DEVICES`** в импортированном стеке. Проект рассчитан на один хост без Kubernetes.

Единая **хостовая** точка входа: **`./slgpu web …`** (bash, только Linux VM); остальное — **slgpu-web**.

---

## Содержание

1. [Назначение](#1-назначение)
2. [Архитектура](#2-архитектура)
3. [Сервисы и порты](#3-сервисы-и-порты)
4. [CLI на хосте (только web)](#4-cli-на-хосте-только-web)
5. [Конфигурация](#5-конфигурация)
6. [Переменные окружения (справочник)](#6-переменные-окружения-справочник)
7. [Подготовка хоста](#7-подготовка-хоста)
8. [Быстрый старт](#8-быстрый-старт)
9. [Бенчмарк и отчёт](#9-бенчмарк-и-отчёт)
10. [Длительный нагрузочный тест (`load`)](#10-длительный-нагрузочный-тест-load)
11. [Рецепты 8× H200](#11-рецепты-8-h200)
12. [Мониторинг и безопасность](#12-мониторинг-и-безопасность)
13. [Reasoning / thinking](#13-reasoning--thinking)
14. [Устранение неполадок](#14-устранение-неполадок)
15. [Ограничения](#15-ограничения)
16. [Структура репозитория](#16-структура-репозитория)

---

## 1. Назначение

- Сравнение **vLLM** и **SGLang** на одной модели и одинаковых сценариях нагрузки.
- Локальные веса на хосте (`MODELS_DIR`, по умолчанию **`./data/models`** в корне репо; см. [`data/README.md`](data/README.md)).
- Один движок за раз; **vLLM: порт 8111**, **SGLang: 8222** (по умолчанию на хосте и в контейнере, см. `docker/docker-compose.llm.yml`).
- Пресеты моделей в `data/presets/<slug>.env` — **локально на стенде** (не в git); эталоны — **`examples/presets/`** (`cp examples/presets/*.env data/presets/` после клона). Скачивание весов — задача **`native.model.pull`** в **Web UI** (страница «Модели»), не отдельная host-команда.

---

## 2. Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         Linux host                               │
│  data/models (MODELS_DIR)  ──bind──►  /models (ro) в контейнерах │
└─────────────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   ┌──────────┐         ┌──────────┐
   │  vLLM    │         │ SGLang   │   profiles: vllm | sglang
   │ :8111    │         │ :8222    │
   └────┬─────┘         └────┬─────┘
        └────────┬───────────┘
                 ▼
  **Мониторинг** и **proxy** — **раздельно** из **Develonica.LLM** (`native.monitoring.*` и `native.proxy.*`):
  `docker-compose.monitoring.yml` (Prometheus → Grafana, Loki ← Promtail, …) и
  `docker-compose.proxy.yml` (Langfuse, LiteLLM, Postgres/MinIO/…).
```

Логи контейнеров: **Grafana → Explore → Loki**; данные Loki на диске: `LOKI_DATA_DIR` (см. [configs/monitoring/LOGS.md](configs/monitoring/LOGS.md)).

Переменные для **слотов** передаёт **docker-py** + [`scripts/serve.sh`](scripts/serve.sh) в рантайме. Для **ручного** запуска LLM через `docker/docker-compose.llm.yml` (legacy) снимок env — с **`configs/main.env`** и пресетом. Корневой **`.env`** не дублируйте с пресетом по **`MAX_MODEL_LEN`**, **`GPU_MEM_UTIL`**, парсерам (см. [`docker/README.md`](docker/README.md)).

---

## 3. Сервисы и порты

| Сервис | Образ (файл compose) | Порт / доступ |
|--------|----------------------|---------------|
| **vLLM** | [`VLLM_DOCKER_IMAGE`](examples/presets/) в пресете; fallback в [`docker/docker-compose.llm.yml`](docker/docker-compose.llm.yml): `v0.19.1-cu130` | **8111** на хосте (`LLM_API_PORT`) |
| **SGLang** | `lmsysorg/sglang:latest` в [`docker/docker-compose.llm.yml`](docker/docker-compose.llm.yml) | **8222** (`LLM_API_PORT`, внутри контейнера тот же порт) |
| **Prometheus** | `prom/prometheus:v3.11.3` (`PROMETHEUS_IMAGE` в [`main.env`](main.env)) | **9090** (`PROMETHEUS_BIND`, по умолч. **0.0.0.0**; без auth) |
| **Grafana** | `grafana/grafana:13.0.1` (`GRAFANA_IMAGE` в `main.env`) | **3000** (`GRAFANA_BIND` / `GRAFANA_PORT`) |
| **Loki** | `grafana/loki:3.7.1` (`LOKI_IMAGE`; fallback `SLGPU_LOKI_IMAGE`) | **без публикации наружу** — только внутренняя сеть с Grafana, API `http://loki:3100` |
| **Promtail** | `grafana/promtail:3.6.10` (`PROMTAIL_IMAGE`; fallback `SLGPU_PROMTAIL_IMAGE`) | только сеть; читает `docker.sock` и `/var/lib/docker/containers` на хосте |
| **dcgm-exporter** | `nvidia/dcgm-exporter:4.5.2-4.8.1-ubuntu22.04` (`DCGM_EXPORTER_IMAGE`) | **9400** (`DCGM_BIND`) |
| **node-exporter** | `prom/node-exporter:v1.11.1` (`NODE_EXPORTER_IMAGE`) | **9100** (`NODE_EXPORTER_BIND`) |
| **Langfuse** | `langfuse/langfuse:3` и `langfuse/langfuse-worker:3` ([`docker/docker-compose.proxy.yml`](docker/docker-compose.proxy.yml): Postgres, ClickHouse, Redis, MinIO) | **3001** на хосте (`LANGFUSE_PORT`, **не** 3000 — Grafana) |
| **LiteLLM** | `ghcr.io/berriai/litellm:main-latest` ([`docker/docker-compose.proxy.yml`](docker/docker-compose.proxy.yml)) | Порт: **`LITELLM_PORT`** (хост и внутри контейнера совпадают); vLLM — `host.docker.internal:${LLM_API_PORT}`; **Admin UI** — `http://<хост>:<LITELLM_PORT>/ui`; креды / master key в стеке БД. |

Образ **vLLM** задаётся **в пресете** (семейные теги `*-cu130` и т.д.); остальные сервисы в compose в основном на **`latest`**, **Loki/Promtail** зафиксированы (в шаблоне `main.env` — **3.7.1** / **3.6.10**) — при `docker compose pull` меняется состав чужого **`latest`**. Для продакшена задайте **тег** или **digest** в compose / `main.env` (`GRAFANA_IMAGE` и т.д.; старые `SLGPU_*_IMAGE` читаются как fallback, см. [`main.env`](main.env)).

Базовый URL: порты и хосты **vLLM/SGLang** — из стека и слотов (**Inference** в UI; типичные дефолты в seed — 8111 / 8222).

---

## 4. CLI на хосте (только web)

На Linux VM: **[`./slgpu help`](scripts/cmd_help.sh)** и **[`./slgpu web …`](scripts/cmd_web.sh)** ([`slgpu`](slgpu)). Исполняемый бит: `chmod +x slgpu scripts/cmd_web.sh scripts/cmd_help.sh`.

### Кратко

| Подкоманда | Назначение |
|------------|------------|
| **`help`** | Справка. |
| **`web` `up` / `down` / `restart` / `logs` / `build` / `install`** | Контейнер **slgpu-web** ([`docker/docker-compose.web.yml`](docker/docker-compose.web.yml)). Для compose на хосте: env-файл — **`configs/bootstrap.env`** (`scripts/_lib.sh`). **`install`**: `POST /api/v1/app-config/install` читает **`configs/main.env`** и сидит SQLite. |

Остальное (модели, слоты, мониторинг, proxy, бенч) — **Develonica.LLM**, jobs **`native.*** ([`web/CONTRACT.md`](web/CONTRACT.md)). Бенч и долгий load-прогон — **из UI** (`/bench` и API), на хосте при необходимости — `python scripts/bench_openai.py` / `bench_load.py` вручную. Артефакты: **`data/bench/results/<engine>/<timestamp>/summary.json`**.

---

## 5. Конфигурация

- **Хост, `./slgpu web`:** для `docker compose` на VM используется **минимальный** [`configs/bootstrap.env`](configs/bootstrap.env) (см. `scripts/_lib.sh`). Сам **`configs/main.env`** теперь **только** шаблон для кнопки «Импорт настроек» в UI — backend читает его **только** в обработчике `POST /api/v1/app-config/install`, **не** при старте. Источник правды в рантайме slgpu-web — **SQLite** (`stack_params`, реестр `STACK_KEY_REGISTRY` в `web/backend/.../stack_registry.py`).
- **`data/presets/<preset>.env`** (каталог **`PRESETS_DIR`**, обычно **`./data/presets`**) — модель, образ vLLM, `MAX_MODEL_LEN`, `TP`, парсеры, KV. Импорт в БД — через UI или `install` (см. [web/README.md](web/README.md)).
- **Конфиги мониторинга** (`prometheus.yml`, `loki-config.yaml`, `promtail-config.yml`, `datasource.yml`) хранятся как **`*.tmpl`** и **рендерятся** из БД (`render_monitoring_configs()`) в **`${WEB_DATA_DIR}/.slgpu/monitoring/`** перед `monitoring up/restart` — никаких хардкод-DNS внутри YAML.
- **Контейнеры vLLM/SGLang, мониторинг, proxy** поднимаются **из Develonica.LLM** (jobs `native.*`), не через host-команды. Снимок env для compose: **`${WEB_DATA_DIR}/.slgpu/compose-service.env`** (генерируется из БД, ключи — по **`STACK_KEY_REGISTRY`**, включая имена сервисов / контейнеров / сети — `*_SERVICE_NAME`, `*_CONTAINER_NAME`, `*_INTERNAL_PORT`, `SLGPU_NETWORK_NAME`, `WEB_DOCKER_IMAGE`). Внутри слотов: [`scripts/serve.sh`](scripts/serve.sh) → `/etc/slgpu/serve.sh`.

Справка по формату пресетов: [`configs/models/README.md`](configs/models/README.md).

---

## 6. Переменные окружения (справочник)

| Переменная | Где задаётся | Назначение |
|------------|--------------|------------|
| `HF_TOKEN` | `main.env` (локально) или `export`; для gated HF — **не** в git | `huggingface-cli` / загрузка весов; UI (`native.model.pull`) передаёт токен из стека/настроек |
| `MODELS_DIR`, `LLM_API_BIND`, `PROMETHEUS_DATA_DIR`, `GRAFANA_DATA_DIR`, `LOKI_DATA_DIR`, `PROMTAIL_DATA_DIR`, `LANGFUSE_*_DATA_DIR`, `GRAFANA_BIND`, `GRAFANA_PORT`, `PROMETHEUS_*`, `DCGM_BIND`, `NODE_EXPORTER_BIND` и пр. | **web:** SQLite `stack_params`; **CLI:** [`main.env`](main.env) | Данные на хосте — bind mount, см. [configs/monitoring/README](configs/monitoring/README.md) |
| `LANGFUSE_PORT`, `NEXTAUTH_URL`, `LANGFUSE_BIND`, `NEXTAUTH_SECRET`, `LITELLM_MASTER_KEY`, `LANGFUSE_POSTGRES_*`, `LANGFUSE_REDIS_AUTH`, `MINIO_ROOT_*`, `WEB_COMPOSE_PROJECT_PROXY` и т.д. | **web:** SQLite `stack_params` | Langfuse + Postgres/MinIO + **LiteLLM** — [proxy compose](docker/docker-compose.proxy.yml); **Prometheus/Grafana/Loki** — [monitoring compose](docker/docker-compose.monitoring.yml). **Трейсинг LiteLLM → Langfuse:** `${WEB_DATA_DIR}/secrets/langfuse-litellm.env` (генерируется из БД; см. [configs/monitoring/README](configs/monitoring/README.md), [data/README.md](data/README.md)); **доступ к UI:** `NEXTAUTH_URL`. LiteLLM — [`configs/monitoring/litellm/config.yaml`](configs/monitoring/litellm/config.yaml), модели в **/ui** |
| `VLLM_DOCKER_IMAGE` | пресет [`data/presets/<slug>.env`](examples/presets/) | Семейные теги vLLM (`*-cu130` и т.д.); fallback в [`docker/docker-compose.llm.yml`](docker/docker-compose.llm.yml) |
| `GRAFANA_ADMIN_PASSWORD` | `main.env` (локально) или `export` | Секрет; см. шаблон внизу [`main.env`](main.env) |
| `GF_SERVER_ROOT_URL`, `LLM_API_PORT`, `SLGPU_NVIDIA_VISIBLE_DEVICES` (опц.) | `main.env` или `export` | В [`main.env`](main.env) — закомментированные заготовки |
| `SERVED_MODEL_NAME` | [`main.env`](main.env) | Имя модели в `/v1/models` и в полях `model` (OpenAI); не задано → `MODEL_ID`; **devllm** — фиксированный идентификатор вне смены чекпоинта, см. [`serve.sh`](scripts/serve.sh). Старое: `SLGPU_SERVED_MODEL_NAME` |
| `MODEL_ID`, `MODEL_REVISION`, `VLLM_DOCKER_IMAGE`, `MAX_MODEL_LEN`, `TP`, `GPU_MEM_UTIL`, `KV_CACHE_DTYPE`, `MAX_NUM_BATCHED_TOKENS`, `MAX_NUM_SEQS` (опц., `--max-num-seqs`), `BLOCK_SIZE` (опц., `--block-size`, DeepSeek V4: 256), `ENFORCE_EAGER` (опц., `--enforce-eager`), `DISABLE_CUSTOM_ALL_REDUCE`, `ENABLE_PREFIX_CACHING`, `SGLANG_MEM_FRACTION_STATIC`, `REASONING_PARSER`, `TOOL_CALL_PARSER`, `MM_ENCODER_TP_MODE`, `ATTENTION_BACKEND` (опц.), `TOKENIZER_MODE` (опц., DeepSeek V4), `BENCH_MODEL_NAME`, `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS`, `COMPILATION_CONFIG`, `SPECULATIVE_CONFIG` | пресет + `docker-compose` | Параметры инференса; **каждая** нужная для `serve.sh` переменная должна быть в [`docker/docker-compose.llm.yml`](docker/docker-compose.llm.yml) (см. `ENABLE_PREFIX_CACHING`). Старые имена `SLGPU_*` поддерживаются как fallback. |

---

## 7. Подготовка хоста

Ubuntu/Debian, драйвер **NVIDIA** (рекомендуется ≥ 560 для H200/FP8), **Docker** + **Compose v2**, **NVIDIA Container Toolkit**, достаточный `vm.swappiness` / `ulimit` — по стандартной доке NVIDIA и Docker. Каталог весов: **`MODELS_DIR`** (по умолчанию `data/models`). В v5 **нет** `sudo ./slgpu prepare`; при миграции со старого репо ориентируйтесь на требования к GPU/Docker вручную.

---

## 8. Быстрый старт (v5)

```bash
git clone <repo-url> /opt/slgpu && cd /opt/slgpu
chmod +x slgpu scripts/cmd_web.sh scripts/cmd_help.sh

# Шаблон стека: скопируйте в корень как main.env (для install) и при необходимости отредактируйте
# cp configs/main.env ./main.env

./slgpu web up
./slgpu web install   # POST /api/v1/app-config/install: импорт main.env + пресетов в SQLite
# Откройте UI (WEB_BIND:WEB_PORT, по умолчанию 0.0.0.0:8000) — Модели, Слоты, Мониторинг, LiteLLM
```

- Загрузка весов, слоты, мониторинг, proxy, бенч — **только из UI** (или API `native.*` / `POST /api/v1/...`, см. [web/CONTRACT.md](web/CONTRACT.md)). Для gated HF задайте **`HF_TOKEN`** в стеке/настройках. **Прокси-стек** (`native.proxy.*`): при первом подъёме — bootstrap MinIO/БД LiteLLM; **мониторинг** — отдельно, см. [configs/monitoring/README.md](configs/monitoring/README.md).
- Примеры пресетов: **`examples/presets/`**; рабочие копии — **`data/presets/`** (см. [data/README.md](data/README.md)).

---

## 9. Бенчмарк и отчёт

- В **UI** — раздел **«Бенч»** / API **`/api/v1/bench/...`**: движок и модель подтягиваются из запущенного слота; отчёты в **`data/bench/results/<engine>/<timestamp>/summary.json`**, просмотр в модалке.
- Локально на хосте (без UI): `python3 scripts/bench_openai.py` / `scripts/bench_load.py` — смотрите `--help` и активный порт в **`GET /v1/models`** (слот).

---

## 10. Длительный нагрузочный тест (`load`)

Скрипт **[`scripts/bench_load.py`](scripts/bench_load.py)** (не host-`./slgpu load`) эмулирует **200–300 виртуальных пользователей** и **15–20 мин** steady (см. опции ниже). Строит **ramp-up → steady → ramp-down** и time-series (CSV/JSONL).

### Архитектура нагрузки

| Параметр | Значение по умолчанию | Описание |
|---|---|---|
| `--users` | 250 | Целевое число виртуальных пользователей |
| `--duration` | 900 | Длительность **steady** фазы (сек) |
| `--ramp-up` | 120 | Время разгона до полной нагрузки (сек) |
| `--ramp-down` | 60 | Время снижения нагрузки (сек) |
| `--think-time` | `2000,5000` | Задержка между запросами пользователя (min,max ms) |
| `--max-prompt` | 512 | Макс длина prompt (токенов) |
| `--max-output` | 256 | Макс длина output (токенов) |
| `--report-interval` | 5 | Интервал записи CSV (сек) |

### Артефакты результатов

В `data/bench/results/<engine>/<timestamp>/` создаётся 3 файла:

1. **`summary.json`** — сводка по всему прогону: total_duration_sec, throughput_rps, ttft_p50_ms, error_rate, …
2. **`time_series.csv`** — time-series каждые 5 сек: timestamp, phase, active_users, throughput_rps, ttft_p50_ms, ttft_p95_ms, latency_p50_ms, latency_p95_ms, tokens_per_sec, error_rate.
3. **`users.jsonl`** — по одному JSON на каждого виртуального пользователя: uid, total_requests, ok_requests, err_requests, список всех вызовов с ttft/total_ms.

### Примеры запуска (хост, при поднятом API слота)

```bash
# URL API — из слота / curl к /v1/models; пример:
export OPENAI_BASE_URL=http://127.0.0.1:8111/v1
python3 scripts/bench_load.py --users 250 --duration 900
```

### Советы

- Сначала короткий **`bench_openai`**, затем `bench_load` при устойчивой работе.
- При росте `error_rate` — снижайте `--users` или `--max-output`.
- `time_series.csv` — в Grafana (CSV datasource) или вручную.

---

## 11. Рецепты 8× H200

Ориентир: **8× H200** (~141 GiB × 8). В шаблонах репо **`TP=8`**; при меньшем числе GPU — правьте пресет. **`gpu-mem`**, батч, контекст и парсеры — **в** `data/presets/<preset>.env` (см. [`examples/presets/`](examples/presets/)). В v5: **загрузите веса и поднимите слот** в **UI** (модель/пресет, `native.model.pull` / `native.slot.*`).

- **Qwen3.6-35B-A3B** — `qwen3.6-35b-a3b` (см. `examples/presets/qwen3.6-35b-a3b.env`).
- **Kimi K2.6** — `kimi-k2.6` и др. по **examples/presets/**.
- **MiniMax-M2.7**, **GLM-5.1** — соседние `.env` и [рецепты vLLM](https://github.com/vllm-project/recipes).
- **gpt-oss-120b** — пресет по образцу соседей, полный HF id в `model`.

**Замечания:** **Qwen3.6** — KV, см. [§14](#14-устранение-неполадок). **MoE** — часто **TP=8** или другой чекпоинт. **MiniMax** — [рецепт](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md) (**TP4** + EP). **GLM-5.1** — при OOM смотрите **glm-5.1-fp8**.

---

## 12. Мониторинг и безопасность

- **Стек мониторинга** (Prometheus / Grafana / Loki / …) — **`native.monitoring.*`**, страница **Мониторинг**; **прокси** (Langfuse + LiteLLM) — **`native.proxy.*`**, страница **LiteLLM Proxy** — независимые compose-файлы. На хосте: [`docker/docker-compose.monitoring.yml`](docker/docker-compose.monitoring.yml) и [`docker/docker-compose.proxy.yml`](docker/docker-compose.proxy.yml). Скрейп: [`configs/monitoring/prometheus/prometheus.yml`](configs/monitoring/prometheus/prometheus.yml). **Langfuse** + **LiteLLM** — [`configs/monitoring/README.md`](configs/monitoring/README.md) (`LANGFUSE_PORT` по умолч. 3001, `LITELLM_PORT`); **имя модели** в LiteLLM — как в **/ui** / **`SERVED_MODEL_NAME`**. Секреты — в `stack_params`, не в git.
- **Grafana** (`127.0.0.1:3000`), дашборды: в [`configs/monitoring/grafana/provisioning/dashboards/json/`](configs/monitoring/grafana/provisioning/dashboards/json/) лежат JSON с provisioning (Prometheus, uid `prometheus`): краткий **SGLang** (`sglang-dashboard-slgpu.json`), расширенный **SGLang по мотивам vLLM V2** (`sglangdash2-slgpu.json`, сборка из [`templates/vllmdash2.json`](configs/monitoring/grafana/templates/vllmdash2.json) скриптом `_build_sglangdash2.py`), плюс эталон **vLLM** для ручного импорта — тот же [`vllmdash2.json`](configs/monitoring/grafana/templates/vllmdash2.json) (вне provisioning, см. [`templates/README.md`](configs/monitoring/grafana/templates/README.md)). Подробности, переменные `instance` / `model_name` и типичные сбои — в [`configs/monitoring/README.md`](configs/monitoring/README.md). **Логи контейнеров:** datasource **Loki** (uid `loki`) — **Explore → Loki**; хранение на диске, см. `LOKI_DATA_DIR` / [configs/monitoring/LOGS.md](configs/monitoring/LOGS.md).
- Сырые логи: **`docker compose -f docker/docker-compose.llm.yml logs -f vllm`**; **`docker compose -f docker/docker-compose.monitoring.yml logs -f prometheus`**; при необходимости — **`docker compose -f docker/docker-compose.proxy.yml logs`**. Ротация **json-file** (100 MiB × 5) в compose-файлах.

**Безопасность:** смените пароль Grafana; не коммитьте `main.env` с реальными секретами в публичный репозиторий.

---

## 13. Reasoning / thinking

- vLLM: `--reasoning-parser` и `--tool-call-parser` из пресета (см. [`scripts/serve.sh`](scripts/serve.sh) → `slgpu_run_vllm`).
- SGLang: `--reasoning-parser` из пресета ([`scripts/serve.sh`](scripts/serve.sh) → `slgpu_run_sglang`).

Пример Qwen3 (подставьте `model` из `/v1/models`):

```bash
curl -s http://127.0.0.1:8111/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "Qwen/Qwen3-30B-A3B",
    "messages": [{"role":"user","content":"Сколько будет 17*23?"}],
    "chat_template_kwargs": {"enable_thinking": true},
    "max_tokens": 1024
  }' | jq '.choices[0].message'
```

---

## 14. Устранение неполадок

| Симптом | Что сделать |
|---------|-------------|
| **Qwen3 Next / Qwen3.6:** assert / `fp8_e5m2` | В пресете: `KV_CACHE_DTYPE=fp8_e4m3` или `fp8`, пересоздать контейнер |
| **DeepSeek V4 (Pro/Flash, vLLM):** `DeepseekV4 only supports fp8 kv-cache… got auto` | `KV_CACHE_DTYPE=fp8` или `fp8_e4m3` (пресеты [`deepseek-v4-pro.env`](examples/presets/deepseek-v4-pro.env) / [`deepseek-v4-flash.env`](examples/presets/deepseek-v4-flash.env)), не `auto` |
| **DeepSeek V4 (vLLM):** INFO `Using DeepSeek's fp8_ds_mla KV cache` | Нормально: так задумано по умолчанию. «Стандартный» fp8 KV — при необходимости задать `ATTENTION_BACKEND=FLASHINFER_MLA_SPARSE` в пресете/[`main.env`](main.env), пересоздать контейнер; иначе не трогать |
| **DeepSeek V4 (vLLM):** пустой ответ / «тишина», 200 OK | Пресет: `REASONING_PARSER=deepseek_v4`, `TOOL_CALL_PARSER=deepseek_v4`, `TOKENIZER_MODE=deepseek_v4` (см. [блог vLLM](https://vllm.ai/blog/deepseek-v4)); **`deepseek_r1`** — для R1, не для V4. Проверьте `max_tokens` и поля `reasoning_content` в JSON |
| **vLLM V1:** `ValueError: … KV cache is needed, which is larger than the available KV cache memory` (при большом `max_model_len`) | **Поднять `GPU_MEM_UTIL`** (пресеты [DeepSeek-V4-Pro/Flash](examples/presets/deepseek-v4-pro.env) — **0.94** при 256K; в логе при `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1` — **~0.9033**). В логе всё ещё **0.88** — проверьте импорт стека/пресета в SQLite и **пересоздайте слот** из UI, не «голый» `docker compose` в обход. Либо **снизить `MAX_MODEL_LEN`**. [Док. vLLM: память](https://docs.vllm.ai/en/latest/configuration/conserving_memory/) |
| **vLLM (DeepSeek V4 Flash):** стек `flashinfer` / `torch.cuda` / `KeyboardInterrupt: terminated` при старте API | Не убивать контейнер на первом долгом шаге (импорт FlashInfer, `_set_compile_ranges`). **Снизить `MAX_MODEL_LEN`** (пресет [deepseek-v4-flash.env](examples/presets/deepseek-v4-flash.env) — **262144** вместо 384K+). С Pro: `GPU_MEM_UTIL=0.94`, `--block-size` / `compilation_config` в пресете |
| **vLLM / torch.compile:** `Compiling model again… mhc_pre` / `'_OpNamespace' 'vllm' object has no attribute 'mhc_pre'` | Смена/обновление образа vLLM при старом **AOT** в `~/.cache/vllm/torch_compile_cache`: в контейнере **удалить кэш** (например `rm -rf /root/.cache/vllm/torch_compile_cache`) и перезапустить; либо одноразовый пустой volume вместо сохранения кэша между образами |
| **vLLM (DeepSeek V4+):** `torch._inductor... InductorError` / `replace_by_example` / `profile_run` / `determine_available_memory` | В [deepseek-v4-flash.env](examples/presets/deepseek-v4-flash.env) по умолчанию **`ENFORCE_EAGER=1`** → `--enforce-eager` (без custom `compilation_config` Inductor всё равно может падать). Иначе: **убрать** жёсткий `COMPILATION_CONFIG` / задать **`ENFORCE_EAGER=1`** в [`main.env`](main.env) |
| **vLLM:** много параллельных запросов, в логе `Waiting: N`, `Running: 0`, мало KV | Главное — **уменьшить `MAX_MODEL_LEN`** до реального потолка диалога (например 64k–128k вместо 384k): иначе под длинное окно уходит KV и **одновременных** сессий почти нет. Дополнительно: **`GPU_MEM_UTIL`**, **`MAX_NUM_BATCHED_TOKENS`**, опционально **`MAX_NUM_SEQS`** (после снижения контекста; при OOM — меньше). Рецепт **data-parallel** для V4 — в [блоге/рецептах vLLM](https://vllm.ai/blog/deepseek-v4). Горизонтально: несколько реплик + балансировщик |
| **MiniMax-M2.7 (vLLM):** нельзя только **TP8**; ошибки распределения / рекомендации vLLM | [Рецепт](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md): **TP4**; на 8×GPU — **`ENABLE_EXPERT_PARALLEL=1`**, `TP=4`, маска **всех** GPU в **`NVIDIA_VISIBLE_DEVICES`** (см. [`minimax-m2.7.env`](examples/presets/minimax-m2.7.env)); образ в пресете — **`minimax27-…-cu130`**, **`COMPILATION_CONFIG`** с `fuse_minimax_qk_norm` |
| **GLM-5.1 (vLLM):** `No valid attention backend` / `FLASHMLA_SPARSE: [kv_cache_dtype not supported]` | `KV_CACHE_DTYPE=auto` (в пресете [`data/presets/glm-5.1.env`](examples/presets/glm-5.1.env)); не `fp8_e4m3` для sparse MLA+KV |
| **GLM-5.1 (bf16):** `OutOfMemoryError` / `SharedFusedMoE` / `unquantized_fused_moe` при `load_model` | Снизить **`GPU_MEM_UTIL`** (в пресете **0.75**; при повторе — **0.72–0.70**) — vLLM резервирует меньше под KV, больше остаётся под веса. Плюс **`MAX_MODEL_LEN`**, **`MAX_NUM_BATCHED_TOKENS`**, **`ENABLE_PREFIX_CACHING=0`**. Предпочтительно: чекпоинт **FP8** — пресет [`glm-5.1-fp8`](examples/presets/glm-5.1-fp8.env) (**`VLLM_DOCKER_IMAGE`** с **glm51** — там же), см. [GLM/GLM5.md](https://github.com/vllm-project/recipes/blob/main/GLM/GLM5.md). Если в логе prefix cache `True` при `0` в пресете — в **`docker/docker-compose.llm.yml`** у vLLM должен быть **`ENABLE_PREFIX_CACHING`**. Дальше: **больше GPU** (`TP`). |
| **`ContextOverflowError`** | Увеличить `MAX_MODEL_LEN` или уменьшить `max_tokens` |
| **OOM при старте** | Снизить `MAX_MODEL_LEN`, `GPU_MEM_UTIL`, `SGLANG_MEM_FRACTION_STATIC`, увеличить `TP`, квантованный чекпоинт |
| **OOM MoE при загрузке весов** | Часто не спасает только снижение контекста; **TP=8**, другой чекпоинт HF или квант |
| **vLLM:** `WorkerProc initialization failed` | Ищите `CUDA OOM` выше в логе; см. [`scripts/serve.sh`](scripts/serve.sh), [`main.env`](main.env) |
| **vLLM:** `custom_all_reduce.cuh` / `invalid argument` при старте | Дефолт **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=1`** (NCCL). Не задавайте `0` в пресете, пока custom all-reduce стабилен на вашем образе/модели. |
| **404 model `gpt-oss-120b`** | Используйте **`openai/gpt-oss-120b`** как в `/v1/models` |
| **Hermes2ProToolParser / `token_ids` (gpt-oss)** | `TOOL_CALL_PARSER=openai` в пресете |

---

## 15. Ограничения

- В пресетах vLLM задайте тег/дижест через **`VLLM_DOCKER_IMAGE`** (в compose — fallback, по умолчанию `v0.19.1-cu130`); **Loki** и **Promtail** в [`docker/docker-compose.monitoring.yml`](docker/docker-compose.monitoring.yml) берут теги из **`LOKI_IMAGE`** / **`PROMTAIL_IMAGE`** (в шаблоне `main.env` — Loki **3.7.1**, Promtail **3.6.10**); **Langfuse 3** и **LiteLLM** — в основном **`:3` / `main-*`**; **SGLang** / **MinIO** в примерах часто с **`latest`** — в проде зафиксируйте **тег** или **digest** в `main.env` (Prometheus, Grafana, node-exporter, dcgm-exporter — см. тот же файл).
- **Langfuse** (Postgres, MinIO, секреты `NEXTAUTH_*` / `LANGFUSE_ENCRYPTION_KEY`) — для **прод** смените пароли и `NEXTAUTH_URL`; данные в **`LANGFUSE_*_DATA_DIR`**. Права на тома — UI: «Стек мониторинга» → «Чинить права» (`native.monitoring.fix-perms`); см. [configs/monitoring/README](configs/monitoring/README.md). **LiteLLM** — при поднятом инференсе; в **/ui** задайте тот же **`model`**, что отдаёт API (**`SERVED_MODEL_NAME`**, `GET /v1/models`).
- SGLang может не знать те же `--reasoning-parser`, что vLLM.
- Сервисы LLM используют **`gpus: all`**, а реальная маска GPU — **`NVIDIA_VISIBLE_DEVICES`**: **первые `TP` карт** (`0`…`TP-1`) задаёт **слот/пресет** в UI. На хосте с **4** GPU — **`TP=4`** в пресете; маппинг вручную — **`SLGPU_NVIDIA_VISIBLE_DEVICES`** в стеке / `export`.

---

## 16. Структура репозитория

**`docs/`** и **`grace/`** в репозитории есть (см. [`.gitignore`](.gitignore) за исключениями). **`.cursor/`** / **`.kilo/`** — локальные; в **remote** часто нет. Корневые [`AGENTS.md`](AGENTS.md) и [`HISTORY.md`](HISTORY.md) — краткие указатели; полная карта — **`docs/AGENTS.md`**, журнал — **`docs/HISTORY.md`**.

```
slgpu/
├── slgpu                       # диспетчер: help + web
├── VERSION                     # SemVer
├── AGENTS.md
├── docker/
│   ├── README.md
│   ├── docker-compose.monitoring.yml
│   ├── docker-compose.proxy.yml
│   ├── Dockerfile.web
│   └── docker-compose.web.yml
├── README.md
├── docs/
│   ├── AGENTS.md
│   └── HISTORY.md
├── configs/
│   ├── bootstrap.env           # минимум для ./slgpu web up (--env-file)
│   ├── main.env                # шаблон импорта в UI (POST /app-config/install)
│   ├── models/README.md
│   └── monitoring/             # *.tmpl → рендер в WEB_DATA_DIR/.slgpu/monitoring/
├── data/                       # см. data/README.md
├── scripts/
│   ├── serve.sh                    # entrypoint LLM-слота (vLLM / SGLang)
│   ├── _lib.sh                     # bash helpers для cmd_web.sh
│   ├── cmd_web.sh, cmd_help.sh     # подкоманды диспетчера ./slgpu
│   ├── bench_openai.py, bench_load.py  # native.bench.scenario / .load
│   ├── check-stack-guards.sh, test_web.sh  # local guards / pytest+tsc
├── grace/                      # GRACE (требования, план, верификация, граф)
└── web/                        # Develonica.LLM: FastAPI + Vite
```

> **Develonica.LLM** — управление стеком, слотами, `native.*` jobs, SQLite; хост: только **`./slgpu web`**. Контракт — [`web/CONTRACT.md`](web/CONTRACT.md), подробности — [`web/README.md`](web/README.md).

---

## Лицензии образов

`vllm/vllm-openai`, `lmsysorg/sglang`, `prom/prometheus`, `prom/node-exporter`, `grafana/grafana`, `grafana/loki`, `grafana/promtail`, `ghcr.io/berriai/litellm`, `langfuse/langfuse` / `langfuse/langfuse-worker`, `postgres`, `clickhouse/clickhouse-server`, `minio/minio`, `redis`, `nvidia/dcgm-exporter` — см. лицензии поставщиков; веса на Hugging Face — отдельные лицензии репозиториев.
