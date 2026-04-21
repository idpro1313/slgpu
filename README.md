# slgpu

Репозиторий **стенда для сравнения LLM-инференса** на Linux-сервере с GPU: два движка (**vLLM** и **SGLang**) в Docker, общий локальный кэш моделей, OpenAI-совместимый HTTP API, нагрузочный бенчмарк, **Prometheus + Grafana + NVIDIA DCGM Exporter**.

Целевая конфигурация при разработке: **8× NVIDIA H200** (в `docker-compose.yml` заданы `device_ids` 0–7). **Tensor parallel по умолчанию `TP=8`**: в пресетах [`configs/models/*.env`](configs/models/), в [`./slgpu pull`](scripts/cmd_pull.sh) (если не указать `--tp`) и в [`serve.sh`](configs/vllm/serve.sh) при отсутствии переменной. На меньшем числе GPU уменьшите `TP` и список `device_ids` в compose. Проект рассчитан на один хост без Kubernetes.

Единая точка входа: **`./slgpu`** (bash, только Linux VM).

---

## Содержание

1. [Назначение](#1-назначение)
2. [Архитектура](#2-архитектура)
3. [Сервисы и порты](#3-сервисы-и-порты)
4. [CLI `./slgpu`](#4-cli-slgpu)
5. [Конфигурация: `.env` и пресеты](#5-конфигурация)
6. [Переменные окружения (справочник)](#6-переменные-окружения)
7. [Подготовка хоста](#7-подготовка-хоста)
8. [Быстрый старт](#8-быстрый-старт)
9. [Бенчмарк и A/B](#9-бенчмарк-и-ab)
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
- Один движок за раз; **порт 8111** общий.
- Пресеты моделей в `configs/models/<slug>.env`; **`./slgpu pull <HF_ID>`** создаёт пресет автоматически.

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
   │ :8111    │         │ :8111    │
   └────┬─────┘         └────┬─────┘
        └────────┬───────────┘
                 ▼
         Prometheus :9090 → Grafana :3000
                 ▲
         dcgm-exporter :9400 · node-exporter :9100
```

Переменные модели передаются в контейнер через блок **`environment`** в `docker-compose.yml` и значения, экспортированные в shell командой **`./slgpu up`** (после слияния `.env` + `configs/<engine>/<engine>.env` + пресет).

---

## 3. Сервисы и порты

| Сервис | Образ в `docker-compose.yml` | Порт на хосте |
|--------|-------------------------------|---------------|
| **vLLM** | `vllm/vllm-openai:latest` | **8111** |
| **SGLang** | `lmsysorg/sglang:latest` | **8111** |
| **Prometheus** | `prom/prometheus:latest` | **9090** (`PROMETHEUS_BIND`) |
| **Grafana** | `grafana/grafana:latest` | **3000** |
| **dcgm-exporter** | `nvidia/dcgm-exporter:latest` | **9400** |
| **node-exporter** | `prom/node-exporter:latest` | **9100** |

Все перечисленные сервисы в compose собраны на теге **`latest`**: при `docker compose pull` вы получаете актуальные сборки, но **воспроизводимость** между машинами и во временем не гарантируется. Для зафиксированного стенда подставьте **конкретный тег** или **digest** образа в [`docker-compose.yml`](docker-compose.yml).

Базовый URL API: `http://<host>:8111/v1`.

---

## 4. CLI `./slgpu`

Точка входа для всего жизненного цикла стенда: подготовка ОС, загрузка весов, запуск выбранного движка в Docker, бенчмарки, логи и диагностика. Команды реализованы в [`scripts/cmd_*.sh`](scripts/) и вызываются через корневой скрипт [`slgpu`](slgpu). В репозитории для `slgpu` и `cmd_*.sh` уже выставлен исполняемый бит; при необходимости на VM: `chmod +x slgpu scripts/cmd_*.sh`.

### Шпаргалка синтаксиса

```text
./slgpu help
./slgpu prepare [1–6]
./slgpu pull <HF_ID|preset> [опции]
./slgpu up <vllm|sglang> -m <preset>
./slgpu down [--all]
./slgpu restart -m <preset>
./slgpu bench <vllm|sglang> -m <preset>
./slgpu load <vllm|sglang> -m <preset> [опции]
./slgpu ab -m <preset>
./slgpu compare
./slgpu logs [SERVICE] [аргументы docker compose logs…]
./slgpu status
./slgpu config <vllm|sglang> -m <preset>
```

### Назначение команд

| Команда | Назначение |
|---------|------------|
| **`help`** | Краткая справка по всем подкомандам и примерам вызова (то же, что и `./slgpu` без аргументов с подсказкой). |
| **`prepare`** | **Один раз при создании ВМ** (или после переустановки ОС): проверка драйвера NVIDIA, установка Docker и Compose v2, NVIDIA Container Toolkit, при желании persistence mode GPU, создание каталога `MODELS_DIR`, sysctl (`vm.swappiness`), лимиты `nofile`, напоминание про firewall. Запуск от root: `sudo ./slgpu prepare` или шаг `sudo ./slgpu prepare 1` … `6`; выборочно: `STEPS=2,4 sudo -E ./slgpu prepare`. |
| **`pull`** | **Скачивание весов** в `${MODELS_DIR}/<MODEL_ID>` через CLI `hf` (`huggingface_hub`). Если аргумент — **HF id с `/`** (например `Qwen/Qwen3.6-35B-A3B`), **автоматически создаётся** файл пресета `configs/models/<slug>.env` (slug из имени репозитория) с дефолтами и угадыванием парсеров; **`--tp` по умолчанию 8**; **`MAX_MODEL_LEN`** без **`--max-len`** выбирается эвристикой (часто 262144; см. [`configs/models/README.md`](configs/models/README.md)); затем выполняется загрузка. Если аргумент **без `/`** — трактуется как **уже существующий пресет** (только `hf download` по полям из этого `.env`). Опции: `--slug`, `--force`, `--keep`, `--revision`, `--max-len`, `--tp`, `--kv-dtype`, `--gpu-mem`, `--sglang-mem`, `--batch`, `--reasoning-parser`, `--tool-call-parser`. Токен для приватных репозиториев: [`configs/secrets/hf.env`](configs/secrets/hf.env) (`HF_TOKEN`). |
| **`up`** | **Запуск стенда**: останавливает и удаляет контейнеры другого движка (vllm/sglang), поднимает мониторинг (Prometheus, Grafana, экспортеры), затем поднимает **один** выбранный профиль — `vllm` или `sglang` с tensor parallel и параметрами из **`-m <preset>`** (обязательно). Экспортирует в shell переменные из `.env` + `configs/<engine>/<engine>.env` + пресета и ждёт готовность `http://127.0.0.1:8111/v1/models`. Идемпотентен при повторном вызове с тем же движком. |
| **`down`** | **Остановка инференса**: по умолчанию останавливает и снимает контейнеры **только** `vllm` и `sglang` (мониторинг остаётся). С флагом **`--all`** — останавливаются **все** сервисы проекта compose (включая Prometheus/Grafana/экспортеры). Удобно перед сменой движка или освобождением GPU без сноса данных в томах Grafana/Prometheus при обычном `down`. |
| **`restart`** | **Перезапуск с новым пресетом без смены движка**: определяет, какой сервис сейчас в статусе *running* (`vllm` или `sglang`), и выполняет для него ту же последовательность, что и `up`, с новым **`-m <preset>`**. Если ни один LLM-контейнер не запущен — сообщение об ошибке; тогда используйте `up`. |
| **`bench`** | **Нагрузочный тест** против уже поднятого API на `127.0.0.1:8111`: запускает [`scripts/bench_openai.py`](scripts/bench_openai.py), подгружает пресет **`-m`** (для `MAX_MODEL_LEN`, `BENCH_MODEL_NAME` и т.д.), пишет артефакты в `bench/results/<engine>/<timestamp>/`. Должен совпадать движок в аргументе (`vllm` или `sglang`) с тем, что реально запущен. |
| **`load`** | **Длительный нагрузочный тест** (15–20 мин, 200–300 виртуальных пользователей): запускает [`scripts/bench_load.py`](scripts/bench_load.py), эмулирует фазы ramp-up → steady → ramp-down, собирает time-series метрики (throughput, TTFT, latency, error rate) в CSV каждые 5 сек. Артефакты: `summary.json`, `time_series.csv`, `users.jsonl`. Опции: `--users`, `--duration`, `--ramp-up`, `--ramp-down`, `--think-time`, `--max-prompt`, `--max-output`, `--report-interval`. |
| **`ab`** | **Сквозной A/B-сценарий** для честного сравнения на одной модели: `up vllm` → `bench vllm` → `down` (только LLM) → `up sglang` → `bench sglang` → `compare`. Один пресет **`-m`** на всю цепочку; в конце обновляется [`bench/report.md`](bench/report.md). |
| **`compare`** | **Сводка двух последних прогонов**: читает последние `summary.json` для `vllm` и `sglang` в `bench/results/` (или пути из флагов скрипта) и перезаписывает таблицу в `bench/report.md`. Можно вызывать отдельно после ручных бенчей. |
| **`logs`** | **Потоковые логи Docker** выбранного сервиса (`docker compose logs -f --tail=200`). Без имени сервиса — логи того из `vllm`/`sglang`, который сейчас *running*. Дополнительные флаги пробрасываются в `docker compose logs` (например другой `--tail`). Сервисы: `vllm`, `sglang`, `prometheus`, `grafana`, `dcgm-exporter`, `node-exporter`. |
| **`status`** | **Быстрая диагностика «с первого взгляда»**: `docker compose ps`, проверка `GET /v1/models` на localhost:8111, краткий вывод `nvidia-smi` по GPU. Не требует пресета; полезно после `up` или при сбоях. |
| **`config`** | **Печать эффективного окружения** после слияния `.env` + `configs/<vllm|sglang>/<engine>.env` + пресета **`-m`**: отфильтрованный список переменных (`MODEL_*`, `TP`, `KV_*`, парсеры, …). Нужен, чтобы убедиться, что в контейнер уйдут ожидаемые значения, не заглядывая вручную во все файлы. |

Подробности по флагам **`pull`**: см. `./slgpu pull -h` и [`configs/models/README.md`](configs/models/README.md).

---

## 5. Конфигурация

- **Корневой `.env`** — только сервер: `MODELS_DIR`, биндинги Grafana/Prometheus/DCGM, пароль Grafana. Копия из [`.env.example`](.env.example).
- **`configs/models/<preset>.env`** — модель: `MODEL_ID`, `MAX_MODEL_LEN`, **`TP`** (в шаблонах репозитория **8**; на 4 GPU — **4**), парсеры, KV и т.д. Обязателен для `up` / `bench` / `restart` (флаг **`-m`**).
- **`configs/vllm/vllm.env`**, **`configs/sglang/sglang.env`** — NCCL, логи, alloc (см. комментарии в файлах).
- **CLI движка**: [`configs/vllm/serve.sh`](configs/vllm/serve.sh), [`configs/sglang/serve.sh`](configs/sglang/serve.sh).

Справка по парсерам: [`configs/models/README.md`](configs/models/README.md).

---

## 6. Переменные окружения (справочник)

| Переменная | Где задаётся | Назначение |
|------------|--------------|------------|
| `HF_TOKEN` | [`configs/secrets/hf.env`](configs/secrets/hf.env) | Только для `./slgpu pull` |
| `MODELS_DIR` | `.env` | Путь к моделям на хосте → `/models` |
| `MODEL_ID`, `MODEL_REVISION`, `MAX_MODEL_LEN`, `TP`, `GPU_MEM_UTIL`, `KV_CACHE_DTYPE`, `SLGPU_MAX_NUM_BATCHED_TOKENS`, `SGLANG_MEM_FRACTION_STATIC`, `REASONING_PARSER`, `TOOL_CALL_PARSER`, `MM_ENCODER_TP_MODE`, `BENCH_MODEL_NAME`, `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS` | пресет | Параметры инференса (см. `configs/models/README.md`) |
| `LLM_API_BIND`, `GRAFANA_*`, `PROMETHEUS_*`, `DCGM_BIND`, `NODE_EXPORTER_BIND` | `.env` | Сеть и мониторинг |

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

cp .env.example .env
# Опционально для gated моделей:
# cp configs/secrets/hf.env.example configs/secrets/hf.env

pip install -U "huggingface_hub[cli]"

./slgpu pull Qwen/Qwen3.6-35B-A3B
./slgpu up vllm -m qwen3.6-35b-a3b

curl -s http://127.0.0.1:8111/v1/models
```

Готовые примеры пресетов в репозитории: `qwen3.6-35b-a3b`, `qwen3-30b-a3b`. Остальные модели — через `./slgpu pull <HF_ID> ...`.

---

## 9. Бенчмарк и A/B

```bash
M=qwen3.6-35b-a3b
./slgpu up vllm   -m $M && ./slgpu bench vllm   -m $M
./slgpu down
./slgpu up sglang -m $M && ./slgpu bench sglang -m $M
./slgpu compare              # → bench/report.md
```

Или одной командой: **`./slgpu ab -m qwen3.6-35b-a3b`**.

Результаты: `bench/results/<engine>/<timestamp>/summary.json`.

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

## 11. Рецепты 8x H200

Ориентир: **8× H200** (~141 GiB × 8). **`TP=8` уже по умолчанию** в `./slgpu pull` и в шаблонных пресетах — флаг `--tp` можно не указывать. Ниже — агрессивные `gpu-mem` / `batch` для максимума пропускной способности (при OOM уменьшайте `--max-len` или `--batch`).

```bash
# Qwen3.6-35B-A3B (pull без --max-len даёт MAX_MODEL_LEN=262144 и парсеры qwen3/hermes)
./slgpu pull Qwen/Qwen3.6-35B-A3B \
  --gpu-mem 0.95 --sglang-mem 0.92 \
  --batch 24576 --kv-dtype fp8_e4m3
./slgpu up vllm -m qwen3.6-35b-a3b

# moonshotai/Kimi-K2.6 (заявленное окно на HF — 128K; при OOM снизьте --max-len; веса ~1T — fp8/квант на чекпоинте)
# Пресет по умолчанию: TP=8, MAX_MODEL_LEN=262144 (как у pull для длинного контекста), kimi_k2-парсеры, MM_ENCODER_TP_MODE=data.
./slgpu pull moonshotai/Kimi-K2.6 \
  --gpu-mem 0.94 --sglang-mem 0.90 \
  --batch 16384 --kv-dtype fp8_e4m3
./slgpu up vllm -m kimi-k2.6
# ./slgpu up sglang -m kimi-k2.6

# MiniMax-M2.7 (дефолт MAX_MODEL_LEN=262144)
./slgpu pull MiniMaxAI/MiniMax-M2.7 \
  --gpu-mem 0.95 --sglang-mem 0.92 \
  --batch 24576 --kv-dtype fp8_e4m3 \
  --reasoning-parser minimax_m2 --tool-call-parser minimax_m2
./slgpu up vllm -m minimax-m2.7

# GLM-5.1 (дефолт MAX_MODEL_LEN=131072)
./slgpu pull zai-org/GLM-5.1 \
  --gpu-mem 0.95 --sglang-mem 0.92 \
  --batch 24576 --kv-dtype fp8_e4m3 \
  --reasoning-parser glm45 --tool-call-parser glm45
./slgpu up vllm -m glm-5.1

# openai/gpt-oss-120b (дефолт MAX_MODEL_LEN=131072; Harmony: tool parser `openai`; в API model = openai/gpt-oss-120b)
./slgpu pull openai/gpt-oss-120b \
  --gpu-mem 0.9296 --sglang-mem 0.90 \
  --batch 16384 --kv-dtype auto \
  --reasoning-parser openai_gptoss --tool-call-parser openai
./slgpu up vllm -m gpt-oss-120b
```

**Замечания:** у **Qwen3.6** не используйте `fp8_e5m2` для KV — см. troubleshooting. **Kimi / большие MoE:** OOM на `create_weights` — упор в размер весей на шард; не всегда помогает снижение контекста — нужен **TP=8**, другой чекпоинт или квант. **gpt-oss:** полный id в поле `model`. **MiniMax/GLM:** имена парсеров зависят от версии образа vLLM.

---

## 11. Мониторинг и безопасность

- **Prometheus** (`127.0.0.1:9090`): см. [`monitoring/prometheus.yml`](monitoring/prometheus.yml). Неактивный профиль (vllm/sglang) даёт DOWN target — норма для A/B.
- **Grafana**, дашборды: [`monitoring/README.md`](monitoring/README.md).
- Логи контейнеров: **`./slgpu logs vllm -f`**; ротация **json-file** (100 MiB × 5) задана в compose.

**Безопасность:** смените пароль Grafana; не коммитьте `.env` с секретами.

---

## 12. Reasoning / thinking

- vLLM: `--reasoning-parser` и `--tool-call-parser` из пресета (см. [`configs/vllm/serve.sh`](configs/vllm/serve.sh)).
- SGLang: `--reasoning-parser` из пресета ([`configs/sglang/serve.sh`](configs/sglang/serve.sh)).

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

## 13. Устранение неполадок

| Симптом | Что сделать |
|---------|-------------|
| **Qwen3 Next / Qwen3.6:** assert / `fp8_e5m2` | В пресете: `KV_CACHE_DTYPE=fp8_e4m3` или `fp8`, пересоздать контейнер |
| **`ContextOverflowError`** | Увеличить `MAX_MODEL_LEN` или уменьшить `max_tokens` |
| **OOM при старте** | Снизить `MAX_MODEL_LEN`, `GPU_MEM_UTIL`, `SGLANG_MEM_FRACTION_STATIC`, увеличить `TP`, квантованный чекпоинт |
| **OOM MoE при загрузке весов** | Часто не спасает только снижение контекста; **TP=8**, другой чекпоинт HF или квант |
| **vLLM:** `WorkerProc initialization failed` | Ищите `CUDA OOM` выше в логе; см. [`configs/vllm/serve.sh`](configs/vllm/serve.sh), [`configs/vllm/vllm.env`](configs/vllm/vllm.env) |
| **404 model `gpt-oss-120b`** | Используйте **`openai/gpt-oss-120b`** как в `/v1/models` |
| **Hermes2ProToolParser / `token_ids` (gpt-oss)** | `TOOL_CALL_PARSER=openai` в пресете |

---

## 14. Ограничения

- В **`docker-compose.yml`** для vLLM, SGLang, Prometheus, Grafana, node-exporter и dcgm-exporter задан тег **`latest`**: содержимое образов меняется без bump версии в репозитории; для продакшена зафиксируйте **digest** или явный **тег** версии.
- SGLang может не знать те же `--reasoning-parser`, что vLLM.
- В `docker-compose.yml` заданы **8** `device_ids` (0–7). На хосте с **4** GPU укажите `["0","1","2","3"]` и выставьте **`TP=4`** в пресете.

---

## 15. Структура репозитория

```
slgpu/
├── slgpu                       # CLI-диспетчер
├── docker-compose.yml
├── .env.example
├── README.md
├── HISTORY.md
├── configs/
│   ├── secrets/hf.env.example
│   ├── vllm/{serve.sh,vllm.env}
│   ├── sglang/{serve.sh,sglang.env}
│   └── models/*.env
├── scripts/
│   ├── _lib.sh
│   ├── cmd_*.sh
│   ├── bench_openai.py
│   └── compare.py
├── monitoring/
└── bench/
```

---

## Лицензии образов

`vllm/vllm-openai`, `lmsysorg/sglang`, `prom/prometheus`, `prom/node-exporter`, `grafana/grafana`, `nvidia/dcgm-exporter` — см. лицензии поставщиков; веса на Hugging Face — отдельные лицензии репозиториев.
