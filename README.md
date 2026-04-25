# slgpu

Репозиторий **стенда для сравнения LLM-инференса** на Linux-сервере с GPU: два движка (**vLLM** и **SGLang**) в Docker, общий локальный кэш моделей, OpenAI-совместимый HTTP API, нагрузочный бенчмарк, **Prometheus + Grafana Loki (логи) + Promtail + Langfuse (трейсинг) + LiteLLM Proxy (шлюз) + NVIDIA DCGM Exporter** (см. [§3](#3-сервисы-и-порты), [`monitoring/README.md`](monitoring/README.md)).

Целевая конфигурация при разработке: **8× NVIDIA H200**. **Tensor parallel по умолчанию `TP=8`**: в пресетах [`configs/models/*.env`](configs/models/) и в [`serve.sh`](scripts/serve.sh) при отсутствии переменной. При [`./slgpu up`](scripts/cmd_up.sh) в контейнеры выставляется **`NVIDIA_VISIBLE_DEVICES=0,1,…,TP-1`**, так что число видимых GPU согласовано с `TP` (ручной список в `docker-compose` не нужен; нестандартная нумерация — `SLGPU_NVIDIA_VISIBLE_DEVICES` в `main.env` или `export`). Проект рассчитан на один хост без Kubernetes.

Единая точка входа: **`./slgpu`** (bash, только Linux VM).

---

## Содержание

1. [Назначение](#1-назначение)
2. [Архитектура](#2-архитектура)
3. [Сервисы и порты](#3-сервисы-и-порты)
4. [CLI `./slgpu`](#4-cli-slgpu)
5. [Конфигурация: `main.env` и пресеты](#5-конфигурация)
6. [Переменные окружения (справочник)](#6-переменные-окружения)
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
- Локальные веса на хосте (`MODELS_DIR`, по умолчанию `/opt/models`).
- Один движок за раз; **vLLM: порт 8111**, **SGLang: 8222** (по умолчанию на хосте и в контейнере, см. `docker-compose.yml`).
- Пресеты моделей в `configs/models/<slug>.env` — **создаются вручную** (или берутся из репозитория); **`./slgpu pull`** только скачивает веса.

---

## 2. Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         Linux host                               │
│  /opt/models  ──bind mount──►  /models (ro) в контейнерах        │
└─────────────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   ┌──────────┐         ┌──────────┐
   │  vLLM    │         │ SGLang   │   profiles: vllm | sglang
   │ :8111    │         │ :8222    │
   └────┬─────┘         └────┬─────┘
        └────────┬───────────┘
                 ▼
  отдельный compose: `docker-compose.monitoring.yml` (`./slgpu monitoring up`)
         Prometheus :9090 → Grafana :3000
         Loki (3100, только сеть) ← Promtail (docker + /var/lib/docker/containers)
                 ▲
         dcgm-exporter :9400 · node-exporter :9100
```

Логи контейнеров: **Grafana → Explore → Loki**; данные Loki на диске: `LOKI_DATA_DIR` (см. [monitoring/LOGS.md](monitoring/LOGS.md)).

Переменные модели передаются в контейнер через блок **`environment`** в `docker-compose.yml` и значения, экспортированные в shell командой **`./slgpu up`** (после слияния [`main.env`](main.env) + пресет).

---

## 3. Сервисы и порты

| Сервис | Образ (файл compose) | Порт / доступ |
|--------|----------------------|---------------|
| **vLLM** | [`VLLM_DOCKER_IMAGE`](configs/models/) в пресете; fallback в [`docker-compose.yml`](docker-compose.yml): `v0.19.1-cu130` | **8111** на хосте (`LLM_API_PORT`) |
| **SGLang** | `lmsysorg/sglang:latest` в [`docker-compose.yml`](docker-compose.yml) | **8222** (`LLM_API_PORT`, внутри контейнера тот же порт) |
| **Prometheus** | `prom/prometheus:latest` ([`docker-compose.monitoring.yml`](docker-compose.monitoring.yml)) | **9090** (`PROMETHEUS_BIND`, по умолч. **0.0.0.0**; без auth) |
| **Grafana** | `grafana/grafana:latest` (тот же файл) | **3000** (`GRAFANA_BIND` / `GRAFANA_PORT`) |
| **Loki** | `grafana/loki:2.9.8` (переменная `SLGPU_LOKI_IMAGE` в main.env) | **без публикации наружу** — только внутренняя сеть с Grafana, API `http://loki:3100` |
| **Promtail** | `grafana/promtail:2.9.8` (`SLGPU_PROMTAIL_IMAGE`) | только сеть; читает `docker.sock` и `/var/lib/docker/containers` на хосте |
| **dcgm-exporter** | `nvidia/dcgm-exporter:latest` | **9400** (`DCGM_BIND`) |
| **node-exporter** | `prom/node-exporter:latest` | **9100** (`NODE_EXPORTER_BIND`) |
| **Langfuse** | `langfuse/langfuse:3` и `langfuse/langfuse-worker:3` (Postgres, ClickHouse, Redis, MinIO) | **3001** на хосте (`LANGFUSE_PORT`, **не** 3000 — Grafana) |
| **LiteLLM** | `ghcr.io/berriai/litellm:main-latest` (или `SLGPU_LITELLM_IMAGE`) | **4000** (`LITELLM_PORT`); vLLM — `host.docker.internal:${LLM_API_PORT}`; **Admin UI** — `http://<хост>:4000/ui`, **`UI_USERNAME` / `UI_PASSWORD`** в `main.env`; **`x-api-key`** — если задан **`LITELLM_MASTER_KEY`** (пусто = без ключа, только в закрытой сети) |

Образ **vLLM** задаётся **в пресете** (семейные теги `*-cu130` и т.д.); остальные сервисы в compose в основном на **`latest`**, **Loki/Promtail** зафиксированы **2.9.8** — при `docker compose pull` меняется состав `latest`. Для продакшена задайте **тег** или **digest** в compose / `main.env` (`SLGPU_*_IMAGE`, см. комментарии в [`main.env`](main.env)).

Базовый URL API: vLLM `http://<host>:8111/v1`, SGLang `http://<host>:8222/v1` (по умолчанию; `-p` в `./slgpu up` меняет порт на хосте).

---

## 4. CLI `./slgpu`

Точка входа для жизненного цикла стенда: подготовка ОС, загрузка весов, запуск движка в Docker, бенчмарки. Логи и проверка API — через **`docker compose`** и **`curl`** (см. [§9](#9-бенчмарк-и-отчёт), [§12](#12-мониторинг-и-безопасность)). Команды реализованы в [`scripts/cmd_*.sh`](scripts/) и вызываются через корневой скрипт [`slgpu`](slgpu). В репозитории для `slgpu` и `cmd_*.sh` уже выставлен исполняемый бит; при необходимости на VM: `chmod +x slgpu scripts/cmd_*.sh`.

### Шпаргалка синтаксиса

```text
./slgpu help
./slgpu prepare [1–6]
./slgpu pull <HF_ID|preset> [опции]
./slgpu up [<vllm|sglang>] [-m <preset>] [-p <порт>] [--tp <N>]   # без арг. — интерактив (TTY)
./slgpu down [--all]
./slgpu restart -m <preset> [--tp <N>]
./slgpu bench [vllm|sglang] [-m <preset>]
./slgpu load [vllm|sglang] [-m <preset>] [опции]
```

### Назначение команд

| Команда | Назначение |
|---------|------------|
| **`help`** | Краткая справка по всем подкомандам и примерам вызова (то же, что и `./slgpu` без аргументов с подсказкой). |
| **`prepare`** | **Один раз при создании ВМ** (или после переустановки ОС): проверка драйвера NVIDIA, установка Docker и Compose v2, NVIDIA Container Toolkit, при желании persistence mode GPU, создание каталога `MODELS_DIR`, sysctl (`vm.swappiness`), лимиты `nofile`, напоминание про firewall. Запуск от root: `sudo ./slgpu prepare` или шаг `sudo ./slgpu prepare 1` … `6`; выборочно: `STEPS=2,4 sudo -E ./slgpu prepare`. |
| **`pull`** | **Скачивание весов** в `${MODELS_DIR}/<MODEL_ID>` через `hf download`. **Файл пресета не создаётся.** Аргумент **с `/`** — HF id: если есть `configs/models/<slug>.env` (slug из имени репо), подхватывается `MODEL_ID` и т.д.; если пресета **нет** — скачивание только по HF id, для `./slgpu up` заведите `configs/models/<slug>.env`. Аргумент **без `/`** — имя существующего пресета. Опция **`--revision`**: пин ревизии (переопределяет `MODEL_REVISION` при загрузке с пресетом). Токен: [`configs/secrets/hf.env`](configs/secrets/hf.env) (`HF_TOKEN`). |
| **`up`** | **Запуск движка**: останавливает и удаляет контейнеры другого движка (vllm/sglang), поднимает **один** выбранный профиль — `vllm` или `sglang` (см. `./slgpu up -h`) с **`-m <preset>`** (в неинтерактивном вызове). **`./slgpu up` без аргументов** при **TTY** сначала предлагает выбрать движок, затем пресет из `configs/models/*.env`; **без TTY** укажите `vllm`/`sglang` и **`-m`** явно. Мониторинг (Prometheus, Grafana) **отдельно**: **`./slgpu monitoring up`** (один раз на хост). **Не ждёт** `GET /v1/models` — `curl` вручную. |
| **`monitoring`** | **`up` / `down` / `restart` / `fix-perms`**: стек в [`docker-compose.monitoring.yml`](docker-compose.monitoring.yml); **`fix-perms`** — chown каталогов `PROMETHEUS_DATA_DIR`, `GRAFANA_DATA_DIR`, `LOKI_DATA_DIR`, `PROMTAIL_DATA_DIR` по uid:gid из образов (см. [monitoring/README](monitoring/README.md)). |
| **`down`** | **Остановка инференса**: по умолчанию — **только** `vllm` и `sglang`. С флагом **`--all`** — ещё и стек мониторинга. Тома метрик/дашбордов не удаляются. |
| **`restart`** | **Перезапуск с новым пресетом без смены движка**: определяет, какой сервис сейчас в статусе *running* (`vllm` или `sglang`), и выполняет для него ту же последовательность, что и `up`, с новым **`-m <preset>`**; опционально **`--tp`**, как у `up`. Если ни один LLM-контейнер не запущен — сообщение об ошибке; тогда используйте `up`. |
| **`bench`** | **Нагрузочный тест** против уже поднятого API (порт vLLM 8111 / SGLang 8222 по умолчанию, см. `docker compose -f docker-compose.yml port`): запускает [`scripts/bench_openai.py`](scripts/bench_openai.py). Модель и engine **автоматически определяются** из запущенного API (`/v1/models`) и docker compose. Пресет **`-m`** опционален — используется только для `MAX_MODEL_LEN` и `BENCH_MODEL_NAME`, если указан. Пишет артефакты в `bench/results/<engine>/<timestamp>/`. |
| **`load`** | **Длительный нагрузочный тест** (15–20 мин, 200–300 виртуальных пользователей): запускает [`scripts/bench_load.py`](scripts/bench_load.py). Модель и engine **автоматически определяются** из запущенного API. Эмулирует фазы ramp-up → steady → ramp-down, собирает time-series метрики (throughput, TTFT, latency, error rate) в CSV каждые 5 сек. Артефакты: `summary.json`, `time_series.csv`, `users.jsonl`. Опции: `--users`, `--duration`, `--ramp-up`, `--ramp-down`, `--think-time`, `--max-prompt`, `--max-output`, `--report-interval`, `--burst` (макс throughput без пауз). |
Подробности по флагам **`pull`**: см. `./slgpu pull -h` и [`configs/models/README.md`](configs/models/README.md). Результаты бенчей: **`bench/results/<engine>/<timestamp>/summary.json`**. Пример разборов — [`bench/report.md`](bench/report.md) (вручную, не генерируется репо). Логи: **`docker compose -f docker-compose.yml logs -f vllm`**; мониторинг: **`./slgpu monitoring up`**, логи — `-f docker-compose.monitoring.yml`. Диагностика: **`docker compose ps`**, **`curl`**, **`nvidia-smi`**.

---

## 5. Конфигурация

- **[`main.env`](main.env)** — **дефолты хоста и движка** (пути, `MODELS_DIR`, `MAX_MODEL_LEN`, `TP`, NCCL, мониторинг, …); **образ vLLM** — в пресете (`VLLM_DOCKER_IMAGE`); **имя в OpenAI API** — **`SLGPU_SERVED_MODEL_NAME`** (по умолч. в репо **`devllm`**, иначе в ответах был бы полный `MODEL_ID`); секреты и редкие per-host поля — в комментариях-заготовках внизу файла или через `export` (см. шапку `main.env`).
- **`configs/models/<preset>.env`** — модель: `MODEL_ID`, **`VLLM_DOCKER_IMAGE`**, `MAX_MODEL_LEN`, **`TP`** (в шаблонах репозитория **8**; на 4 GPU — **4**), парсеры, KV и т.д. Для **`bench` / `restart`** — флаг **`-m`** обязателен. Для **`up`** пресет задаётся через **`-m`** **или** интерактивным выбором при **`./slgpu up`** без аргументов (TTY).
- Все **дефолты движка** (listen vLLM/SGLang, `VLLM_LOGGING_LEVEL`, **Triton/TorchInductor** для SGLang, NCCL, и т.д.) — в [`main.env`](main.env); в контейнер — **`env_file: main.env`** в [`docker-compose.yml`](docker-compose.yml) (движок) и в [`docker-compose.monitoring.yml`](docker-compose.monitoring.yml). Сырой `docker compose`: **`docker compose -f docker-compose.yml --env-file main.env`**, для мониторинга — **`-f docker-compose.monitoring.yml`**. См. [`./slgpu monitoring -h`](scripts/cmd_monitoring.sh).
- **CLI движка**: единый [`scripts/serve.sh`](scripts/serve.sh) (`SLGPU_ENGINE=vllm|sglang` задаёт `docker-compose`; в контейнере — `/etc/slgpu/serve.sh`).

Справка по парсерам: [`configs/models/README.md`](configs/models/README.md).

---

## 6. Переменные окружения (справочник)

| Переменная | Где задаётся | Назначение |
|------------|--------------|------------|
| `HF_TOKEN` | [`configs/secrets/hf.env`](configs/secrets/hf.env) | Только для `./slgpu pull` |
| `MODELS_DIR`, `LLM_API_BIND`, `PROMETHEUS_DATA_DIR`, `GRAFANA_DATA_DIR`, `LOKI_DATA_DIR`, `PROMTAIL_DATA_DIR`, `LANGFUSE_*_DATA_DIR` (Postgres/ClickHouse/MinIO/Redis), `GRAFANA_BIND`, `GRAFANA_PORT`, `GRAFANA_ADMIN_USER`, `PROMETHEUS_*`, `DCGM_BIND`, `NODE_EXPORTER_BIND` и пр. | [`main.env`](main.env) | Дефолты в репозитории; данные на хосте — bind mount, см. [monitoring/README](monitoring/README.md) |
| `LANGFUSE_PORT`, `NEXTAUTH_URL`, `LANGFUSE_BIND`, `NEXTAUTH_SECRET`, `LITELLM_MASTER_KEY`, `LANGFUSE_POSTGRES_*`, `LANGFUSE_REDIS_AUTH`, `MINIO_ROOT_*` и т.д. | [`main.env`](main.env) | Langfuse + LiteLLM в [monitoring compose](docker-compose.monitoring.yml); **трейсинг LiteLLM → Langfuse:** [`configs/secrets/langfuse-litellm.env`](configs/secrets/langfuse-litellm.env.example) (не в git); **доступ к UI извне:** `NEXTAUTH_URL` (см. [monitoring/README](monitoring/README.md)); LiteLLM — глоб. настройки в [`monitoring/litellm/config.yaml`](monitoring/litellm/config.yaml), модели в **/ui** |
| `VLLM_DOCKER_IMAGE` | пресет [`configs/models/<slug>.env`](configs/models/) | Семейные теги vLLM (`*-cu130` и т.д.); fallback в [`docker-compose.yml`](docker-compose.yml) |
| `GRAFANA_ADMIN_PASSWORD` | `main.env` (локально) или `export` | Секрет; см. шаблон внизу [`main.env`](main.env) |
| `GF_SERVER_ROOT_URL`, `LLM_API_PORT`, `SLGPU_NVIDIA_VISIBLE_DEVICES` (опц.) | `main.env` или `export` | В [`main.env`](main.env) — закомментированные заготовки |
| `SLGPU_SERVED_MODEL_NAME` | [`main.env`](main.env) | Имя модели в `/v1/models` и в полях `model` (OpenAI); не задано → `MODEL_ID`; **devllm** — фиксированный идентификатор вне смены чекпоинта, см. [`serve.sh`](scripts/serve.sh) |
| `MODEL_ID`, `MODEL_REVISION`, `VLLM_DOCKER_IMAGE`, `MAX_MODEL_LEN`, `TP`, `GPU_MEM_UTIL`, `KV_CACHE_DTYPE`, `SLGPU_MAX_NUM_BATCHED_TOKENS`, `SLGPU_VLLM_MAX_NUM_SEQS` (опц., `--max-num-seqs`), `SLGPU_VLLM_BLOCK_SIZE` (опц., `--block-size`, DeepSeek V4: 256), `SLGPU_DISABLE_CUSTOM_ALL_REDUCE`, `SLGPU_ENABLE_PREFIX_CACHING`, `SGLANG_MEM_FRACTION_STATIC`, `REASONING_PARSER`, `TOOL_CALL_PARSER`, `MM_ENCODER_TP_MODE`, `SLGPU_VLLM_ATTENTION_BACKEND` (опц.), `SLGPU_VLLM_TOKENIZER_MODE` (опц., DeepSeek V4), `BENCH_MODEL_NAME`, `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS`, `SLGPU_VLLM_COMPILATION_CONFIG`, `SLGPU_VLLM_SPECULATIVE_CONFIG` | пресет + `docker-compose` | Параметры инференса; **каждая** нужная для `serve.sh` переменная должна быть в [`docker-compose.yml`](docker-compose.yml) (см. `SLGPU_ENABLE_PREFIX_CACHING`). |

---

## 7. Подготовка хоста

Ubuntu/Debian, драйвер NVIDIA (рекомендуется ≥ 560 для H200/FP8).

```bash
sudo ./slgpu prepare              # шаги 1–6
sudo ./slgpu prepare 1            # только проверка драйвера
sudo STEPS=2,4 ./slgpu prepare
```

Docker, Compose v2, NVIDIA Container Toolkit, каталог `MODELS_DIR`, sysctl, limits — см. реализацию [`scripts/cmd_prepare.sh`](scripts/cmd_prepare.sh).

---

## 8. Быстрый старт

```bash
git clone <repo-url> /opt/slgpu && cd /opt/slgpu

# Опционально: при необходимости — пароль Grafana и т.д. (см. шапку main.env)
# Опционально для gated моделей:
# cp configs/secrets/hf.env.example configs/secrets/hf.env

pip install -U "huggingface_hub[cli]"

./slgpu pull Qwen/Qwen3.6-35B-A3B   # пресет qwen3.6-35b-a3b.env есть в репо — pull подхватит MODEL_ID
./slgpu up vllm -m qwen3.6-35b-a3b

curl -s http://127.0.0.1:8111/v1/models
```

Полный стек мониторинга и логов (Prometheus, Grafana, Loki, Promtail): сначала **`sudo ./slgpu monitoring fix-perms`**, чтобы каталоги `LOKI_DATA_DIR` / `PROMTAIL_DATA_DIR` и т.д. существовали с правами для контейнеров, затем **`./slgpu monitoring up`**; подробности — [monitoring/README.md](monitoring/README.md), логи — [monitoring/LOGS.md](monitoring/LOGS.md).

Готовые примеры пресетов в репозитории: `qwen3.6-35b-a3b`, `qwen3-30b-a3b` и др. Для новой модели: добавьте `configs/models/<slug>.env` (см. соседние пресеты), затем **`./slgpu pull <slug>`** или **`./slgpu pull <HF id>`** при совпадении slug.

---

## 9. Бенчмарк и отчёт

```bash
M=qwen3.6-35b-a3b
./slgpu up vllm   -m $M && ./slgpu bench vllm   -m $M
./slgpu down
./slgpu up sglang -m $M && ./slgpu bench sglang -m $M
# Артефакты: bench/results/vllm|sglang/<timestamp>/summary.json
```

Артефакты: `bench/results/<engine>/<timestamp>/summary.json`.

---

## 10. Длительный нагрузочный тест (`load`)

Команда `./slgpu load` эмулирует реальную нагрузку от **200–300 виртуальных пользователей** на протяжении **15–20 минут** (настраивается). В отличие от быстрого `./slgpu bench`, этот режим строит фазы **ramp-up → steady → ramp-down** и пишет time-series метрики, что позволяет увидеть деградацию производительности во времени.

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

В `bench/results/<engine>/<timestamp>/` создаётся 3 файла:

1. **`summary.json`** — сводка по всему прогону: total_duration_sec, throughput_rps, ttft_p50_ms, error_rate, …
2. **`time_series.csv`** — time-series каждые 5 сек: timestamp, phase, active_users, throughput_rps, ttft_p50_ms, ttft_p95_ms, latency_p50_ms, latency_p95_ms, tokens_per_sec, error_rate.
3. **`users.jsonl`** — по одному JSON на каждого виртуального пользователя: uid, total_requests, ok_requests, err_requests, список всех вызовов с ttft/total_ms.

### Примеры запуска

```bash
# Стандартный режим: 250 пользователей, 15 мин steady
./slgpu load vllm -m qwen3.6-35b-a3b

# Максимальная нагрузка: 300 пользователей, 20 мин steady
./slgpu load vllm -m qwen3.6-35b-a3b --users 300 --duration 1200

# Быстрый тест для отладки: 50 пользователей, 2 мин steady
./slgpu load vllm -m qwen3.6-35b-a3b --users 50 --duration 120 --ramp-up 30 --ramp-down 30

# Burst-режим: максимальная нагрузка, запросы без пауз (для 192 vCPU)
./slgpu load vllm -m qwen3.6-35b-a3b --users 384 --burst --duration 900

# Разные сценарии prompt/output
./slgpu load sglang -m qwen3.6-35b-a3b --max-prompt 2048 --max-output 512
```

### Советы

- Запускайте `load` **после** `bench`, чтобы сначала убедиться в базовой работоспособности.
- Если `error_rate` растёт в steady фазе — снижайте `--users` или `--max-output`.
- `time_series.csv` удобно визуализировать в Grafana: импортируйте через datasource CSV или `grafana-csv-datasource`.

---

## 11. Рецепты 8× H200

Ориентир: **8× H200** (~141 GiB × 8). **`TP=8` по умолчанию** в шаблонных пресетах (или **`--tp`** в `./slgpu up` — см. [§4](#4-cli-slgpu)). **`gpu-mem`**, **`batch`**, контекст и парсеры задаются **только в** `configs/models/<preset>.env` — не в `pull`. Ниже: `pull` (скачивание) + `up`; пресеты лежат в репо или добавляйте вручную.

```bash
# Qwen3.6-35B-A3B (пресет: MAX_MODEL_LEN=262144, qwen3/hermes; см. qwen3.6-35b-a3b.env)
./slgpu pull Qwen/Qwen3.6-35B-A3B
./slgpu up vllm -m qwen3.6-35b-a3b

# moonshotai/Kimi-K2.6 (kimi_k2, MM_ENCODER_TP_MODE=data, см. kimi-k2.6.env)
./slgpu pull moonshotai/Kimi-K2.6
./slgpu up vllm -m kimi-k2.6
# ./slgpu up sglang -m kimi-k2.6

# MiniMax-M2.7 (рецепт vLLM: TP4+EP; образ minimax27 — в пресете minimax-m2.7.env)
./slgpu pull MiniMaxAI/MiniMax-M2.7
./slgpu up vllm -m minimax-m2.7

# GLM-5.1 / GLM-5.1-FP8 (см. glm-5.1.env, glm-5.1-fp8.env; образ glm51 — в пресете)
./slgpu pull zai-org/GLM-5.1
./slgpu up vllm -m glm-5.1
./slgpu pull zai-org/GLM-5.1-FP8
./slgpu up vllm -m glm-5.1-fp8

# openai/gpt-oss-120b (добавьте пресет gpt-oss-120b.env по образцу README/соседей, затем:)
# ./slgpu pull openai/gpt-oss-120b && ./slgpu up vllm -m gpt-oss-120b
```

**Замечания:** у **Qwen3.6** не используйте `fp8_e5m2` для KV — см. troubleshooting. **Kimi / большие MoE:** OOM на `create_weights` — упор в размер весей на шард; не всегда помогает снижение контекста — нужен **TP=8**, другой чекпоинт или квант. **MiniMax-M2.7** — не «чистый» **TP8**; см. пресет **`minimax-m2.7`** и [рецепт vLLM](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md) (образ `minimax27`, **TP4**, на 8×GPU **TP+EP** / опционально **DP+EP**). **GLM-5.1** bf16 на грани VRAM — пресет **`glm-5.1-fp8`**, [GLM/GLM5.md](https://github.com/vllm-project/recipes/blob/main/GLM/GLM5.md). **gpt-oss:** полный id в поле `model`. **GLM** и иные: парсеры зависят от образа vLLM.

---

## 12. Мониторинг и безопасность

- **Поднять стек** (если ещё не поднимали): по желанию сначала **`./slgpu monitoring fix-perms`**, затем **`./slgpu monitoring up`**. Движок и мониторинг — разные `docker compose` (сеть `slgpu`, скрейп из [`monitoring/prometheus.yml`](monitoring/prometheus.yml)). Неактивный движок (vllm/sglang) в targets — норма. **Langfuse** (трейсинг) и **LiteLLM** (шлюз к vLLM) — в [`monitoring/README.md`](monitoring/README.md) и `main.env` (`LANGFUSE_PORT` по умолч. 3001, `LITELLM_PORT` 4000); vLLM при этом должен быть поднят; **имя модели** в запросах — как в **LiteLLM /ui** (часто **`devllm`**, как **`SLGPU_SERVED_MODEL_NAME`**); маршрут — в БД, глобальные настройки — [`monitoring/litellm/config.yaml`](monitoring/litellm/config.yaml).
- **Grafana** (`127.0.0.1:3000`), дашборды: в [`monitoring/grafana/provisioning/dashboards/json/`](monitoring/grafana/provisioning/dashboards/json/) лежат JSON с provisioning (Prometheus, uid `prometheus`): краткий **SGLang** (`sglang-dashboard-slgpu.json`), расширенный **SGLang по мотивам vLLM V2** (`sglangdash2-slgpu.json`, сборка из `vllmdash2.json` скриптом `_build_sglangdash2.py`), плюс эталон **vLLM** для ручного импорта (`vllmdash2.json`). Подробности, переменные `instance` / `model_name` и типичные сбои — в [`monitoring/README.md`](monitoring/README.md). **Логи контейнеров:** datasource **Loki** (uid `loki`) — **Explore → Loki**; хранение на диске, см. `LOKI_DATA_DIR` / [monitoring/LOGS.md](monitoring/LOGS.md).
- Сырые логи: **`docker compose -f docker-compose.yml logs -f vllm`**; **`docker compose -f docker-compose.monitoring.yml logs -f prometheus`**. Ротация **json-file** (100 MiB × 5) в обоих compose.

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
| **DeepSeek V4 (Pro/Flash, vLLM):** `DeepseekV4 only supports fp8 kv-cache… got auto` | `KV_CACHE_DTYPE=fp8` или `fp8_e4m3` (пресеты [`deepseek-v4-pro.env`](configs/models/deepseek-v4-pro.env) / [`deepseek-v4-flash.env`](configs/models/deepseek-v4-flash.env)), не `auto` |
| **DeepSeek V4 (vLLM):** INFO `Using DeepSeek's fp8_ds_mla KV cache` | Нормально: так задумано по умолчанию. «Стандартный» fp8 KV — при необходимости задать `SLGPU_VLLM_ATTENTION_BACKEND=FLASHINFER_MLA_SPARSE` в пресете/[`main.env`](main.env), пересоздать контейнер; иначе не трогать |
| **DeepSeek V4 (vLLM):** пустой ответ / «тишина», 200 OK | Пресет: `REASONING_PARSER=deepseek_v4`, `TOOL_CALL_PARSER=deepseek_v4`, `SLGPU_VLLM_TOKENIZER_MODE=deepseek_v4` (см. [блог vLLM](https://vllm.ai/blog/deepseek-v4)); **`deepseek_r1`** — для R1, не для V4. Проверьте `max_tokens` и поля `reasoning_content` в JSON |
| **vLLM V1:** `ValueError: … KV cache is needed, which is larger than the available KV cache memory` (при большом `max_model_len`) | **Поднять `GPU_MEM_UTIL`** (для [DeepSeek-V4-Pro](configs/models/deepseek-v4-pro.env) при 256K — **0.91**; при `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1` в логе часто фигурирует **~0.9033** как эквивалент «старого» бюджета). Либо **снизить `MAX_MODEL_LEN`** до значения из строки *estimated maximum model length* в логе. [Док. vLLM: память](https://docs.vllm.ai/en/latest/configuration/conserving_memory/) |
| **vLLM (DeepSeek V4 Flash):** стек `flashinfer` / `torch.cuda` / `KeyboardInterrupt: terminated` при старте API | Не убивать контейнер на первом долгом шаге (импорт FlashInfer, `_set_compile_ranges`). **Снизить `MAX_MODEL_LEN`** (пресет [deepseek-v4-flash.env](configs/models/deepseek-v4-flash.env) — **262144** вместо 384K+). При необходимости согласовать с Pro: `GPU_MEM_UTIL=0.91`, `--block-size` / `compilation_config` в пресете |
| **vLLM:** много параллельных запросов, в логе `Waiting: N`, `Running: 0`, мало KV | Главное — **уменьшить `MAX_MODEL_LEN`** до реального потолка диалога (например 64k–128k вместо 384k): иначе под длинное окно уходит KV и **одновременных** сессий почти нет. Дополнительно: **`GPU_MEM_UTIL`**, **`SLGPU_MAX_NUM_BATCHED_TOKENS`**, опционально **`SLGPU_VLLM_MAX_NUM_SEQS`** (после снижения контекста; при OOM — меньше). Рецепт **data-parallel** для V4 — в [блоге/рецептах vLLM](https://vllm.ai/blog/deepseek-v4). Горизонтально: несколько реплик + балансировщик |
| **MiniMax-M2.7 (vLLM):** нельзя только **TP8**; ошибки распределения / рекомендации vLLM | [Рецепт](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md): **TP4**; на 8×GPU — **`SLGPU_ENABLE_EXPERT_PARALLEL=1`**, `TP=4`, маска **всех** GPU в **`SLGPU_NVIDIA_VISIBLE_DEVICES`** (см. [`minimax-m2.7.env`](configs/models/minimax-m2.7.env)); образ в пресете — **`minimax27-…-cu130`**, **`SLGPU_VLLM_COMPILATION_CONFIG`** с `fuse_minimax_qk_norm` |
| **GLM-5.1 (vLLM):** `No valid attention backend` / `FLASHMLA_SPARSE: [kv_cache_dtype not supported]` | `KV_CACHE_DTYPE=auto` (в пресете [`configs/models/glm-5.1.env`](configs/models/glm-5.1.env)); не `fp8_e4m3` для sparse MLA+KV |
| **GLM-5.1 (bf16):** `OutOfMemoryError` / `SharedFusedMoE` / `unquantized_fused_moe` при `load_model` | Снизить **`GPU_MEM_UTIL`** (в пресете **0.75**; при повторе — **0.72–0.70**) — vLLM резервирует меньше под KV, больше остаётся под веса. Плюс **`MAX_MODEL_LEN`**, **`SLGPU_MAX_NUM_BATCHED_TOKENS`**, **`SLGPU_ENABLE_PREFIX_CACHING=0`**. Предпочтительно: чекпоинт **FP8** — пресет [`glm-5.1-fp8`](configs/models/glm-5.1-fp8.env) (**`VLLM_DOCKER_IMAGE`** с **glm51** — там же), см. [GLM/GLM5.md](https://github.com/vllm-project/recipes/blob/main/GLM/GLM5.md). Если в логе prefix cache `True` при `0` в пресете — в **`docker-compose.yml`** у vLLM должен быть **`SLGPU_ENABLE_PREFIX_CACHING`**. Дальше: **больше GPU** (`TP`). |
| **`ContextOverflowError`** | Увеличить `MAX_MODEL_LEN` или уменьшить `max_tokens` |
| **OOM при старте** | Снизить `MAX_MODEL_LEN`, `GPU_MEM_UTIL`, `SGLANG_MEM_FRACTION_STATIC`, увеличить `TP`, квантованный чекпоинт |
| **OOM MoE при загрузке весов** | Часто не спасает только снижение контекста; **TP=8**, другой чекпоинт HF или квант |
| **vLLM:** `WorkerProc initialization failed` | Ищите `CUDA OOM` выше в логе; см. [`scripts/serve.sh`](scripts/serve.sh), [`main.env`](main.env) |
| **vLLM:** `custom_all_reduce.cuh` / `invalid argument` при старте | Дефолт **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=1`** (NCCL). Не задавайте `0` в пресете, пока custom all-reduce стабилен на вашем образе/модели. |
| **404 model `gpt-oss-120b`** | Используйте **`openai/gpt-oss-120b`** как в `/v1/models` |
| **Hermes2ProToolParser / `token_ids` (gpt-oss)** | `TOOL_CALL_PARSER=openai` в пресете |

---

## 15. Ограничения

- В пресетах vLLM задайте тег/дижест через **`VLLM_DOCKER_IMAGE`** (в compose — fallback, по умолчанию `v0.19.1-cu130`); **Loki** и **Promtail** в [`docker-compose.monitoring.yml`](docker-compose.monitoring.yml) зафиксированы **2.9.8** (переопределяемые через **`SLGPU_LOKI_IMAGE`** / **`SLGPU_PROMTAIL_IMAGE`** в `main.env`); **Langfuse 3** и **LiteLLM** — в основном **`:3` / `main-*`**; для SGLang, Prometheus, Grafana, node-exporter, MinIO, Postgres, dcgm-exporter в compose в основом **`latest`** — при необходимости зафиксируйте **digest** или явный **тег** (`SLGPU_*_IMAGE` в `main.env`).
- **Langfuse** (Postgres, MinIO, секреты `NEXTAUTH_*` / `LANGFUSE_ENCRYPTION_KEY`) — для **прод** смените пароли и `NEXTAUTH_URL`; данные в **`LANGFUSE_*_DATA_DIR`** на диске (см. [monitoring/README](monitoring/README.md), `fix-perms`). **LiteLLM** — при запущенном vLLM; в **/ui** задайте тот же **`model`**, что отдаёт vLLM (**`SLGPU_SERVED_MODEL_NAME`**, `GET /v1/models`).
- SGLang может не знать те же `--reasoning-parser`, что vLLM.
- Сервисы LLM используют **`gpus: all`**, а реальная маска GPU — **`NVIDIA_VISIBLE_DEVICES`**: по умолчанию **первые `TP` карт** (`0`…`TP-1` через [`./slgpu up`](scripts/cmd_up.sh)). На хосте с **4** GPU задайте **`TP=4`** (или `--tp 4`); маппинг вручную — **`SLGPU_NVIDIA_VISIBLE_DEVICES`** в `main.env` или `export`.

---

## 16. Структура репозитория

Каталоги **`docs/`**, **`grace/`**, **`.cursor/`**, **`.kilo/`** в **git** не входят (см. [`.gitignore`](.gitignore)); после **`git clone`** их в дереве не будет — перенесите с рабочей машины или создайте заново. Корневые **[`AGENTS.md`](AGENTS.md)** и **[`HISTORY.md`](HISTORY.md)** в репозитории есть: краткие указатели; полная история и семантическая карта — в локальном **`docs/`** (если вы его ведёте).

```
slgpu/
├── slgpu                       # CLI-диспетчер
├── VERSION                     # SemVer
├── AGENTS.md                   # Короткий указатель: docs/grace/.cursor/.kilo — только локально
├── docker-compose.yml
├── main.env                    # дефолты (в т.ч. vLLM/SGLang); затем пресет
├── README.md
├── docs/
│   ├── AGENTS.md               # Семантическая карта (GRACE)
│   └── HISTORY.md              # Хронология репо и журнал сессий
├── configs/
│   ├── secrets/hf.env.example
│   └── models/*.env
├── scripts/
│   ├── serve.sh                # vLLM + SGLang (SLGPU_ENGINE) → /etc/slgpu/serve.sh в контейнере
│   ├── _lib.sh
│   ├── cmd_*.sh
│   ├── bench_openai.py
│   └── bench_load.py           # Длительный нагрузочный тест
├── monitoring/
│   ├── LOGS.md                   # Loki + Promtail, Explore, пути на диске
│   ├── README.md
│   ├── prometheus.yml
│   ├── loki/loki-config.yaml
│   ├── promtail/promtail-config.yml
│   ├── litellm/                # config.yaml + entrypoint (LiteLLM → vLLM, Langfuse)
│   └── grafana/provisioning/   # в dashboards/json/ — vLLM/SGLang Grafana JSON, datasource Loki
├── bench/
│   └── results/{vllm,sglang}/
├── grace/                      # GRACE-артефакты
│   ├── requirements/requirements.xml
│   ├── technology/technology.xml
│   ├── plan/development-plan.xml
│   ├── verification/verification-plan.xml
│   └── knowledge-graph/knowledge-graph.xml
├── web/                        # Web Control Plane (FastAPI + React/Vite, см. web/README.md)
├── .cursor/rules/*.mdc         # Правила Cursor (GRACE)
└── .kilo/agent/rules.md        # Правила Kilo
```

> **Web Control Plane**: отдельное приложение в каталоге [`web/`](web/) на FastAPI + React/Vite, запускается одним контейнером и хранит состояние в SQLite. Управляет загрузкой моделей с Hugging Face, пресетами, инференсом vLLM/SGLang, мониторингом и LiteLLM поверх существующего `./slgpu` CLI и Docker API. Контракт — [`web/CONTRACT.md`](web/CONTRACT.md), документация — [`web/README.md`](web/README.md).

---

## Лицензии образов

`vllm/vllm-openai`, `lmsysorg/sglang`, `prom/prometheus`, `prom/node-exporter`, `grafana/grafana`, `grafana/loki`, `grafana/promtail`, `ghcr.io/berriai/litellm`, `langfuse/langfuse` / `langfuse/langfuse-worker`, `postgres`, `clickhouse/clickhouse-server`, `minio/minio`, `redis`, `nvidia/dcgm-exporter` — см. лицензии поставщиков; веса на Hugging Face — отдельные лицензии репозиториев.
