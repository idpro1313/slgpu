# История проекта slgpu

Документ фиксирует **цели**, **эволюцию** и **ключевые коммиты** репозитория. Даты — по мере появления в истории git (ветка `main`).

---

## Зачем проект

Стенд для **сравнения двух движков LLM-инференса** на одном Linux-сервере с несколькими GPU:

- **vLLM** и **SGLang** в Docker, OpenAI-совместимый API.
- Локальный кэш моделей (изначально ориентир **`/opt/models`**).
- Целевая конфигурация (эволюция): изначально ориентир **4× H200**, **TP=4**; в текущем репозитории — **8× H200**, **`TP=8` по умолчанию** в пресетах, `pull` и `serve.sh`, один порт API **8111** для vLLM и SGLang по очереди.
- Наблюдаемость: **Prometheus**, **Grafana**, **NVIDIA DCGM Exporter**.
- Скрипты: скачивание модели, запуск compose, бенчмарк, сравнение отчётов, подготовка хоста.

Позже к базовому сценарию A/B добавлены **co-run** (оба движка по 2 GPU), **пресеты моделей**, **thinking/reasoning**, тонкая настройка **gpt-oss** и параметры **пропускной способности** vLLM.

---

## Хронология (от старых коммитов к новым)

### Исходный каркас

| Коммит | Суть |
|--------|------|
| `06abe8a` | Первый коммит: `docker-compose`, vLLM/SGLang, мониторинг, скрипты, бенч, конфиги без секретов в истории. |

### Скрипты и окружение

| Коммит | Суть |
|--------|------|
| `d0c0ece` | Исполняемые биты (`100755`) для `scripts/*.sh`. |
| `9a9692a` | Правки скриптов. |
| `b9f3e28` | Служебный коммит git. |
| `35cb079` | `download-model.sh`: приоритет **`hf download`** вместо устаревшего `huggingface-cli`. |

### Qwen3 Next / KV и контекст

| Коммит | Суть |
|--------|------|
| `235e4c3` | Дефолт **`KV_CACHE_DTYPE=fp8_e4m3`**: для Qwen3 Next `fp8_e5m2` ломал attention / Dynamo. |
| `5e537ec` | Grafana: пустые provisioning для `plugins`/`alerting`, пояснения в README. |
| `e22cb3e` | **`MAX_MODEL_LEN=65536`** по умолчанию; бенч учитывает окно и ужимает `max_tokens`. |
| `cee515f` | Дефолт **`MAX_MODEL_LEN=262144`** (максимальное окно Qwen3 Next по запросу пользователя). |

### Grafana и доступ

| Коммит | Суть |
|--------|------|
| `e5bc4a0` | Grafana: внешний bind по умолчанию; вместо `.gitkeep` — валидные пустые YAML provisioning; переменные `GRAFANA_BIND`, `PROMETHEUS_BIND`, `DCGM_BIND`, `GF_SERVER_ROOT_URL`. |

### Reasoning (Qwen3)

| Коммит | Суть |
|--------|------|
| `3c68062` | **`--reasoning-parser qwen3`** для vLLM и SGLang; переменная `REASONING_PARSER`; документация `chat_template_kwargs.enable_thinking`. |

### Память CUDA Graph (vLLM)

| Коммит | Суть |
|--------|------|
| `91acd19` | **`VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1`** в `configs/vllm/args.env`; **`GPU_MEM_UTIL=0.9242`** в `.env.example` по рекомендации vLLM 0.19. |

### Co-run (два движка на одном хосте)

| Коммит | Суть |
|--------|------|
| `fd417b1` | **`docker-compose.both.yml`**: vLLM на GPU 0–1, SGLang на 2–3, **TP=2**; `TP` параметризован в compose; **`scripts/up.sh both`**. |

### Пресеты моделей

| Коммит | Суть |
|--------|------|
| `52f7433` | **`configs/models/*.env`**, **`scripts/_lib.sh`**, флаг **`-m`** / **`MODEL=`** для `up.sh`, `bench.sh`, `download-model.sh`; разделение серверного `.env` и модельных пресетов. |
| `5966aaa` | Пресеты: **gpt-oss-120b**, **Kimi-K2.5**, **GLM-5.1**, **MiniMax-M2.7**; **`TOOL_CALL_PARSER`** в compose. |

### Qwen3.6-27B и vLLM all-reduce

