# slgpu

Репозиторий **стенда для сравнения LLM-инференса** на Linux-сервере с GPU: два движка (**vLLM** и **SGLang**) в Docker, общий локальный кэш моделей, OpenAI-совместимый HTTP API, нагрузочный бенчмарк, **Prometheus + Grafana + NVIDIA DCGM Exporter**.

Целевая конфигурация при разработке: **8× NVIDIA H200** (в `docker-compose.yml` заданы `device_ids` 0–7), **TP** задаётся в пресете (`configs/models/*.env`). Проект рассчитан на один хост без Kubernetes.

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
10. [Рецепты 8× H200](#10-рецепты-8-h200)
11. [Мониторинг и безопасность](#11-мониторинг-и-безопасность)
12. [Reasoning / thinking](#12-reasoning--thinking)
13. [Устранение неполадок](#13-устранение-неполадок)
14. [Ограничения](#14-ограничения)
15. [Структура репозитория](#15-структура-репозитория)

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

| Сервис | Образ (типично) | Порт на хосте |
|--------|-----------------|---------------|
| **vLLM** | `vllm/vllm-openai:latest` | **8111** |
| **SGLang** | `lmsysorg/sglang:latest` | **8111** |
| **Prometheus** | `prom/prometheus:v2.53.3` | **9090** (`PROMETHEUS_BIND`) |
| **Grafana** | `grafana/grafana:11.4.0` | **3000** |
| **dcgm-exporter** | `nvidia/dcgm-exporter:latest` | **9400** |
| **node-exporter** | `prom/node-exporter:v1.8.2` | **9100** |

Базовый URL API: `http://<host>:8111/v1`.

---

## 4. CLI `./slgpu`

```bash
chmod +x slgpu scripts/cmd_*.sh   # на Linux VM

./slgpu help

./slgpu prepare [1–6]              # подготовка хоста (часто: sudo ./slgpu prepare)
./slgpu pull <HF_ID|preset> [...]  # скачать веса; HF id → автогенерация configs/models/<slug>.env
./slgpu up <vllm|sglang> -m <preset>
./slgpu down [--all]
./slgpu restart -m <preset>        # перезапуск текущего running-движка
./slgpu bench <vllm|sglang> -m <preset>
./slgpu ab -m <preset>             # vllm→bench→sglang→bench→compare
./slgpu compare
./slgpu logs [SERVICE] [-f]
./slgpu status
./slgpu config <vllm|sglang> -m <preset>
```

**`./slgpu pull`**: если аргумент содержит `/` (например `Qwen/Qwen3.6-35B-A3B`), считается Hugging Face id: создаётся пресет с slug из имени репозитория (`qwen3.6-35b-a3b`). Опции: `--slug`, `--force`, `--keep`, `--revision`, `--max-len`, `--tp`, `--kv-dtype`, `--gpu-mem`, `--sglang-mem`, `--batch`, `--reasoning-parser`, `--tool-call-parser`. Токен: `configs/secrets/hf.env` (`HF_TOKEN`).

---

## 5. Конфигурация

- **Корневой `.env`** — только сервер: `MODELS_DIR`, биндинги Grafana/Prometheus/DCGM, пароль Grafana. Копия из [`.env.example`](.env.example).
- **`configs/models/<preset>.env`** — модель: `MODEL_ID`, `MAX_MODEL_LEN`, `TP`, парсеры, KV, и т.д. Обязателен для `up` / `bench` / `restart` (флаг **`-m`**).
- **`configs/vllm/vllm.env`**, **`configs/sglang/sglang.env`** — NCCL, логи, alloc (см. комментарии в файлах).
- **CLI движка**: [`configs/vllm/serve.sh`](configs/vllm/serve.sh), [`configs/sglang/serve.sh`](configs/sglang/serve.sh).

Справка по парсерам: [`configs/models/README.md`](configs/models/README.md).

---

## 6. Переменные окружения (справочник)

| Переменная | Где задаётся | Назначение |
|------------|--------------|------------|
| `HF_TOKEN` | [`configs/secrets/hf.env`](configs/secrets/hf.env) | Только для `./slgpu pull` |
| `MODELS_DIR` | `.env` | Путь к моделям на хосте → `/models` |
| `MODEL_ID`, `MODEL_REVISION`, `MAX_MODEL_LEN`, `TP`, `GPU_MEM_UTIL`, `KV_CACHE_DTYPE`, `VLLM_MAX_NUM_BATCHED_TOKENS`, `SGLANG_MEM_FRACTION_STATIC`, `REASONING_PARSER`, `TOOL_CALL_PARSER`, `BENCH_MODEL_NAME`, `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS` | пресет | Параметры инференса (см. `configs/models/README.md`) |
| `LLM_API_BIND`, `GRAFANA_*`, `PROMETHEUS_*`, `DCGM_BIND`, `NODE_EXPORTER_BIND` | `.env` | Сеть и мониторинг |

---

## 7. Подготовка хоста

Ubuntu/Debian, драйвер NVIDIA (рекомендуется ≥ 560 для H200/FP8).

```bash
chmod +x slgpu scripts/cmd_*.sh
sudo ./slgpu prepare              # шаги 1–6
sudo ./slgpu prepare 1            # только проверка драйвера
sudo STEPS=2,4 ./slgpu prepare
```

Docker, Compose v2, NVIDIA Container Toolkit, каталог `MODELS_DIR`, sysctl, limits — см. реализацию [`scripts/cmd_prepare.sh`](scripts/cmd_prepare.sh).

---

## 8. Быстрый старт

```bash
git clone <repo-url> /opt/slgpu && cd /opt/slgpu
chmod +x slgpu scripts/cmd_*.sh

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

## 10. Рецепты 8× H200

Ориентир: **8× H200** (~141 GiB × 8), **`TP=8`** в флагах `pull`, агрессивные `gpu-mem` / `batch` для максимума пропускной способности (при OOM уменьшайте `--max-len` или `--batch`).

```bash
# Qwen3.6-35B-A3B (окно до 262144)
./slgpu pull Qwen/Qwen3.6-35B-A3B \
  --tp 8 --max-len 262144 --gpu-mem 0.95 --sglang-mem 0.92 \
  --batch 24576 --kv-dtype fp8_e4m3 \
  --reasoning-parser qwen3 --tool-call-parser hermes
./slgpu up vllm -m qwen3.6-35b-a3b

# moonshotai/Kimi-K2.6 (архитектурное окно 128K; веса ~1T — нужен fp8/квант на чекпоинте)
./slgpu pull moonshotai/Kimi-K2.6 \
  --tp 8 --max-len 131072 --gpu-mem 0.94 --sglang-mem 0.90 \
  --batch 16384 --kv-dtype fp8_e4m3 \
  --reasoning-parser kimi_k2 --tool-call-parser kimi_k2
./slgpu up vllm -m kimi-k2.6

# MiniMax-M2.7
./slgpu pull MiniMaxAI/MiniMax-M2.7 \
  --tp 8 --max-len 262144 --gpu-mem 0.95 --sglang-mem 0.92 \
  --batch 24576 --kv-dtype fp8_e4m3 \
  --reasoning-parser minimax_m2 --tool-call-parser minimax_m2
./slgpu up vllm -m minimax-m2.7

# GLM-5.1
./slgpu pull zai-org/GLM-5.1 \
  --tp 8 --max-len 131072 --gpu-mem 0.95 --sglang-mem 0.92 \
  --batch 24576 --kv-dtype fp8_e4m3 \
  --reasoning-parser glm45 --tool-call-parser glm45
./slgpu up vllm -m glm-5.1

# openai/gpt-oss-120b (Harmony: tool parser `openai`; в API указывайте model = openai/gpt-oss-120b)
./slgpu pull openai/gpt-oss-120b \
  --tp 8 --max-len 131072 --gpu-mem 0.9296 --sglang-mem 0.90 \
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

- Теги образов **`latest`** меняются; для продакшена зафиксируйте digest.
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
