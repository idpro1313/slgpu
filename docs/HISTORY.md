# История проекта slgpu

Каноничный файл: **полная хронология репозитория** (цели, таблицы версий, аналитика, приложение `git log`) и **журнал итераций агентов** (правило *project-history*). Корневой `HISTORY.md` оставлен как короткий указатель на этот документ.

---

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
| 1.8.0 | Пресет [**`configs/models/qwen3.6-27b.env`**](../configs/models/qwen3.6-27b.env) (throughput: **`SLGPU_MAX_NUM_BATCHED_TOKENS=16384`**, **`GPU_MEM_UTIL=0.9262`**, опционально **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE`**); переменная **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE`** в [`docker-compose.yml`](../docker-compose.yml) и условный **`--disable-custom-all-reduce`** в `serve.sh` (см. [`scripts/serve.sh`](../scripts/serve.sh)). |
| 1.8.1 | Дефолт **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=0`** (custom all-reduce без флага); `1` — **NCCL**; документация и [`qwen3.6-27b.env`](../configs/models/qwen3.6-27b.env) без дублирования `0`. |
| 1.8.2 | Снова дефолт **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=1`** (NCCL): на vLLM 0.19 + Qwen3.6 custom all-reduce даёт **`custom_all_reduce.cuh` / `invalid argument`** при graph capture; troubleshooting в README. |
| 1.9.0 | Пресет [`configs/models/glm-5.1.env`](../configs/models/glm-5.1.env), эвристика **pull**: **zai-org/GLM*** → `MAX_MODEL_LEN=202752`, `KV_CACHE_DTYPE=auto` (разреженная MLA+DSA несовместима с fp8 KV в vLLM 0.19); README и troubleshooting. |
| 1.9.1 | **GLM-5.1:** в пресете `MAX_MODEL_LEN=131072`, `GPU_MEM_UTIL=0.88` (OOM `SharedFusedMoE` на 8×~140 GB); README / `configs/models/README.md` / troubleshooting. |
| 1.9.2 | **GLM-5.1:** пресет **65536** / **0.82** / **4096** batched, **`SLGPU_ENABLE_PREFIX_CACHING=0`**; в **`serve.sh`** опциональное отключение prefix cache; vllm.env, README, troubleshooting. |
| 1.9.3 | **`serve.sh`:** при `SLGPU_ENABLE_PREFIX_CACHING=0` — **`--no-enable-prefix-caching`** (vLLM 0.19 по умолчанию включает кэш; раньше флаг не отключался). README troubleshooting. |
| 1.9.4 | **GLM-5.1:** в пресете **`GPU_MEM_UTIL=0.75`** (OOM `SharedFusedMoE` при 0.82: vLLM просит снизить util, чтобы освободить память под веса). |
| 1.9.5 | **`docker-compose.yml` (vLLM):** **`SLGPU_ENABLE_PREFIX_CACHING`** в `environment` — иначе из пресета в контейнер не попадала; `serve.sh` видел дефолт `1` → в логах оставалось `enable_prefix_caching: True`. |
| 1.10.0 | **GLM-5.1-FP8:** пресет [`configs/models/glm-5.1-fp8.env`](../configs/models/glm-5.1-fp8.env); `serve.sh` — **`CHAT_TEMPLATE_CONTENT_FORMAT`** → `--chat-template-content-format`; compose — **`VLLM_DOCKER_IMAGE`**, **`CHAT_TEMPLATE_CONTENT_FORMAT`**; `_lib.sh` — HF id с **FP8** → tool **`glm47`**; README, `.env.example`. |
| 1.11.0 | **MiniMax-M2.7:** пресет [`configs/models/minimax-m2.7.env`](../configs/models/minimax-m2.7.env) ([рецепт](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md) — **TP4**, **TP4+EP** на 8×GPU, **`--compilation-config`**); `serve.sh` / compose — **`SLGPU_VLLM_COMPILATION_CONFIG`**, **`SLGPU_ENABLE_EXPERT_PARALLEL`**, **`SLGPU_VLLM_DATA_PARALLEL_SIZE`**; **`slgpu_guess_max_model_len`** — **200704** для `MiniMaxAI/MiniMax*`. |
| 1.11.1 | **`pull`:** только скачивание весов, **без** создания `configs/models/*.env`; обновлены README, `configs/models/README.md`, справка. |
| 1.11.2 | **`up`:** убрано ожидание `GET /v1/models` (пуллинг API); README, `grace` M-UP, `.env.example` (удалён `SLGPU_UP_READY_ATTEMPTS`). |
| 2.0.0 | **CLI:** удалены команды **`ab`**, **`compare`**, **`logs`**, **`status`**, **`config`**; соответствующие `cmd_*.sh`. Внешняя A/B-сводка ранее: `compare.py` (сам скрипт удалён в 2.0.15). README, GRACE, `configs/models/README.md`. |
| 2.0.1 | **`_lib.sh`:** удалена **`slgpu_guess_parsers`** — парсеры только из пресета; GRACE, `configs/models/README.md`. |
| 2.0.2 | **`_lib.sh`:** удалена **`slgpu_guess_max_model_len`** — **`MAX_MODEL_LEN`** только из пресета; GRACE, `configs/models/README.md`. |
| 2.0.3 | **`_lib.sh`:** удалена **`slgpu_gen_preset_file`** (не вызывалась); GRACE, `configs/models/README.md`, журналы. |
| 2.0.4 | **`-m` без пресета:** вывод списка пресетов (`slgpu_fail_if_missing_preset_arg`); `cmd_up` и др. |
| 2.0.5 | **GRACE / `docs/AGENTS.md`:** сценарии pull/up, риск парсеров, контракт M-PULL, версии XML. |
| 2.0.6 | Дефолты в `main.env`, `slgpu_source_main_env` в `_lib.sh`; README, compose, vllm/sglang env, GRACE. |
| 2.0.7 | **`main.env` в корне репозитория** (ранее `configs/main.env`); README, `_lib.sh`, GRACE. |
| 2.0.8 | **NCCL / PyTorch** в `main.env`; vllm/sglang `*.env` укорочены; `docker-compose` pass. |
| 2.0.9 | **`.env.example`:** без дублей с `main.env`; README, `main` шапка. |
| 2.0.10 | **`docker-compose.yml`:** `env_file: main.env`; комментарий про `--env-file`. |
| 2.0.11 | **Без обязательного `.env`:** `_lib.sh`, compose, удалён `.env.example`; секреты — `main.env` / `export`. |
| 2.0.12 | **Один `serve.sh` (тогда `configs/`, сейчас [`scripts/serve.sh`](../scripts/serve.sh)):** `SLGPU_ENGINE=vllm|sglang`; удалены `configs/vllm/serve.sh`, `configs/sglang/serve.sh`; compose, README, GRACE. |
| 2.0.13 | **Параметры из `vllm.env` / `sglang.env` в [`main.env`](../main.env);** удалены файлы движка; compose — только `env_file: main.env`; [`scripts/_lib.sh`](../scripts/_lib.sh) без `configs/<engine>.env`. |
| 2.0.14 | **[`scripts/serve.sh`](../scripts/serve.sh)** (был `configs/serve.sh`); compose монтирует `./scripts/serve.sh` → `/etc/slgpu/serve.sh`. |
| 2.0.15 | Удалён `scripts/compare.py` (A/B-сводка `bench/report.md`); README, `cmd_help`, GRACE. |
| 2.0.16 | **`serve` / `main`:** `SLGPU_VLLM_TRUST_REMOTE_CODE`, `SLGPU_VLLM_ENABLE_CHUNKED_PREFILL`, `SLGPU_VLLM_ENABLE_AUTO_TOOL_CHOICE` в `main.env`; SGLang — `MODEL_PATH` через **`SLGPU_MODEL_ROOT`**; `docker-compose` pass **`SLGPU_MODEL_ROOT`**, vLLM-флаги, **`SGLANG_TRUST_REMOTE_CODE`**. |
| 2.1.0 | **Мониторинг отдельно от движка:** [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml), сеть `slgpu` + **`./slgpu monitoring up|down|restart`**; **`./slgpu up`** — только vLLM/SGLang; **`./slgpu down --all`**, `_lib.sh`, README, [monitoring/README](../monitoring/README.md), GRACE. |
| 2.1.1 | **Prometheus/Grafana:** bind mount в **`PROMETHEUS_DATA_DIR`**, **`GRAFANA_DATA_DIR`** (по умолч. `/var/lib/slgpu/…`); миграция с named volume в [monitoring/README](../monitoring/README.md). |
| 2.1.2 | **Grafana bind mount:** `user: 472:0` в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml), на хосте **`chown -R 472:0`**; правка [monitoring/README](../monitoring/README.md) (ошибка 472:472), main.env. |
| 2.1.3 | **Prometheus:** `user: 65534:65534`, **`chown -R 65534:65534`** на `PROMETHEUS_DATA_DIR` (fix `queries.active` / mmap panic); [monitoring/README](../monitoring/README.md), main.env. |
| 2.1.4 | **`./slgpu monitoring fix-perms`**, [`scripts/monitoring_fix_permissions.sh`](../scripts/monitoring_fix_permissions.sh) (uid:gid из образов); в compose **убраны** жёсткие `user:` у Prom/Grafana; [monitoring/README](../monitoring/README.md), README, main.env. |
| 2.1.5 | Дефолт **`PROMETHEUS_DATA_DIR` / `GRAFANA_DATA_DIR`**: `/opt/mon/prometheus`, `/opt/mon/grafana` (ранее `/var/lib/slgpu/…`). |
| 2.1.6 | SGLang Grafana: **Model** — `includeAll` + `allValue: ".*"` в `sglangdash2-slgpu` / `sglang-dashboard-slgpu` (без пустого `model_name`); [monitoring/README](../monitoring/README.md). |
| 2.1.7 | **Документация:** полный обзор `git log` (приложение ниже), эпоха 20.04–22.04.2026 между «ранними» коммитами и нумерованными релизами, раздел **«Диалоги и инциденты запуска»** (транскрипты сессий Cursor + соответствие правкам в репо). |
| 2.1.8 | **Аналитика в `HISTORY.md`:** крупный раздел **«что делали → что произошло → что поменяли»** — vLLM `SLGPU_*`, KV Qwen, custom AR Qwen3.6, tool parsers, gpt-oss, Kimi, пошагово GLM-5.1 (262k→202k, fp8 KV, MoE OOM, prefix cache, compose), MiniMax, порты SGLang/compose, мониторинг (uid, mmap, Grafana variables), CLI 2.0, бенч; **шпаргалка** по файлам. |
| 2.1.9 | **Мониторинг / vLLM Grafana V2:** в [monitoring/README.md](../monitoring/README.md) — раздел **«vLLM V2: все панели No data»** (чеклист: только vLLM vs SGLang, Targets UP, `curl /metrics`, опционально **`VLLM_USE_V1=0`**, трафик); в [main.env](../main.env) — закомментированный **`VLLM_USE_V1=0`** и ссылка на vLLM #16348. |
| 2.1.10 | **Prometheus снаружи:** [main.env](../main.env) — **`PROMETHEUS_BIND=0.0.0.0`** (предупреждение: UI/API без auth); [docker-compose.monitoring.yml](../docker-compose.monitoring.yml) — fallback `0.0.0.0`; [monitoring/README.md](../monitoring/README.md), [README.md](../README.md), `cmd_prepare.sh`, `cmd_monitoring.sh`. |
| 2.1.11 | **Скрейп vLLM/SGLang:** [prometheus.yml](../monitoring/prometheus.yml) — `host.docker.internal` + relabel `instance` → `vllm:8111` / `sglang:8222` (обход DNS *lookup vllm* между compose-проектами); [docker-compose.monitoring.yml](../docker-compose.monitoring.yml) — `extra_hosts` у Prometheus; [monitoring/README.md](../monitoring/README.md). |
| 2.2.0 | **Пресет DeepSeek-V4-Flash:** [`configs/models/deepseek-v4-flash.env`](../configs/models/deepseek-v4-flash.env); таблица парсеров в [configs/models/README.md](../configs/models/README.md). |
| 2.2.1 | **DeepSeek-V4-Flash:** `MAX_MODEL_LEN=393216` (384K) в [deepseek-v4-flash.env](../configs/models/deepseek-v4-flash.env). |
| 2.2.2 | **DeepSeek-V4-Flash:** `KV_CACHE_DTYPE=auto` в [deepseek-v4-flash.env](../configs/models/deepseek-v4-flash.env). |
| 2.3.0 | **Пресет DeepSeek-V4-Pro:** [`configs/models/deepseek-v4-pro.env`](../configs/models/deepseek-v4-pro.env). |

### Документация и gpt-oss (исправления)

| Коммит | Суть |
|--------|------|
| `214b2bc` | **README**: полное описание (архитектура, конфигурация, скрипты, мониторинг, troubleshooting). |
| `3a664eb` | **gpt-oss**: **`TOOL_CALL_PARSER=openai`** (Hermes давал `TypeError` с `token_ids`); имя модели в API **`openai/gpt-oss-120b`**; **`GPU_MEM_UTIL=0.9296`**; **`BENCH_MODEL_NAME`**; строки в README troubleshooting. |
| `7b3254e` | **`VLLM_MAX_NUM_BATCHED_TOKENS`** в compose (дефолт 8192); в пресете gpt-oss **16384** для пропускной способности; документация в README и `.env.example`. |

### Рефакторинг CLI (после плана)

| Изменение | Суть |
|-----------|------|
| `./slgpu` | Единый диспетчер: `prepare`, `pull`, `up`, `down`, `restart`, `bench`, `load`, `help` (v2.0.0 — убраны `ab`, `compare`, `logs`, `status`, `config`). |
| `scripts/cmd_*.sh` | Логика бывших `up.sh`, `bench.sh`, `download-model.sh`, `prepare-host.sh`, `healthcheck.sh`. |
| `./slgpu pull` | Только `hf download`; пресет не создаётся. При существующем `configs/models/<slug>.env` — загрузка по полям из файла. |
| `main.env` + пресет | Server-level в `main.env`; параметры модели только в пресете. |
| `docker-compose.yml` | **`gpus: all`**, маска GPU через **`NVIDIA_VISIBLE_DEVICES`** (по умолчанию `0,…,TP-1` из [`./slgpu up`](../scripts/cmd_up.sh)); блок **`environment`** для vLLM/SGLang; **json-file** логи 100m×5. |
| Пресеты в репо | Минимум: `qwen3.6-27b`, `qwen3.6-35b-a3b`, `qwen3-30b-a3b`; остальные модели — через `./slgpu pull`. |
| README | Раздел рецептов **8× H200** (Qwen3.6, Kimi-K2.6, MiniMax, GLM, gpt-oss). |
| Образы compose | Prometheus, Grafana, **node-exporter** на **`latest`** (вместе с vLLM/SGLang/dcgm); в README — про воспроизводимость и pin digest/тега. |
| Исполняемый бит | В git для **`slgpu`** и **`scripts/cmd_*.sh`** — **100755**. |
| vLLM 0.19+ и `Unknown VLLM_*` | Служебные переменные listen/batch переименованы в **`SLGPU_VLLM_HOST`**, **`SLGPU_VLLM_PORT`**, **`SLGPU_MAX_NUM_BATCHED_TOKENS`** (`vllm.env`, `serve.sh`, compose); на хосте compose по-прежнему подхватывает **`VLLM_MAX_NUM_BATCHED_TOKENS`** как fallback для старых пресетов. |

---

## Аналитика: «что делали → что произошло → что поменяли»

Ниже — развёрнутые сценарии для статьи: **контекст**, **симптом/ошибка**, **механизм**, **артефакты в репо** (файлы, переменные, флаги CLI). Сводные таблицы по GLM/Qwen/мониторингу — в отдельном разделе **«Диалоги (сессии Cursor)…»** ниже по этому файлу.

### vLLM 0.19+ и «неизвестные» переменные окружения

- **Делали:** в `.env` / пресете задавали **`VLLM_HOST`**, **`VLLM_PORT`**, **`VLLM_MAX_NUM_BATCHED_TOKENS`** (или аналоги), ожидая, что vLLM их «поймёт» по префиксу.
- **Произошло:** в логах vLLM **0.19+** предупреждения вроде *Unknown / unsupported environment variable* для префикса `VLLM_*`, потому что движок **не** экспортируемые в контейнер переменные сканирует и ругается на незарегистрированные имена; часть настроек должна идти **только** через `vllm serve` (аргументы, не «магия» env).
- **Поменяли:** в [`scripts/serve.sh`](../scripts/serve.sh) и [`docker-compose.yml`](../docker-compose.yml) — служебные вещи переименованы в **`SLGPU_VLLM_HOST`**, **`SLGPU_VLLM_PORT`**, **`SLGPU_MAX_NUM_BATCHED_TOKENS`**; в compose оставлен **fallback** `VLLM_MAX_NUM_BATCHED_TOKENS` для старых пресетов. Коммит `36d56f7` (см. таблицу «Рефакторинг CLI»).

### Qwen3 Next: тип KV — не «любой fp8»

- **Делали:** для экономии VRAM тянули **KV fp8**; пробовали варианты, близкие к `fp8_e5m2`.
- **Произошло:** **assert** / поломка attention / Dynamo (зависит от сборки) при **`KV_CACHE_DTYPE=fp8_e5m2`**; для Qwen3 Next в карточке и vLLM стабильнее **`fp8_e4m3`**.
- **Поменяли:** дефолт в цепочке env → **`KV_CACHE_DTYPE=fp8_e4m3`** (`235e4c3`); комментарии в `main.env` / пресетах, troubleshooting в README. Бенч: [`scripts/bench_openai.py`](../scripts/bench_openai.py) уважает **`MAX_MODEL_LEN`** и ужимает **`max_tokens`** (`e22cb3e`), чтобы не ловить переполнение окна.

### Qwen3.6-27B: custom all-reduce и graph capture