| Версия | Суть |
|--------|------|
| 1.8.0 | Пресет [**`configs/models/qwen3.6-27b.env`**](configs/models/qwen3.6-27b.env) (throughput: **`SLGPU_MAX_NUM_BATCHED_TOKENS=16384`**, **`GPU_MEM_UTIL=0.9262`**, опционально **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE`**); переменная **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE`** в [`docker-compose.yml`](docker-compose.yml) и условный **`--disable-custom-all-reduce`** в [`configs/vllm/serve.sh`](configs/vllm/serve.sh). |
| 1.8.1 | Дефолт **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=0`** (custom all-reduce без флага); `1` — **NCCL**; документация и [`qwen3.6-27b.env`](configs/models/qwen3.6-27b.env) без дублирования `0`. |
| 1.8.2 | Снова дефолт **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=1`** (NCCL): на vLLM 0.19 + Qwen3.6 custom all-reduce даёт **`custom_all_reduce.cuh` / `invalid argument`** при graph capture; troubleshooting в README. |

### Документация и gpt-oss (исправления)

| Коммит | Суть |
|--------|------|
| `214b2bc` | **README**: полное описание (архитектура, конфигурация, скрипты, мониторинг, troubleshooting). |
| `3a664eb` | **gpt-oss**: **`TOOL_CALL_PARSER=openai`** (Hermes давал `TypeError` с `token_ids`); имя модели в API **`openai/gpt-oss-120b`**; **`GPU_MEM_UTIL=0.9296`**; **`BENCH_MODEL_NAME`**; строки в README troubleshooting. |
| `7b3254e` | **`VLLM_MAX_NUM_BATCHED_TOKENS`** в compose (дефолт 8192); в пресете gpt-oss **16384** для пропускной способности; документация в README и `.env.example`. |

### Рефакторинг CLI (после плана)

| Изменение | Суть |
|-----------|------|
| `./slgpu` | Единый диспетчер: `prepare`, `pull`, `up`, `down`, `restart`, `bench`, `ab`, `compare`, `logs`, `status`, `config`, `help`. |
| `scripts/cmd_*.sh` | Логика бывших `up.sh`, `bench.sh`, `download-model.sh`, `prepare-host.sh`, `healthcheck.sh`. |
| `./slgpu pull <HF_ID>` | Автогенерация `configs/models/<slug>.env`, опции `--tp`, `--max-len`, парсеры и т.д. |
| Корневой `.env` | Только server-level (пути, мониторинг); параметры модели только в пресете. |
| `docker-compose.yml` | **`gpus: all`**, маска GPU через **`NVIDIA_VISIBLE_DEVICES`** (по умолчанию `0,…,TP-1` из [`./slgpu up`](scripts/cmd_up.sh)); блок **`environment`** для vLLM/SGLang; **json-file** логи 100m×5. |
| Пресеты в репо | Минимум: `qwen3.6-27b`, `qwen3.6-35b-a3b`, `qwen3-30b-a3b`; остальные модели — через `./slgpu pull`. |
| README | Раздел рецептов **8× H200** (Qwen3.6, Kimi-K2.6, MiniMax, GLM, gpt-oss). |
| Образы compose | Prometheus, Grafana, **node-exporter** на **`latest`** (вместе с vLLM/SGLang/dcgm); в README — про воспроизводимость и pin digest/тега. |
| Исполняемый бит | В git для **`slgpu`** и **`scripts/cmd_*.sh`** — **100755**. |
| vLLM 0.19+ и `Unknown VLLM_*` | Служебные переменные listen/batch переименованы в **`SLGPU_VLLM_HOST`**, **`SLGPU_VLLM_PORT`**, **`SLGPU_MAX_NUM_BATCHED_TOKENS`** (`vllm.env`, `serve.sh`, compose); на хосте compose по-прежнему подхватывает **`VLLM_MAX_NUM_BATCHED_TOKENS`** как fallback для старых пресетов. |

---

## Вне git (контекст разработки)

- Планировался **A/B** vLLM vs SGLang на модели вроде **Qwen/Qwen3.6-35B-A3B**, единый порт API **8111**, модели в **`/opt/models`** (сейчас по умолчанию **TP=8** на 8 GPU).
- Решались инциденты: **утечка HF-токена** в истории (история переписана, токен отозвать), **`ContextOverflowError`** (окно и адаптивный бенч), доступ к **Grafana** снаружи.
- Пользовательские пожелания: **thinking Qwen3**, **co-run по 2 GPU**, **универсальные скрипты без правки `.env` под каждую модель** (пресеты), **полный README**, **ускорение gpt-oss**, **запись истории** (этот файл).

---

## Как обновлять этот файл

После значимых изменений добавляйте строку в таблицу хронологии и при необходимости абзац в раздел «Зачем проект» или «Вне git».

Формат коммита для истории:

```text
краткая тема: что сделано и зачем (1 строка)
```
