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
| 1.8.0 | Пресет [**`configs/models/qwen3.6-27b.env`**](configs/models/qwen3.6-27b.env) (throughput: **`SLGPU_MAX_NUM_BATCHED_TOKENS=16384`**, **`GPU_MEM_UTIL=0.9262`**, опционально **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE`**); переменная **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE`** в [`docker-compose.yml`](docker-compose.yml) и условный **`--disable-custom-all-reduce`** в `serve.sh` (см. [`scripts/serve.sh`](scripts/serve.sh)). |
| 1.8.1 | Дефолт **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=0`** (custom all-reduce без флага); `1` — **NCCL**; документация и [`qwen3.6-27b.env`](configs/models/qwen3.6-27b.env) без дублирования `0`. |
| 1.8.2 | Снова дефолт **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=1`** (NCCL): на vLLM 0.19 + Qwen3.6 custom all-reduce даёт **`custom_all_reduce.cuh` / `invalid argument`** при graph capture; troubleshooting в README. |
| 1.9.0 | Пресет [`configs/models/glm-5.1.env`](configs/models/glm-5.1.env), эвристика **pull**: **zai-org/GLM*** → `MAX_MODEL_LEN=202752`, `KV_CACHE_DTYPE=auto` (разреженная MLA+DSA несовместима с fp8 KV в vLLM 0.19); README и troubleshooting. |
| 1.9.1 | **GLM-5.1:** в пресете `MAX_MODEL_LEN=131072`, `GPU_MEM_UTIL=0.88` (OOM `SharedFusedMoE` на 8×~140 GB); README / `configs/models/README.md` / troubleshooting. |
| 1.9.2 | **GLM-5.1:** пресет **65536** / **0.82** / **4096** batched, **`SLGPU_ENABLE_PREFIX_CACHING=0`**; в **`serve.sh`** опциональное отключение prefix cache; vllm.env, README, troubleshooting. |
| 1.9.3 | **`serve.sh`:** при `SLGPU_ENABLE_PREFIX_CACHING=0` — **`--no-enable-prefix-caching`** (vLLM 0.19 по умолчанию включает кэш; раньше флаг не отключался). README troubleshooting. |
| 1.9.4 | **GLM-5.1:** в пресете **`GPU_MEM_UTIL=0.75`** (OOM `SharedFusedMoE` при 0.82: vLLM просит снизить util, чтобы освободить память под веса). |
| 1.9.5 | **`docker-compose.yml` (vLLM):** **`SLGPU_ENABLE_PREFIX_CACHING`** в `environment` — иначе из пресета в контейнер не попадала; `serve.sh` видел дефолт `1` → в логах оставалось `enable_prefix_caching: True`. |
| 1.10.0 | **GLM-5.1-FP8:** пресет [`configs/models/glm-5.1-fp8.env`](configs/models/glm-5.1-fp8.env); `serve.sh` — **`CHAT_TEMPLATE_CONTENT_FORMAT`** → `--chat-template-content-format`; compose — **`VLLM_DOCKER_IMAGE`**, **`CHAT_TEMPLATE_CONTENT_FORMAT`**; `_lib.sh` — HF id с **FP8** → tool **`glm47`**; README, `.env.example`. |
| 1.11.0 | **MiniMax-M2.7:** пресет [`configs/models/minimax-m2.7.env`](configs/models/minimax-m2.7.env) ([рецепт](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md) — **TP4**, **TP4+EP** на 8×GPU, **`--compilation-config`**); `serve.sh` / compose — **`SLGPU_VLLM_COMPILATION_CONFIG`**, **`SLGPU_ENABLE_EXPERT_PARALLEL`**, **`SLGPU_VLLM_DATA_PARALLEL_SIZE`**; **`slgpu_guess_max_model_len`** — **200704** для `MiniMaxAI/MiniMax*`. |
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
| 2.0.12 | **Один `serve.sh` (тогда `configs/`, сейчас [`scripts/serve.sh`](scripts/serve.sh)):** `SLGPU_ENGINE=vllm|sglang`; удалены `configs/vllm/serve.sh`, `configs/sglang/serve.sh`; compose, README, GRACE. |
| 2.0.13 | **Параметры из `vllm.env` / `sglang.env` в [`main.env`](main.env);** удалены файлы движка; compose — только `env_file: main.env`; [`scripts/_lib.sh`](scripts/_lib.sh) без `configs/<engine>.env`. |
| 2.0.14 | **[`scripts/serve.sh`](scripts/serve.sh)** (был `configs/serve.sh`); compose монтирует `./scripts/serve.sh` → `/etc/slgpu/serve.sh`. |
| 2.0.15 | Удалён `scripts/compare.py` (A/B-сводка `bench/report.md`); README, `cmd_help`, GRACE. |
| 2.0.16 | **`serve` / `main`:** `SLGPU_VLLM_TRUST_REMOTE_CODE`, `SLGPU_VLLM_ENABLE_CHUNKED_PREFILL`, `SLGPU_VLLM_ENABLE_AUTO_TOOL_CHOICE` в `main.env`; SGLang — `MODEL_PATH` через **`SLGPU_MODEL_ROOT`**; `docker-compose` pass **`SLGPU_MODEL_ROOT`**, vLLM-флаги, **`SGLANG_TRUST_REMOTE_CODE`**. |
| 2.1.0 | **Мониторинг отдельно от движка:** [`docker-compose.monitoring.yml`](docker-compose.monitoring.yml), сеть `slgpu` + **`./slgpu monitoring up|down|restart`**; **`./slgpu up`** — только vLLM/SGLang; **`./slgpu down --all`**, `_lib.sh`, README, [monitoring/README](monitoring/README.md), GRACE. |
| 2.1.1 | **Prometheus/Grafana:** bind mount в **`PROMETHEUS_DATA_DIR`**, **`GRAFANA_DATA_DIR`** (по умолч. `/var/lib/slgpu/…`); миграция с named volume в [monitoring/README](monitoring/README.md). |
| 2.1.2 | **Grafana bind mount:** `user: 472:0` в [`docker-compose.monitoring.yml`](docker-compose.monitoring.yml), на хосте **`chown -R 472:0`**; правка [monitoring/README](monitoring/README.md) (ошибка 472:472), main.env. |
| 2.1.3 | **Prometheus:** `user: 65534:65534`, **`chown -R 65534:65534`** на `PROMETHEUS_DATA_DIR` (fix `queries.active` / mmap panic); [monitoring/README](monitoring/README.md), main.env. |
| 2.1.4 | **`./slgpu monitoring fix-perms`**, [`scripts/monitoring_fix_permissions.sh`](scripts/monitoring_fix_permissions.sh) (uid:gid из образов); в compose **убраны** жёсткие `user:` у Prom/Grafana; [monitoring/README](monitoring/README.md), README, main.env. |
| 2.1.5 | Дефолт **`PROMETHEUS_DATA_DIR` / `GRAFANA_DATA_DIR`**: `/opt/mon/prometheus`, `/opt/mon/grafana` (ранее `/var/lib/slgpu/…`). |
| 2.1.6 | SGLang Grafana: **Model** — `includeAll` + `allValue: ".*"` в `sglangdash2-slgpu` / `sglang-dashboard-slgpu` (без пустого `model_name`); [monitoring/README](monitoring/README.md). |
| 2.1.7 | **Документация:** полный обзор `git log` (приложение ниже), эпоха 20.04–22.04.2026 между «ранними» коммитами и нумерованными релизами, раздел **«Диалоги и инциденты запуска»** (транскрипты сессий Cursor + соответствие правкам в репо). |
| 2.1.8 | **Аналитика в `HISTORY.md`:** крупный раздел **«что делали → что произошло → что поменяли»** — vLLM `SLGPU_*`, KV Qwen, custom AR Qwen3.6, tool parsers, gpt-oss, Kimi, пошагово GLM-5.1 (262k→202k, fp8 KV, MoE OOM, prefix cache, compose), MiniMax, порты SGLang/compose, мониторинг (uid, mmap, Grafana variables), CLI 2.0, бенч; **шпаргалка** по файлам. |

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
| `docker-compose.yml` | **`gpus: all`**, маска GPU через **`NVIDIA_VISIBLE_DEVICES`** (по умолчанию `0,…,TP-1` из [`./slgpu up`](scripts/cmd_up.sh)); блок **`environment`** для vLLM/SGLang; **json-file** логи 100m×5. |
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
- **Поменяли:** в [`scripts/serve.sh`](scripts/serve.sh) и [`docker-compose.yml`](docker-compose.yml) — служебные вещи переименованы в **`SLGPU_VLLM_HOST`**, **`SLGPU_VLLM_PORT`**, **`SLGPU_MAX_NUM_BATCHED_TOKENS`**; в compose оставлен **fallback** `VLLM_MAX_NUM_BATCHED_TOKENS` для старых пресетов. Коммит `36d56f7` (см. таблицу «Рефакторинг CLI»).

### Qwen3 Next: тип KV — не «любой fp8»

- **Делали:** для экономии VRAM тянули **KV fp8**; пробовали варианты, близкие к `fp8_e5m2`.
- **Произошло:** **assert** / поломка attention / Dynamo (зависит от сборки) при **`KV_CACHE_DTYPE=fp8_e5m2`**; для Qwen3 Next в карточке и vLLM стабильнее **`fp8_e4m3`**.
- **Поменяли:** дефолт в цепочке env → **`KV_CACHE_DTYPE=fp8_e4m3`** (`235e4c3`); комментарии в `main.env` / пресетах, troubleshooting в README. Бенч: [`scripts/bench_openai.py`](scripts/bench_openai.py) уважает **`MAX_MODEL_LEN`** и ужимает **`max_tokens`** (`e22cb3e`), чтобы не ловить переполнение окна.

### Qwen3.6-27B: custom all-reduce и graph capture

- **Делали:** `TP=8`, custom all-reduce vLLM **включён** (`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=0`) — ожидание низкой латентности all-reduce.
- **Произошло:** при **CUDA graph capture** / инициализации движка — падения из **`vllm/model_executor/layers/custom_all_reduce.cuh`** с сообщениями в духе **`invalid argument`**, `WorkerProc` / `EngineCore` не дожидается готовности воркеров.
- **Поменяли:** флаг в [`scripts/serve.sh`](scripts/serve.sh): при **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE=1`** добавляется **`--disable-custom-all-reduce`** (обход через **NCCL**). Итерация версий: **1.8.0** (пресет + переменная в compose) → **1.8.1** дефолт `0` → **1.8.2** снова дефолт **`1`** как практичный default для 0.19 + Qwen3.6. Пресет: [`configs/models/qwen3.6-27b.env`](configs/models/qwen3.6-27b.env).

### Qwen3.6-27B: tool calling и несовместимость `hermes` parser

- **Делали:** `TOOL_CALL_PARSER=hermes` (как у классического Qwen2.5 / JSON tool schema).
- **Произошло:** модель (ветка Qwen3.6 / Coder) эмитит **XML-инструменты**; `hermes_tool_parser` ждёт JSON → **`JSONDecodeError`**, бесконечный стрим для клиента, **таймаут** на tool round-trip.
- **Поменяли:** **`TOOL_CALL_PARSER=qwen3_xml`** (альтернатива в комментариях: `qwen3_coder`). Версия **1.8.3**, тот же пресет + [`configs/models/README.md`](configs/models/README.md).

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
   - *Поменяли:* для **`zai-org/GLM*`** в логике **pull** / доках — **202752**; пресет [`configs/models/glm-5.1.env`](configs/models/glm-5.1.env) (см. `MAX_MODEL_LEN`).

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
   - *Поменяли:* пресет [`configs/models/glm-5.1-fp8.env`](configs/models/glm-5.1-fp8.env), **`VLLM_DOCKER_IMAGE`**, **`CHAT_TEMPLATE_CONTENT_FORMAT=string`**, `TOOL`/`REASON` **`glm47`** / **`glm45`**, `serve` — флаг **`--chat-template-content-format`**. **Версия 1.10.0** (`d8bfc79`).

### MiniMax-M2.7: рецепт vLLM ≠ «голый TP8»

- **Делали:** `TP=8` на 8 GPU «по привычке».
- **Произошло:** [рецепт vLLM](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md) требует на 8×GPU **TP4 + expert parallel (EP)** и **`--compilation-config`**; маска **`NVIDIA_VISIBLE_DEVICES`** на **все** карты при EP; **200704** max len по карточке/рецепту.
- **Поменяли:** [`configs/models/minimax-m2.7.env`](configs/models/minimax-m2.7.env), переменные **`SLGPU_VLLM_COMPILATION_CONFIG`**, **`SLGPU_ENABLE_EXPERT_PARALLEL`**, **`SLGPU_VLLM_DATA_PARALLEL_SIZE`**, pass в [`docker-compose.yml`](docker-compose.yml) и [`scripts/serve.sh`](scripts/serve.sh). **1.11.0** (`937422a`).

### Сеть и порты: внешний `LLM_API_PORT` vs внутри контейнера

- **Делали:** `./slgpu up sglang -m kimi-k2.6 -p 8222` — ожидание, что **и** healthcheck, **и** `curl` **внутри** контейнера ходят на **8222**.
- **Произошло:** в compose проброс **`${LLM_API_PORT:-8222}:8222`**: **хост 8222 → контейнер 8222** (SGLang). Внутри **`SGLANG_LISTEN_PORT`** (часто **8222** в `main.env` для sglang-профиля) должен **совпадать** с целевым портом образа. Путаница: **`curl` к `127.0.0.1:8111` внутри sglang-контейнера** при том, что слушатель на **8222** → *connection refused*; снаружи **Connection reset** при обращении, пока идут **Triton autotune** / **graph capture** (десятки минут) — **нормальная** фаза, не «сломанный» compose.
- **Поменяли:** **1.3.0** — `-p` / `LLM_API_PORT`; **1.4.3** — SGLang, метрики, Prometheus targets на **8222**; troubleshooting в [monitoring/README.md](monitoring/README.md) (**instance:8222** для SGLang vs **8111** для vLLM в scrape).

### Мониторинг: права, mmap Prometheus, дашборды

- **Делали:** bind mount **`-v /path/grafana:/var/lib/grafana`**, **`-v /path/prometheus`**, запуск **от root** / случайные `chown`.
- **Произошло:** Grafana: **`GF_PATHS_DATA is not writable`**, плагины/БД; Prometheus **3.x**: **mmap** на TSDB, ошибки **`queries.active`**, **panic** при **root**-владельце файлов, созданных вне контейнера.
- **Поменяли:** **2.1.0** — отдельный [`docker-compose.monitoring.yml`](docker-compose.monitoring.yml), сеть **`slgpu`**; **2.1.1** — bind; **2.1.2** — Grafana `user: 472:0`, **`chown -R 472:0`**, не 472:472; **2.1.3** — Prometheus `65534:65534` и **рекурсивный** chown; **2.1.4** — **`./slgpu monitoring fix-perms`**, снятие жёсткого `user:` из compose (uid из **реального** образа); **2.1.5** — дефолт **`/opt/mon/prometheus`**, **`/opt/mon/grafana`**.

- **Grafana: «No data» на панелях SGLang**
  - *Произошло:* variable **`model_name`** в JSON без корректного **«All»** / **`.*`**, или пустой label при отсутствии трафика.
  - *Поменяли:* **2.1.6** — в `sglangdash2-slgpu` / `sglang-dashboard-slgpu`: **`includeAll: true`**, **`allValue: ".*"`** (аналогия с уже исправленным **vllmdash2** в **1.5.4**).

- **vLLM дашборд пустой при работе только SGLang**
  - *Механизм:* **PromQL** `vllm:*` + `job="vllm"` — **нет** рядов, если не запущен scrape target **vllm** / нет запросов — не баг дашборда, а **отсутствие процесса vllm** или **модель не создаёт** label `model_name` до первого вызова.

### CLI 2.0: один `serve.sh`, `main.env`, отказ от лишнего

- **Делали:** много расслоений: `configs/vllm/vllm.env`, `sglang/sglang.env`, корневой **`.env`**, автогенерация пресетов в `pull`, команды `status`/`compare`/…
- **Поменяли:** единый [`scripts/serve.sh`](scripts/serve.sh) с **`SLGPU_ENGINE`**, всё движковое в [**`main.env`**](main.env) + **пресет**; **2.0.11** — без **обязательного** `.env` в корне; **1.11.1** — `pull` **без** автосоздания `configs/models/*.env`; **2.0.0** — урезан CLI. **`SLGPU_MODEL_ROOT`**: SGLang читает веса из примонтированного корня, совпадающего с vLLM.

### Бенчмарк: сеть, `no_content`, коды ошибок

- **Делали:** в SSE принимать только **truthy** `content` для учёта токенов.
- **Произошло:** vLLM отдаёт чанк с **`content: ""`** (служебный кадр) при наличии **`reasoning_content`** → сценарий бенчмарка помечал ответ как **`no_content`**, хотя HTTP 200.
- **Поменяли:** **1.2.1** — учёт пустой строки как «стрим начался»; **1.2.0** — `error_code` / `errors_breakdown` вместо «немых» **NaN** в сводке. **1.1.5+** — сверка **engine** (из compose) с флагом **`--engine`** / модель с `/v1/models`.

### Шпаргалка: ключевые файлы, где «живут» настройки

| Назначение | Файлы (типично) |
|------------|-----------------|
| Дефолты хоста / оба движка | [`main.env`](main.env) |
| Параметры конкретной модели | [`configs/models/<preset>.env`](configs/models/) |
| Сборка аргументов vLLM / SGLang | [`scripts/serve.sh`](scripts/serve.sh) |
| Проброс в контейнер | [`docker-compose.yml`](docker-compose.yml) |
| Сеть LLM + scrape | [monitoring/prometheus.yml](monitoring/prometheus.yml), [monitoring/README.md](monitoring/README.md) |
| Дашборды | [monitoring/grafana/provisioning/dashboards/json/](monitoring/grafana/provisioning/dashboards/json/) |

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

Сводка по **транскриптам** в `agent-transcripts` и по итерациям, отражённым в коммитах 1.8.x–2.1.x. Настройки — из пресетов [`configs/models/`](configs/models/); движок **vLLM 0.19.x**, стенд **8× H200** / **TP=8**, если не оговорено иное.

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
- **SGLang + внешний порт / Kimi (диалоги 22.04):** путаница **хост `8222` → контейнер** vs внутренний **`SGLANG_LISTEN_PORT` / `LLM_API_PORT` (часто 8111)**: `curl` на хост должен бить в проброшенный порт, внутри контейнера — в порт, на котором реально слушает процесс. Таймаут `up` / «ожидание `/v1/models`» и **`Connection reset` при 8222** — типично, пока идут **Triton autotune** и долгий **CUDA graph capture** (десятки минут); не ошибка конфига, а фаза прогрева. Отдельно встречались **падения scheduler при graph capture** на Kimi в SGLang — вне репо решались снижением/отключением graph, правками mem; см. релизы **1.4.x** (флаги graph, custom AR) и [monitoring/README](monitoring/README.md) (instance **8222** для метрик SGLang vs **8111** API vLLM).

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

После значимых изменений добавляйте строку в таблицу хронологии и при необходимости абзац в раздел «Зачем проект» или «Вне git».

Формат коммита для истории:

```text
краткая тема: что сделано и зачем (1 строка)
```