- **Делали:** `TP=8`, custom all-reduce vLLM **включён** (`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=0`) — ожидание низкой латентности all-reduce.
- **Произошло:** при **CUDA graph capture** / инициализации движка — падения из **`vllm/model_executor/layers/custom_all_reduce.cuh`** с сообщениями в духе **`invalid argument`**, `WorkerProc` / `EngineCore` не дожидается готовности воркеров.
- **Поменяли:** флаг в [`scripts/serve.sh`](../scripts/serve.sh): при **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=1`** добавляется **`--disable-custom-all-reduce`** (обход через **NCCL**). Итерация версий: **1.8.0** (пресет + переменная в compose) → **1.8.1** дефолт `0` → **1.8.2** снова дефолт **`1`** как практичный default для 0.19 + Qwen3.6. Пресет: [`configs/models/qwen3.6-27b.env`](../configs/models/qwen3.6-27b.env).

### Qwen3.6-27B: tool calling и несовместимость `hermes` parser

- **Делали:** `TOOL_CALL_PARSER=hermes` (как у классического Qwen2.5 / JSON tool schema).
- **Произошло:** модель (ветка Qwen3.6 / Coder) эмитит **XML-инструменты**; `hermes_tool_parser` ждёт JSON → **`JSONDecodeError`**, бесконечный стрим для клиента, **таймаут** на tool round-trip.
- **Поменяли:** **`TOOL_CALL_PARSER=qwen3_xml`** (альтернатива в комментариях: `qwen3_coder`). Версия **1.8.3**, тот же пресет + [`configs/models/README.md`](../configs/models/README.md).

### gpt-oss-120b: tool parser и пропускная способность

- **Делали:** `TOOL_CALL_PARSER=hermes` (или близкое) для tool-enabled сценариев.
- **Произошло:** **`TypeError`** вокруг `token_ids` (несовпадение ожидаемого формата Hermes с фактическим выводом gpt-oss); для бенча нужна консистентная строка **имени модели** в запросе vs сервер.
- **Поменяли:** **`TOOL_CALL_PARSER=openai`**, в API / бенче ориентир **`openai/gpt-oss-120b`**, поднят **`GPU_MEM_UTIL=0.9296`**, введён **`BENCH_MODEL_NAME`**, в compose — лимит **`VLLM_MAX_NUM_BATCHED_TOKENS`** (в пресете gpt-oss **16384** для throughput) — коммиты `3a664eb`, `7b3254e`.

### Kimi-K2.6: вес MoE, OOM, remote code (vLLM и SGLang)

- **Делали:** запуск `moonshotai/Kimi-K2.6` на **4×140 GB** или 8×H200; ожидание «подкрутить только KV / batch».
- **Произошло:** **OOM** ещё на фазе загрузки / размещения весов; на **4×140 GB** упирались **в лимит размера модели**, а не в тонкую настройку KV. Для HF-моделей с custom tokenizer / кода в репо — vLLM/SGLang требуют **`--trust-remote-code`**.
- **Поменяли (vLLM):** `SLGPU_VLLM_TRUST_REMOTE_CODE` / путь в `serve` к **`MODEL_ID`**, **`PYTORCH_ALLOC_CONF`** с **`expandable_segments:True`**, снижение **GPU mem**, отключение profiler CUDA graphs для стабильности — `8fa0bce`, `d7326a2`, `291e00a`, референс Moonshot `c4955b8`. **SGLang:** `SGLANG_TRUST_REMOTE_CODE`, **`PYTORCH_CUDA_ALLOC_CONF`** для MoE — `c01bb74`, `accef7f`. Док: «OOM на 4×140 = weight limit» — `f5c5471`.

### GLM-5.1 (zai-org/GLM-5.1, bf16): пошаговая эскалация инцидентов

1. **Контекст 262144 vs `config.json`**
   - *Делали:* выставляли **`MAX_MODEL_LEN=262144`** (как у Qwen long-context), либо тянули дефолт **pull** для длинного окна.
   - *Произошло:* vLLM валидатор сравнивает с **`max_position_embeddings`** в **`config.json`** весов (**≈202752**); Pydantic / argparse отвергает **`--max-model-len`**, если оно **выше** «родного» RoPE-лимита (сообщение указывает на **`VLLM_ALLOW_LONG_MAX_MODEL_LEN`** как небезопасный override).
   - *Поменяли:* для **`zai-org/GLM*`** в логике **pull** / доках — **202752**; пресет [`configs/models/glm-5.1.env`](../configs/models/glm-5.1.env) (см. `MAX_MODEL_LEN`).

2. **Sparse MLA + `KV_CACHE_DTYPE=fp8_e4m3`**
   - *Делали:* оставляли глобальный дефолт **fp8_e4m3** для KV (как для Qwen3 Next) после `pull` без ручного `--kv-dtype auto`.
   - *Произошло:* **`ValueError: No valid attention backend`**, в логе — связка **`FLASHMLA_SPARSE`** и **`kv_cache_dtype not supported`** (ни один backend vLLM 0.19.x не сочетает sparse MLA+DSA с **fp8** KV).
   - *Поменяли:* **`KV_CACHE_DTYPE=auto`** в пресете; в **`cmd_pull`** для **`zai-org/GLM*`** — автоматически **`KV=auto`**, unless явный **`--kv-dtype`**. **Версия 1.9.0** (`1f62104`).

3. **OOM `SharedFusedMoE` / `unquantized_fused_moe` при 202k и высоком util**
   - *Делали:* **`MAX_MODEL_LEN=202752`**, **`GPU_MEM_UTIL=0.92`–0.95**, **`SLGPU_MAX_NUM_BATCHED_TOKENS=24576`**.
   - *Произошло:* **CUDA OOM** в **`SharedFusedMoE`**, **`torch.empty`** при создании весов expert-слоёв; рекомендация vLLM: снизить **`--gpu-memory-utilization`**, уменьшить окно и/или **prefix cache** (съедает пул под KV/буферы).
   - *Поменяли (итеративно):* **1.9.1** — **`131072`**, **`0.88`**; **1.9.2** — **`65536`**, **`0.82`**, **`4096` batched**, **`SLGPU_ENABLE_PREFIX_CACHING=0`**; **1.9.3** — в `serve` при `0` флаг **`--no-enable-prefix-caching`** (в vLLM 0.19 prefix cache **включён по умолчанию**, просто «не передавать» флаг = кэш остаётся **включённым**); **1.9.4** — **`GPU_MEM_UTIL=0.75`**; **1.9.5** — переменная **`SLGPU_ENABLE_PREFIX_CACHING`** добавлена в **`docker-compose.yml` → `environment` сервиса `vllm`**, иначе пресет с хоста **не** попадал в контейнер и `serve.sh` брал **дефолт `1`**.

4. **GLM-5.1-FP8 (отдельный чекпоинт)**
   - *Делали:* перейти на **`zai-org/GLM-5.1-FP8`**, сменить **Docker-образ** (рецепт vLLM GLM5.md).
   - *Поменяли:* пресет [`configs/models/glm-5.1-fp8.env`](../configs/models/glm-5.1-fp8.env), **`VLLM_DOCKER_IMAGE`**, **`CHAT_TEMPLATE_CONTENT_FORMAT=string`**, `TOOL`/`REASON` **`glm47`** / **`glm45`**, `serve` — флаг **`--chat-template-content-format`**. **Версия 1.10.0** (`d8bfc79`).

### MiniMax-M2.7: рецепт vLLM ≠ «голый TP8»

- **Делали:** `TP=8` на 8 GPU «по привычке».
- **Произошло:** [рецепт vLLM](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md) требует на 8×GPU **TP4 + expert parallel (EP)** и **`--compilation-config`**; маска **`NVIDIA_VISIBLE_DEVICES`** на **все** карты при EP; **200704** max len по карточке/рецепту.
- **Поменяли:** [`configs/models/minimax-m2.7.env`](../configs/models/minimax-m2.7.env), переменные **`SLGPU_VLLM_COMPILATION_CONFIG`**, **`SLGPU_ENABLE_EXPERT_PARALLEL`**, **`SLGPU_VLLM_DATA_PARALLEL_SIZE`**, pass в [`docker-compose.yml`](../docker-compose.yml) и [`scripts/serve.sh`](../scripts/serve.sh). **1.11.0** (`937422a`).

### Сеть и порты: внешний `LLM_API_PORT` vs внутри контейнера

- **Делали:** `./slgpu up sglang -m kimi-k2.6 -p 8222` — ожидание, что **и** healthcheck, **и** `curl` **внутри** контейнера ходят на **8222**.
- **Произошло:** в compose проброс **`${LLM_API_PORT:-8222}:8222`**: **хост 8222 → контейнер 8222** (SGLang). Внутри **`SGLANG_LISTEN_PORT`** (часто **8222** в `main.env` для sglang-профиля) должен **совпадать** с целевым портом образа. Путаница: **`curl` к `127.0.0.1:8111` внутри sglang-контейнера** при том, что слушатель на **8222** → *connection refused*; снаружи **Connection reset** при обращении, пока идут **Triton autotune** / **graph capture** (десятки минут) — **нормальная** фаза, не «сломанный» compose.
- **Поменяли:** **1.3.0** — `-p` / `LLM_API_PORT`; **1.4.3** — SGLang, метрики, Prometheus targets на **8222**; troubleshooting в [monitoring/README.md](../monitoring/README.md) (**instance:8222** для SGLang vs **8111** для vLLM в scrape).

### Мониторинг: права, mmap Prometheus, дашборды

- **Делали:** bind mount **`-v /path/grafana:/var/lib/grafana`**, **`-v /path/prometheus`**, запуск **от root** / случайные `chown`.
- **Произошло:** Grafana: **`GF_PATHS_DATA is not writable`**, плагины/БД; Prometheus **3.x**: **mmap** на TSDB, ошибки **`queries.active`**, **panic** при **root**-владельце файлов, созданных вне контейнера.
- **Поменяли:** **2.1.0** — отдельный [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml), сеть **`slgpu`**; **2.1.1** — bind; **2.1.2** — Grafana `user: 472:0`, **`chown -R 472:0`**, не 472:472; **2.1.3** — Prometheus `65534:65534` и **рекурсивный** chown; **2.1.4** — **`./slgpu monitoring fix-perms`**, снятие жёсткого `user:` из compose (uid из **реального** образа); **2.1.5** — дефолт **`/opt/mon/prometheus`**, **`/opt/mon/grafana`**.

- **Grafana: «No data» на панелях SGLang**
  - *Произошло:* variable **`model_name`** в JSON без корректного **«All»** / **`.*`**, или пустой label при отсутствии трафика.
  - *Поменяли:* **2.1.6** — в `sglangdash2-slgpu` / `sglang-dashboard-slgpu`: **`includeAll: true`**, **`allValue: ".*"`** (аналогия с уже исправленным **vllmdash2** в **1.5.4**).

- **vLLM дашборд пустой при работе только SGLang**
  - *Механизм:* **PromQL** `vllm:*` + `job="vllm"` — **нет** рядов, если не запущен scrape target **vllm** / нет запросов — не баг дашборда, а **отсутствие процесса vllm** или **модель не создаёт** label `model_name` до первого вызова.

### CLI 2.0: один `serve.sh`, `main.env`, отказ от лишнего

- **Делали:** много расслоений: `configs/vllm/vllm.env`, `sglang/sglang.env`, корневой **`.env`**, автогенерация пресетов в `pull`, команды `status`/`compare`/…
- **Поменяли:** единый [`scripts/serve.sh`](../scripts/serve.sh) с **`SLGPU_ENGINE`**, всё движковое в [**`main.env`**](../main.env) + **пресет**; **2.0.11** — без **обязательного** `.env` в корне; **1.11.1** — `pull` **без** автосоздания `configs/models/*.env`; **2.0.0** — урезан CLI. **`SLGPU_MODEL_ROOT`**: SGLang читает веса из примонтированного корня, совпадающего с vLLM.

### Бенчмарк: сеть, `no_content`, коды ошибок

- **Делали:** в SSE принимать только **truthy** `content` для учёта токенов.
- **Произошло:** vLLM отдаёт чанк с **`content: ""`** (служебный кадр) при наличии **`reasoning_content`** → сценарий бенчмарка помечал ответ как **`no_content`**, хотя HTTP 200.
- **Поменяли:** **1.2.1** — учёт пустой строки как «стрим начался»; **1.2.0** — `error_code` / `errors_breakdown` вместо «немых» **NaN** в сводке. **1.1.5+** — сверка **engine** (из compose) с флагом **`--engine`** / модель с `/v1/models`.

### Шпаргалка: ключевые файлы, где «живут» настройки

| Назначение | Файлы (типично) |
|------------|-----------------|
| Дефолты хоста / оба движка | [`main.env`](../main.env) |
| Параметры конкретной модели | [`configs/models/<preset>.env`](../configs/models/) |
| Сборка аргументов vLLM / SGLang | [`scripts/serve.sh`](../scripts/serve.sh) |
| Проброс в контейнер | [`docker-compose.yml`](../docker-compose.yml) |
| Сеть LLM + scrape | [monitoring/prometheus.yml](../monitoring/prometheus.yml), [monitoring/README.md](../monitoring/README.md) |
| Дашборды | [monitoring/grafana/provisioning/dashboards/json/](../monitoring/grafana/provisioning/dashboards/json/) |

---

## Промежуточная эпоха: 20.04–22.04.2026 (коммиты до нумерованных тегов 1.6+)

Период от первого `HISTORY.md` и расширения README до **1.5.x / 1.6.0** в git не дублирует каждую строку в таблице «Пресеты / версии» выше; смысловые группы:

| Тема | Коммиты (хронология) | Суть |
|------|----------------------|------|
| **Доки и диск** | `b204e5d` | Появление корневого `HISTORY.md` и ссылка в README. |
| **Node Exporter** | `77ed2c5`, `fb5c1f9` | Добавлен node-exporter для дашборда *Node Exporter Full*; `job=node-exporter` и troubleshooting. |
| **Prometheus** | `787cd44` | Named volume, retention, документация при заполнении диска. |
| **vLLM: remote code, Kimi, serve** | `8fa0bce`, `45e1d0f`, `d7326a2`, `291e00a`, `5f5e43a`, `f5c5471` | `--trust-remote-code`; пресет/доки Kimi-K2.6, OOM на 4×140 GB как лимит веса; `serve` с позиционным путём к модели; снят дублирующий `serve` (ENTRYPOINT образа = `vllm serve`); уточнение про вес, не только KV. |
| **SGLang: remote code, MoE alloc** | `c01bb74`, `accef7f` | `--trust-remote-code`; `PYTORCH_CUDA_ALLOC_CONF` для MoE, OOM Kimi в SGLang. |
| **Custom all-reduce** | `0be5328` | `--disable-custom-all-reduce` (gpt-oss и др., обход `invalid argument` в custom AR). |
| **Упрощение стенда** | `c8dd602` | Один порт 8111, без co-run и systemd, комментарии в конфигах. |
| **Unified CLI** | `c018bd3`, `d3c0d06`, `da808f4`, `a7a12a9` | `./slgpu`, pull с автогенерацией пресетов (позже отключена в 1.11.1), обновлённый compose, исполняемость, доки про `latest` образов. |
| **TP=8** | `5a63468` | Дефолт **TP=8** в `serve.sh`, пресетах, pull, README. |
| **SLGPU_* / vLLM 0.19** | `36d56f7` | Переименование переменных, чтобы убрать предупреждения `Unknown VLLM_*`. |
| **Kimi-K2.6** | `c4955b8`, `6aca9bb`, `6a7c768` | Выровнено с референсом Moonshot; эвристика `MAX_MODEL_LEN` в pull; для Kimi 262k как у других long-context. |
| **GRACE + bench load** | `ba91d5e` … `629e3f7` | Каркас GRACE; `bench_load` (1.1.x), burst, валидация engine/model, фиксы SSE/race, отчёты Kimi. |
| **Сеть и SGLang** | `0294dfd`–`0d42151` | Порт наружу `-p`, `LLM_API_PORT`, SGLang 8222, метрики, кэш ядер, комментарии в `.env`, troubleshooting Grafana (instance 8222 vs 8111), дашборд `sglangdash2-slgpu` по мотивам vLLM V2. |
| **Grafana** | `3a664eb` area … `3563023` | README про дашборды; sync GRACE; `vllmdash2` — datasource `prometheus`, переменные **Instance / Model** с `includeAll` и `job="vllm"`. |
| **TP и GPU** | `e2f9a94`, `1319908` | Флаг `--tp` для up/restart; `NVIDIA_VISIBLE_DEVICES` от TP без жёсткого `device_ids` в compose. |

---

## Диалоги (сессии Cursor) и инциденты при запуске моделей

Сводка по **транскриптам** в `agent-transcripts` и по итерациям, отражённым в коммитах 1.8.x–2.1.x. Настройки — из пресетов [`configs/models/`](../configs/models/); движок **vLLM 0.19.x**, стенд **8× H200** / **TP=8**, если не оговорено иное.

### GLM-5.1 (zai-org/GLM-5.1)

| Симптом / ошибка | Условия (настройки) | Что сделали в репо / вывод |
|------------------|---------------------|---------------------------|
| Pydantic / валидация `max_model_len` | `MAX_MODEL_LEN=262144` при `max_position_embeddings` / RoPE **202752** в `config.json` | Согласовать окно с конфигом весов: **202752**; опционально `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1` (риск NaN/_oob). Эвристика `pull` для `zai-org/GLM*`, README. |
| `ValueError: No valid attention backend` / `FLASHMLA_SPARSE: [kv_cache_dtype not supported]` | Дефолтный для Qwen **`KV_CACHE_DTYPE=fp8_e4m3`** + sparse MLA / DSA | **KV_CACHE_DTYPE=auto** в пресете; в `cmd_pull` — авто **`KV=auto`** для `zai-org/GLM*`, ручной `--kv-dtype` помечается флагом. |
| OOM / `SharedFusedMoE` / `unquantized_fused_moe` | Полное окно 202752 + высокий **GPU_MEM_UTIL** (0.88–0.95), MoE | Пошаговое **сжатие**: 1.9.1 **131072 / 0.88**; 1.9.2 **65536 / 0.82 / batch 4096** + `SLGPU_ENABLE_PREFIX_CACHING=0`; 1.9.3 явный **`--no-enable-prefix-caching`**; 1.9.4 **0.75**; 1.9.5 проброс `SLGPU_ENABLE_PREFIX_CACHING` в **compose** (иначе в контейнере оставался дефолт vLLM). |
| `enable_prefix_caching: True` при `=0` в пресете | Переменная не попадала в контейнер vLLM | Исправление `docker-compose.yml` (1.9.5). |
| User-generated `pull` снова **fp8_e4m3** | Старый шаблон pull перезатёр `KV` | Пояснения в README; пресет в репо закрепляет **auto**; сессия: ручная правка после pull. |

### Qwen3.6-27B

| Симптом | Условия | Что сделали |
|---------|---------|-------------|
| `custom_all_reduce.cuh` / **`invalid argument`** при graph capture | vLLM 0.19 + Qwen3.6, custom all-reduce | Дефолт **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=1`** (NCCL); итерации 1.8.0–1.8.2. |
| Таймауты **tool calling**, `JSONDecodeError` / зависание стрима | `TOOL_CALL_PARSER=hermes` | **1.8.3:** `TOOL_CALL_PARSER=qwen3_xml` (Qwen3.6 ветка Coder, XML-инструменты, не JSON Hermes). |

### Мониторинг (Grafana / Prometheus)

| Симптом | Условия | Что сделали |
|---------|---------|-------------|
| «No data» / пустой **Model** на SGLang | Переменная `model_name` без `includeAll` / пустой лейбл | **2.1.6:** `includeAll` + `allValue: ".*"` в `sglangdash2-slgpu` и `sglang-dashboard-slgpu`. |
| «No data» на **vLLM V2** | Только SGLang запущен, или target **down**, или нет трафика / не тот `job` | **1.5.3–1.5.4:** дашборд vLLM: datasource, `job="vllm"`, `instance`/`model_name` с `All`. Если крутится только SGLang — метрик `vllm:*` нет (ожидаемо). |
| Ошибки прав на данные Grafana | Bind mount, uid не **472:0** | 2.1.2, затем **2.1.4** `fix-perms` и снятие жёсткого `user:` в compose. |
| Prometheus **mmap** / `queries.active` | Данные на хосте с **root**-файлами | chown **65534**; 2.1.4 — автоматизировано `fix-perms`. |

### Прочее (кратко)

- **gpt-oss:** `TOOL_CALL_PARSER=openai` (Hermes + `token_ids` → TypeError), имя в API, пропускная способность — см. коммиты `3a664eb`, `7b3254e` и таблицу «Документация и gpt-oss».
- **Kimi-K2.6 (vLLM):** OOM → trust-remote-code, ужатие памяти, `PYTORCH_ALLOC_CONF`, отдельно от KV — см. `d7326a2`–`291e00a` и референс Moonshot `c4955b8`.
- **Бенч / load:** ложный `no_content` при пустом `content` в SSE — `1.2.1`; валидация engine+модель — `1.1.5+`.
- **SGLang + внешний порт / Kimi (диалоги 22.04):** путаница **хост `8222` → контейнер** vs внутренний **`SGLANG_LISTEN_PORT` / `LLM_API_PORT` (часто 8111)**: `curl` на хост должен бить в проброшенный порт, внутри контейнера — в порт, на котором реально слушает процесс. Таймаут `up` / «ожидание `/v1/models`» и **`Connection reset` при 8222** — типично, пока идут **Triton autotune** и долгий **CUDA graph capture** (десятки минут); не ошибка конфига, а фаза прогрева. Отдельно встречались **падения scheduler при graph capture** на Kimi в SGLang — вне репо решались снижением/отключением graph, правками mem; см. релизы **1.4.x** (флаги graph, custom AR) и [monitoring/README](../monitoring/README.md) (instance **8222** для метрик SGLang vs **8111** API vLLM).

---

## Приложение: полный список коммитов (`main`, хронологически)

Ниже — **снимок** `git log --reverse` (от первого коммита к последней строке таблицы). После новых пушей пересоберите список командой в подвале — иначе таблица не включает свежие ревизии. Таблица выше сжимает смысл; дубликаты смотрите в SHA.

| Hash | Дата | Сообщение |
|------|------|-----------|
| `06abe8a` | 2026-04-20 | slgpu: vLLM/SGLang inference stand (no secrets in history) |
| `d0c0ece` | 2026-04-20 | chore: выставить исполняемость (100755) для scripts/*.sh |
| `9a9692a` | 2026-04-20 | fix script |
| `b9f3e28` | 2026-04-20 | git |
| `35cb079` | 2026-04-20 | fix: download-model.sh использует hf download вместо устаревшего huggingface-cli |
| `235e4c3` | 2026-04-20 | fix(vllm): KV fp8_e4m3 по умолчанию для Qwen3 Next (fp8_e5m2 ломает attention) |
| `5e537ec` | 2026-04-20 | fix(grafana): пустые каталоги plugins/alerting provisioning, пояснения в README |
| `e22cb3e` | 2026-04-20 | fix: MAX_MODEL_LEN=65536 по умолчанию + bench уважает окно и ужимает max_tokens |
| `cee515f` | 2026-04-20 | chore: дефолт MAX_MODEL_LEN=262144 (макс. окно Qwen3 Next) |
| `e5bc4a0` | 2026-04-20 | feat(grafana): внешний bind по умолчанию; пустые provisioning yaml вместо .gitkeep |
| `3c68062` | 2026-04-20 | feat(reasoning): включить thinking-режим Qwen3 (--reasoning-parser qwen3) |
| `91acd19` | 2026-04-20 | perf(vllm): включить VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS и поднять GPU_MEM_UTIL до 0.9242 |
| `fd417b1` | 2026-04-20 | feat(co-run): режим both — vLLM и SGLang одновременно по 2 GPU каждому |
| `52f7433` | 2026-04-20 | feat(presets): пресеты моделей и флаг -m в скриптах |
| `5966aaa` | 2026-04-20 | feat(presets): пресеты gpt-oss-120b, Kimi-K2.5, GLM-5.1, MiniMax-M2.7 |
| `214b2bc` | 2026-04-20 | docs(readme): полное описание проекта, архитектуры и рабочих процессов |
| `3a664eb` | 2026-04-20 | fix(gpt-oss): TOOL_CALL_PARSER=openai; GPU_MEM_UTIL 0.9296; BENCH_MODEL_NAME |
| `7b3254e` | 2026-04-20 | feat(vllm): VLLM_MAX_NUM_BATCHED_TOKENS для пропускной способности |
| `b204e5d` | 2026-04-20 | docs: HISTORY.md — хронология проекта и ссылка в README |
| `77ed2c5` | 2026-04-20 | monitoring: add node-exporter for Node Exporter Full dashboard |
| `787cd44` | 2026-04-20 | monitoring: prometheus volume, retention env, disk full docs |
| `8fa0bce` | 2026-04-20 | vllm: add --trust-remote-code for HF models with custom tokenizer code |
| `45e1d0f` | 2026-04-20 | docs: Kimi-K2.6 preset, vLLM WorkerProc/engine failure troubleshooting |
| `d7326a2` | 2026-04-20 | vllm: Kimi-K2.6 OOM defaults, PYTORCH_ALLOC_CONF expandable_segments |
| `291e00a` | 2026-04-20 | vllm: serve positional model path; Kimi-K2.6 tighter memory + disable cuda graph profiler |
| `5f5e43a` | 2026-04-20 | fix(vllm): do not duplicate 'serve' — image ENTRYPOINT is vllm serve |
| `f5c5471` | 2026-04-20 | docs: Kimi-K2.6 OOM on 4x140GB is weight limit, not KV tuning |
| `c01bb74` | 2026-04-20 | sglang: включить --trust-remote-code для моделей с custom HF code (Kimi-K2.x) |
| `accef7f` | 2026-04-20 | sglang: PYTORCH_CUDA_ALLOC_CONF для MoE; документация OOM Kimi в SGLang |
| `fb5c1f9` | 2026-04-20 | monitoring: job node-exporter для Node Exporter Full; раздел troubleshooting |
| `0be5328` | 2026-04-20 | vllm: --disable-custom-all-reduce (обход custom_all_reduce invalid argument, gpt-oss и др.) |
| `c8dd602` | 2026-04-21 | Упрощение стенда: один порт 8111, без co-run и systemd; комментарии в конфигах |
| `c018bd3` | 2026-04-21 | refactor: unified ./slgpu CLI, pull autogenerates presets, compose env for models |
| `d3c0d06` | 2026-04-21 | docker-compose.yml updated |
| `da808f4` | 2026-04-21 | chore: executable slgpu/cmd_*.sh; docs for compose latest images |
| `a7a12a9` | 2026-04-21 | docs(README): expand section 4 with per-command purpose table |
| `5a63468` | 2026-04-21 | defaults: TP=8 in serve.sh, presets, pull, and docs |
| `36d56f7` | 2026-04-21 | fix(vllm): use SLGPU_* env vars to avoid vLLM 0.19 unknown VLLM_* warnings |
| `c4955b8` | 2026-04-21 | feat(kimi-k2.6): align preset and serve with Moonshot reference |
| `6aca9bb` | 2026-04-21 | feat(pull): default MAX_MODEL_LEN via slgpu_guess_max_model_len (often 262144) |
| `6a7c768` | 2026-04-21 | fix(pull): Kimi-K2.6 default MAX_MODEL_LEN 262144 like other long-context models |
| `ba91d5e` | 2026-04-21 | 1.0.0: инициализация GRACE-фреймворка для slgpu |
| `662c82a` | 2026-04-21 | 1.1.0: длительный нагрузочный тест bench_load (200-300 виртуальных пользователей) |
| `165f78a` | 2026-04-21 | 1.1.1: обновлен README с описанием команды load и документацией bench_load |
| `4e020a8` | 2026-04-21 | 1.1.2: fix bench_load.py — race condition, delta RPS, preflight API check |
| `89e460f` | 2026-04-21 | 1.1.3: fix SSE parsing — delta.content='' no longer breaks TTFT |
| `c6600e6` | 2026-04-21 | 1.1.4: добавлен burst-режим (--burst) для макс нагрузки на 192 vCPU |
| `ca4b7ad` | 2026-04-21 | 1.1.5: автоопределение и валидация запущенного engine+model (bench/load) |
| `9994f66` | 2026-04-21 | 1.1.6: обновлён README — актуальная структура, описание load/bench с валидацией, фикс нумерации |
| `06a147c` | 2026-04-21 | 1.1.7: автоопределение engine из docker compose для bench/load |
| `71e5f52` | 2026-04-21 | 1.1.8: убрана валидация MODEL_ID — проверяется только engine |
| `31b64af` | 2026-04-21 | 1.1.9: -m <preset> сделан опциональным для bench/load |
| `f8725c1` | 2026-04-21 | 1.1.10: fix unbound variable MODEL_ID при отсутствии -m |
| `3d4eb0d` | 2026-04-21 | 1.1.11: fix 'local: can only be used in a function' |
| `629e3f7` | 2026-04-22 | 1.2.0: отчёт Kimi-K2.6, коды ошибок в bench_openai, compare err:code |
| `a8cee93` | 2026-04-22 | 1.2.1: парсинг SSE bench — content/reasoning, фикс no_content |
| `e7165d4` | 2026-04-22 | 1.2.2: отчёт — эталонный прогон 20260422_104802 Kimi scenario |
| `0294dfd` | 2026-04-22 | 1.3.0: флаг -p/--port для ./slgpu up (внешний порт API) |
| `4da131e` | 2026-04-22 | 1.3.1: явный LLM_API_PORT в docker compose, дольше wait API, диагностика |
| `a7208ad` | 2026-04-22 | 1.4.0: SGLang — флаги cuda graph; пресет kimi-k2.6 |
| `0d9ed55` | 2026-04-22 | 1.4.1: SGLang --disable-custom-all-reduce для сбоя custom AR при graph capture |
| `c8d37f8` | 2026-04-22 | 1.4.2: прокидывать SGLang-флаги пресета в compose (custom AR, graph) |
| `15418cc` | 2026-04-22 | 1.4.3: SGLang на 8222 (Prometheus, compose, дефолт up/bench/status) |
| `e04d5e3` | 2026-04-22 | 1.4.4: SGLang --enable-metrics по умолчанию для Grafana/Prometheus |
| `8e232b4` | 2026-04-22 | 1.4.5: том sglang-kernel-cache для Triton/TorchInductor autotune |
| `f4233aa` | 2026-04-22 | 1.4.6: уточнение TORCHINDUCTOR_FX_GRAPH_CACHE в sglang.env |
| `e920e0a` | 2026-04-22 | 1.4.7: комментарии к каждому параметру во всех .env и в генерации pull |
| `0d42151` | 2026-04-22 | 1.4.8: troubleshooting SGLang Grafana (instance 8222 vs 8111) |
| `09094a1` | 2026-04-22 | 1.4.9: SGLang Grafana slgpu: sglang: метрики, uid prometheus, переменные |
| `ce2036c` | 2026-04-22 | 1.5.0: Grafana SGLang-дашборд по мотивам vLLM V2 (sglangdash2-slgpu) |
| `a66534e` | 2026-04-22 | 1.5.1: README — дашборды Grafana (SGLang v1/V2, vllmdash2) |
| `36f7cd8` | 2026-04-22 | 1.5.2: синхронизация GRACE с дашбордами Grafana |
| `c269809` | 2026-04-22 | 1.5.3: vllmdash2 - datasource prometheus for provisioning |
| `3563023` | 2026-04-22 | 1.5.4: vllmdash2 - instance/Model All и job=vllm в запросах |
| `e2f9a94` | 2026-04-23 | 1.6.0: флаг --tp для up и restart (без правки пресета) |
| `1319908` | 2026-04-23 | 1.7.0: NVIDIA_VISIBLE_DEVICES от TP, без device_ids в compose |
| `291654c` | 2026-04-23 | 1.8.0: пресет qwen3.6-27b, SLGPU_DISABLE_CUSTOM_ALL_REDUCE |
| `3b00e1a` | 2026-04-23 | 1.8.1: SLGPU_DISABLE_CUSTOM_ALL_REDUCE по умолчанию 0 |
| `30acd89` | 2026-04-23 | 1.8.2: дефолт SLGPU_DISABLE_CUSTOM_ALL_REDUCE=1 (NCCL) |
| `7f11d38` | 2026-04-23 | 1.8.3: qwen3.6-27b — TOOL_CALL_PARSER hermes → qwen3_xml (фикс таймаутов tool calling) |
| `1f62104` | 2026-04-23 | 1.9.0: пресет GLM-5.1, pull: max_len 202752 и KV auto для zai-org/GLM* |
| `6739488` | 2026-04-23 | 1.9.1: GLM-5.1 — пресет 131k контекста и GPU_MEM 0.88 против OOM MoE |
| `24a374d` | 2026-04-23 | 1.9.2: GLM-5.1 пресет 65536, optional prefix cache в serve |
| `b8b7b1a` | 2026-04-23 | 1.9.3: SLGPU_ENABLE_PREFIX_CACHING=0 → --no-enable-prefix-caching |
| `16b50e0` | 2026-04-23 | 1.9.4: GLM-5.1 GPU_MEM_UTIL=0.75 для OOM SharedFusedMoE |
| `b361d2d` | 2026-04-23 | 1.9.5: проброс SLGPU_ENABLE_PREFIX_CACHING в vLLM compose |
| `d8bfc79` | 2026-04-23 | 1.10.0: GLM-5.1-FP8 preset, VLLM_DOCKER_IMAGE, chat template flag |
| `937422a` | 2026-04-23 | 1.11.0: MiniMax-M2.7 preset (vLLM recipe TP4+EP, compilation-config) |
| `0cfff1a` | 2026-04-23 | 1.11.1: pull скачивает веса без автогенерации пресетов |
| `08b8d1d` | 2026-04-23 | 1.11.2: up без ожидания /v1/models |
| `2b42dfc` | 2026-04-23 | 2.0.0: remove ab, compare, logs, status, config from ./slgpu |
| `b2a4360` | 2026-04-23 | 2.0.1: убрать slgpu_guess_parsers, парсеры только из пресета |
| `c5b6b3e` | 2026-04-23 | 2.0.2: убрать slgpu_guess_max_model_len, MAX_MODEL_LEN из пресета |
| `a2915e2` | 2026-04-23 | 2.0.3: удалить slgpu_gen_preset_file |
| `930189e` | 2026-04-23 | tp8 |
| `90f413a` | 2026-04-23 | 2.0.4: -m без пресета — список доступных вместо ошибки bash |
| `3a978bb` | 2026-04-23 | max_model_len |
| `9f8f61c` | 2026-04-23 | mmmax_model_len |
| `d1fac76` | 2026-04-23 | 2.0.5: подчистить устаревшие формулировки в GRACE и docs |
| `c4079fb` | 2026-04-23 | 2.0.6: configs/main.env — слой дефолтов до .env и пресета |
| `4ba5b48` | 2026-04-23 | 2.0.7: main.env в корне репозитория |
| `741db51` | 2026-04-23 | 2.0.8: NCCL и PyTorch в main.env, compose pass |
| `0a0f66e` | 2026-04-23 | 2.0.9: .env.example без пересечения с main.env |
| `a98418d` | 2026-04-23 | 2.0.10: env_file main.env в compose, комментарий про подстановку |
| `2598597` | 2026-04-23 | 2.0.11: без обязательного корневого .env |
| `0ed09de` | 2026-04-23 | 2.0.12: универсальный configs/serve.sh (SLGPU_ENGINE) |
| `a48ee95` | 2026-04-23 | 2.0.13: vLLM/SGLang defaults в main.env |
| `8941ef6` | 2026-04-23 | 2.0.14: serve.sh в scripts/ |
| `12d333d` | 2026-04-23 | 2.0.15: удалён scripts/compare.py |
| `eaf7904` | 2026-04-23 | 2.0.16: vLLM/SGLang — env в main, compose, SLGPU_MODEL_ROOT для SGLang |
| `e44f39f` | 2026-04-23 | 2.1.0: мониторинг в отдельном compose и ./slgpu monitoring |
| `3bc3487` | 2026-04-23 | 2.1.1: Prometheus и Grafana на диске хоста (bind mount) |
| `28822c7` | 2026-04-23 | 2.1.2: Grafana — chown 472:0, user 472:0 в compose |
| `aab778c` | 2026-04-23 | 2.1.3: Prometheus — user 65534, chown -R на TSDB |
| `a2e0298` | 2026-04-23 | 2.1.4: ./slgpu monitoring fix-perms (uid:gid из образов) |
| `aaf7a51` | 2026-04-23 | 2.1.5: дефолт данных мониторинга в /opt/mon |
| `1532aa5` | 2026-04-23 | 2.1.6: SGLang Grafana — Model All, избегаем No data |
| `91775be` | 2026-04-23 | 2.1.7: HISTORY — полный git-log, эпоха 20–22.04, инциденты диалогов |
| `bf61808` | 2026-04-23 | 2.1.7: приложение git-log — коммит 91775be |
| `8a2fc35` | 2026-04-23 | 2.1.8: HISTORY — аналитика «делали / произошло / поменяли» |

*Чтобы обновить список после новых коммитов:* `git log --reverse --format="%h|%ad|%s" --date=short` и дописать строки.

---

## Вне git (контекст разработки)

- Планировался **A/B** vLLM vs SGLang на модели вроде **Qwen/Qwen3.6-35B-A3B**, единый порт API **8111**, модели в **`/opt/models`** (сейчас по умолчанию **TP=8** на 8 GPU).
- Решались инциденты: **утечка HF-токена** в истории (история переписана, токен отозвать), **`ContextOverflowError`** (окно и адаптивный бенч), доступ к **Grafana** снаружи.
- Пользовательские пожелания: **thinking Qwen3**, **co-run по 2 GPU**, **универсальные скрипты через пресеты** (без правки общего env под каждую модель), **полный README**, **ускорение gpt-oss**, **запись истории** (этот файл).

---

## Как обновлять этот файл

Редактируйте **этот** (`docs/HISTORY.md`) — корневой [`HISTORY.md`](../HISTORY.md) — только короткий указатель сюда. После значимых изменений добавляйте строку в таблицу хронологии и при необходимости абзац в раздел «Зачем проект» или «Вне git»; новые итерации — в **«Журнал итераций (агенты)»** в конце файла.

Формат коммита для истории:

```text
краткая тема: что сделано и зачем (1 строка)
```

---

## Журнал итераций (агенты)

Журнал итераций для агентов (правило **project-history** в `.cursor/rules`). Дописывайте запись после каждой завершённой задачи: что сделано, почему, какие файлы затронуты.

## 2026-04-24 — `./slgpu up` без аргументов: интерактив (движок + пресет)

- **Что:** при отсутствии **vllm|sglang** и/или **`-m`** [`scripts/cmd_up.sh`](../scripts/cmd_up.sh) вызывает **`slgpu_interactive_choose_engine`** и **`slgpu_interactive_choose_preset`** в [`scripts/_lib.sh`](../scripts/_lib.sh) (чтение с `/dev/tty`). Обновлены [README.md](../README.md), [cmd_help.sh](../scripts/cmd_help.sh), [configs/models/README.md](../configs/models/README.md). [VERSION](../VERSION) **2.4.0**.
- **Почему:** запрос — сначала тип инференса, потом пресет из списка.
- **Файлы:** `scripts/_lib.sh`, `scripts/cmd_up.sh`, `README.md`, `scripts/cmd_help.sh`, `configs/models/README.md`, `VERSION`, `docs/HISTORY.md`.

## 2026-04-24 — AGENTS.md: рекомендации → обязательные формулировки

- **Что:** [AGENTS.md](../AGENTS.md) — **обязательные** инструкции: «прочитайте», «нельзя», «нужно», «соблюдайте»; уточнён блок про журнал при `.gitignore`. [VERSION](../VERSION) **2.3.6**.
- **Почему:** запрос — не рекомендательный, а обязательный тон.
- **Файлы:** `AGENTS.md`, `VERSION`, `docs/HISTORY.md`.

## 2026-04-24 — AGENTS.md: универсальный шаблон (не привязан к slgpu)

- **Что:** [AGENTS.md](../AGENTS.md) переписан как **универсальный**: чтение README и правил репо, `.gitignore`, стиль и минимальный дифф, версия/коммит «как принято в проекте», запрет на лишний запуск инфраструктуры, таблица навигации по незнакомому репо. [VERSION](../VERSION) **2.3.5**.
- **Почему:** запрос — не привязка к этому стенду.
- **Файлы:** `AGENTS.md`, `VERSION`, `docs/HISTORY.md`.

## 2026-04-24 — AGENTS.md в корне: явные шаги для агентов

- **Что:** [AGENTS.md](../AGENTS.md) переписан: сначала читать `README` и релевантный код; таблица «что в git / чего в clone нет»; **делать** / **не делать**; `VERSION` + commit message; точки входа по темам; без поднятия Docker в среде агента. [VERSION](../VERSION) **2.3.4**.
- **Почему:** запрос — явно указать агентам, что делать.
- **Файлы:** `AGENTS.md`, `VERSION`, `docs/HISTORY.md`.

## 2026-04-24 — README и справка: нумерация, clone, bench/load

- **Что:** в [README.md](../README.md) выровнены разделы **12–16** (раньше дублировался §12); уточнено, что после `git clone` нет `docs/`/`grace/`/`.cursor`/`.kilo`, и что дают корневые `AGENTS.md` / `HISTORY.md`. В [`scripts/cmd_help.sh`](../scripts/cmd_help.sh) синтаксис **`bench`** и **`load`** приведён к факту: **`-m` опционален** (как в `cmd_bench.sh` / `cmd_load.sh`). [VERSION](../VERSION) **2.3.3**.
- **Почему:** запрос — проверка на устаревание и обновление README.
- **Файлы:** `README.md`, `scripts/cmd_help.sh`, `VERSION`, `docs/HISTORY.md`.

## 2026-04-24 — Единый `docs/HISTORY.md`: перенос из корня

- **Что:** весь нарратив бывшего корневого `HISTORY.md` (хронология, аналитика, приложение `git log`) объединён с этим файлом — разделы выше; журнал итераций — ниже. В корне репозитория [`HISTORY.md`](../HISTORY.md) оставлен короткий указатель на **этот** документ.
- **Почему:** запрос — вести полную историю в `docs/HISTORY.md` (правило *project-history*), без дублирования с корнем.
- **Файлы:** `docs/HISTORY.md`, `HISTORY.md` (корень).

---

## 2026-04-23 — Пресет deepseek-ai/DeepSeek-V4-Pro

- **Что:** новый [deepseek-v4-pro.env](../configs/models/deepseek-v4-pro.env) (`MODEL_ID`, 384K, `KV_CACHE_DTYPE=auto`, `deepseek_r1` / `pythonic`, чуть ниже `GPU_MEM_UTIL` 0.88 из‑за масштаба MoE). [VERSION](../VERSION) **2.3.0**, [HISTORY.md](./HISTORY.md), GRACE.
- **Почему:** запрос — [DeepSeek-V4-Pro](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro) в том же духе, что Flash.

## 2026-04-23 — DeepSeek-V4-Flash: KV_CACHE_DTYPE=auto

- **Что:** в [deepseek-v4-flash.env](../configs/models/deepseek-v4-flash.env) **`KV_CACHE_DTYPE=auto`**. [VERSION](../VERSION) **2.2.2**, [HISTORY.md](./HISTORY.md), GRACE.
- **Почему:** vLLM сам выбирает dtype кэша.

## 2026-04-23 — DeepSeek-V4-Flash: MAX_MODEL_LEN 384K

- **Что:** в [deepseek-v4-flash.env](../configs/models/deepseek-v4-flash.env) **`MAX_MODEL_LEN=393216`** (384×1024), комментарий под Think Max. [VERSION](../VERSION) **2.2.1**, [HISTORY.md](./HISTORY.md), GRACE.
- **Почему:** запрос — окно 384K в пресете.

## 2026-04-23 — Пресет deepseek-ai/DeepSeek-V4-Flash

- **Что:** добавлен [`configs/models/deepseek-v4-flash.env`](../configs/models/deepseek-v4-flash.env) (ориентиры по `MAX_MODEL_LEN`, `KV_CACHE_DTYPE`, reasoning/tool из README); строка в таблице парсеров [configs/models/README.md](../configs/models/README.md). [VERSION](../VERSION) **2.2.0**, [HISTORY.md](./HISTORY.md), GRACE.
- **Почему:** запрос — готовый пресет для [DeepSeek-V4-Flash](https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash) под `./slgpu pull` / `./slgpu up vllm -m deepseek-v4-flash`.

## 2026-04-23 — Prometheus: скрейп vLLM/SGLang через host.docker.internal (fix DNS vllm)

- **Что:** в [prometheus.yml](../monitoring/prometheus.yml) вместо `vllm:8111` / `sglang:8222` — **host.docker.internal:8111** / **:8222** (порты, опубликованные на хосте), **relabel_configs** задают **instance** `vllm:8111` / `sglang:8222` для Grafana. В [docker-compose.monitoring.yml](../docker-compose.monitoring.yml) у сервиса `prometheus` — **extra_hosts: host.docker.internal:host-gateway**. [monitoring/README.md](../monitoring/README.md) — ввод, таблица vLLM, блок SGLang/instance. [VERSION](../VERSION) 2.1.11, [HISTORY.md](./HISTORY.md), GRACE.
- **Почему:** на Targets ошибка *lookup vllm on 127.0.0.11 … server misbehaving* — разные compose-проекты (slgpu / slgpu-monitoring), краткое DNS-имя `vllm` не резолвится между стеками; контейнер vLLM при этом может быть **running** и публиковать **8111** на хост.
- **Если сменили LLM_API_PORT** на хосте: поправьте `targets` порт в `prometheus.yml` (должен совпадать с публикацией в `docker-compose.yml`).

## 2026-04-23 — Prometheus: доступ с внешних хостов (0.0.0.0:9090)

- **Что:** в [main.env](../main.env) по умолчанию **`PROMETHEUS_BIND=0.0.0.0`**, комментарий про отсутствие auth; в [docker-compose.monitoring.yml](../docker-compose.monitoring.yml) — fallback `0.0.0.0` для порта 9090. Обновлены [monitoring/README.md](../monitoring/README.md), [README.md](../README.md), [cmd_prepare.sh](../scripts/cmd_prepare.sh) (шаг UFW: опционально 3000/9090), [cmd_monitoring.sh](../scripts/cmd_monitoring.sh). [VERSION](../VERSION) **2.1.10**, [HISTORY.md](./HISTORY.md), GRACE.
- **Почему:** запрос — Prometheus доступен «извне» (с другой машины в сети), не только localhost.
- **Откат:** в `main.env` задать `PROMETHEUS_BIND=127.0.0.1` и перезапустить monitoring.

## 2026-04-23 — vLLM Grafana V2: troubleshooting «No data»

- **Что:** в [monitoring/README.md](../monitoring/README.md) — подраздел **«vLLM V2: все панели No data»** (почему пусто при одном SGLang; Prometheus Targets; `curl …/metrics`; опционально **`VLLM_USE_V1=0`**, vLLM #16348; окно Last 3h и трафик). В [main.env](../main.env) — закомментированный **`VLLM_USE_V1=0`** + пояснение (через `env_file` попадает в контейнер vLLM). [HISTORY.md](./HISTORY.md) — строка **2.1.9**; [VERSION](../VERSION) **2.1.9**; GRACE `*.xml` **2.1.9**.
- **Почему:** запрос: дашборд vLLM в Grafana без данных; нужна ясная диагностика и обход.
- **Файлы:** `monitoring/README.md`, `main.env`, `HISTORY.md`, `VERSION`, `docs/HISTORY.md`, `grace/`.

## 2026-04-23 — HISTORY.md: аналитика «делали → произошло → поменяли»

- **Что:** в [HISTORY.md](./HISTORY.md) после таблицы «Рефакторинг CLI» добавлен раздел **«Аналитика»** — длинные сценарии с тройками **делали / произошло / поменяли**, именами переменных (`SLGPU_*`, `KV_CACHE_DTYPE`, `SLGPU_ENABLE_PREFIX_CACHING`, `LLM_API_PORT` и т.д.), путями к [`main.env`](../main.env), [`scripts/serve.sh`](../scripts/serve.sh), [`docker-compose.yml`](../docker-compose.yml), пресетам, мониторингу; отдельно **пошаговая** цепочка **GLM-5.1** (контекст, sparse MLA+fp8 KV, MoE OOM, prefix cache, 1.9.0–1.9.5, FP8 1.10.0) и **шпаргалка** «где живут настройки». В таблице версий — строка **2.1.8**.
- **Почему:** запрос — больше технических данных в `HISTORY.md` для аналитической статьи, не только сжатые таблицы.
- **Версия:** 2.1.7 → **2.1.8** (PATCH), [`VERSION`](../VERSION), `grace/*.xml` с `2.1.8`.

## 2026-04-23 — HISTORY.md: полный git-log, диалоги, инциденты запуска

- **Что:** в корневом [`HISTORY.md`](./HISTORY.md) — раздел **«Промежуточная эпоха: 20.04–22.04.2026»** (смысловые группы коммитов между ранним README и релизами 1.6+); **«Диалоги и инциденты при запуске»** (таблицы: GLM-5.1, Qwen3.6, мониторинг; в **«Прочее»** — SGLang/порты/графы из сессий 22.04); **приложение** с полной таблицей `git log --reverse` и команда обновления списка. Версия **2.1.6 → 2.1.7** (PATCH), синхронизированы [`VERSION`](../VERSION), `grace/*.xml` (`Project` / `*Plan` / `TechnologyStack` и т.д.). Дополнительные коммиты 2.1.7: уточнение снимка приложения, строка о коммите `91775be`, **прочие диалоги (SGLang).**
- **Почему:** запрос пользователя — максимально подробная история по git с начала репо и фиксация ошибок/настроек из сессий Cursor (транскрипты агентов).
- **Файлы:** `HISTORY.md`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `grace/requirements/requirements.xml`, `grace/technology/technology.xml`, `docs/HISTORY.md`.

## 2026-04-23 — SGLang Grafana: Model «All», no data

- **Что:** в [sglangdash2-slgpu.json](../monitoring/grafana/provisioning/dashboards/json/sglangdash2-slgpu.json) и [sglang-dashboard-slgpu.json](../monitoring/grafana/provisioning/dashboards/json/sglang-dashboard-slgpu.json) — переменная **Model** с **includeAll** и **allValue `.*`**, дефолт **All** (избегаем `No data` при пустом `model_name`). [monitoring/README.md](../monitoring/README.md) — уточнение про метрики в Prometheus, не «сохранение» в Grafana.
- **Версия:** `2.1.5` → `2.1.6` (PATCH).

## 2026-04-23 — дефолт данных мониторинга: `/opt/mon`

- **Что:** в [`main.env`](../main.env) и fallbacks в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml), [`scripts/monitoring_fix_permissions.sh`](../scripts/monitoring_fix_permissions.sh), [monitoring/README](../monitoring/README.md) — **`/opt/mon/prometheus`**, **`/opt/mon/grafana`** вместо `/var/lib/slgpu/…`.
- **Версия:** `2.1.4` → `2.1.5` (PATCH).

## 2026-04-23 — monitoring fix-perms, без жёсткого user в compose

- **Что:** [`scripts/monitoring_fix_permissions.sh`](../scripts/monitoring_fix_permissions.sh), подкоманда **`./slgpu monitoring fix-perms`**: `id -u`/`id -g` в `grafana/grafana` и `prom/prometheus`, `chown -R` на `GRAFANA_DATA_DIR` / `PROMETHEUS_DATA_DIR`. Опции **`SLGPU_GRAFANA_IMAGE`**, **`SLGPU_PROMETHEUS_IMAGE`** в [main.env](../main.env). В [docker-compose.monitoring.yml](../docker-compose.monitoring.yml) **удалены** `user: 472:0` / `65534:65534` (совпадение с `latest` не гарантировано). [monitoring/README.md](../monitoring/README.md), [README.md](../README.md), [cmd_help](../scripts/cmd_help.sh).
- **Почему:** повторяющиеся ошибки прав на bind mount; автоматизировать и не гадать uid.
- **Версия:** `2.1.3` → `2.1.4` (PATCH).

## 2026-04-23 — Prometheus: chown -R, user 65534:65534

- **Что:** в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) — **`user: "65534:65534"`**; [monitoring/README.md](../monitoring/README.md) — **рекурсивный** `chown` для TSDB, troubleshooting `queries.active` / panic active query log; [main.env](../main.env).
- **Почему:** bind mount с подкаталогами/copied данными `root` — Prometheus не пишет `queries.active` (Prometheus 3.x).
- **Версия:** `2.1.2` → `2.1.3` (PATCH).

## 2026-04-23 — Grafana: chown 472:0, user в compose

- **Что:** в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) у Grafana **`user: "472:0"`**; в [monitoring/README.md](../monitoring/README.md) — **не** 472:472, а **472:0** и блок troubleshooting при `GF_PATHS_DATA is not writable`; [main.env](../main.env) — комментарий.
- **Почему:** официальный `grafana/grafana` в Docker: uid 472, gid 0; bind mount с `root:root` или `472:472` не даёт писать в `plugins` и т.д.
- **Версия:** `2.1.1` → `2.1.2` (PATCH).

## 2026-04-23 — Prom/Grafana: данные на диске хоста

- **Что:** в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) вместо named volumes — bind mount **`PROMETHEUS_DATA_DIR`**, **`GRAFANA_DATA_DIR`** (дефолт `/var/lib/slgpu/prometheus`, `/var/lib/slgpu/grafana` в [`main.env`](../main.env)). В [monitoring/README.md](../monitoring/README.md) — `mkdir`/`chown` и **перенос** из `slgpu_prometheus-data` / `slgpu_grafana-data` через `rsync`.
- **Почему:** явные пути на локальном диске сервера, контроль бэкапа и места; сохранение существующих данных при миграции.
- **Версия:** `2.1.0` → `2.1.1` (PATCH).

## 2026-04-23 — мониторинг отдельно от `up`

- **Что:** стек **dcgm-exporter, node-exporter, Prometheus, Grafana** вынесен в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml), проект **`slgpu-monitoring`**. Сеть **`slgpu`** (bridge) общая с движком vLLM/SGLang, чтобы [prometheus.yml](../monitoring/prometheus.yml) по-прежнему целился в `vllm:8111` и `sglang:8222`. Команда **`./slgpu monitoring up|down|restart`**; **`./slgpu up`** поднимает только движок. Тома Grafana/Prometheus: явные имена **`slgpu_grafana-data`**, **`slgpu_prometheus-data`**. **Файлы:** [`scripts/cmd_monitoring.sh`](../scripts/cmd_monitoring.sh), [`scripts/_lib.sh`](../scripts/_lib.sh) (`slgpu_ensure_slgpu_network`), `cmd_up.sh`, `cmd_down.sh`, `slgpu`, `cmd_help.sh`, `README*`, [monitoring/README](../monitoring/README.md), **GRACE** verification.
- **Почему:** запрос — мониторинг постоянен и не должен дублироваться при смене модели/движка.
- **Версия:** `2.0.16` → **`2.1.0`** (MINOR — новая команда `./slgpu`).

## 2026-04-23 — serve: env из `main` и compose

- **Что:** в [`main.env`](../main.env) явно заданы `SLGPU_VLLM_TRUST_REMOTE_CODE`, `SLGPU_VLLM_ENABLE_CHUNKED_PREFILL`, `SLGPU_VLLM_ENABLE_AUTO_TOOL_CHOICE` (реле для флагов `vllm serve`); в [`scripts/serve.sh`](../scripts/serve.sh) SGLang использует тот же **`SLGPU_MODEL_ROOT`**, что и vLLM. В [`docker-compose.yml`](../docker-compose.yml) в `environment` vllm/sglang — pass этих и связанных переменных с хоста. **GRACE** — bump версии.
- **Почему:** убрать «зашитые» в скрипте настройки и дать override из `main` / пресета.
- **Версия:** `2.0.15` → `2.0.16` (PATCH).

## 2026-04-23 — удалён `compare.py`

- **Что:** удалён `scripts/compare.py` (ранее собирал A/B-таблицу vLLM vs SGLang в `bench/report.md` из пары `summary.json`). Актуальные артефакты — `bench/results/<engine>/<timestamp>/`. Обновлены [README.md](../README.md), [`scripts/cmd_help.sh`](../scripts/cmd_help.sh), [`docs/AGENTS.md`](../docs/AGENTS.md), **GRACE**.
- **Версия:** `2.0.14` → `2.0.15` (PATCH).

## 2026-04-23 — `serve.sh` в `scripts/`

- **Что:** entrypoint контейнеров LLM — **[`scripts/serve.sh`](../scripts/serve.sh)** (удалён `configs/serve.sh`); в [`docker-compose.yml`](../docker-compose.yml) volume **`./scripts/serve.sh:/etc/slgpu/serve.sh`**. README, GRACE, `configs/models/README`.
- **Версия:** `2.0.13` → `2.0.14` (PATCH).

## 2026-04-23 — vLLM/SGLang: всё в `main.env`

- **Что:** переменные из удалённых `configs/vllm/vllm.env` и `configs/sglang/sglang.env` перенесены в [`main.env`](../main.env) (в т.ч. `SLGPU_VLLM_*`, `VLLM_LOGGING_LEVEL`, `SGLANG_LISTEN_*`, `TRITON_CACHE_DIR`, `TORCHINDUCTOR_CACHE_DIR`). В [`docker-compose.yml`](../docker-compose.yml) у vllm/sglang — только **`env_file: main.env`**. В [`scripts/_lib.sh`](../scripts/_lib.sh) **`slgpu_load_compose_env`** больше не подключает `configs/<engine>/<engine>.env`. Обновлены README, GRACE, [`configs/models/kimi-k2.6.env`](../configs/models/kimi-k2.6.env).
- **Версия:** `2.0.12` → `2.0.13` (PATCH).

## 2026-04-23 — универсальный `configs/serve.sh`

- **Что:** один скрипт **[`configs/serve.sh`](../configs/serve.sh)** с **`SLGPU_ENGINE=vllm|sglang`** (в [`docker-compose.yml`](../docker-compose.yml) у сервисов vllm/sglang). Логика бывших `configs/vllm/serve.sh` и `configs/sglang/serve.sh` перенесена в функции **`slgpu_run_vllm`** / **`slgpu_run_sglang`**. Обновлены README, `vllm.env` / `sglang.env`, `configs/models/README`, **GRACE**.
- **Версия:** `2.0.11` → `2.0.12` (PATCH).

## 2026-04-23 — без обязательного корневого `.env`

- **Что:** убрана зависимость от файла **`.env`** в корне: [`scripts/_lib.sh`](../scripts/_lib.sh) больше не требует и не читает его; в [`docker-compose.yml`](../docker-compose.yml) из **`env_file`** удалён **`.env`**; удалён шаблон **`.env.example`**. Секреты и опции — в шапке/хвосте [`main.env`](../main.env) (комментарии + `export`) и в [`README.md`](../README.md). Обновлены vllm/sglang, `cmd_*`, monitoring, `configs/models/README`, **GRACE**, [`scripts/bench_openai.py`](../scripts/bench_openai.py).
- **Версия:** `2.0.10` → `2.0.11` (PATCH).

## 2026-04-23 — docker-compose: `env_file: main.env`

- **Что:** в [`docker-compose.yml`](../docker-compose.yml) у vllm/sglang и сервисов мониторинга первым в **`env_file`** указан **`main.env`**; убран дублирующий явный pass **NCCL/PyTorch** из `environment` (значения приходят из `main` в контейнер). В шапке compose — пояснение: подстановка `${VAR}` в YAML vs `env_file`; для сырого compose — `docker compose --env-file main.env`. [README.md](../README.md).
- **Версия:** `2.0.9` → `2.0.10` (PATCH).

## 2026-04-23 — `.env` без пересечения с `main.env`

- **Что:** [`.env.example`](../.env.example) содержит только **секрет** `GRAFANA_ADMIN_PASSWORD` и опциональные поля, **отсутствующие** в [`main.env`](../main.env) (`GF_SERVER_ROOT_URL`, `SLGPU_NVIDIA_VISIBLE_DEVICES`, `LLM_API_PORT`). Все бывшие дубли (пути, бинды, `VLLM_DOCKER_IMAGE`, …) убраны из примера `.env`. Обновлены [README.md](../README.md), [`configs/models/README.md`](../configs/models/README.md), шапка [`main.env`](../main.env).
- **Версия:** `2.0.8` → `2.0.9` (PATCH).

## 2026-04-23 — `main.env`: NCCL и PyTorch из vllm/sglang env

- **Что:** в [`main.env`](../main.env) вынесены **NCCL_P2P_LEVEL**, **NCCL_IB_DISABLE**, **PYTORCH_ALLOC_CONF** (vLLM), **PYTORCH_CUDA_ALLOC_CONF** (SGLang); убрано из [`configs/vllm/vllm.env`](../configs/vllm/vllm.env) / [`sglang.env`](../configs/sglang/sglang.env). В [`docker-compose.yml`](../docker-compose.yml) у сервисов vllm/sglang — явный pass в `environment`, иначе значения из `main` не доходят до контейнера. Обновлён [README.md](../README.md).
- **Версия:** `2.0.7` → `2.0.8` (PATCH).

## 2026-04-23 — `main.env` в корне (вместо configs/main.env)

- **Что:** файл дефолтов — **[`main.env`](../main.env)** в корне репозитория; удалён `configs/main.env`. [`scripts/_lib.sh`](../scripts/_lib.sh) — **`${root}/main.env`**; обновлены ссылки в README, `.env.example`, `configs/models/README`, GRACE.
- **Версия:** `2.0.6` → `2.0.7` (PATCH).

## 2026-04-23 — `main.env`: дефолты в одном файле

- **Что:** добавлен слой `main.env` (пути, `MAX_MODEL_LEN`/`TP`/KV, мониторинг, `VLLM_DOCKER_IMAGE` и т.д.); в 2.0.7 файл перенесён в корень репозитория; в [`scripts/_lib.sh`](../scripts/_lib.sh) — **`slgpu_source_main_env`**, подмешивание **до** `.env` и пресета в **`slgpu_load_server_env`**, **`slgpu_load_env`**, **`slgpu_load_compose_env`**. Обновлены комментарии в `docker-compose.yml`, `vllm.env` / `sglang.env`, `serve.sh`, [`.env.example`](../.env.example), `README`, `configs/models/README`, GRACE.
- **Почему:** единая точка для базовых значений вместо разрозненных `${:-}` только в compose.
- **Версия:** `2.0.5` → `2.0.6` (PATCH — новый файл дефолтов и порядок `source` в `_lib.sh`).

## 2026-04-23 — GRACE / docs: убрать устаревшие формулировки

- **Что:** в [`grace/plan/development-plan.xml`](../grace/plan/development-plan.xml) **risk-2** — не «автоопределение парсеров», а риск ошибок в пресете/образе; контракт **M-PULL** — убран выход `preset_file` (pull не создаёт `.env`); **V-M-PULL** / **V-M-UP** в [`verification-plan.xml`](../grace/verification/verification-plan.xml) — сценарии без «создаёт пресет» и без ссылки на удалённый **`status`**; выровнены **VERSION** в XML; [`docs/AGENTS.md`](../docs/AGENTS.md) — keywords, «A/B» → сравнение движков, пометка **HISTORY**; [`knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml) `Project/@VERSION`.
- **Версия:** `2.0.4` → `2.0.5` (PATCH).

## 2026-04-23 — up/pull/bench/load/restart: -m без имени — список пресетов

- **Что:** в [`scripts/_lib.sh`](../scripts/_lib.sh) добавлена **`slgpu_fail_if_missing_preset_arg`**; в **`cmd_{up,pull,bench,load,restart}.sh`** вместо **`${2:?}`** у **`-m`/`--model`** — явная проверка: пусто или следующий аргумент начинается с **`-`** → подсказка и **доступные пресеты** (как `slgpu_list_presets`), **exit 1** (без `parameter null or not set` из bash).
- **Версия:** `2.0.3` → `2.0.4` (PATCH). `grace/knowledge-graph/knowledge-graph.xml`.

## 2026-04-23 — _lib: удалён slgpu_gen_preset_file

- **Что:** из [`scripts/_lib.sh`](../scripts/_lib.sh) удалена **`slgpu_gen_preset_file`** — пресеты только вручную (`cp` с примера, правка), вызовов из CLI не было.
- **Почему:** мёртвый код после отказа от автогенерации в `pull`.
- **Версия:** `2.0.2` → `2.0.3` (PATCH). GRACE M-LIB / M-MODELS, `configs/models/README.md`.

## 2026-04-23 — _lib: удалён slgpu_guess_max_model_len

- **Что:** из [`scripts/_lib.sh`](../scripts/_lib.sh) удалена **`slgpu_guess_max_model_len`** — дефолт **`MAX_MODEL_LEN`** по HF id больше не вычисляется; окно задаётся **в пресете** (`configs/models/*.env`).
- **Почему:** тот же принцип, что для парсеров: один источник истины — пресет и документация модели.
- **Версия:** `2.0.1` → `2.0.2` (PATCH). GRACE, `configs/models/README.md`.

## 2026-04-23 — _lib: удалён slgpu_guess_parsers

- **Что:** из [`scripts/_lib.sh`](../scripts/_lib.sh) удалена **`slgpu_guess_parsers`**; **`REASONING_PARSER`** / **`TOOL_CALL_PARSER`** — только в пресете.
- **Почему:** не дублировать эвристику парсеров; источник истины — `configs/models/*.env` и доку vLLM.
- **Версия:** `2.0.0` → `2.0.1` (PATCH). GRACE, `configs/models/README.md`.

## 2026-04-23 — CLI 2.0: удалены ab, compare, logs, status, config

- **Что:** из [`slgpu`](../slgpu) убраны команды **`ab`**, **`compare`**, **`logs`**, **`status`**, **`config`**; удалены `scripts/cmd_{ab,compare,logs,status,config}.sh`. Сводка бенчей: **`python3 scripts/compare.py`**; логи — **`docker compose logs`**; диагностика — **`curl`**, **`docker compose ps`**, **`nvidia-smi`**.
- **Почему:** упрощение поверхности CLI; сравнение отчётов остаётся в `compare.py` без обёртки.
- **Версия:** `1.11.2` → **`2.0.0`** (MAJOR — ломающее сокращение команд).
- **Документация / GRACE:** README, `cmd_help.sh`, `configs/models/README.md`, requirements, plan, knowledge-graph, verification, technology.

## 2026-04-23 — up: без ожидания /v1/models

- **Что:** в [`scripts/cmd_up.sh`](../scripts/cmd_up.sh) убран цикл `curl` до готовности API; `up` завершается после `docker compose up -d` и краткого вывода проброса порта; в конце — подсказка `curl` / `docker compose logs`.
- **Почему:** тяжёлые MoE могут поднимать модель дольше прежнего таймаута; готовность удобнее проверять вручную (`curl` / `docker compose ps`).
- **Версия:** `1.11.1` → `1.11.2` (PATCH). Удалены упоминания `SLGPU_UP_READY_ATTEMPTS` из [`.env.example`](../.env.example).

## 2026-04-23 — pull: без автогенерации пресетов

- **Что:** [`scripts/cmd_pull.sh`](../scripts/cmd_pull.sh) — только `hf download`. HF id: при наличии `configs/models/<slug>.env` — подгрузка пресета, иначе скачивание по id и подсказка создать `.env` вручную. Опция **`--revision`**. Удалены **`--force`**, **`--keep`**, **`--slug`**, флаги, относившиеся к генерации.
- **Почему:** пресеты — явный артефакт в репозитории, без скрытой подстановки по pull.
- **Версия:** `1.11.0` → `1.11.1` (PATCH).
- **Документация:** README, `configs/models/README.md`, `cmd_help.sh`, `HISTORY.md`.

## 2026-04-23 — MiniMax-M2.7: пресет по рецепту vLLM (TP4+EP, compilation-config)

- **Что:** пресет [`configs/models/minimax-m2.7.env`](../configs/models/minimax-m2.7.env) — в т.ч. **`MAX_MODEL_LEN=200704`** по рецепту; `serve.sh` — `SLGPU_VLLM_COMPILATION_CONFIG` → `--compilation-config`, `SLGPU_ENABLE_EXPERT_PARALLEL` → `--enable-expert-parallel`, опционально `SLGPU_VLLM_DATA_PARALLEL_SIZE` → `--data-parallel-size`; `docker-compose` — проброс этих переменных; README / `.env.example` — образ `minimax27`.
- **Почему:** [рецепт vLLM MiniMax-M2](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md) — **не** «голый» TP8, на 8×GPU **TP4+EP** и `fuse_minimax_qk_norm`; на 4×GPU — **TP4** без EP; для EP нужна маска **всех** GPU → **`SLGPU_NVIDIA_VISIBLE_DEVICES`** в пресете.
- **Версия:** `1.10.0` → `1.11.0` (MINOR — новый пресет, расширение serve/compose).

## 2026-04-23 — GLM-5.1-FP8: пресет, рецепт vLLM, VLLM_DOCKER_IMAGE, chat template

- **Что:** пресет [`configs/models/glm-5.1-fp8.env`](../configs/models/glm-5.1-fp8.env) (`zai-org/GLM-5.1-FP8`, `TOOL_CALL_PARSER=glm47`, `REASONING_PARSER=glm45`, `CHAT_TEMPLATE_CONTENT_FORMAT=string`); в `serve.sh` — опциональный флаг `--chat-template-content-format`; в `docker-compose` — `CHAT_TEMPLATE_CONTENT_FORMAT`, `image: ${VLLM_DOCKER_IMAGE:-...}`; в `_lib.sh` — для `*FP8` эвристика tool → `glm47`.
- **Почему:** [официальный рецепт vLLM GLM/GLM5.md](https://github.com/vllm-project/recipes/blob/main/GLM/GLM5.md) рекомендует FP8 и образ `glm51`; меньше OOM, чем у bf16 на том же железе.
- **Версия:** `1.9.5` → `1.10.0` (MINOR — новый пресет, расширение serve/compose).

## 2026-04-23 — docker-compose: проброс SLGPU_ENABLE_PREFIX_CACHING в vLLM

- **Что:** в `docker-compose.yml` у сервиса `vllm` в `environment` добавлена **`SLGPU_ENABLE_PREFIX_CACHING`** (`${...:-1}`), по аналогии с `SLGPU_DISABLE_CUSTOM_ALL_REDUCE` / `SLGPU_MAX_NUM_BATCHED_TOKENS`.
- **Почему:** пресет подмешивается на хосте при `./slgpu up`, но в контейнер попадают только переменные из `env_file` и явного `environment`. Без ключа `SLGPU_ENABLE_PREFIX_CACHING` в compose контейнер не получал `0` из `glm-5.1.env`, `serve.sh` брал дефолт `1` → в логах vLLM `enable_prefix_caching: True` и нет `--no-enable-prefix-caching`.
- **Версия:** `1.9.4` → `1.9.5` (PATCH).

## 2026-04-23 — GLM-5.1: GPU_MEM_UTIL 0.75 (OOM MoE при 0.82)

- **Что:** в `configs/models/glm-5.1.env` — `GPU_MEM_UTIL=0.75`, комментарий про снижение util по подсказке vLLM (освободить память под веса MoE).
- **Почему:** OOM в `unquantized_fused_moe` при ~0.82 и прежних настройках; сообщение: «Try lowering --gpu-memory-utilization».
- **Версия:** `1.9.3` → `1.9.4` (PATCH).

## 2026-04-23 — vLLM: отключение prefix cache — --no-enable-prefix-caching

- **Что:** в `configs/vllm/serve.sh` при `SLGPU_ENABLE_PREFIX_CACHING=0` добавляется `--no-enable-prefix-caching` (а не «ничего»): в vLLM 0.19 prefix cache включён по умолчанию, из‑за этого в логах оставалось `enable_prefix_caching: True`. Обновлены комментарии в `vllm.env`, `glm-5.1.env`, README troubleshooting.
- **Почему:** пользовательский лог с пресетом 1.9.2 показывал `enable_prefix_caching: True` при `SLGPU_ENABLE_PREFIX_CACHING=0`.
- **Версия:** `1.9.2` → `1.9.3` (PATCH).

## 2026-04-23 — GLM-5.1: пресет 65536, prefix cache off, serve.sh

- **Что:** `configs/models/glm-5.1.env` — `MAX_MODEL_LEN=65536`, `GPU_MEM_UTIL=0.82`, `SLGPU_MAX_NUM_BATCHED_TOKENS=4096`, `SLGPU_ENABLE_PREFIX_CACHING=0`; `configs/vllm/serve.sh` — `--enable-prefix-caching` только при `SLGPU_ENABLE_PREFIX_CACHING=1` (дефолт 1); `configs/vllm/vllm.env` — закомментированный пример; README / troubleshooting / `configs/models/README.md`.
- **Почему:** при 131072+0.88 OOM в `SharedFusedMoE` (нехватка ~1.5 GiB); отключение prefix cache и снижение окна/батча освобождает VRAM.
- **Версия:** `1.9.1` → `1.9.2` (PATCH).

## 2026-04-23 — GLM-5.1: OOM MoE (SharedFusedMoE) — пресет 131072 и GPU_MEM_UTIL 0.88

- **Что:** в `configs/models/glm-5.1.env` — `MAX_MODEL_LEN=131072`, `GPU_MEM_UTIL=0.88`, комментарии про 202k и запас VRAM; README (рецепт, troubleshooting), `configs/models/README.md`.
- **Почему:** на 8×~140 GB при 202752+0.92 OOM в `unquantized_fused_moe` при загрузке весов.
- **Файлы:** `configs/models/glm-5.1.env`, `README.md`, `configs/models/README.md`, `VERSION`, `HISTORY.md`, `docs/HISTORY.md`.
- **Версия:** `1.9.0` → `1.9.1` (PATCH — настройка пресета и документация).

## 2026-04-23 — GLM-5.1: пресет, max_len 202752, KV auto, документация

- **Что:** `configs/models/glm-5.1.env` (`MAX_MODEL_LEN=202752`, `KV_CACHE_DTYPE=auto`); README (рецепт GLM, troubleshooting: `No valid attention backend` / fp8 KV); `configs/models/README.md`.
- **Почему:** лимит контекста из `config.json`; sparse MLA+KV fp8_e4m3 даёт `ValueError: No valid attention backend` в vLLM 0.19.1.
- **Файлы:** `scripts/_lib.sh`, `scripts/cmd_pull.sh`, `configs/models/glm-5.1.env`, `README.md`, `configs/models/README.md`, `VERSION`, `HISTORY.md`, `docs/HISTORY.md`.
- **Версия:** `1.8.3` → `1.9.0` (MINOR — пресет и доработки `pull`/`_lib` того релиза).

## 2026-04-23 — qwen3.6-27b: TOOL_CALL_PARSER hermes → qwen3_xml (фикс таймаутов tool calling)

- **Что:** в `configs/models/qwen3.6-27b.env` `TOOL_CALL_PARSER=hermes` заменён на `TOOL_CALL_PARSER=qwen3_xml`, к строке добавлен развёрнутый комментарий с вариантами (`qwen3_xml` / `qwen3_coder`) и предупреждением про несовместимость `hermes`. В `configs/models/README.md` таблица парсеров разделена на строки `Qwen3 / Qwen2.5` (hermes) и `Qwen3-Coder / Qwen3.6` (qwen3_xml | qwen3_coder); добавлен поясняющий абзац и команда проверки доступных tool-парсеров в образе.
- **Почему:** пользователь сообщил, что tool calling у `Qwen/Qwen3.6-27B` падает по таймауту. Причина — семейство Qwen3.6 (ветка Qwen3-Coder) эмитит XML-формат tool calls, а `hermes_tool_parser` ждёт JSON и падает `JSONDecodeError`, из-за чего финальный чанк стрима не формируется и клиент висит до таймаута. Официальная карточка [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) рекомендует `qwen3_coder`; vLLM docs ≥0.12 и [PR vllm-project/vllm#25028](https://github.com/vllm-project/vllm/pull/25028) — более новый streaming-safe `qwen3_xml`.
- **Файлы:** `configs/models/qwen3.6-27b.env`, `configs/models/README.md`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** `qwen3_xml` по умолчанию (streaming, community-verified для долгих агентных сессий); `qwen3_coder` оставлен как fallback в комментарии пресета. Пресет `configs/models/qwen3-30b-a3b.env` (классический Qwen3, не `.6`) и `kimi-k2.6` не трогал — у них другое семейство tool-формата (`hermes` / `kimi_k2`).
- **Версия:** `1.8.2` → `1.8.3` (PATCH — багфикс конфигурации пресета).

## 2026-04-22 — ./slgpu up / restart: флаг --tp (без правки пресета)

- **Что:** в `cmd_up.sh` — опция `--tp <N>` переопределяет `TP` на запуск, передача `TP` в `compose_llm_env`; `cmd_restart.sh` пробрасывает `--tp` в `up`. Обновлены `cmd_help.sh`, `README.md`, `configs/models/README.md`.
- **Почему:** запрос — выбирать TP при `up` без правки файлов, по умолчанию по-прежнему из пресета / 8.
- **Версия:** 1.6.0 (MINOR — расширение CLI).

## 2026-04-22 — vllmdash2: переменные instance / Model (All) и фильтр job

- **Что:** в `vllmdash2.json` — `instance` + `model_name` с **includeAll** / `allValue: .*`, во всех expr — `job="vllm"`, `instance=~"$instance"`, `model_name=~"$model_name"`; GC/RSS с фильтром job/instance. `monitoring/README.md`: vLLM vs SGLang, пустой Model.
- **Почему:** «No data» при пустом Model и несоответствии scrape; вопрос «куда делись данные» — на самом деле нет рядов `vllm:*` при одном SGLang.
- **Файлы:** `vllmdash2.json`, `monitoring/README.md`, `VERSION` 1.5.4.

## 2026-04-22 — vllmdash2.json: исправление datasource для Grafana provisioning

- **Что:** из JSON удалены `__inputs`/`__requires`, все `"uid": "${DS_PROMETHEUS}"` заменены на `prometheus` (как в [`datasource.yml`](../monitoring/grafana/provisioning/datasources/datasource.yml)). Обновлён `monitoring/README.md`.
- **Почему:** при provisioning Grafana не подставляет `DS_PROMETHEUS` — дашборд «vLLM Monitoring - V2» не находил datasource.
- **Файлы:** `vllmdash2.json`, `monitoring/README.md`, `VERSION` 1.5.3.

## 2026-04-22 — GRACE: синхронизация с дашбордами Grafana

### Артефакты grace/** и AGENTS
- **Что:** обновлены `grace/technology/technology.xml` (Observability / grafana-provisioning), `grace/plan/development-plan.xml` (M-MONITOR, DF-MONITOR), `grace/knowledge-graph/knowledge-graph.xml` (M-MONITOR), `grace/requirements/requirements.xml` (UC-008), `grace/verification/verification-plan.xml` (V-M-MONITOR), `grace/README.md`; в `docs/AGENTS.md` — дерево `monitoring/`. Версии XML-наборов **1.0.0 → 1.1.0**, graph Project **1.1.0**.
- **Почему:** запрос пользователя — обновить GRACE везде под текущие JSON-дашборды.
- **Файлы:** перечисленные + `VERSION` 1.5.2.

## 2026-04-22 — README: дашборды Grafana (vLLM + SGLang)

### Документация мониторинга
- **Что:** в [`README.md`](../README.md) §12 и в [`monitoring/README.md`](../monitoring/README.md) описаны `sglang-dashboard-slgpu`, `sglangdash2-slgpu`, `vllmdash2`, скрипт `_build_sglangdash2.py`; в дереве репозитория указан `monitoring/README.md` и `dashboards/json/`.
- **Почему:** запрос пользователя — обновить README.
- **Файлы:** `README.md`, `monitoring/README.md`, `VERSION` 1.5.1.

## 2026-04-22 — Grafana: SGLang дашборд по мотивам vLLM V2 (sglangdash2-slgpu)

### Импорт vllmdash2 и порт на sglang:*
- **Что:** в `monitoring/grafana/provisioning/dashboards/json/` добавлены исходник `vllmdash2.json` (vLLM Monitoring V2) и адаптация `sglangdash2-slgpu.json` (uid `sglangdash2-slgpu`, метрики `sglang:*`, переменные `instance` / `model_name`, datasource `prometheus`); скрипт `_build_sglangdash2.py` для пересборки из vLLM JSON.
- **Почему:** запрос пользователя — переделать vLLM-дашборд под SGLang.
- **Файлы:** `vllmdash2.json`, `sglangdash2-slgpu.json`, `_build_sglangdash2.py`, `VERSION` 1.5.0.
- **Решение:** прямой 1:1 по метрикам невоземён (нет `finished_reason` в Prometheus SGLang); вместо этого — сопоставления (aborted/requests, TTFT/inter-token, `token_usage`, retraction вместо preemption и т.д.).

## 2026-04-22 — прогон 20260422_104802 и обновление bench/report.md

### Эталонная scenario-матрица Kimi-K2.6
- **Что:** локально добавлен полный прогон `bench/results/vllm/20260422_104802/` (676 запросов, 0 ошибок, `summary.json`). В `bench/report.md`: строка в §1, новая §2.4 с таблицей метрик, уточнения §2/§4.1/§5 под эталон после фикса SSE v1.2.1; контекст прогона `20260422_103109` (ложный `no_content`).
- **Почему:** пользователь сообщил о новых результатах прогона; зафиксированы выводы для отчёта A/B.
- **Файлы:** `bench/report.md`, `VERSION` 1.2.2, `docs/HISTORY.md`. Артефакты `bench/results/*` в `.gitignore` — в git только отчёт.

---

## 2026-04-22 — парсинг SSE в bench_openai / bench_load (no_content)

### Исправление no_content при валидном ответе vLLM/Kimi
- **Что:** в `scripts/bench_openai.py` и `scripts/bench_load.py` добавлены `_delta_stream_started` и `_delta_text_chunk_count`. TTFT фиксируется при появлении ключа `content` (включая пустую строку в служебных чанках vLLM), либо ключей `reasoning_content` / `reasoning`. Счётчик выхода учитывает непустой `content`, элементы `content[].text` и reasoning-текст. Убрана логика «только `if content:`», из-за которой часть успешных стримов помечалась как `no_content`.
- **Почему:** прогон `20260422_103109` показал массовый `no_content` при HTTP 200; причина — несовпадение с фактическим форматом чанков (пустой content + reasoning / служебные кадры).
- **Файлы:** `scripts/bench_openai.py`, `scripts/bench_load.py`, `docs/HISTORY.md`.
- **Версия:** `1.2.0` → `1.2.1` (patch — исправление парсинга SSE / `no_content`).

---

## 2026-04-22 — отчёт по бенчмаркам Kimi-K2.6 и коды ошибок в scenario-бенче

### Сводный отчёт vLLM (Kimi-K2.6)
- **Что:** заполнен `bench/report.md`: сводная таблица прогонов Kimi-K2.6 (scenario + load), таблицы по сценариям `20260421_144128` и `20260421_181145`, разбор фаз load-тестов по `time_series.csv`, аналитика (насыщение очереди, сравнение 250 vs 1500 users), выводы для A/B с SGLang. Добавлена §2.0 с расшифровкой имён сценариев `p*_o*_c*` и ролей concurrency (ссылка на `scripts/bench_openai.py`).
- **Почему:** запрос пользователя на сводный отчёт с аналитикой по результатам в `bench/results/vllm/`.
- **Файлы:** `bench/report.md`, `docs/HISTORY.md`.

### Коды ошибок вместо NaN в `bench_openai.py`
- **Что:** в `ScenarioResult` при полном фейле ячейки числовые поля сериализуются как `null` (не `NaN`). Добавлены `error_code` (самый частый код) и `errors_breakdown` (счётчики). Исключения нормализуются через `_classify_exception` (`HTTPError:N`, `URLError:…`, `TimeoutError`, краткий `ClassName:msg`). В `compare.py` функция `_fmt` выводит `err:<code>` для `null`/NaN при наличии `error_code`.
- **Почему:** запрос пользователя — в прогонах scenario вместо нечитаемого NaN видеть код ошибки.
- **Файлы:** `scripts/bench_openai.py`, `scripts/compare.py`, `docs/HISTORY.md`.

### Соблюдение правил сессии (read-history / project-history)
- **Что:** явное чтение `docs/HISTORY.md`, `docs/AGENTS.md` при старте задачи и дополнение журнала этой записью.
- **Почему:** правила `.cursor/rules/read-history-on-start.mdc` и `project-history.mdc`.
- **Файлы:** `docs/HISTORY.md`.

### Релиз 1.2.0 — коммит и push
- **Что:** `VERSION` 1.1.11 → 1.2.0; `git add/commit/push` изменений бенчмарка, отчёта, GRACE knowledge-graph (аннотации M-BENCH/M-COMPARE).
- **Почему:** запрос пользователя на коммит и push; MINOR — расширение формата вывода scenario-бенча (`error_code`, `errors_breakdown`).
- **Файлы:** `VERSION`, `bench/report.md`, `scripts/bench_openai.py`, `scripts/compare.py`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.

---

## Автоопределение и валидация запущенного engine+model (bench/load)

### slgpu_validate_running_config
- **Что:** добавлены `slgpu_detect_running_model()` и `slgpu_validate_running_config()` в `_lib.sh`. `cmd_bench.sh` и `cmd_load.sh` теперь автоматически читают запущенный движок из docker compose и текущую модель из `/v1/models`, сравнивая с аргументами `--engine` и `-m`. При несоответствии — информативная ошибка с подсказкой `down`/`up`/`restart`. Связаны с CrossLinks M-BENCH/M-LOAD → M-LIB.
- **Почему:** пользователь запросил, чтобы bench и load читали и проверяли текущую конфигурацию запущенного движка и модели.
- **Файлы:** `scripts/_lib.sh`, `scripts/cmd_bench.sh`, `scripts/cmd_load.sh`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`, `VERSION`.
- **Версия:** `1.1.4` → `1.1.5` (patch — фича).

## Длительный нагрузочный тест (bench_load)

### Burst-режим — максимальная throughput на 192 vCPU
- **Что:** добавлен флаг `--burst` в `bench_load.py` и `cmd_load.sh`. В burst-режиме `think_time=0`, каждый worker шлёт запросы без пауз. Для 192 vCPU рекомендуется `--users 384` (по 2 одновременных запроса на ядро). Обновлён README с примером burst-команды.
- **Почему:** пользователь запросил распараллелить запросы по 2 на каждый vCPU для максимальной нагрузки.
- **Файлы:** `scripts/bench_load.py`, `scripts/cmd_load.sh`, `docs/HISTORY.md`, `VERSION`.
- **Версия:** `1.1.3` → `1.1.4` (patch — фича).

### Фиксы bench_load.py (race condition, RPS delta, логирование)
- **Что:** fix race condition в `_user_worker` — потоки теперь активно ждут включения через sleep/poll вместо мгновенного break при `active=False`. RPS пересчитан через delta (snapshot) вместо cumulative. Добавлено логирование ошибок API в stdout. `cmd_load.sh` — добавлена preflight-проверка API (`curl /v1/models`) с информативным сообщением об ошибке и подсказкой команды `./slgpu up`.
- **Почему:** пользователь запустил `load` без предварительного `up` и получал 100% ошибок с неинформативным CSV. Также 250 потоков мгновенно умирали из-за race condition.
- **Файлы:** `scripts/bench_load.py`, `scripts/cmd_load.sh`, `docs/HISTORY.md`, `VERSION`.
- **Версия:** `1.1.1` → `1.1.2` (patch — багфикс).

### Реализация M-LOAD
- **Что:** создан `scripts/bench_load.py` — длительный нагрузочный тест с эмуляцией 200-300 виртуальных пользователей, фазами ramp-up/steady/ramp-down, сбором time-series метрик (TTFT, latency, throughput, error rate) в CSV каждые 5 сек. `scripts/cmd_load.sh` — обёртка интеграция с `./slgpu`. Обновлены GRACE-артефакты: M-LOAD добавлен в knowledge-graph, development-plan, verification-plan. README обновлён разделом 10 с примерами запуска и описанием артефактов.
- **Почему:** пользователь запросил эмуляцию работы 200-300 пользователей в течение 15-20 минут с записью параметров производительности.
- **Файлы:** `scripts/bench_load.py`, `scripts/cmd_load.sh`, `slgpu`, `scripts/cmd_help.sh`, `README.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `VERSION`.
- **Версия:** `1.1.0` → `1.1.1` (patch — документация).

---

## Инициализация GRACE-фреймворка

### Развёртывание каркаса GRACE из template
- **Что:** проект адаптирован к методологии GRACE (Graph-RAG Anchored Code Engineering): скопированы `.cursor/rules/` (7 файлов), `.kilo/agent/rules.md`, созданы `docs/AGENTS.md`, `docs/HISTORY.md`, `grace/**` (requirements, technology, plan, verification, knowledge-graph), корневой `AGENTS.md` и `VERSION`.
- **Почему:** внедрение унифицированных правил Cursor/Kilo и GRACE для управляемой разработки AI-агентами в проекте slgpu.
- **Файлы:** `.cursor/rules/`, `.kilo/agent/rules.md`, `docs/AGENTS.md`, `docs/HISTORY.md`, `grace/**`, `AGENTS.md`, `VERSION`.
- **Версия:** `1.0.0`.

---

## Per-preset образы vLLM (cu130, Driver 580)

### VLLM_DOCKER_IMAGE в каждом пресете
- **Что:** в девяти файлах `configs/models/*.env` задана **`VLLM_DOCKER_IMAGE`** с тегами **`*-x86_64-cu130`** (или `v0.19.1-x86_64-cu130` для Kimi — отдельного семейного тега в Hub нет). Qwen-линейка — `qwen3_5-x86_64-cu130`, GLM — `glm51-x86_64-cu130`, MiniMax — `minimax27-x86_64-cu130`, DeepSeek V4 — `deepseekv4-x86_64-cu130`. Обновлены `configs/models/README.md`, корневой `README.md` (таблица переменных, примеры, troubleshooting, ограничения). **`VERSION`** 2.4.0 → **2.5.0** (MINOR: поведение конфигурации по пресетам).
- **Почему:** запрос пользователя — хост **NVIDIA Driver 580 / nvidia-smi «CUDA 13.0»**, сервер **Supermicro SYS-821GE-TNHR** (x86); образы vLLM с **CUDA 13.x в контейнере** и семейные теги с [Docker Hub vllm/vllm-openai](https://hub.docker.com/r/vllm/vllm-openai/tags), без дублирования образа в `main.env`.
- **Файлы:** `configs/models/*.env`, `configs/models/README.md`, `README.md`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** явные теги **x86_64** для однозначности на H200-стенде; Kimi — стабильная линия **v0.19.1-cu130** в отсутствие отдельного тега модели.

### Prometheus: длительное хранение TSDB
- **Что:** в `main.env` **`PROMETHEUS_RETENTION_TIME=100y`** (вместо 15d); в `docker-compose.monitoring.yml` дефолт `${PROMETHEUS_RETENTION_TIME:-100y}`; в `monitoring/README.md` — пояснение про лимит по размеру.
- **Почему:** запрос пользователя хранить данные Prometheus «бесконечно»; у Prometheus нет флага без срока — **100y** как практическая бесконечность; диск растёт без верхней границы, пока **`PROMETHEUS_RETENTION_SIZE=0`**.
- **Файлы:** `main.env`, `docker-compose.monitoring.yml`, `monitoring/README.md`, `VERSION` 2.5.1, `docs/HISTORY.md`.

### GLM-5.1-FP8: ускорение (MTP + batch)
- **Что:** `SLGPU_VLLM_SPECULATIVE_CONFIG` в `serve.sh` и `docker-compose.yml`; в `glm-5.1-fp8.env` — **MTP** `{"method":"mtp","num_speculative_tokens":3}` по [GLM/GLM5.md](https://github.com/vllm-project/recipes/blob/main/GLM/GLM5.md); **`SLGPU_MAX_NUM_BATCHED_TOKENS=16384`**. `configs/models/README`, `VERSION` 2.5.2.
- **Почему:** запрос ускорить пресет; рецепт vLLM для 8×H200 с MTP и крупнее chunked prefill.
- **Решение:** при OOM — снизить batched tokens или убрать `SLGPU_VLLM_SPECULATIVE_CONFIG` из пресета.

### Комментарии «Что / Для чего / Варианты» во всех .env
- **Что:** в `main.env` и во всех `configs/models/*.env` у каждого параметра (или блока) — тройка: определение, назначение в slgpu/vLLM/SGLang, типичные значения.
- **Почему:** запрос пользователя на прозрачную настройку без чтения только README.
- **Файлы:** `main.env`, `configs/models/*.env`, `VERSION` 2.5.4, `docs/HISTORY.md`. В `kimi-k2.6.env` добавлен явный `MM_ENCODER_TP_MODE=data` (как в README) с комментариями. Дополнительно: `configs/secrets/hf.env.example` — тот же формат к `HF_TOKEN`.

### Сеть Docker `slgpu`: метки compose (incorrect label)
- **Что:** `slgpu_ensure_slgpu_network` в `scripts/_lib.sh` больше не вызывает «голый» `docker network create slgpu` без меток; при отсутствии сети создаёт с `com.docker.compose.project` / `com.docker.compose.network`. Если сеть есть с неправильными метками — явная ошибка с командами `down` + `network rm`. Раздел в `monitoring/README.md`.
- **Почему:** Docker Compose v2 отказывается подключать к проекту сеть без ожидаемых label (симптом пользователя: *network has incorrect label*).
- **Файлы:** `scripts/_lib.sh`, `monitoring/README.md`, `VERSION` 2.5.5, `docs/HISTORY.md`.

### Документация: централизация логов Docker
- **Что:** `monitoring/LOGS.md` — варианты: journald, syslog, Loki+Grafana, внешние агенты; ссылка из `monitoring/README.md`.
- **Почему:** запрос, как собрать логи контейнеров в одно место.
- **Файлы:** `monitoring/LOGS.md`, `monitoring/README.md`, `VERSION` 2.5.6, `docs/HISTORY.md`.

### Мониторинг: Grafana Loki + Promtail (локальный диск /opt/mon)
- **Что:** сервисы `loki` и `promtail` в `docker-compose.monitoring.yml`; `LOKI_DATA_DIR` и `PROMTAIL_DATA_DIR` в `main.env` (по умолчанию `/opt/mon/loki`, `/opt/mon/promtail`); `monitoring/loki/loki-config.yaml`, `monitoring/promtail/promtail-config.yml`; provisioning datasource Loki в Grafana; `scripts/monitoring_fix_permissions.sh` — права Loki + каталога Promtail; `monitoring/LOGS.md`, `README`, `cmd_monitoring.sh`.
- **Почему:** запуск Loki+Promtail в Docker с хранением на локальном диске.
- **Версия:** 2.6.0 (MINOR — новые сервисы мониторинга).

### Langfuse: редирект на 127.0.0.1 после регистрации (док)
- **Что:** в [main.env](../main.env) и [monitoring/README.md](../monitoring/README.md) явно: **NEXTAUTH_URL** = URL из адресной строки (с `:LANGFUSE_PORT`), без `/` в конце; иначе NextAuth ведёт на localhost.
- **Версия:** 2.7.5 (PATCH).

### Langfuse (публичный URL) + LiteLLM без master key
- **Что:** в [`main.env`](../main.env) публичный **`NEXTAUTH_URL`** (с `:LANGFUSE_PORT`); **`LITELLM_MASTER_KEY=`** пусто; в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) убран дефолт `sk-slgpu-change-me` для `LITELLM_MASTER_KEY`; обновлены [`monitoring/litellm/config.yaml`](../monitoring/litellm/config.yaml), [README.md](../README.md), [monitoring/README.md](../monitoring/README.md).
- **Почему:** внешний доступ к UI без редиректа на localhost; вызов LiteLLM **без** заголовка `x-api-key` в доверенной сети.
- **Версия:** 2.7.6 (PATCH — конфиг/док).

### LiteLLM: 401 «No api key passed in» при пустом LITELLM_MASTER_KEY
- **Что:** в [`monitoring/litellm/litellm-entrypoint.sh`](../monitoring/litellm/litellm-entrypoint.sh) — **`unset LITELLM_MASTER_KEY`**, если значение пусто (как с Langfuse). Иначе прокси считает, что мастер-ключ задан, и требует `x-api-key` у клиента.
- **Версия:** 2.7.7 (PATCH).

### Langfuse: доступ извне (NEXTAUTH_URL, документация)
- **Что:** в [`main.env`](../main.env) расширены комментарии к **`NEXTAUTH_URL`**; явно **`LANGFUSE_BIND=0.0.0.0`**; раздел [«Доступ к Langfuse извне»](../monitoring/README.md) в [monitoring/README.md](../monitoring/README.md); строка в корневом [README.md](../README.md) §6.
- **Почему:** при подключении к Langfuse **извне** критичен публичный `NEXTAUTH_URL` (не 127.0.0.1) и публикация порта/прокси.
- **Версия:** 2.7.4 (PATCH — док/дефолты main.env).

### Langfuse: данные на диске (bind), не named volumes
- **Что:** в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) вместо томов `slgpu_lf_*` — bind mount: **`LANGFUSE_POSTGRES_DATA_DIR`**, **`LANGFUSE_CLICKHOUSE_DATA_DIR`**, **`LANGFUSE_CLICKHOUSE_LOGS_DIR`**, **`LANGFUSE_MINIO_DATA_DIR`**, **`LANGFUSE_REDIS_DATA_DIR`** (дефолт `/opt/mon/langfuse/...`); [`main.env`](../main.env); [`scripts/monitoring_fix_permissions.sh`](../scripts/monitoring_fix_permissions.sh) — chown; [monitoring/README.md](../monitoring/README.md) — перенос со старых volumes.
- **Почему:** запрос хранить данные контейнеров Langfuse локально на диске, в одном стиле с Prometheus/Grafana.
- **Версия:** 2.7.3 (PATCH — только пути/права).

### LiteLLM: `config.yaml` в репо вместо шаблона
- **Что:** рабочий [`monitoring/litellm/config.yaml`](../monitoring/litellm/config.yaml) в git; плейсхолдер **`__LLM_API_PORT__`** в `api_base` подставляется `sed` в entrypoint; удалён `config.yaml.template`, compose монтирует `config.yaml`.
- **Почему:** запуск `./slgpu monitoring up` сразу после `git pull` без генерации из шаблона.
- **Файлы:** `monitoring/litellm/*`, `docker-compose.monitoring.yml`, `main.env` (LITELLM_LLM_ID), `README.md`, `monitoring/README.md`, `cmd_monitoring.sh`, `VERSION` 2.7.2.

### Фиксированное имя модели в API (devllm)
- **Что:** в [`serve.sh`](../scripts/serve.sh) флаг **`--served-model-name`** берётся из **`SLGPU_SERVED_MODEL_NAME`** (по умолч. в [`main.env`](../main.env) **`devllm`**), иначе `MODEL_ID`; то же для SGLang. В [`monitoring/litellm/`](../monitoring/litellm/) upstream для прокси: `LITELLM_LLM_ID` → `SLGPU_SERVED_MODEL_NAME` → `devllm`; в **config** одна модель **`devllm`**.
- **Почему:** запрос пользователя — одно и то же имя в API вне зависимости от выбранного чекпоинта.
- **Файлы:** `serve.sh`, `main.env`, `monitoring/litellm/*`, `README.md`, `monitoring/README.md`, `VERSION` 2.7.1.

### Мониторинг: Langfuse + LiteLLM Proxy
- **Что:** в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) — **Langfuse 3** (web + worker, Postgres, ClickHouse, Redis, MinIO в сети `langfuse` и на named volumes) и **LiteLLM** (прокси к vLLM через `host.docker.internal` + `LITELLM_LLM_ID`); UI Langfuse на **`LANGFUSE_PORT`** (по умолч. 3001, не 3000); MinIO на **9010/9011** (не 9090); [`monitoring/litellm/config.yaml.template`](../monitoring/litellm/config.yaml.template) и **entrypoint**; переменные в [`main.env`](../main.env); [README](../README.md), [monitoring/README](../monitoring/README.md), `scripts/cmd_monitoring.sh`.
- **Почему:** запрос пользователя — встроить **Langfuse** и **LiteLLM** в тот же стек мониторинга.
- **Решение:** vLLM не переименовывать по DNS между compose-проектами — тот же приём, что и для Prometheus, через **host** и `LITELLM_LLM_ID` = id из `/v1/models`. Langfuse: секреты и пароли в prod заменить; опциональные `LANGFUSE_*_KEY` для трейсинга из LiteLLM.
- **Версия:** 2.7.0 (MINOR — новые сервисы мониторинга).

### GLM-5.1-FP8: GPU_MEM_UTIL 0.88 → 0.94
- **Что:** в `glm-5.1-fp8.env` поднят **`GPU_MEM_UTIL`** при заметном свободном VRAM после старта.
- **Почему:** запрос пользователя; больше памяти под KV и батчи при том же `MAX_MODEL_LEN`.
- **Файлы:** `configs/models/glm-5.1-fp8.env`, `VERSION` 2.5.3, `docs/HISTORY.md`.

### LiteLLM: `STORE_MODEL_IN_DB`, снятие Python-обёртки
- **Что:** включено хранение моделей в БД: **`STORE_MODEL_IN_DB=True`** в [`main.env`](../main.env) и **`STORE_MODEL_IN_DB`** в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) (дефолт `True` при пустом). В [`litellm-entrypoint.sh`](../monitoring/litellm/litellm-entrypoint.sh) снова прямой запуск **`litellm`**; удалён `monitoring/litellm/slgpu_litellm_entry.py`, убран volume в compose. Обновлён [`monitoring/README.md`](../monitoring/README.md).
- **Почему:** ошибка `Set 'STORE_MODEL_IN_DB='True'...` при работе с моделями в UI; просьба убрать кастомную обёртку.
- **Компромисс:** без обёртки при необходимости для Langfuse 3 снова возможны 500 на OTEL, если upstream не шлёт `x-langfuse-ingestion-version` — согласовано с запросом.
- **Версия:** 2.7.16 (PATCH).

### LiteLLM: LITELLM_LOG и --detailed_debug
- **Что:** в [`main.env`](../main.env) — **`LITELLM_LOG`** (по умолч. INFO); в [`litellm-entrypoint.sh`](../monitoring/litellm/litellm-entrypoint.sh) при `DEBUG` добавляется **`--detailed_debug`**. В [`monitoring/README.md`](../monitoring/README.md) — кратко про отладку и `OTEL_LOG_LEVEL`.
- **Почему:** запрос — подробнее писать ошибки и детали в логах прокси.
- **Версия:** 2.7.17 (PATCH).

### Langfuse: док — HTTP 500 и MinIO/S3 vs OTEL
- **Что:** в [`monitoring/README.md`](../monitoring/README.md) — раздел про **500** при сбоях **blob storage** (MinIO) и отличие от ошибок **OTEL/LiteLLM**; в [`main.env`](../main.env) — закомментированный **`LANGFUSE_LOG_LEVEL=debug`**.
- **Почему:** типовой чеклист (ingestion 500, credentials, сеть) при self-hosted.
- **Версия:** 2.7.18 (PATCH).

### Monitoring: одна сеть `slgpu` (без `langfuse`)
- **Что:** в [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) все сервисы (включая Postgres, ClickHouse, Redis, MinIO, Langfuse, LiteLLM, `litellm-pg-init`) подключены только к внешней **`slgpu`**; удалена отдельная сеть **`slgpu-monitoring-langfuse`**. Обновлены [`monitoring/README.md`](../monitoring/README.md), [`main.env`](../main.env) (комментарий).
- **Почему:** запрос — «в одной slgpu»; проще рассуждать о DNS и изоляции.
- **Миграция:** после `git pull` — `docker compose -f docker-compose.monitoring.yml --env-file main.env up -d` (пересоздание контейнеров). Старую неиспользуемую сеть при желании: `docker network rm slgpu-monitoring-langfuse`.
- **Версия:** 2.7.19 (PATCH).

### Langfuse + MinIO: minio-bucket-init (NoSuchBucket)
- **Что:** сервис **`minio-bucket-init`** (`minio/mc`, скрипт [`monitoring/langfuse/minio-bucket-init.sh`](../monitoring/langfuse/minio-bucket-init.sh)) создаёт S3-бакеты для `LANGFUSE_S3_EVENT_UPLOAD_BUCKET` / `LANGFUSE_S3_MEDIA_BUCKET` до старта **langfuse-web** / **langfuse-worker**; комментарии в [`main.env`](../main.env); раздел в [`monitoring/README.md`](../monitoring/README.md).
- **Почему:** в логах web — **`NoSuchBucket`**, upload в `events/otel/…` при пустом MinIO.
- **Версия:** 2.7.20 (PATCH).

### LiteLLM: model_info (цена за 1M токенов)
- **Что:** в [`monitoring/litellm/config.yaml`](../monitoring/litellm/config.yaml) у **`devllm`** — **`input_cost_per_1m_token: 1.0`**, **`output_cost_per_1m_token: 3.0`** (в 10 раз выше ориентира 0.1 / 0.3).
- **Почему:** запрос — задать стоимость модели для LiteLLM.
- **Версия:** 2.7.21 (PATCH).

### LiteLLM: модели только в БД, пустой model_list в config
- **Что:** [`monitoring/litellm/config.yaml`](../monitoring/litellm/config.yaml) — **`model_list: []`**, маршруты в UI/БД. Обновлены [`monitoring/README.md`](../monitoring/README.md), [`main.env`](../main.env) (комментарий).
- **Почему:** запрос — убрать модель из файла, добавлена в БД.
- **Версия:** 2.7.22 (PATCH).

## 2026-04-25 — DeepSeek V4: KV cache не auto

### Пресеты deepseek-v4-pro / deepseek-v4-flash: `KV_CACHE_DTYPE=fp8_e4m3`
- **Что:** в [`configs/models/deepseek-v4-pro.env`](../configs/models/deepseek-v4-pro.env) и [`deepseek-v4-flash.env`](../configs/models/deepseek-v4-flash.env) вместо **`auto`** — **`fp8_e4m3`** (комментарии: vLLM `DeepseekV4MLAAttention` assert — только `fp8*`). В [`README.md`](../README.md) §14 строка в таблице troubleshooting; в [`configs/models/README.md`](../configs/models/README.md) — уточнение к **`KV_CACHE_DTYPE`**.
- **Почему:** сбой старта vLLM: `AssertionError: DeepseekV4 only supports fp8 kv-cache format for now, got auto` при `kv_cache_dtype=auto` в логе движка.
- **Файлы:** `configs/models/deepseek-v4-pro.env`, `configs/models/deepseek-v4-flash.env`, `README.md`, `configs/models/README.md`, `VERSION`, `docs/HISTORY.md`.
- **Версия:** 2.7.22 → **2.7.23** (PATCH).

### vLLM: опциональный `SLGPU_VLLM_ATTENTION_BACKEND` (DeepSeek V4, INFO fp8_ds_mla)
- **Что:** в [`scripts/serve.sh`](../scripts/serve.sh) при непустом **`SLGPU_VLLM_ATTENTION_BACKEND`** — флаг **`--attention-backend`**. Проброс в [`docker-compose.yml`](../docker-compose.yml) (`vllm`), комментарии в [`main.env`](../main.env), в пресетах [`deepseek-v4-pro.env`](../configs/models/deepseek-v4-pro.env) / [`deepseek-v4-flash.env`](../configs/models/deepseek-v4-flash.env) (закомментированный пример `FLASHINFER_MLA_SPARSE`); [`README.md`](../README.md) §6/§14, [`configs/models/README.md`](../configs/models/README.md).
- **Почему:** INFO vLLM: *Using DeepSeek's fp8_ds_mla KV cache* — штатно; переключение на «стандартный» fp8 KV — по рекомендации vLLM через backend.
- **Версия:** 2.7.23 → **2.7.24** (PATCH).

## 2026-04-25 — DeepSeek V4: парсеры `deepseek_v4`, tokenizer-mode

### Пресеты deepseek-v4-pro / deepseek-v4-flash: reasoning/tool + tokenizer
- **Что:** в пресетах вместо **`deepseek_r1` / `pythonic`** — **`REASONING_PARSER=deepseek_v4`**, **`TOOL_CALL_PARSER=deepseek_v4`**, **`SLGPU_VLLM_TOKENIZER_MODE=deepseek_v4`** по [блогу vLLM DeepSeek V4](https://vllm.ai/blog/deepseek-v4). В [`scripts/serve.sh`](../scripts/serve.sh) — при непустом **`SLGPU_VLLM_TOKENIZER_MODE`** флаг **`--tokenizer-mode`**. Проброс в [`docker-compose.yml`](../docker-compose.yml) (сервис `vllm`). Обновлены [`README.md`](../README.md) §6/§14, [`configs/models/README.md`](../configs/models/README.md), [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml).
- **Почему:** запрос пользователя — сменить/отключить парсер; исследование: для **V4** в vLLM задокументирован **`deepseek_v4`**, не **`deepseek_r1`** (R1-семейство); неверный парсер давал пустой/некорректный расклад `content` / reasoning.
- **Решение:** не вводить «отключение» парсера в `serve.sh` (vLLM по-прежнему требует корректные флаги для V4) — вместо этого выровнять пресет с официальным рецептом.
- **Версия:** 2.7.24 → **2.7.25** (PATCH).

### Пресеты DeepSeek V4: `KV_CACHE_DTYPE=fp8`
- **Что:** в [`configs/models/deepseek-v4-pro.env`](../configs/models/deepseek-v4-pro.env) и [`deepseek-v4-flash.env`](../configs/models/deepseek-v4-flash.env) **`KV_CACHE_DTYPE=fp8`** (ранее `fp8_e4m3`); комментарии в пресетах; строка troubleshooting в [`README.md`](../README.md).
- **Почему:** запрос пользователя — перейти на обобщённое значение `fp8` в vLLM (внутренняя развязка формата).
- **Версия:** 2.7.25 → **2.7.26** (PATCH).

### vLLM: `SLGPU_VLLM_MAX_NUM_SEQS` → `--max-num-seqs`, конкуренция запросов
- **Что:** в [`scripts/serve.sh`](../scripts/serve.sh) при заданной **`SLGPU_VLLM_MAX_NUM_SEQS`** (положительное целое) — флаг **`--max-num-seqs`**. Проброс в [`docker-compose.yml`](../docker-compose.yml); комментарий и пример в [`configs/models/deepseek-v4-pro.env`](../configs/models/deepseek-v4-pro.env); [`README.md`](../README.md) §6/§14, [`configs/models/README.md`](../configs/models/README.md); [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml).
- **Почему:** запрос — стабильно **50+** одновременных запросов; без снижения **`MAX_MODEL_LEN`** KV vLLM не даёт много слотов (в логе: малый `GPU KV cache size` при большом `max_model_len`); `max_num_seqs` — доп. рычаг после снижения окна.
- **Версия:** 2.7.26 → **2.7.27** (MINOR-уровень по смыслу — новый проброс в CLI, по SemVer в репо — PATCH как обычно для slgpu).

### Пресет deepseek-v4-pro: 256K, рецепт vLLM, `--block-size`
- **Что:** [`configs/models/deepseek-v4-pro.env`](../configs/models/deepseek-v4-pro.env): **`MAX_MODEL_LEN=262144`**, **`SLGPU_MAX_NUM_BATCHED_TOKENS=12288`**, **`SLGPU_VLLM_MAX_NUM_SEQS=128`**, **`VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=1`**, **`SLGPU_VLLM_BLOCK_SIZE=256`**, **`SLGPU_VLLM_COMPILATION_CONFIG`** (блог vLLM); комментарий про **DP+EP** vs **TP8**; [`scripts/serve.sh`](../scripts/serve.sh) — **`--block-size`**, [`docker-compose.yml`](../docker-compose.yml) — **`SLGPU_VLLM_BLOCK_SIZE`**. [`README.md`](../README.md) §6, [`configs/models/README.md`](../configs/models/README.md), [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml).
- **Почему:** запрос — 262144 и улучшения по рецепту; без переключения на **data-parallel-size 8** (иная топология, чем slgpu **TP8**).
- **Версия:** 2.7.27 → **2.7.28** (PATCH).

### Пресет deepseek-v4-pro: `GPU_MEM_UTIL=0.91` (KV vs 262144)
- **Что:** в [`configs/models/deepseek-v4-pro.env`](../configs/models/deepseek-v4-pro.env) **`GPU_MEM_UTIL=0.91`**, выровненный **`SGLANG_MEM_FRACTION_STATIC=0.91`**; комментарии про проверку vLLM V1 (минимум KV под одну последовательность `max_model_len`, профайлер графов). В [`README.md`](../README.md) §14 — строка troubleshooting для `ValueError` KV.
- **Почему:** падение старта: при **`MAX_MODEL_LEN=262144`**, **0.88** и **~6.7 GiB** free KV vLLM требовал **~8.3 GiB** на один запрос полной длины; в логе *estimated maximum model length* ~12k.
- **Решение:** поднять util (не только «~0.9033» из лога — это эквивалент старого поведения без профайлера, не гарантия 262K); при OOM — снижать **`MAX_MODEL_LEN`** или util.
- **Версия:** 2.7.28 → **2.7.29** (PATCH).

### Пресет deepseek-v4-flash: 256K, выравнивание с Pro (KV, рецепт v4)
- **Что:** [`configs/models/deepseek-v4-flash.env`](../configs/models/deepseek-v4-flash.env): **`MAX_MODEL_LEN=262144`** (вместо 393216), **`GPU_MEM_UTIL` / `SGLANG_MEM_FRACTION_STATIC=0.91`**, **`SLGPU_MAX_NUM_BATCHED_TOKENS=12288`**, **`SLGPU_VLLM_MAX_NUM_SEQS=128`**, **`SLGPU_VLLM_BLOCK_SIZE=256`**, **`SLGPU_VLLM_COMPILATION_CONFIG`**. [`README.md`](../README.md) §14 — коротко про стартовый стек `flashinfer` / `KeyboardInterrupt: terminated`.
- **Почему:** на стенде: падение/прерывание на **`create_engine_config` → _set_compile_ranges → flashinfer** и **`KeyboardInterrupt: terminated`**, плюс 384K `max_model_len` непрактичен для KV на том же шаблоне, что Pro.
- **Версия:** 2.7.29 → **2.7.30** (PATCH).

### cmd_up: явный `env` для docker compose; V4 Pro/Flash `GPU_MEM_UTIL=0.94`; кэш `mhc_pre`
- **Что:** в [`scripts/cmd_up.sh`](../scripts/cmd_up.sh) функция **`compose_llm_env`** передаёт в `docker compose` **VLLM_DOCKER_IMAGE**, **MODEL_ID**, **MAX_MODEL_LEN**, **GPU_MEM_UTIL**, **KV_CACHE_DTYPE**, **SLGPU_** батч/парсеры и т.д., чтобы корневой **`.env`** (подстановка в YAML) не перебивал пресет (**0.88** vs **0.94**). Пресеты [**deepseek-v4-pro.env**](../configs/models/deepseek-v4-pro.env) / [**deepseek-v4-flash.env**](../configs/models/deepseek-v4-flash.env): **`GPU_MEM_UTIL` / `SGLANG_MEM_FRACTION_STATIC=0.94`**, комментарии. [`README.md`](../README.md): §2–3 про `.env`, §14 — KV, **mhc_pre** / очистка `torch_compile_cache`.
- **Почему:** лог: **`gpu_memory_utilization: 0.88`** при пресете 0.91; **ValueError** KV 8.34 vs 6.67 GiB; предупреждение **mhc_pre** из устаревшего AOT после смены образа vLLM.
- **Версия:** 2.8.1 → **2.8.2** (PATCH).

### Web Control Plane: новое приложение `web/` (FastAPI + React/Vite)
- **Что:** добавлен модуль [`web/`](../web/) — отдельное web-приложение управления стендом. Backend на FastAPI + SQLAlchemy 2.0 (async) + aiosqlite + Alembic; frontend на React 18 + Vite + TypeScript + TanStack Query; UI выполнен в стиле [`develonica.ru`](https://develonica.ru/) (тёмная навигация, крупные градиентные карточки, светлый enterprise-фон). Один контейнер с bind-mount `/data` для SQLite и read-only `/var/run/docker.sock` для опроса статусов. Контракт зафиксирован в [`web/CONTRACT.md`](../web/CONTRACT.md).
- **Возможности:** реестр HF-моделей и инициируемые загрузки через `./slgpu pull`; CRUD пресетов с двусторонней синхронизацией с [`configs/models/*.env`](../configs/models/); запуск/останов/рестарт vLLM/SGLang через `./slgpu up|down|restart`; управление мониторингом через `./slgpu monitoring …`; здоровье и базовые маршруты LiteLLM Proxy; журнал всех CLI-операций со stdout/stderr tail и advisory lock на `(scope, resource)`.
- **Границы:** mutating-операции уходят только через CLI allowlist в [`app.services.slgpu_cli`](../web/backend/app/services/slgpu_cli.py); Docker socket используется read-only для статусов, портов и логов; секреты HF/Grafana/LiteLLM/Langfuse в БД не сохраняются.
- **Почему:** запрос пользователя — единое web-окно для скачивания моделей, пресетов, инференса, мониторинга и LiteLLM на современном стеке, без поломки текущей CLI-логики и компоуз-файлов.
- **Версия:** 2.7.30 → **2.8.0** (MINOR — новый модуль `web/` с публичным API).

### Web backend: `spa_fallback` — `response_model=None` (FastAPI + Pydantic v2)
- **Что:** в [`web/backend/app/main.py`](../web/backend/app/main.py) у catch-all маршрута SPA — **`response_model=None`**, чтобы FastAPI не пытался строить Pydantic-модель от аннотации **`FileResponse | JSONResponse`**.
- **Почему:** при старте uvicorn: **`FastAPIError: Invalid args for response field`** на `@app.get("/{full_path:path}" …)`.
- **Файлы:** `web/backend/app/main.py`, `VERSION`, `docs/HISTORY.md`.
- **Версия:** 2.8.0 → **2.8.1** (PATCH).

### Web: SQLite `unable to open database file` на bind-mount `/data`
- **Что:** [`web/docker-entrypoint.sh`](../web/docker-entrypoint.sh) — старт от root, `mkdir -p /data`, `chown -R 10001:10001 /data`, запуск `tini`+uvicorn через `setpriv` (UID 10001). В [`web/Dockerfile`](../web/Dockerfile) убран `USER slgpuweb` на этапе **PID 1**; в [`web/docker-compose.yml`](../web/docker-compose.yml) снят `user: 10001:10001` (чтобы сработал chown). В [`web/backend/app/db/session.py`](../web/backend/app/db/session.py) — `_ensure_sqlite_parent_dir` перед созданием движка. [`.gitattributes`](../.gitattributes) — LF для `web/docker-entrypoint.sh`. [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml) — уточнение `export-web-image`. [`web/CONTRACT.md`](../web/CONTRACT.md) — раздел 5, entrypoint и `/data`.
- **Почему:** bind-монт `./data` с хоста часто **root-owned**, UID 10001 не мог создать `slgpu-web.db` → `sqlite3.OperationalError: unable to open database file` при `init_db`. На Docker Desktop / NTFS **chown** к монту не всегда «липнет» — тогда named volume для `/data` или права/владелец с хоста.
- **Версия:** 2.8.2 → **2.8.3** (PATCH).

### Web: `WEB_COMPOSE_PROJECT_*` — дашборд и нестандартное имя стека (`sigpu` / …)
- **Что:** в [`web/backend/app/core/config.py`](../web/backend/app/core/config.py) — **`compose_project_infer`**, **`compose_project_monitoring`** (env: **`WEB_COMPOSE_PROJECT_INFER`**, **`WEB_COMPOSE_PROJECT_MONITORING`**). Используются в [`monitoring.py`](../web/backend/app/services/monitoring.py) и [`runtime.py`](../web/backend/app/services/runtime.py) вместо захардкоженных `slgpu` / `slgpu-monitoring`. [`web/docker-compose.yml`](../web/docker-compose.yml), [`web/.env.example`](../web/.env.example), [`web/CONTRACT.md`](../web/CONTRACT.md) обновлены. Локально: [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml).
- **Почему:** при другом `COMPOSE_PROJECT_NAME` (например `sigpu`) опрос Docker по лейблам не находит контейнеры → **«container not found»**, хотя в Portainer стеки **running**.
- **Версия:** 2.8.3 → **2.8.4** (PATCH).

### Web: `PermissionError` на `/var/run/docker.sock` (docker group / GID)
- **Что:** [`web/docker-entrypoint.sh`](../web/docker-entrypoint.sh) — после `chown /data` по GID сокета: `getent`/`groupadd` при необходимости, `usermod -aG` для **`slgpuweb`**, запуск через **`runuser -u slgpuweb`** (вместо `setpriv`, чтобы подхватывались доп. группы). В [`web/Dockerfile`](../web/Dockerfile) — пакет **`util-linux`**, комментарий. В [`docker_client.py`](../web/backend/app/services/docker_client.py) — уточнение в логе при Permission. [`web/CONTRACT.md`](../web/CONTRACT.md) — раздел 5.
- **Почему:** `PermissionError(13) cannot connect` к Docker API: сокет **660** `root:docker`, ранее процесс оставался только с gid 10001 без группы сокета.
- **Версия:** 2.8.5 → **2.8.6** (PATCH).

### Web: tini «не PID 1» (subreaper)
- **Что:** в [`web/Dockerfile`](../web/Dockerfile) — **`ENTRYPOINT ["/usr/bin/tini", "-g", "--", "…/docker-entrypoint.sh"]`**, внутри скрипта убран вложенный tini, после root: **`exec runuser -u slgpuweb -- "$@"`**, иначе **`exec "$@"`**. [`web/CONTRACT.md`](../web/CONTRACT.md), [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml).
- **Почему:** `runuser` стал PID 1, tini — дочерний процесс → предупреждение **Tini is not running as PID 1** и отсутствие reaping.
- **Версия:** 2.8.7 → **2.8.8** (PATCH).

### Web: больше логов (дашборд, Docker, `WEB_LOG_LEVEL`)
- **Что:** `get_docker_inspector()` (один `DockerInspector` на процесс) — не спамить при опросе. INFO: [`dashboard.py`](../web/backend/app/api/v1/dashboard.py) `[api][dashboard][BLOCK_AGGREGATE]`, [`monitoring.py`](../web/backend/app/services/monitoring.py) `probe_all`, [`runtime.py`](../web/backend/app/services/runtime.py) `snapshot`; DEBUG: [`docker_client`](../web/backend/app/services/docker_client.py) `get_by_service` при пустом списке. В [`config.py`](../web/backend/app/core/config.py) / [`main.py`](../web/backend/app/main.py) — **`log_level`**, `WEB_LOG_LEVEL` в [docker-compose](web/docker-compose.yml), [`.env.example`](../web/.env.example), [`web/CONTRACT.md`](../web/CONTRACT.md). **VERSION** 2.8.9.
- **Почему:** запрос — «не хватает логов, чтобы видеть, что пыталось сделать приложение» (Docker down / не тот project).
- **Версия:** 2.8.8 → **2.8.9** (PATCH).

### Web compose: `MODELS_DIR` (по умолчанию /opt/models)
- **Что:** в [`web/docker-compose.yml`](../web/docker-compose.yml) — том **`${MODELS_DIR:-/opt/models}:${MODELS_DIR:-/opt/models}:rw`**; комментарии, [`web/.env.example`](../web/.env.example), [`web/CONTRACT.md`](../web/CONTRACT.md), [`web/README.md`](../web/README.md). [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml) — `export-web-image`.
- **Почему:** веса и `./slgpu pull` из job runner читают путь из `../main.env` (часто **`/opt/models`**) внутри контейнера — без mount каталога не существовало. Данные мониторинга в web не дублируем (только API/движок).
- **Версия:** 2.8.9 → **2.8.10** (PATCH).

### Web: `get_by_service` — fallback Portainer/Compose (лейблы, имена v1/v2)
- **Что:** в [`web/backend/app/services/docker_client.py`](../web/backend/app/services/docker_client.py) после неудачного `containers.list(…, filters=...)` — нормализованные `com.docker.compose.*` (регистр, `-`/`_`) и сопоставление по имени `project-service-N` / `project_service_N`; кэш `containers.list(all)` 1,5s. [`web/CONTRACT.md`](../web/CONTRACT.md) — краткое пояснение.
- **Почему:** при `docker=ok` и `WEB_COMPOSE_PROJECT_*=sigpu*`, но 8/8 `container not_found`: двойной label-filter на стороне демона/Portainer не находил контейнеры, тогда как в Portainer стек **running**.
- **Версия:** 2.8.10 → **2.8.11** (PATCH).

### DeepSeek V4 Flash: без `compilation_config`; `SLGPU_VLLM_ENFORCE_EAGER` → `--enforce-eager`
- **Что:** в [`configs/models/deepseek-v4-flash.env`](../configs/models/deepseek-v4-flash.env) **`SLGPU_VLLM_COMPILATION_CONFIG`** не задаётся по умолчанию (закомментирован рецепт как у Pro). В [`scripts/serve.sh`](../scripts/serve.sh) при **`SLGPU_VLLM_ENFORCE_EAGER=1`** — **`--enforce-eager`**. Проброс в [`docker-compose.yml`](../docker-compose.yml), [`scripts/cmd_up.sh`](../scripts/cmd_up.sh) (`compose_llm_env`), [`README.md`](../README.md) §6/§14, [`configs/models/README.md`](../configs/models/README.md). Web: [`web/backend/app/services/presets.py`](../web/backend/app/services/presets.py), [`env_files.py`](../web/backend/app/services/env_files.py). Комментарий в [`deepseek-v4-pro.env`](../configs/models/deepseek-v4-pro.env) при том же **InductorError**.
- **Почему:** на стенде: **`torch._inductor.exc.InductorError`** / `replace_by_example` при **`determine_available_memory` → profile_run** с полным compile-рецептом.
- **Версия:** 2.8.4 → **2.8.5** (PATCH).

### DeepSeek V4 Flash: `SLGPU_VLLM_ENFORCE_EAGER=1` по умолчанию
- **Что:** в [`configs/models/deepseek-v4-flash.env`](../configs/models/deepseek-v4-flash.env) задано **`SLGPU_VLLM_ENFORCE_EAGER=1`**; комментарий: Inductor падает и при дефолтной компиляции vLLM V1 без `SLGPU_VLLM_COMPILATION_CONFIG`. Точечно: [`README.md`](../README.md) §14, [`configs/models/README.md`](../configs/models/README.md).
- **Почему:** повтор **InductorError** / `profile_run` при **gpu_memory_utilization 0.94** и без non-default `compilation_config` в логе — обход **`--enforce-eager`**.
- **Версия:** 2.8.6 → **2.8.7** (PATCH).

### Структура репо: `configs/monitoring/`, `data/`, `./slgpu web up`
- **Что:** каталог **`monitoring/`** перенесён в **`configs/monitoring/`** (Prometheus, Grafana, Loki, Langfuse, LiteLLM и т.д.); **`docker-compose.monitoring.yml`** монтирует конфиги из **`./configs/monitoring/…`**. Добавлен каталог **`data/`** с **`data/README.md`** и `.gitkeep` под **`models/`**, **`web/`**; в **`main.env`** по умолчанию **`MODELS_DIR=./data/models`**, **`WEB_DATA_DIR=./data/web`**, **`PROMETHEUS_*` / Langfuse и др. — под **`./data/monitoring/…`**; **`.gitignore`** скрывает содержимое `data/**` кроме README и `.gitkeep`. **`slgpu_docker_compose`** в **`scripts/_lib.sh`** (`docker compose --project-directory` = корень репо); **`slgpu_ensure_data_dirs`** создаёт относительные `./data/…`. Новая команда **`./slgpu web`** → **`scripts/cmd_web.sh`** (`up|down|restart|logs|build`); **`web/docker-compose.yml`**: том **`.:/slgpu`**, **`WEB_DATA_DIR`**, **`MODELS_DIR`**. Обновлены **`README.md`**, **`web/CONTRACT.md`**, **`web/README.md`**, **`main.env`**, **`scripts/cmd_*`**, **`monitoring_fix_permissions.sh`**, **`cmd_prepare.sh`**, **`cmd_pull.sh`**, **`grace/**`**, **`docs/AGENTS.md`**, **VERSION** 2.9.0 → **2.10.0** (MINOR).
- **Почему:** запрос — единая схема путей на сервере и запуск web через **`slgpu`**, конфиги мониторинга рядом с остальными конфигами.
- **Решение:** при миграции с `/opt/models` и `/opt/mon/…` перенесите данные на диске и обновите **`main.env`**; пересоздайте контейнеры compose.

### Infra: жёсткие `container_name`; web — fallback по имени `slgpu-*`
- **Что:** в [`docker-compose.yml`](../docker-compose.yml) — **`container_name: slgpu-vllm`**, **`slgpu-sglang`**. В [`docker-compose.monitoring.yml`](../docker-compose.monitoring.yml) — у перечисленных сервисов префикс **`slgpu-monitoring-`** (без автоматического суффикса `…-1` у одного реплики на сервис). В [`web/backend/app/services/docker_client.py`](../web/backend/app/services/docker_client.py) в **`get_by_service`** (fallback) — сопоставление по имени **`slgpu-<service>`** / **`slgpu-monitoring-<service>`**. [`web/CONTRACT.md`](../web/CONTRACT.md) — п.5–6. Синхронизация GRACE: [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml), [`grace/plan/development-plan.xml`](../grace/plan/development-plan.xml). **VERSION** 2.8.11 → **2.9.0** (MINOR).
- **Почему:** запрос — стабильные имена в Portainer/CLI; дашборд web должен находить контейнеры и при «чужом» `COMPOSE_PROJECT_NAME`, согласуясь с жёсткими именами в compose.
- **Решение:** `scale>1` для сервиса с **`container_name`** в Compose несовместим — в корневом compose комментарий; для мониторинга по одной реплике на сервис.

### Web: один источник настроек — `main.env` (без `web/.env.example`)
- **Что:** в [`main.env`](../main.env) в секции Web UI — явно заданы `WEB_*`, `LLM_API_PORT*`, `PROMETHEUS_PORT`, `LITELLM_PORT`, `LOKI_PORT` и т.д.; удалён шаблон [`web/.env.example`](../web/.env.example). Обновлены [`web/README.md`](../web/README.md), [`web/CONTRACT.md`](../web/CONTRACT.md), [`web/docker-compose.yml`](../web/docker-compose.yml), [`web/backend/app/core/config.py`](../web/backend/app/core/config.py), [`grace/plan/development-plan.xml`](../grace/plan/development-plan.xml) (M-WEB), **VERSION** 2.10.0 → **2.10.1** (PATCH).
- **Почему:** запрос — не вести отдельный env для web, держать параметры в `main` (как и при `./slgpu web up --env-file main.env`).
- **Решение:** ручной запуск compose — из корня с `--env-file main.env` (см. `web/README.md`).

### Docker: compose-файлы в каталоге `docker/`
- **Что:** в каталоге **`docker/`**: `docker-compose.yml`, `docker-compose.monitoring.yml`, `docker-compose.web.yml` (ранее корень и `web/docker-compose.yml`; web: `build.context: ./web`, `Dockerfile` в `web/`). Добавлен `docker/README.md`. Обновлены `scripts/cmd_*.sh`, `scripts/_lib.sh`, `README.md`, `web/*`, `configs/**`, `main.env`, `grace/**`, **VERSION** 2.10.1 → **2.11.0** (MINOR).
- **Почему:** запрос — все файлы запуска Docker лежат в одной папке `docker/`.
- **Решение:** `slgpu_docker_compose` по-прежнему с `--project-directory` = корень репо; пути в YAML и `env_file: main.env` не менялись по смыслу.

### Docker: vLLM/SGLang — `docker-compose.llm.yml`
- **Что:** файл **`docker/docker-compose.yml`** переименован в **`docker/docker-compose.llm.yml`**; обновлены ссылки (скрипты, README, `main.env`, `grace/verification/verification-plan.xml` и др.), **VERSION** 2.11.0 → **2.11.1** (PATCH).
- **Почему:** не путать с остальными `docker-compose*.yml` в каталоге `docker/`.
- **Решение:** `docker compose -f docker/docker-compose.llm.yml …` из корня с `--project-directory` репозитория.

### Web: `Dockerfile` в `docker/Dockerfile.web`
- **Что:** `web/Dockerfile` перенесён в [`docker/Dockerfile.web`](../docker/Dockerfile.web); в [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml) — `dockerfile: ../docker/Dockerfile.web` (при `context: ./web`). Обновлены [`README.md`](../README.md), [`web/README.md`](../web/README.md), [`docker/README.md`](../docker/README.md), [`grace/plan/development-plan.xml`](../grace/plan/development-plan.xml) (M-WEB), **VERSION** 2.11.1 → **2.11.2** (PATCH).
- **Почему:** единая папка `docker/` для compose и инструкций сборки, без `Dockerfile` в `web/`.
- **Решение:** `docker-entrypoint.sh` остаётся в `web/` (в контексте сборки).

### Пресеты: `data/presets`, `PRESETS_DIR`, web + CLI
- **Что:** файлы пресетов `*.env` перенесены из `configs/models/` в **`data/presets/`**; в **`main.env`** добавлено **`PRESETS_DIR=./data/presets`**. **`scripts/_lib.sh`**: **`slgpu_presets_dir`**, все команды и списки пресетов используют этот путь; **`slgpu_ensure_data_dirs`** создаёт каталог. **Web**: `app/core/config.py` читает путь из `main.env` (как `MODELS_DIR` в `hf_models.py`). **`.gitignore`**: исключение для **`data/presets/**`**, чтобы шаблоны пресетов оставались в git. Справка по полям — по-прежнему **`configs/models/README.md`**. Обновлены **`README.md`**, **`data/README.md`**, **`web/**`**, **`docs/AGENTS.md`**, **`grace/knowledge-graph/knowledge-graph.xml`**, **`grace/plan/development-plan.xml`**, **VERSION** 2.11.2 → **2.12.0** (MINOR: новая раскладка данных для пресетов).
- **Почему:** запрос — единый каталог под веса/данные и явное чтение/запись пресетов web’ом в `data/presets`.
- **Решение:** на уже развёрнутых хостах: перенести `*.env` в `data/presets` или задать **`PRESETS_DIR`** на старый путь.

### Web compose: `MODELS_DIR` в контейнере — абсолютный target
- **Что:** в [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml) bind-монтирование заменено на `…:/slgpu/data/models:rw` (вместо `${MODELS_DIR}:${MODELS_DIR}` — справа был относительный `data/models`, Docker требует абсолютный путь). В [`web/backend/app/services/hf_models.py`](../web/backend/app/services/hf_models.py) относительный `MODELS_DIR` из `main.env` разрешается от `WEB_SLGPU_ROOT` (`/slgpu`). [`web/README.md`](../web/README.md). **VERSION** 2.12.0 → **2.12.1** (PATCH).
- **Почему:** `docker: invalid mount path: 'data/models' mount path must be absolute` при **`./slgpu web up`**, если `MODELS_DIR=./data/models`.
- **Решение:** снова **`./slgpu web up`**. Абсолютный `MODELS_DIR` вне репо: по-прежнему монтируется в `/slgpu/data/models` — при необходимости обновите `main.env` или сделайте symlink `data/models` на внешний путь, чтобы UI и `MODEL_ID` совпадали.

### Web: `WEB_BIND` по умолчанию `0.0.0.0`
- **Что:** в [`main.env`](../main.env), [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml) и [`scripts/cmd_web.sh`](../scripts/cmd_web.sh) дефолт **внешнего** доступа: **`WEB_BIND=0.0.0.0`**. Обновлены [`web/README.md`](../web/README.md), [`web/CONTRACT.md`](../web/CONTRACT.md). **VERSION** 2.12.1 → **2.12.2** (PATCH).
- **Почему:** порт slgpu-web по умолчанию должен быть доступен вовне, не только с localhost.
- **Решение:** только с того же хоста — **`WEB_BIND=127.0.0.1`**; при открытом порту защиту обеспечивают firewall, VPN, обратный прокси; сам UI без отдельной аутентификации (см. контракт).

### Loki/Promtail: монтирование каталога конфига
- **Что:** в [`docker/docker-compose.monitoring.yml`](../docker/docker-compose.monitoring.yml) вместо бинда одного файла — **`./configs/monitoring/loki` → `/etc/loki`**, **`./configs/monitoring/promtail` → `/etc/promtail`**. Пояснение и починка в [`configs/monitoring/LOGS.md`](../configs/monitoring/LOGS.md) (§3). **VERSION** 2.12.2 → **2.12.3** (PATCH).
- **Почему:** `read /etc/loki/loki-config.yaml: is a directory` — на хосте путь к конфигу был каталогом (типично, если исходного файла не было при первом up).
- **Решение:** после `git pull` — `rm` ошибочного каталога, `git checkout` файла, **`./slgpu monitoring up`**, при необходимости `--force-recreate` для `loki`/`promtail`.

### Loki: автоисправление каталога вместо `loki-config.yaml`
- **Что:** в [`scripts/_lib.sh`](../scripts/_lib.sh) — **`slgpu_ensure_config_yaml_is_file`**; вызывается из [`scripts/cmd_monitoring.sh`](../scripts/cmd_monitoring.sh) перед **`monitoring up|restart`**: если `loki-config.yaml` / `promtail-config.yml` — каталог, удаление и **`git checkout`**. **VERSION** 2.12.3 → **2.12.4** (PATCH).
- **Почему:** ошибка «is a directory» повторялась, пока на диске оставался каталог.
- **Решение:** без git на сервере — вручную положить файлы из репо; затем **`./slgpu monitoring up`**.

### Web UI: HTTP-пробы мониторинга через `host.docker.internal`
- **Что:** в [`web/backend/app/core/config.py`](../web/backend/app/core/config.py) — **`monitoring_http_host`** (env `WEB_MONITORING_HTTP_HOST`); в [`web/backend/app/services/monitoring.py`](../web/backend/app/services/monitoring.py) вместо **`127.0.0.1`** для Prometheus, Grafana, Langfuse, LiteLLM. В [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml) — **`WEB_MONITORING_HTTP_HOST=host.docker.internal`**. В [`docker/Dockerfile.web`](../docker/Dockerfile.web) — пакет **`git`** (для `slgpu_ensure_loki_promtail_config_files` из job). [`main.env`](../main.env), [`web/README.md`](../web/README.md). **VERSION** 2.12.4 → **2.12.5** (PATCH).
- **Почему:** из контейнера `slgpu-web` адрес `127.0.0.1` — сам контейнер; стек monitoring слушает на хосте. В UI казалось, что «из web не работает», хотя `./slgpu monitoring up` с хоста поднимал стек.
- **Решение:** **`./slgpu web build`** (образ с `git`) и **`./slgpu web up`**. Локальный запуск backend без Docker — оставить **`127.0.0.1`** (дефолт).

### Prometheus: каталог `configs/monitoring/prometheus` вместо бинда отдельных yaml
- **Что:** конфиги перенесены в **`configs/monitoring/prometheus/`** (`prometheus.yml`, `prometheus-alerts.yml`); в [`docker/docker-compose.monitoring.yml`](../docker/docker-compose.monitoring.yml) — том **`./configs/monitoring/prometheus:/etc/prometheus:ro`**. В [`scripts/cmd_monitoring.sh`](../scripts/cmd_monitoring.sh) — **`slgpu_ensure_monitoring_bind_config_files`**: **`slgpu_ensure_config_yaml_is_file`** для обоих yaml. Обновлены [`README.md`](../README.md), [`configs/monitoring/README.md`](../configs/monitoring/README.md), [`configs/monitoring/LOGS.md`](../configs/monitoring/LOGS.md), [`docs/AGENTS.md`](../AGENTS.md), **`grace/knowledge-graph/knowledge-graph.xml`**, **`grace/plan/development-plan.xml`**, **`grace/verification/verification-plan.xml`**. **VERSION** 2.12.5 → **2.12.6** (PATCH).
- **Почему:** при запуске monitoring из web (job) Docker падал с **`not a directory` / file vs directory** на монте **`/slgpu/configs/monitoring/prometheus.yml`** — та же ситуация, что с Loki: отсутствие файла и создание каталога с таким именем.
- **Решение:** после `git pull` удалить на хосте ошибочные каталоги `prometheus.yml` / `prometheus-alerts.yml`, если остались; затем **`./slgpu monitoring up`** или пересоздать сервис **`prometheus`**.

### Web: монтаж репо по хост-пути (`SLGPU_HOST_REPO`) — лечит запуск `monitoring up` из web
- **Что:** **корневая** причина падений `slgpu monitoring up`/`fix-perms` из web — рассогласование путей: репо в web было смонтировано как `/slgpu`, а на хосте лежит в другом каталоге. `docker compose` внутри web резолвил относительные bind-маунты от `/slgpu/...` и отдавал docker daemon (на хосте) пути, которых на хосте нет → daemon **создавал пустые каталоги** на месте файлов и монтировал их (Loki: `is a directory`; Prometheus: `mount … not a directory`; **`minio-bucket-init` exit 126** на «скрипте-каталоге»; `monitoring fix-perms` дополнительно падал на `sudo: command not found`, потому что внутри web нет `sudo`). Фикс: репо bind-монтируется в web по **тому же абсолютному хост-пути**.
  - [`scripts/cmd_web.sh`](../scripts/cmd_web.sh): `export SLGPU_HOST_REPO="$ROOT"` в начале скрипта.
  - [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml): `working_dir: ${SLGPU_HOST_REPO:-/slgpu}`, `WEB_SLGPU_ROOT: ${SLGPU_HOST_REPO:-/slgpu}`, том `${SLGPU_HOST_REPO:-.}:${SLGPU_HOST_REPO:-/slgpu}`, target моделей — `${SLGPU_HOST_REPO:-/slgpu}/data/models`.
  - [`scripts/cmd_monitoring.sh`](../scripts/cmd_monitoring.sh): `slgpu_ensure_monitoring_bind_config_files` теперь дополнительно лечит каталоги-обманки на месте `configs/monitoring/langfuse/minio-bucket-init.sh`, `configs/monitoring/litellm/{init-litellm-db.sh,litellm-entrypoint.sh,config.yaml}` (на случай, если до фикса web уже создал такие каталоги на хосте).
  - Документация: [`README.md`](../README.md), [`web/CONTRACT.md`](../web/CONTRACT.md), [`web/README.md`](../web/README.md), [`configs/monitoring/LOGS.md`](../configs/monitoring/LOGS.md). GRACE: M-WEB, V-M-WEB.
  - **VERSION** 2.12.6 → **2.13.0** (MINOR — меняется bind-схема web-контейнера и публичный контракт `WEB_SLGPU_ROOT`).
- **Почему:** через web **обязательно** работает не только сам web-контейнер, но и любые `docker compose` команды, которые web запускает в host-daemon — у них общий язык **хостовых путей**, поэтому пути в web и на хосте обязаны совпадать.
- **Решение:** на сервере `./slgpu web restart` (или `down` → `up`). На хосте удалить ошибочно созданные каталоги под старым префиксом `/slgpu/...` (если есть). После этого `monitoring up`/`fix-perms` из UI должны проходить так же, как с консоли. **`fix-perms` из web** по-прежнему требует, чтобы внутри web-контейнера `chown` был доступен (entrypoint web — root, потом drop в `slgpuweb`; backend job runner работает уже не от root, поэтому `chown` без `sudo` не сработает — `fix-perms` лучше делать с хоста; в UI оставлено как удобный вход для будущего «root-job-runner», см. отдельный backlog).

### Web 2.13.0 follow-up: регресс uvicorn, `hf` в образе, `fix-perms` без `sudo`

- **Что:** три исправления поверх 2.13.0:
  1. **Регресс uvicorn `ModuleNotFoundError: No module named 'app'`.** В 2.13.0 в [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml) был добавлен `working_dir: ${SLGPU_HOST_REPO:-/slgpu}`, что переопределяло `WORKDIR /srv/app` из [`docker/Dockerfile.web`](../docker/Dockerfile.web). uvicorn запускался из хост-пути репо, где нет пакета `app/`, и контейнер падал в рестарт-цикл. **Фикс:** убран `working_dir` из compose; uvicorn снова стартует из `/srv/app`. Для CLI-вызовов backend сам выставляет `cwd=settings.slgpu_root` в `app/services/jobs.py` — это было всегда.
  2. **`slgpu pull` из web падал с `Не найдена команда «hf»`.** В образе [`docker/Dockerfile.web`](../docker/Dockerfile.web) нет `huggingface_hub[cli]`, а [`scripts/cmd_pull.sh`](../scripts/cmd_pull.sh) требует `hf` в `PATH`. **Фикс:** в Dockerfile.web добавлены `huggingface_hub[cli]` (команда `hf`) и `hf_transfer` — нужен `./slgpu web build`.
  3. **`monitoring fix-perms` падал с `sudo: command not found`.** В web-контейнере нет `sudo`, и backend job runner работает под `slgpuweb` (без root). **Фикс:** [`scripts/monitoring_fix_permissions.sh`](../scripts/monitoring_fix_permissions.sh) выполняет `mkdir`/`chown` через короткоживущий root-контейнер `docker run --rm -u 0:0 -v <dir>:/p alpine sh -c '...'`. Образ-помощник: переменная **`SLGPU_FIXPERMS_HELPER_IMAGE`** (по умолчанию `alpine:latest`); работает и на хосте от обычного пользователя, и из web (через `docker.sock`). `sudo` больше не нужен.
- **Файлы:** [`docker/docker-compose.web.yml`](../docker/docker-compose.web.yml), [`docker/Dockerfile.web`](../docker/Dockerfile.web), [`scripts/monitoring_fix_permissions.sh`](../scripts/monitoring_fix_permissions.sh), [`web/CONTRACT.md`](../web/CONTRACT.md), [`web/README.md`](../web/README.md), [`configs/monitoring/LOGS.md`](../configs/monitoring/LOGS.md), [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml), [`grace/plan/development-plan.xml`](../grace/plan/development-plan.xml), [`grace/verification/verification-plan.xml`](../grace/verification/verification-plan.xml). **VERSION** 2.13.0 → **2.13.1** (PATCH).
- **Почему:** регресс ломал старт web; `pull` и `fix-perms` через UI оставались неработоспособны после 2.13.0. Все три — однотипные «образ/контракт» правки.
- **Решение:** на сервере `./slgpu web build && ./slgpu web restart`. После этого `pull` и `fix-perms` проходят из UI; `fix-perms` дополнительно работает с любого пользователя на хосте (без `sudo`). При оффлайн-стенде задайте локально доступный образ через `SLGPU_FIXPERMS_HELPER_IMAGE`.

### Web logging: одна JSON-строка на один LogRecord

- **Что:** [`web/backend/app/core/logging.py`](../web/backend/app/core/logging.py) теперь идемпотентно заменяет handlers у `root`, `app`, `httpx`, `uvicorn`, `uvicorn.error`, `uvicorn.access` и выставляет `propagate=False`, чтобы app/httpx/uvicorn записи не проходили через несколько форматтеров. Из JSON payload исключены служебные поля `message`, `asctime`, `taskName`, которые дублировали `msg`/timestamp. Обновлены [`web/CONTRACT.md`](../web/CONTRACT.md), [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml), [`grace/verification/verification-plan.xml`](../grace/verification/verification-plan.xml). **VERSION** 2.13.1 → **2.13.2** (PATCH).
- **Почему:** после исправления старта web и monitoring logs стали показывать строки вида `INFO INFO ... ts=... logger=... msg=...`, то есть один record рендерился несколькими обработчиками/форматтерами и засорял Portainer/Loki.
- **Решение:** после `git pull` выполнить `./slgpu web build && ./slgpu web restart`. Ожидаемый формат app/httpx/uvicorn логов — одна JSON-строка на событие, без повторяющихся `INFO` и без повторного `msg`.

### Web pull: writable Hugging Face cache и абсолютный MODELS_DIR

- **Что:** [`scripts/cmd_pull.sh`](../scripts/cmd_pull.sh) теперь нормализует `MODELS_DIR` из `main.env` (`./data/models`) в абсолютный путь от корня репозитория, заранее создаёт каталог моделей, а также выбирает writable `HOME`/`HF_HOME` для Hugging Face cache. Если `$HOME` отсутствует или не writable, используется абсолютный `WEB_DATA_DIR`; `HF_HOME` по умолчанию — `${WEB_DATA_DIR}/huggingface`. В [`docker/Dockerfile.web`](../docker/Dockerfile.web) добавлены `HF_HOME=/data/huggingface`, writable `/data/huggingface` и полноценный `/home/slgpuweb` (`useradd --create-home`). Обновлены [`web/CONTRACT.md`](../web/CONTRACT.md), [`web/README.md`](../web/README.md), [`grace/knowledge-graph/knowledge-graph.xml`](../grace/knowledge-graph/knowledge-graph.xml), [`grace/plan/development-plan.xml`](../grace/plan/development-plan.xml), [`grace/verification/verification-plan.xml`](../grace/verification/verification-plan.xml). **VERSION** 2.13.2 → **2.13.3** (PATCH).
- **Почему:** после установки `hf` web download начал выполняться, но падал на `Permission denied: /home/slgpuweb` и относительных путях `data/models/.../.cache/huggingface`; Hugging Face CLI пишет refs/cache даже при `--local-dir`.
- **Решение:** после `git pull` выполнить `./slgpu web build && ./slgpu web restart`, затем повторить pull из UI. На старом образе фикс в `cmd_pull.sh` тоже помогает, но новый образ предпочтителен из-за корректного home/cache.

### Диагностика Qwen3.6-35B-A3B: CUDA error 803

- **Что:** разобран лог старта vLLM для пресета `qwen3.6-35b-a3b`: `cudaGetDeviceCount()` падает с `Error 803: system has unsupported display driver / cuda driver combination`.
- **Почему:** пользователь прислал стек `WorkerProc initialization failed`; проверка пресета показала образ `vllm/vllm-openai:qwen3_5-x86_64-cu130`, рассчитанный на CUDA 13.x и хостовый NVIDIA Driver 580.
- **Файлы:** `data/presets/qwen3.6-35b-a3b.env`, `docker/docker-compose.llm.yml`, `docs/HISTORY.md`.
- **Решение:** первично обновить драйвер NVIDIA на VM до ветки 580+ либо заменить `VLLM_DOCKER_IMAGE` на образ с CUDA runtime, совместимый с текущим драйвером; параметры модели/KV не являются причиной ошибки.

### Pull: создание `--local-dir` модели до `hf download`

- **Что:** в [`scripts/cmd_pull.sh`](../scripts/cmd_pull.sh) перед `hf download --local-dir` теперь создаётся сам каталог модели (`${MODELS_DIR}/${MODEL_ID}`), а не только родительская директория.
- **Почему:** `hf download` из web/CLI падал на `FileNotFoundError: data/models/Qwen/Qwen3-30B-A3B/.cache/huggingface`, потому что Hugging Face CLI пытался создать `.cache/huggingface` внутри ещё отсутствующего `local-dir`.
- **Файлы:** `scripts/cmd_pull.sh`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `docs/HISTORY.md`.
- **Решение:** оставить нормализацию `MODELS_DIR` в абсолютный путь и дополнительно гарантировать существование каталога модели; **VERSION** 2.13.3 → **2.13.4** (PATCH).

### Web Models: источник списка — папки `MODELS_DIR`, не пресеты

- **Что:** [`web/backend/app/services/hf_models.py`](../web/backend/app/services/hf_models.py) добавляет синхронизацию DB-реестра с фактическими каталогами `${MODELS_DIR}/<org>/<repo>`; [`GET /api/v1/models`](../web/backend/app/api/v1/models.py) и дашборд запускают эту синхронизацию перед чтением. Добавлен backend smoke-test на обнаружение локальной модели без пресета.
- **Почему:** пользователь указал, что приложение неверно ищет модели по пресетам, хотя список локальных моделей должен строиться по папкам весов.
- **Файлы:** `web/backend/app/services/hf_models.py`, `web/backend/app/api/v1/models.py`, `web/backend/app/api/v1/dashboard.py`, `web/backend/tests/test_api_smoke.py`, `web/CONTRACT.md`, `web/README.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** пресеты остаются рецептами запуска, но не источником списка скачанных моделей; **VERSION** 2.13.4 → **2.13.5** (PATCH).

### Web Presets: просмотр и редактирование пресета

- **Что:** на странице пресетов добавлена форма просмотра/редактирования выбранного пресета: HF ID, engine, TP, served name, GPU mask, active, описание и JSON параметров. Backend `PATCH /api/v1/presets/{id}` теперь принимает `hf_id` и валидирует его; экспорт в `data/presets/*.env` остаётся отдельной кнопкой.
- **Почему:** пользователь запросил функционал просмотра и редактирования пресета в приложении.
- **Файлы:** `web/frontend/src/pages/Presets.tsx`, `web/frontend/src/api/types.ts`, `web/backend/app/api/v1/presets.py`, `web/backend/app/schemas/presets.py`, `web/backend/tests/test_api_smoke.py`, `web/CONTRACT.md`, `web/README.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** редактирование меняет запись БД и помечает её как drift; запись на диск выполняется явным экспортом, чтобы пользователь контролировал момент перезаписи `.env`; **VERSION** 2.13.5 → **2.13.6** (PATCH).

### Web Runtime: показывать запущенные модель и пресет

- **Что:** `POST /api/v1/runtime/up` и `restart` теперь создают запись `EngineRun` с preset, HF ID, TP и портом; `down` помечает активные запуски остановленными. `GET /api/v1/runtime/snapshot` и dashboard дополняют Docker/API-снимок последним активным web-запуском. Runtime и Dashboard показывают запрошенный пресет, HF ID модели и TP рядом с engine/served models.
- **Почему:** пользователь запросил, чтобы при запуске модели приложение показывало, какая модель/пресет запущены.
- **Файлы:** `web/backend/app/services/runtime.py`, `web/backend/app/api/v1/runtime.py`, `web/backend/app/api/v1/dashboard.py`, `web/backend/app/schemas/runtime.py`, `web/backend/tests/test_api_smoke.py`, `web/frontend/src/api/types.ts`, `web/frontend/src/pages/Runtime.tsx`, `web/frontend/src/pages/Dashboard.tsx`, `web/CONTRACT.md`, `web/README.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** источник `served_models` остаётся `/v1/models`, а source-of-truth для выбранного пользователем рецепта — последняя активная запись `runs`; **VERSION** 2.13.6 → **2.13.7** (PATCH).

### Web Runtime: хвост логов контейнера модели

- **Что:** добавлен `GET /api/v1/runtime/logs?tail=N`, который через read-only Docker API возвращает хвост stdout/stderr текущего `vllm`/`sglang` контейнера. На странице Runtime добавлен блок «Лог контейнера модели» с автообновлением каждые 5 секунд и ручной кнопкой refresh.
- **Почему:** пользователь запросил отображение логов контейнера модели, чтобы видеть, что происходит при запуске/работе.
- **Файлы:** `web/backend/app/services/runtime.py`, `web/backend/app/api/v1/runtime.py`, `web/backend/app/schemas/runtime.py`, `web/backend/tests/test_api_smoke.py`, `web/frontend/src/api/types.ts`, `web/frontend/src/pages/Runtime.tsx`, `web/CONTRACT.md`, `web/README.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** логи читаются только из Docker (`container.logs`, tail ограничен 1..2000), mutations не добавляются; **VERSION** 2.13.7 → **2.13.8** (PATCH).

### Monitoring bootstrap: init-контейнеры только при первом запуске

- **Что:** `minio-bucket-init` и `litellm-pg-init` в [`docker/docker-compose.monitoring.yml`](../docker/docker-compose.monitoring.yml) вынесены в профиль `bootstrap`; долгоживущие `langfuse-*` и `litellm` больше не зависят от них напрямую. [`scripts/cmd_monitoring.sh`](../scripts/cmd_monitoring.sh) при первом `./slgpu monitoring up` запускает эти bootstrap-сервисы, удаляет их остановленные контейнеры и создаёт markers в `data/monitoring/.bootstrap/`. Добавлена ручная команда `./slgpu monitoring bootstrap`.
- **Почему:** пользователь запросил, чтобы контейнеры `slgpu-monitoring-litellm-pg-init` и `slgpu-monitoring-minio-bucket...` создавались только один раз на новом сервере, а не при каждом обычном запуске/перезапуске monitoring.
- **Файлы:** `docker/docker-compose.monitoring.yml`, `scripts/cmd_monitoring.sh`, `README.md`, `configs/monitoring/README.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/verification/verification-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** `monitoring up` сам выполняет bootstrap только при отсутствии marker-файлов; повтор — `./slgpu monitoring bootstrap` или `SLGPU_MONITORING_BOOTSTRAP_FORCE=1`; **VERSION** 2.13.8 → **2.13.9** (PATCH).

### Web UX: активные jobs и защита от повторных кликов

- **Что:** Runtime и Monitoring страницы теперь опрашивают `/api/v1/jobs`, показывают активную queued/running job и блокируют конфликтующие кнопки до завершения. Backend command resources унифицированы: runtime-команды (`up/down/restart`) лочатся на `("engine","runtime")`, monitoring-команды — на `("monitoring","stack")`, поэтому прямые параллельные запросы тоже получают `409`.
- **Почему:** пользователь указал, что при нажатии запуска/остановки мониторинга и запуска модели непонятно, что происходит, и нет защиты от лишних нажатий во время уже выданной команды.
- **Файлы:** `web/backend/app/services/slgpu_cli.py`, `web/backend/tests/test_slgpu_cli.py`, `web/frontend/src/pages/Runtime.tsx`, `web/frontend/src/pages/Monitoring.tsx`, `web/CONTRACT.md`, `web/README.md`, `docs/AGENTS.md`, `grace/verification/verification-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** UI даёт немедленный feedback «команда выполняется», показывает job id/kind/status/message и направляет в «Задачи» за stdout/stderr tail; **VERSION** 2.13.9 → **2.13.10** (PATCH).

### Web branding: Develonica.LLM

- **Что:** web-приложение переименовано в **Develonica.LLM**: обновлены title, header brand, цветовые токены, градиенты, акценты и SVG favicon в LLM-тематике.
- **Почему:** пользователь запросил привести web UI к брендбуку сайта `develonica.ru`, назвать приложение Develonica.LLM и сгенерировать favicon под стиль и тематику приложения.
- **Файлы:** `web/frontend/index.html`, `web/frontend/src/components/Layout.tsx`, `web/frontend/src/styles/globals.css`, `web/frontend/public/favicon.svg`, `README.md`, `web/README.md`, `web/CONTRACT.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** выбран conservative rebrand без изменения API/поведения: тёмная технологичная шапка, синие AI-акценты, светлая рабочая область и векторная иконка; **VERSION** 2.13.10 → **2.13.11** (PATCH).

### Web Settings: публичный host для UI мониторинга

- **Что:** добавлен backend API `GET/PATCH /api/v1/settings/public-access`, сервис хранения настройки `server_host` в SQLite и страница `Настройки` во frontend. Monitoring/Dashboard/LiteLLM теперь подставляют публичный host в ссылки на Grafana, Prometheus, Langfuse и LiteLLM Admin UI.
- **Почему:** пользователь указал, что ссылки вида `http://host.docker.internal:4000/ui` некорректны для браузера; нужен IP/DNS сервера, задаваемый в настройках приложения.
- **Файлы:** `web/backend/app/services/app_settings.py`, `web/backend/app/api/v1/settings.py`, `web/backend/app/api/v1/monitoring.py`, `web/backend/app/api/v1/dashboard.py`, `web/backend/app/api/v1/litellm.py`, `web/backend/app/schemas/settings.py`, `web/backend/tests/test_api_smoke.py`, `web/frontend/src/pages/Settings.tsx`, `web/frontend/src/app/App.tsx`, `web/frontend/src/components/Layout.tsx`, `web/frontend/src/api/types.ts`, `web/CONTRACT.md`, `web/README.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** `WEB_MONITORING_HTTP_HOST` оставлен только для внутренних health-probe из контейнера, а browser URL строятся отдельно из `server_host`; если настройка пустая, используется hostname текущего запроса к Develonica.LLM; **VERSION** 2.13.11 → **2.13.12** (PATCH).

### Web CRUD: расширенное управление моделями и пресетами

- **Что:** добавлены `DELETE /api/v1/models/{id}` и `DELETE /api/v1/presets/{id}`; модели можно редактировать (revision/notes) и удалять из реестра или вместе с локальными весами внутри `MODELS_DIR`. Пресеты можно удалять из БД и опционально удалять `.env` внутри `PRESETS_DIR`. UI Models получил форму редактирования, UI Presets заменил raw JSON textarea параметров на key/value редактор с подсказками типовых runtime-переменных.
- **Почему:** пользователь запросил расширенные функции управления моделями и пресетами: удаление, изменение, особенно редактирование пресетов через набор параметров, а не текстом.
- **Файлы:** `web/backend/app/api/v1/models.py`, `web/backend/app/api/v1/presets.py`, `web/backend/app/services/hf_models.py`, `web/backend/app/services/presets.py`, `web/backend/tests/test_api_smoke.py`, `web/frontend/src/pages/Models.tsx`, `web/frontend/src/pages/Presets.tsx`, `web/CONTRACT.md`, `web/README.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** удаление файлов ограничено разрешёнными корнями (`MODELS_DIR`/`PRESETS_DIR`) и требует отдельного UI-подтверждения; **VERSION** 2.13.12 → **2.13.13** (PATCH).

### Web CSS: точная стилизация под Develonica

- **Что:** CSS Develonica.LLM переработан по сайту `develonica.ru` и публичным материалам бренда: Gilroy-first font stack, фирменный рубиновый акцент, молочно-белая база, крупные округлые карточки, pill-навигация, стрелочный brand mark, обновлённый favicon и theme-color.
- **Почему:** пользователь попросил изучить сайт Develonica и применить правильные стили, цвета, шрифты, управляющие элементы и навигацию.
- **Файлы:** `web/frontend/src/styles/globals.css`, `web/frontend/src/components/Layout.tsx`, `web/frontend/index.html`, `web/frontend/public/favicon.svg`, `web/README.md`, `web/CONTRACT.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** ушли от синего enterprise-акцента к рубиново-молочной брендовой системе; **VERSION** 2.13.13 → **2.13.14** (PATCH).

### Web pull: права на `data/models` bind mount

- **Что:** `web/docker-entrypoint.sh` теперь при старте от root создаёт и chown’ит не только `/data`, но и `${WEB_SLGPU_ROOT}/data/models` и `${WEB_SLGPU_ROOT}/data/presets` под uid 10001 (`slgpuweb`). Комментарий в `docker/docker-compose.web.yml` и web-контракт обновлены.
- **Почему:** пользователь показал ошибку web job `slgpu pull`: `mkdir: cannot create directory './data/models/Qwen/Qwen3-30B-A3B': Permission denied`. Причина — `MODELS_DIR=./data/models` монтируется отдельным bind mount внутри репозитория, а entrypoint исправлял владельца только `/data`.
- **Файлы:** `web/docker-entrypoint.sh`, `docker/docker-compose.web.yml`, `web/README.md`, `web/CONTRACT.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/verification/verification-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** после `git pull` выполнить `./slgpu web build && ./slgpu web restart`; новый контейнер исправит права на models/presets mounts до запуска backend; **VERSION** 2.13.14 → **2.13.15** (PATCH).

### Web Footer: версия и копирайт

- **Что:** общий Layout получил footer с актуальной версией и копирайтом `Igor Yatsishen, Develonica`. Frontend читает `/healthz`, backend теперь берёт версию из корневого `VERSION`, а не из package `app.__version__`.
- **Почему:** пользователь запросил отображать в футере приложения актуальную версию и копирайт.
- **Файлы:** `web/backend/app/main.py`, `web/frontend/src/components/Layout.tsx`, `web/frontend/src/api/types.ts`, `web/frontend/src/styles/globals.css`, `web/README.md`, `web/CONTRACT.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** footer остаётся в общей оболочке и автоматически обновляется после обновления `VERSION`; **VERSION** 2.13.15 → **2.13.16** (PATCH).

### Web CSS: синхронизация с live CSS Develonica

- **Что:** тема Develonica.LLM переделана по фактическому CSS сайта `develonica.ru`: подключены `IBM Plex Sans` и `Finlandica`, заменена рубиновая гипотеза на голубую палитру `#59AFFF`/`#0A5AA4`, светло-голубые градиенты `#F7FBFF`/`#E2EDF8`, белая sticky-шапка, подчёркнутая навигация, кнопки/контролы с radius `10px`, обновлены favicon и `theme-color`.
- **Почему:** пользователь уточнил, что нужна не стилизация «по мотивам», а подробное применение реальных стилей и цветовой гаммы сайта Develonica.
- **Файлы:** `web/frontend/src/styles/globals.css`, `web/frontend/index.html`, `web/frontend/public/favicon.svg`, `web/README.md`, `web/CONTRACT.md`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** за основу взяты переменные live CSS сайта (`--color-blue-develonica`, `--color-dark-blue-develonica`, `--font-family-main`, `--font-family-accent`); **VERSION** 2.13.16 → **2.13.17** (PATCH).

### Web runtime: /v1/models и /metrics из slgpu-web

- **Что:** `app/services/runtime.py` больше не ходит к `http://127.0.0.1:${порт}`: добавлены `WEB_LLM_HTTP_HOST` (в `docker/docker-compose.web.yml` — `host.docker.internal`, как у monitoring) и запасные базы `http://vllm:8111` / `http://sglang:8222` в сети `slgpu`. Dashboard: текст карточки «Метрики» уточняет, что статус — проверка из web, а не факт сбора Prometheus.
- **Почему:** из контейнера `slgpu-web` `127.0.0.1` — loopback web, а не хост с опубликованным портом vLLM; UI показывал «—» в served models и «нет» по /metrics при работающей модели.
- **Файлы:** `web/backend/app/core/config.py`, `web/backend/app/services/runtime.py`, `docker/docker-compose.web.yml`, `web/frontend/src/pages/Dashboard.tsx`, `web/README.md`, `web/CONTRACT.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** после `git pull` на сервере: `./slgpu web build && ./slgpu web restart`; **VERSION** 2.13.17 → **2.13.18** (PATCH).

### Web LiteLLM: health и /v1/models из slgpu-web

- **Что:** `app/services/litellm.py` использует `WEB_MONITORING_HTTP_HOST` (как `probe_all` и страница Мониторинг) вместо `127.0.0.1` для `GET /v1/models`, `/health/liveliness`, `/health/readiness` и `/ui`.
- **Почему:** с прежнего `127.0.0.1:4000` внутри web проверялся loopback web-контейнера, UI показывал FAIL при рабочем LiteLLM на хосте.
- **Файлы:** `web/backend/app/services/litellm.py`, `web/CONTRACT.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** `./slgpu web build && ./slgpu web restart`; **VERSION** 2.13.18 → **2.13.19** (PATCH).

### Web UI: «Отмена» в формах модели и пресета

- **Что:** на страницах **Модели** и **Пресеты** у блока «Изменить / Просмотр и редактирование» добавлена кнопка **Отмена** (`btn--ghost`): сбрасывает выбор и закрывает форму без сохранения. При несохранённых отличиях от данных в БД показывается подтверждение.
- **Почему:** запрос выйти из режима редактирования без записи в реестр.
- **Файлы:** `web/frontend/src/pages/Models.tsx`, `web/frontend/src/pages/Presets.tsx`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.19 → **2.13.20** (PATCH); на сервере пересобрать web при необходимости.

### Web UI: ширина контента и иконки в таблицах

- **Что:** `app-main` и футер растягиваются на ширину окна (`max-width: 100%`, горизонтальные отступы `clamp`). Таблицы «Реестр моделей» и «Все пресеты»: класс `table--registry` (узкая колонка действий, выравнивание вправо), действия — компактные кнопки 40×40 с SVG-иконками и `aria-label`/`title` (редактирование, скачивание, экспорт, удаление).
- **Почему:** удобнее использовать широкий экран; текстовые кнопки раздували строки.
- **Файлы:** `web/frontend/src/components/TableActionIcons.tsx`, `web/frontend/src/pages/Models.tsx`, `web/frontend/src/pages/Presets.tsx`, `web/frontend/src/styles/globals.css`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.20 → **2.13.21** (PATCH).

### Web UI: пресеты — удалить с диска в таблице

- **Что:** в «Все пресеты» добавлена кнопка-иконка (файл с крестом) **удалить пресет и .env с диска** — тот же API, что у «Удалить с .env» в форме: `delete_file=true`. У «удалить только БД» уточнён `aria-label`. У кнопки с диска — пунктирная рамка (`icon-btn--file-wipe`), `table-actions` допускают перенос строки при нехватке ширины.
- **Почему:** в строке таблицы была только операция без удаления `.env` на диске.
- **Файлы:** `web/frontend/src/components/TableActionIcons.tsx`, `web/frontend/src/pages/Presets.tsx`, `web/frontend/src/styles/globals.css`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.21 → **2.13.22** (PATCH).

### Web UI: fix-perms в Настройках

- **Что:** кнопка `fix-perms` убрана с страницы **Мониторинг**; в **Настройки** добавлена секция «Права на каталоги мониторинга» с той же командой `POST /api/v1/monitoring/action` и блокировкой, пока активна job мониторинга.
- **Почему:** перенос редкого административного действия в настройки, основная страница мониторинга — up/restart/down.
- **Файлы:** `web/frontend/src/pages/Monitoring.tsx`, `web/frontend/src/pages/Settings.tsx`, `web/README.md`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.22 → **2.13.23** (PATCH).

### Web UI: выравнивание колонки «Действия»

- **Что:** для `table--registry` последняя колонка: `text-align: center` для `th`/`td`, у `.table-actions` — `justify-content: center`.
- **Почему:** при выравнивании вправо длинный заголовок «Действия» визуально не совпадал с компактной группой иконок.
- **Файлы:** `web/frontend/src/styles/globals.css`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.23 → **2.13.24** (PATCH).

### Web UI: пояснение к полю «Движок» и `SLGPU_ENGINE` в экспорте

- **Что:** **Backend:** `export_preset_to_file` пишет в словарь для файла `SLGPU_ENGINE` из `preset.engine`; `_engine_from_values` при импорте сначала смотрит `SLGPU_ENGINE`, иначе эвристика (`SGLANG_MEM_FRACTION_STATIC` и т.д.); `render_env_text` в группе Runtime включает `SLGPU_ENGINE` для читаемого порядка в `.env`. **Frontend:** под селектором «Движок» — подсказка про БД, экспорт и `./slgpu up vllm|sglang` / Inference. **Контракт:** `web/CONTRACT.md` — таблица `presets` и `SLGPU_ENGINE`.
- **Почему:** вопрос пользователя, записывается ли движок в пресет и как это соотносится с образом vLLM в параметрах.
- **Файлы:** `web/backend/app/services/presets.py`, `web/backend/app/services/env_files.py`, `web/frontend/src/pages/Presets.tsx`, `web/CONTRACT.md`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.24 → **2.13.25** (PATCH).

### Web: движок убран из пресета (БД, экспорт, UI)

- **Что:** колонка `presets.engine` удалена из модели; API create/patch/response больше не принимают и не отдают `engine`; экспорт в `.env` не пишет `SLGPU_ENGINE`; `render_env` в Runtime без `SLGPU_ENGINE`; убраны поле «Движок» и колонка в UI. При старте `init_db` на SQLite — `ALTER TABLE ... DROP COLUMN engine`, если осталась legacy-колонка.
- **Почему:** запрос пользователя — не хранить движок в пресете; выбор vLLM/SGLang — только при запуске.
- **Файлы:** `web/backend/app/models/preset.py`, `app/schemas/presets.py`, `app/api/v1/presets.py`, `app/services/presets.py`, `app/services/env_files.py`, `app/db/session.py`, `web/frontend/src/pages/Presets.tsx`, `web/frontend/src/api/types.ts`, `web/backend/tests/test_api_smoke.py`, `web/CONTRACT.md`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.25 → **2.13.26** (PATCH; для не-SQLite кластеров без миграции вручную убрать колонку при необходимости).

### Web UI: пресеты — без «ложных» плейсхолдеров в параметрах

- **Что:** у полей «Ключ»/«Значение» в блоке параметров запуска убраны `placeholder` с примерами (`MAX_MODEL_LEN`, `262144`), добавлен `autoComplete="off"`.
- **Почему:** при пустом значении серый текст выглядел как заданный дефолт (запрос пользователя).
- **Файлы:** `web/frontend/src/pages/Presets.tsx`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.26 → **2.13.27** (PATCH).

### Web UI: центрирование иконок в кнопках таблиц

- **Что:** для `.btn--icon` заданы `justify-content: center`, `align-items: center`, `gap: 0`; для `svg` внутри — `display: block`, `flex-shrink: 0`.
- **Почему:** у `.btn` по умолчанию `inline-flex` с `flex-start` по главной оси — иконка прилипала к левому краю; у inline-SVG остаётся сдвиг по baseline.
- **Файлы:** `web/frontend/src/styles/globals.css`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.27 → **2.13.28** (PATCH).

### Web: лента «Задачи» = CLI + действия UI

- **Что:** `app.services.ui_audit.record_ui_action` — записи в `audit_events` с `correlation_id IS NULL` для пресетов, моделей (реестр), настроек. `GET /api/v1/activity` — объединение `jobs` и таких audit, сортировка по `created_at`. Страница «Задачи»: таблица с типом CLI/UI, деталь job как раньше, деталь UI — payload. Инвалидация `["activity"]` в мутациях. Smoke-тест `test_activity_includes_ui_after_preset_and_settings`. Контракт и README.
- **Почему:** в журнал не попадали операции без фоновой CLI-job.
- **Файлы:** `web/backend/app/services/ui_audit.py`, `app/schemas/activity.py`, `app/api/v1/activity.py`, `app/api/v1/models.py`, `app/api/v1/presets.py`, `app/api/v1/settings.py`, `app/api/v1/__init__.py`, `web/frontend/src/pages/Jobs.tsx`, `Presets.tsx`, `Models.tsx`, `Runtime.tsx`, `Monitoring.tsx`, `Settings.tsx`, `LiteLLM.tsx`, `api/types.ts`, `web/backend/tests/test_api_smoke.py`, `web/CONTRACT.md`, `web/README.md`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.28 → **2.13.29** (PATCH, новая точка API и UI).

### Web UI: кнопки «Действия» в ряд и центр иконок

- **Что:** `.table-actions` — `flex` + `row` + `nowrap`, `width: max-content`, ячейка последней колонки `table--registry` — `min-width: 12rem` (не схлопывать в столбик). Иконкные `.btn--icon` — `display: grid; place-items: center`, `font-size: 0`, фиксированные 20×20 у `svg`.
- **Почему:** перенос из‑за `flex-wrap` + узкой колонки; flex не выравнивал SVG стабильно.
- **Файлы:** `web/frontend/src/styles/globals.css`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.29 → **2.13.30** (PATCH).

### Web UI: строки реестра как карточки

- **Что:** для `.table--registry` — увеличен `border-spacing` по вертикали, у ячеек `tbody` — рамка, лёгкая тень, без дублирующейся вертикали между колонками; своя подсветка при hover; линия под заголовком.
- **Почему:** визуальное разделение строк (модели и пресеты).
- **Файлы:** `web/frontend/src/styles/globals.css`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.30 → **2.13.31** (PATCH).

### Web UI + API: модели — sync с диском и удалить в списке

- **Что:** `POST /api/v1/models/sync` (скан `MODELS_DIR`, refresh статусов, `ModelSyncResult`, audit `models.sync`). Страница «Модели»: кнопка **Синхронизировать с диском** в секции реестра, в каждой строке — **удалить** (только БД, веса на диске). Smoke-тест `test_models_sync_returns_counts`. Удаление из формы: сброс выбора только если удалили выбранную модель. README, `web/CONTRACT.md`.
- **Почему:** запрос пользователя.
- **Файлы:** `web/backend/app/api/v1/models.py`, `app/schemas/models.py`, `web/frontend/src/pages/Models.tsx`, `web/frontend/src/api/types.ts`, `web/backend/tests/test_api_smoke.py`, `web/README.md`, `web/CONTRACT.md`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.31 → **2.13.32** (PATCH).

### Web: job runner вызывает `slgpu` через `/bin/bash`

- **Что:** `app/services/jobs.py` — `_exec_argv_for_cli`: для argv с `{WEB_SLGPU_ROOT}/slgpu` подстановка на `/bin/bash` + путь к скрипту + остальные аргументы; INFO-лог при таком запуске. Тесты `test_exec_argv_*` в `tests/test_jobs_runner.py`. README §безопасность.
- **Почему:** `create_subprocess_exec` делает execve по argv[0]; на части bind mount (в т.ч. после копирования с Windows) у `slgpu` может не быть +x — тогда CLI из web не стартует или ведёт себя непредсказуемо; явный `bash /…/slgpu` соответствует ручному запуску и не использует интерактивный shell для разбора.
- **Файлы:** `web/backend/app/services/jobs.py`, `web/backend/tests/test_jobs_runner.py`, `web/README.md`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** **VERSION** 2.13.32 → **2.13.33** (PATCH).

## Фаза: web-native stack 3.0.0

### 3.0.0: стек в БД, native jobs, data/bench, UI install/benchmarks

- **Что:** `Settings.models_presets_dir` → `presets_dir_sync()` (БД + дефолты). Порты и compose-проекты для runtime, monitoring, litellm, `public_urls` → `ports_for_probes_sync()`. Бенч в `native_jobs` использует `LLM_API_PORT` из пресета. Перенос **`bench/report.md` → `data/bench/report.md`**; CLI **`cmd_bench.sh` / `cmd_load.sh`** пишут в **`data/bench/results/`**; **`_lib.sh`** создаёт `data/bench/results`; **`.gitignore`** — отслеживаем только `data/bench/report.md`. **`./slgpu web install`** → `POST /api/v1/app-config/install`. Frontend: **Настройки** (install + JSON стека/секретов), **Бенчмарки** (`/benchmarks`). Тесты `test_slgpu_cli` под `native.*`, `test_jobs_runner` для пустого argv. **`pyproject.toml`:** `huggingface_hub`. Документация: README, `data/README.md`, `web/CONTRACT.md`, `docs/AGENTS.md`, **GRACE** (`knowledge-graph`, `development-plan`, `verification-plan`).
- **Почему:** завершение плана — единый источник стека в web, бенч в `data/`, удобный импорт и UI.
- **Файлы:** `web/backend/app/core/config.py`, `app/services/monitoring.py`, `app_settings.py`, `litellm.py`, `runtime.py`, `native_jobs.py`, `api/v1/litellm.py`, `scripts/cmd_bench.sh`, `cmd_load.sh`, `cmd_web.sh`, `cmd_help.sh`, `_lib.sh`, `.gitignore`, `data/bench/report.md`, `web/frontend/src/pages/Settings.tsx`, `Benchmarks.tsx`, `App.tsx`, `Layout.tsx`, `web/backend/tests/test_slgpu_cli.py`, `test_jobs_runner.py`, `web/backend/pyproject.toml`, `README.md`, `data/README.md`, `web/CONTRACT.md`, `docs/AGENTS.md`, `docs/HISTORY.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `grace/verification/verification-plan.xml`, `VERSION`.
- **Решение:** **MAJOR 3.0.0** — смена путей бенч-артефактов и контракта web (native stack вместо argv к `./slgpu` для операций стека).

### 3.0.1: web install — проверка контейнера и fallback curl

- **Что:** `scripts/cmd_web.sh install` проверяет, что `slgpu-web` в состоянии Running; иначе понятное сообщение и exit 1 (сначала `web up`). При сбое curl с хоста — повтор через `docker exec slgpu-web curl http://127.0.0.1:8000/...`. Справка `web -h` и README: порядок up → install.
- **Почему:** пользователь вызывал `web install` без запущенного API → `curl: (7) Couldn't connect`.
- **Файлы:** `scripts/cmd_web.sh`, `README.md`, `VERSION`, `docs/HISTORY.md`, `grace/knowledge-graph/knowledge-graph.xml`.
- **Решение:** PATCH 3.0.1.

### 3.1.0: стек в БД — таблица stack_params вместо JSON-блобов

- **Что:** Модель **`StackParam`** (`stack_params`: уникальный `param_key`, `param_value`, `is_secret`). `init_db`: миграция содержимого `cfg.stack`/`cfg.secrets` из `settings` в строки, обнуление JSON; дефолты `DEFAULT_STACK` подмешиваются через `ensure_default_stack_params`. `sync_merged_flat` читает в первую очередь `stack_params`, иначе legacy JSON. API install/patch переведены на строки; `PATCH` для `stack` поддерживает **`null`** (удаление ключа). UI Настройки: таблица строк вместо двух JSON textarea. Smoke-тест `test_app_config_stack_returns_seeded_params`. Обновлены `web/CONTRACT.md`, `docs/AGENTS.md`, GRACE kg.
- **Почему:** запрос пользователя — хранить набор параметров отдельными ячейками/записями, а не одним текстом JSON.
- **Файлы:** `web/backend/app/models/stack_param.py`, `app/models/__init__.py`, `app/db/session.py`, `app/services/stack_config.py`, `app/api/v1/app_config.py`, `web/frontend/src/pages/Settings.tsx`, `web/backend/tests/test_api_smoke.py`, `web/CONTRACT.md`, `docs/AGENTS.md`, `docs/HISTORY.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`.
- **Решение:** MINOR 3.1.0 — новая схема хранения стека в web (обратная совместимость через миграцию при старте).

### 3.1.1: Настройки — смысловые группы на странице

- **Что:** Страница `/settings` разбита на три блока с заголовком и вводным текстом: **Внешний доступ и ссылки** (публичный host + карточки URL), **Стек в базе данных** (импорт из файлов + таблица параметров), **Обслуживание хоста** (fix-perms). Стили `.settings-group`, `.settings-group__heading`, `.settings-group__lead` в `globals.css`. Уточнены подзаголовки секций.
- **Почему:** запрос пользователя — сгруппировать настройки по смыслу.
- **Файлы:** `web/frontend/src/pages/Settings.tsx`, `web/frontend/src/styles/globals.css`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.1.1.

### 3.1.2: Настройки — без «Итоговых ссылок», параметры стека по подгруппам

- **Что:** Убран блок **Итоговые ссылки**; группа **Внешний доступ** — только публичный host. **Параметры окружения** разбиты на подтаблицы: пути, web UI, сеть API движка, мониторинг/compose, GPU/инференс, прочее, секреты (классификация по имени ключа и флагу «секрет»). Стили `.settings-stack-subgroup*`.
- **Почему:** запрос пользователя — убрать раздел ссылок и сгруппировать переменные стека по смыслу.
- **Файлы:** `web/frontend/src/pages/Settings.tsx`, `web/frontend/src/styles/globals.css`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.1.2.

### 3.1.3: LiteLLM — убрана кнопка monitoring up

- **Что:** На странице `/litellm` удалены кнопка и мутация `POST /monitoring/action` с действием `up`; в подзаголовке указано, что подъём мониторинга — со страницы «Мониторинг» или CLI.
- **Почему:** запрос пользователя — не дублировать отдельный запуск мониторинга на странице LiteLLM.
- **Файлы:** `web/frontend/src/pages/LiteLLM.tsx`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.1.3.

### 3.1.4: Задачи — детали в модальном окне

- **Что:** Компонент `Modal` (оверлей, Esc, клик по фону, блокировка прокрутки body). Страница `/jobs`: по клику на строку CLI/UI детали показываются в попапе, а не в секции внизу страницы.
- **Почему:** запрос пользователя.
- **Файлы:** `web/frontend/src/components/Modal.tsx`, `web/frontend/src/pages/Jobs.tsx`, `web/frontend/src/styles/globals.css`, `web/README.md`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.1.4.

### 3.2.0: Dashboard — блок «Сервер» (CPU, RAM, диск, ОС, NVIDIA/CUDA)

- **Что:** Сервис `app/services/host_info.py` (`collect_host_info`): `/etc/os-release`, `platform`, `/proc/cpuinfo`, `/proc/meminfo`, `shutil.disk_usage(slgpu_root)`, опционально `nvidia-smi` (драйвер, CUDA, список GPU). `GET /api/v1/dashboard` дополняется ключом `host` (сбор в `asyncio.to_thread`). UI: секция «Сервер» на Dashboard, `formatBytesIEC` в `formatters.ts`. В `docker-compose.web.yml` — закомментирован пример `deploy.resources` для GPU web. Документация: `web/CONTRACT.md`, `web/README.md`, GRACE kg.
- **Почему:** запрос пользователя — видеть на дашборде информацию о сервере.
- **Файлы:** `web/backend/app/services/host_info.py`, `app/api/v1/dashboard.py`, `web/backend/tests/test_api_smoke.py`, `web/frontend/src/pages/Dashboard.tsx`, `web/frontend/src/api/types.ts`, `web/frontend/src/components/formatters.ts`, `docker/docker-compose.web.yml`, `web/CONTRACT.md`, `web/README.md`, `VERSION`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/verification/verification-plan.xml`, `docs/AGENTS.md`, `docs/HISTORY.md`.
- **Решение:** MINOR 3.2.0 — расширение контракта дашборда.

### 3.3.0: Модели — прогресс pull в списке

- **Что:** Схема **`ModelPullProgress`** и поле **`pull_progress`** в **`HFModelOut`**. **`GET /api/v1/models`** и **`GET /api/v1/models/{id}`** подмешивают активную задачу **`native.model.pull`** (`active_pull_jobs_by_resource`). Во время **`snapshot_download`** — кастомный **`tqdm_class`** и фоновый flush **`Job.progress`** / **`message`** (~1.5 с). Зависимость **`tqdm`**. UI: полоса и подпись в колонке «Статус», опрос списка каждые 2 с при активном `pull_progress`, подзаголовок страницы обновлён.
- **Почему:** запрос пользователя — не уводить за прогрессом только на вкладку «Задачи».
- **Файлы:** `web/backend/app/schemas/models.py`, `app/api/v1/models.py`, `app/services/hf_models.py`, `app/services/native_jobs.py`, `web/backend/pyproject.toml`, `web/frontend/src/api/types.ts`, `web/frontend/src/pages/Models.tsx`, `web/frontend/src/styles/globals.css`, `web/CONTRACT.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** MINOR 3.3.0 — расширение API и UI без ломки CLI.

### 3.3.1: Пресеты — загрузка шаблонов из examples/presets

- **Что:** **`POST /api/v1/presets/import-templates`**: `copy_example_presets_to_disk` (`examples/presets` → PRESETS_DIR, без перезаписи) + **`import_files_into_db`**. Схема **`PresetImportTemplatesResult`**, audit **`presets.import_templates`**. UI: кнопка «Загрузить шаблоны» в шапке страницы пресетов, блок итогов. Smoke-тест `test_import_templates_from_examples_presets`.
- **Почему:** запрос пользователя — подгрузка эталонов из папки `examples`.
- **Файлы:** `web/backend/app/services/presets.py`, `app/schemas/presets.py`, `app/api/v1/presets.py`, `web/frontend/src/api/types.ts`, `web/frontend/src/pages/Presets.tsx`, `web/backend/tests/test_api_smoke.py`, `web/CONTRACT.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.3.1.

### 3.3.2: Бенчмарки — движок и пресет из runtime

- **Что:** Страница **Benchmarks** опрашивает **`GET /runtime/snapshot`**; при наличии **`engine`** и **`preset_name`** подставляет их в формы scenario и load (обновление при смене пары; сброс ключа при остановке движка). Подсказка под заголовком и уточнён текст ошибки валидации.
- **Почему:** запрос пользователя — бенч после уже загруженной модели, без ручного ввода slug.
- **Файлы:** `web/frontend/src/pages/Benchmarks.tsx`, `web/CONTRACT.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.3.2.

### 3.3.3: Дашборд «Сервер» — железо с хоста через Docker

- **Что:** `host_info.collect_host_info`: при `docker.ping()` — чтение **хостовых** `cpuinfo`/`meminfo`/`version` через эфемерный контейнер с bind `/proc`; `os-release`, `hostname` из `/etc`; NVIDIA — `containers.run` с `DeviceRequest(gpu)` и образом `WEB_NVIDIA_SMI_DOCKER_IMAGE` (дефолт CUDA base). Настройки `WEB_DOCKER_HOST_PROBE_IMAGE`, `WEB_NVIDIA_SMI_DOCKER_IMAGE`. Иначе прежний fallback. Комментарий в `docker-compose.web.yml`.
- **Почему:** запрос пользователя — на сервере есть GPU, а в slgpu-web нет `nvidia-smi`; нужны параметры **сервера**, не изолированного контейнера web.
- **Файлы:** `web/backend/app/services/host_info.py`, `web/backend/app/core/config.py`, `docker/docker-compose.web.yml`, `web/CONTRACT.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.3.3.

### 3.3.4: Бенчмарки — отчёт summary в модалке

- **Что:** Клик по строке прогона открывает **`Modal` wide** с **`BenchSummaryView`**: для **load** — карточки RPS/tok/s/ошибки, сетка TTFT/latency, нагрузка, запросы; для **scenario** — таблица сценариев; иначе fallback JSON. У **`Modal`** опция **`size="wide"`**. Стили `.bench-summary__*`. Убрана нижняя секция с сырым JSON.
- **Почему:** запрос пользователя — наглядное отображение результатов.
- **Файлы:** `web/frontend/src/components/BenchSummaryView.tsx`, `web/frontend/src/components/Modal.tsx`, `web/frontend/src/pages/Benchmarks.tsx`, `web/frontend/src/styles/globals.css`, `grace/knowledge-graph/knowledge-graph.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.3.4.

### 3.3.5: Web — логи без дублей `INFO` (httpx/uvicorn)

- **Что:** `configure_logging`: единственный `StreamHandler` на **root**; у `app`, `httpx`, `httpcore`, `h11`, `uvicorn*`, `fastapi`, `starlette` — `handlers.clear()` и `propagate=True` (раньше тот же handler дублировался на именованных логгерах). Повторный вызов в `startup` после добавления handler'ов uvicorn. Обновлены `web/CONTRACT.md`, аннотация `fn-core_logging` в GRACE.
- **Почему:** в Docker/Loki строки вида `INFO INFO … ts=… logger=httpx` от многократной обработки одной записи; контекст — шум в логах при просмотре httpx (в т.ч. 401 к LiteLLM).
- **Файлы:** `web/backend/app/core/logging.py`, `web/backend/app/main.py` (повторный вызов в startup), `web/CONTRACT.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.3.5.

### 3.3.6: Бенчмарки — убраны статический report.md и секция в UI

- **Что:** Удалён `data/bench/report.md`, эндпоинт `GET /api/v1/bench/report.md`, блок на странице Benchmarks; каталог `data/bench/` сохранён через `.gitignore` + `.gitkeep`. Документация README, `data/README.md`, `web/CONTRACT.md`, GRACE (`fn-api_bench`, `export-bench-ui`).
- **Почему:** запрос пользователя — длинный статический разбор в репозитории и превью в UI не нужны; достаточно модалки по `summary.json`.
- **Файлы:** `web/frontend/src/pages/Benchmarks.tsx`, `web/backend/app/api/v1/bench.py`, `.gitignore`, `data/bench/.gitkeep`, удалён `data/bench/report.md`, `README.md`, `data/README.md`, `web/CONTRACT.md`, `docs/AGENTS.md`, `grace/knowledge-graph/knowledge-graph.xml`, `grace/plan/development-plan.xml`, `VERSION`, `docs/HISTORY.md`.
- **Решение:** PATCH 3.3.6.
