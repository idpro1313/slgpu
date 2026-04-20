# slgpu

Репозиторий **стенда для сравнения LLM-инференса** на выделенном Linux-сервере с несколькими GPU: два движка (**vLLM** и **SGLang**) в Docker, общий локальный кэш моделей, OpenAI-совместимый HTTP API, нагрузочный бенчмарк, **Prometheus + Grafana + NVIDIA DCGM Exporter**, опциональный автозапуск через **systemd**.

Целевая конфигурация при разработке: **4× NVIDIA H200**, **96 vCPU**, **~640 GB RAM**, модели на диске в **`/opt/models`**. Проект рассчитан на один хост без Kubernetes.

---

## Содержание

1. [Назначение и сценарии использования](#1-назначение-и-сценарии-использования)
2. [Архитектура](#2-архитектура)
3. [Сервисы, порты и образы](#3-сервисы-порты-и-образы)
4. [Режимы запуска инференса](#4-режимы-запуска-инференса)
5. [Конфигурация: слои `.env` и пресеты](#5-конфигурация-слои-env-и-пресеты)
6. [Переменные окружения (справочник)](#6-переменные-окружения-справочник)
7. [Подготовка хоста](#7-подготовка-хоста)
8. [Быстрый старт](#8-быстрый-старт)
9. [Скрипты](#9-скрипты)
10. [Бенчмарк и отчёт A/B](#10-бенчмарк-и-отчёт-ab)
11. [Мониторинг и безопасность](#11-мониторинг-и-безопасность)
12. [Reasoning / thinking и парсеры](#12-reasoning--thinking-и-парсеры)
13. [Автозапуск (systemd)](#13-автозапуск-systemd)
14. [Устранение неполадок](#14-устранение-неполадок)
15. [Ограничения и версии](#15-ограничения-и-версии)
16. [Структура репозитория](#16-структура-репозитория)
17. [Лицензии образов](#17-лицензии-образов)

---

## 1. Назначение и сценарии использования

- **Сравнение vLLM и SGLang** на одной и той же модели и одинаковых сценариях нагрузки (латентность TTFT, длительность ответа, RPS).
- **Локальные веса** на хосте (`MODELS_DIR`, по умолчанию `/opt/models`), без повторной загрузки при переключении движка.
- **Два режима GPU**: либо весь кластер на один движок (**TP=4**), либо **два движка параллельно** по две карты (**TP=2**, overlay `docker-compose.both.yml`).
- **Пресеты моделей** — не править `.env` под каждую модель: параметры в `configs/models/<slug>.env`, выбор флагом `-m` или `MODEL=...`.
- **Наблюдаемость**: метрики движков и GPU в Grafana; алерты GPU в Prometheus.

Не входит в объём: reverse-proxy с TLS, LiteLLM-фронт, Kubernetes — при необходимости добавляются снаружи.

---

## 2. Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                         Linux host                               │
│  /opt/models  ──bind mount──►  /models (ro) в контейнерах vLLM/SGLang │
└─────────────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
   ┌──────────┐         ┌──────────┐
   │  vLLM    │         │ SGLang   │   profiles: vllm | sglang (или оба в both)
   │ :8111    │         │ :8222    │   OpenAI API: /v1/chat/completions, /v1/models, /metrics
   └────┬─────┘         └────┬─────┘
        │                    │
        └────────┬───────────┘
                 ▼
         ┌───────────────┐
         │  Prometheus   │  :9090 (по умолчанию 127.0.0.1)
         └───────┬───────┘
                 ▼
         ┌───────────────┐
         │   Grafana     │  :3000 (bind настраивается)
         └───────────────┘
                 ▲
         ┌───────┴───────┐
         │ dcgm-exporter │  :9400 (GPU metrics)
         └───────────────┘
```

- **Compose-проект** `slgpu`: сервисы описаны в `docker-compose.yml`; для co-run подключается второй файл `docker-compose.both.yml`.
- **Профили** Docker Compose: `vllm`, `sglang` — поднимается только выбранный LLM-сервис (или оба в режиме `both`).
- **GPU**: в базовом compose для vLLM/SGLang заданы `device_ids` 0–3; overlay `both` переопределяет на `0,1` и `2,3`.

---

## 3. Сервисы, порты и образы

| Сервис | Образ (типично) | Порт на хосте | Назначение |
|--------|------------------|---------------|------------|
| **vLLM** | `vllm/vllm-openai:latest` | **8111** | OpenAI API, `/metrics` |
| **SGLang** | `lmsysorg/sglang:latest` | **8222** | OpenAI API, `/metrics` |
| **Prometheus** | `prom/prometheus:v2.53.3` | **9090** (`PROMETHEUS_BIND`) | Сбор метрик |
| **Grafana** | `grafana/grafana:11.4.0` | **3000** (`GRAFANA_BIND`/`GRAFANA_PORT`) | Дашборды |
| **dcgm-exporter** | `nvidia/dcgm-exporter:latest` | **9400** (`DCGM_BIND`) | Метрики GPU |

Базовые URL API: `http://<host>:8111/v1`, `http://<host>:8222/v1`.

---

## 4. Режимы запуска инференса

### 4.1. Последовательный A/B (по умолчанию)

- Поднимается **один** из движков: `./scripts/up.sh vllm` или `./scripts/up.sh sglang`.
- **TP** по умолчанию **4** (все карты), переменная `TP` в окружении/пресете.
- Сравнение производительности: сначала бенч одного, затем переключение и бенч второго (`compare.py`).

### 4.2. Параллельный co-run

- `./scripts/up.sh both` — **оба** движка; внутри скрипт выставляет **`TP=2`** (или `TP_BOTH`, по умолчанию 2) и подключает **`docker-compose.both.yml`**.
- **vLLM** видит GPU **0,1**, **SGLang** — **2,3** (правится в overlay).
- Цифры с TP=2 **не сравнимы напрямую** с TP=4; режим удобен для одновременного ответа двух API на одинаковых запросах.

Под капотом:

```bash
TP=2 docker compose -f docker-compose.yml -f docker-compose.both.yml \
  --profile vllm --profile sglang up -d
```

Проверка видимых GPU:

```bash
docker compose exec vllm nvidia-smi -L
docker compose exec sglang nvidia-smi -L
```

---

## 5. Конфигурация: слои `.env` и пресеты

### 5.1. Корневой `.env` (сервер)

Копируется из [`.env.example`](.env.example). Здесь хранятся **секреты и инфраструктура**:

- `HF_TOKEN` — доступ к Hugging Face Hub (не коммитить).
- `MODELS_DIR` — каталог весов на хосте.
- Биндинги Grafana/Prometheus/DCGM, пароль Grafana и т.д.

### 5.2. Пресеты моделей `configs/models/<slug>.env`

Переопределяют параметры, зависящие от модели, **поверх** `.env`:

- `MODEL_ID`, `MODEL_REVISION`, `MAX_MODEL_LEN`, `KV_CACHE_DTYPE`
- `GPU_MEM_UTIL`, `SGLANG_MEM_FRACTION_STATIC`, `TP`
- `VLLM_MAX_NUM_BATCHED_TOKENS` (vLLM, пропускная способность chunked prefill)
- `REASONING_PARSER`, `TOOL_CALL_PARSER` (vLLM)
- `BENCH_MODEL_NAME` (опционально)

Выбор пресета:

```bash
./scripts/up.sh vllm -m qwen3-30b-a3b
MODEL=gpt-oss-120b ./scripts/up.sh sglang
```

Без `-m` скрипты используют значения из `.env` (fallback для обратной совместимости).

Справка по парсерам и добавлению своих пресетов: [`configs/models/README.md`](configs/models/README.md).

### 5.3. Доп. env для движков

- [`configs/vllm/args.env`](configs/vllm/args.env) — например `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1`.
- [`configs/sglang/args.env`](configs/sglang/args.env) — дополнительные переменные SGLang.

Они подключены как `env_file` в compose и не заменяют пресеты; приоритет при конфликте — порядок и то, что экспортирует shell перед `docker compose` (пресет грузится в `up.sh`/`bench.sh` через `set -a`).

---

## 6. Переменные окружения (справочник)

| Переменная | Где задаётся | Назначение |
|------------|--------------|------------|
| `HF_TOKEN` | `.env` | Токен Hugging Face |
| `MODELS_DIR` | `.env` | Путь к моделям на хосте → `/models` в контейнере |
| `MODEL_ID`, `MODEL_REVISION` | пресет / `.env` | Репозиторий и ревизия на Hub |
| `MAX_MODEL_LEN` | пресет / `.env` | Окно контекста (prompt + max_tokens ≤ этого значения) |
| `TP` | пресет / `.env` | Tensor parallel size |
| `GPU_MEM_UTIL` | пресет / `.env` | `--gpu-memory-utilization` (vLLM) |
| `VLLM_MAX_NUM_BATCHED_TOKENS` | пресет / `.env` | `--max-num-batched-tokens` (vLLM; throughput vs TTFT) |
| `SGLANG_MEM_FRACTION_STATIC` | пресет / `.env` | `--mem-fraction-static` (SGLang) |
| `KV_CACHE_DTYPE` | пресет / `.env` | Тип KV (важно для Qwen3 Next / Qwen3.6) |
| `REASONING_PARSER` | пресет / `.env` | `--reasoning-parser` (vLLM и SGLang) |
| `TOOL_CALL_PARSER` | пресет / `.env` | `--tool-call-parser` (**только vLLM**) |
| `GRAFANA_*`, `PROMETHEUS_BIND`, `DCGM_BIND`, `GF_SERVER_ROOT_URL` | `.env` | Мониторинг и сеть |

В режиме `both` скрипт задаёт **`TP=2`** (переменная окружения при вызове compose), если не переопределено `TP_BOTH`.

---

## 7. Подготовка хоста

Целевая ОС: **Ubuntu 22.04/24.04** (или совместимый Debian) с **NVIDIA**.

```bash
chmod +x scripts/prepare-host.sh
sudo ./scripts/prepare-host.sh        # шаги 1–6, где возможно
sudo ./scripts/prepare-host.sh 1      # только проверка драйвера
sudo STEPS=2,4 ./scripts/prepare-host.sh
```

Скрипт [`scripts/prepare-host.sh`](scripts/prepare-host.sh): Docker, NVIDIA Container Toolkit, каталог моделей, sysctl, limits; **драйвер не устанавливает** — только проверка.

Краткий чек-лист:

1. Драйвер **≥ 560** (`nvidia-smi`).
2. **Docker** + **Compose v2** + [**NVIDIA Container Toolkit**](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
3. По желанию: `sudo nvidia-smi -pm 1`.
4. Каталог **`/opt/models`** (желательно отдельный раздел, `noatime`).
5. `vm.swappiness=10`, большой `ulimit -n`.
6. Firewall: наружу только нужные порты; Prometheus/DCGM лучше на `127.0.0.1`.

---

## 8. Быстрый старт

```bash
git clone <repo-url> /opt/slgpu   # или скопируйте каталог
cd /opt/slgpu
chmod +x scripts/*.sh

cp .env.example .env
# Заполните HF_TOKEN, при необходимости MODELS_DIR и Grafana.

# CLI Hugging Face (рекомендуется hf, не huggingface-cli):
pip install -U "huggingface_hub[cli]"

./scripts/download-model.sh -m qwen3-30b-a3b
./scripts/up.sh vllm -m qwen3-30b-a3b

curl -s http://127.0.0.1:8111/v1/models
```

Список готовых пресетов: `ls configs/models/*.env` (имена без `.env` — аргумент `-m`).

---

## 9. Скрипты

| Скрипт | Назначение |
|--------|------------|
| [`scripts/_lib.sh`](scripts/_lib.sh) | Общая загрузка `.env` + опционального пресета (`slgpu_load_env`) |
| [`scripts/up.sh`](scripts/up.sh) | `vllm` \| `sglang` \| `both` + `-m <preset>`; поднимает мониторинг и LLM; ждёт `/v1/models` |
| [`scripts/download-model.sh`](scripts/download-model.sh) | Скачивание модели в `${MODELS_DIR}/${MODEL_ID}` через `hf download` |
| [`scripts/bench.sh`](scripts/bench.sh) | Запуск [`scripts/bench_openai.py`](scripts/bench_openai.py) против `8111` или `8222` |
| [`scripts/bench_openai.py`](scripts/bench_openai.py) | Streaming-нагрузка, сценарии concurrency × длины; учёт `MAX_MODEL_LEN` |
| [`scripts/compare.py`](scripts/compare.py) | Сводка двух последних `summary.json` → `bench/report.md` |
| [`scripts/healthcheck.sh`](scripts/healthcheck.sh) | `curl` `/v1/models` для vllm/sglang |
| [`scripts/prepare-host.sh`](scripts/prepare-host.sh) | Автоматизация подготовки хоста (Ubuntu/Debian) |

Общий синтаксис: флаг **`-m <slug>`** или переменная **`MODEL=<slug>`** для `up.sh`, `bench.sh`, `download-model.sh`.

---

## 10. Бенчмарк и отчёт A/B

**По очереди (честное сравнение при TP=4):**

```bash
M=qwen3-30b-a3b
./scripts/up.sh vllm   -m $M && ./scripts/bench.sh vllm   -m $M
./scripts/up.sh sglang -m $M && ./scripts/bench.sh sglang -m $M
python3 scripts/compare.py    # → bench/report.md
```

**Параллельно в co-run:**

```bash
M=qwen3-30b-a3b
./scripts/up.sh both -m $M
./scripts/bench.sh vllm -m $M &
./scripts/bench.sh sglang -m $M &
wait
python3 scripts/compare.py
```

Результаты: `bench/results/<engine>/<timestamp>/`, внутри `summary.json` и JSON по сценариям. Сценарии: concurrency `1, 8, 32, 128` и комбинации длин prompt/output; при необходимости `max_tokens` ужимается под `MAX_MODEL_LEN`.

---

## 11. Мониторинг и безопасность

- **Prometheus** скрейпит `vllm:8111/metrics`, `sglang:8222/metrics`, `dcgm-exporter:9400` (см. [`monitoring/prometheus.yml`](monitoring/prometheus.yml)).
- **Grafana**: провижининг датасорса и дашборда в [`monitoring/grafana/provisioning/`](monitoring/grafana/provisioning/).
- Подробности и типичные сообщения в логах: [`monitoring/README.md`](monitoring/README.md).

**Безопасность:** смените пароль Grafana перед выставлением наружу; для продакшена — TLS или reverse-proxy, либо `GRAFANA_BIND=127.0.0.1` и SSH-туннель (`ssh -L 3000:127.0.0.1:3000 user@host`). Не коммитьте `.env` с секретами.

---

## 12. Reasoning / thinking и парсеры

- В compose для обоих движков передаётся **`--reasoning-parser`** из `REASONING_PARSER` (дефолт в compose для обратной совместимости — `qwen3`; в пресетах задаётся своё).
- Для **vLLM** дополнительно **`--tool-call-parser`** из `TOOL_CALL_PARSER` и **`--enable-auto-tool-choice`**.
- У **Qwen3** управление thinking через `chat_template_kwargs.enable_thinking` в запросе; ответ может содержать поле **`reasoning_content`** (см. примеры ниже).

Пример (подставьте свой `model` из пресета):

```bash
curl -s http://<host>:8111/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "Qwen/Qwen3-30B-A3B",
    "messages": [{"role":"user","content":"Сколько будет 17*23?"}],
    "chat_template_kwargs": {"enable_thinking": true},
    "max_tokens": 1024
  }' | jq '.choices[0].message'
```

Таблица соответствия семейств моделей и парсеров (vLLM): в [`configs/models/README.md`](configs/models/README.md).

Известный нюанс: для **Qwen3-Next-Thinking** в SGLang бывают проблемы с выделением reasoning — см. [sgl-project/sglang#16653](https://github.com/sgl-project/sglang/issues/16653); в пресете можно попробовать `REASONING_PARSER=qwen3-thinking`.

---

## 13. Автозапуск (systemd)

Юнит: [`systemd/slgpu.service`](systemd/slgpu.service). Вызывает **`./scripts/up.sh`**, а не «голый» compose.

```bash
sudo systemctl edit slgpu.service
# [Service]
# Environment=SLGPU_MODE=both    # vllm | sglang | both
# Environment=MODEL=qwen3-30b-a3b
```

`ExecStop` останавливает только **`vllm`** и **`sglang`**, мониторинг остаётся работать.

---

## 14. Устранение неполадок

| Симптом | Что сделать |
|---------|-------------|
| **vLLM + Qwen3 Next / Qwen3.6:** `kv_cache_dtype` / assert на `fp8_e5m2` | В пресете или `.env`: `KV_CACHE_DTYPE=fp8_e4m3` (или `fp8`), пересоздать контейнер |
| **`ContextOverflowError`** | Увеличить `MAX_MODEL_LEN` или уменьшить `max_tokens` в клиенте; бенч сам поджимает под окно |
| **OOM при старте** | Уменьшить `MAX_MODEL_LEN`, снизить `GPU_MEM_UTIL` / `SGLANG_MEM_FRACTION_STATIC`, увеличить `TP`, взять квантованный вариант модели |
| **Grafana недоступна снаружи** | Проверить `GRAFANA_BIND`, firewall, `GF_SERVER_ROOT_URL` |
| **Unknown reasoning / tool parser** | Обновить образ vLLM; см. команду проверки списка парсеров в `configs/models/README.md` |
| **404: model `gpt-oss-120b` does not exist** | В запросе укажите тот же `id`, что в `/v1/models` — для пресета `gpt-oss-120b` это **`openai/gpt-oss-120b`**, не короткий алиас |
| **`Hermes2ProToolParser... unexpected keyword argument 'token_ids'`** (gpt-oss) | В пресете задайте **`TOOL_CALL_PARSER=openai`**, не `hermes`; пересоздайте контейнер (`docker compose up -d --force-recreate vllm`) |
| **Оба движка на одни GPU** | Для co-run обязательно `./scripts/up.sh both` (overlay), не два отдельных `up` без overlay |

---

## 15. Ограничения и версии

- Образы **`latest`** меняются; для воспроизводимости зафиксируйте digest или тег образа в fork.
- **SGLang** может не поддерживать все те же `--reasoning-parser`, что vLLM; при ошибке старта уберите парсер в пресете для SGLang или используйте только vLLM для экзотических моделей.
- Крупные MoE (например Kimi K2) могут **не помещаться** в 4×H200 без квантизации — см. комментарии в соответствующих пресетах.
- Сравнение **TP=4** и **TP=2 (both)** по цифрам бенча — разные условия; для публикации метрик используйте один режим.

---

## 16. Структура репозитория

```
slgpu/
├── docker-compose.yml          # сервисы vLLM, SGLang, мониторинг; TP и парсеры из env
├── docker-compose.both.yml     # overlay: split GPU, co-run
├── .env.example
├── README.md                   # этот файл
├── configs/
│   ├── vllm/args.env           # доп. переменные vLLM (например CUDA graph profiler)
│   ├── sglang/args.env
│   └── models/                 # пресеты: *.env + README.md
├── scripts/
│   ├── _lib.sh
│   ├── up.sh
│   ├── download-model.sh
│   ├── bench.sh
│   ├── bench_openai.py
│   ├── compare.py
│   ├── healthcheck.sh
│   └── prepare-host.sh
├── monitoring/
│   ├── prometheus.yml
│   ├── prometheus-alerts.yml
│   ├── README.md
│   └── grafana/provisioning/…
├── bench/
│   ├── results/                # артефакты бенчей (не коммитить большие прогоны)
│   └── report.md               # генерируется compare.py
└── systemd/slgpu.service
```

Файлы в `configs/models/` (пресеты) дополняются по мере необходимости; актуальный список: `ls configs/models/*.env`.

---

## 17. Лицензии образов

Используются публичные образы **`vllm/vllm-openai`**, **`lmsysorg/sglang`**, **`prom/prometheus`**, **`grafana/grafana`**, **`nvidia/dcgm-exporter`**. Для продакшена ознакомьтесь с лицензиями и политиками поставщиков; веса моделей на Hugging Face имеют отдельные лицензии репозиториев.
