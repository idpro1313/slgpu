"""Canonical stack key metadata and per-scope required keys (no default values in code)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from app.services.stack_errors import MissingStackParams

StackScope = Literal[
    "llm_slot",
    "monitoring_up",
    "proxy_up",
    "pull",
    "bench",
    "probes",
    "port_allocation",
    "fix_perms",
    "web_up",
]

_SECRET_EXACT = frozenset(
    {
        "HF_TOKEN",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_SALT",
        "LANGFUSE_ENCRYPTION_KEY",
        "NEXTAUTH_SECRET",
        "LANGFUSE_POSTGRES_PASSWORD",
        "LANGFUSE_REDIS_AUTH",
        "LANGFUSE_CLICKHOUSE_PASSWORD",
        "MINIO_ROOT_PASSWORD",
        "UI_PASSWORD",
        "GRAFANA_ADMIN_PASSWORD",
    }
)
_SECRET_SUFFIXES = (
    "_PASSWORD",
    "_SECRET",
    "_KEY",
    "_SALT",
    "_TOKEN",
    "SECRET_KEY",
    "ENCRYPTION_KEY",
    "NEXTAUTH_SECRET",
    "LANGFUSE_REDIS_AUTH",
)


def is_secret_key(name: str) -> bool:
    if name in _SECRET_EXACT:
        return True
    return any(name.endswith(s) for s in _SECRET_SUFFIXES)


# Scopes used in compose / native jobs («monitorинг» стек без fix_perms; scope fix_perms вешаем точечно — см. _native_fix_perms).
S_MON: tuple[str, ...] = ("monitoring_up", "proxy_up")
S_LLM: tuple[str, ...] = ("llm_slot", "bench")
S_ALL_COMPOSE: tuple[str, ...] = ("monitoring_up", "proxy_up")


def _scopes(*names: str) -> frozenset[StackScope]:
    return frozenset(names)  # type: ignore[arg-type]


@dataclass(frozen=True)
class KeyMeta:
    key: str
    group: str
    description: str
    allow_empty: bool
    is_secret: bool
    required_for: frozenset[StackScope]
    # Не показывать отдельной строкой в «Настройки» — значение подставляется из LLM_API_* см. env_key_aliases
    ui_hidden: bool = False
    # Подгруппа внутри monitoring / proxy (.slug для UI-сортировки и подписи)
    subgroup: str | None = None


def _e(
    key: str,
    group: str,
    description: str,
    *req: str,
    allow_empty: bool = False,
    ui_hidden: bool = False,
    subgroup: str | None = None,
) -> KeyMeta:
    return KeyMeta(
        key=key,
        group=group,
        description=description,
        allow_empty=allow_empty,
        is_secret=is_secret_key(key),
        required_for=_scopes(*req) if req else frozenset(),
        ui_hidden=ui_hidden,
        subgroup=subgroup,
    )


# --- Registry: every install-time key from main.env; required_for per scope. ---
# Порядок и группы (meta.group) **строго** соответствуют разделам `configs/main.env`:
#   1. network    — Docker-сеть и compose-проекты
#   2. web        — slgpu-web (образ, контейнер, порт/bind, логирование, host-проб)
#   3. paths      — пути на хосте (bind mount)
#   4. images     — Docker-образы для LLM/мониторинга/прокси
#   5. inference  — LLM API, движок, vLLM, SGLang, кеши
#   6. monitoring — Prometheus/Grafana/Loki/Promtail/DCGM/NodeExporter (имена/порты/binds/retention/auth)
#   7. proxy      — Langfuse + LiteLLM + Postgres + Redis + ClickHouse + MinIO (имена/порты/binds/cred/secrets)
#   8. secrets    — отдельные секреты приложения (HF_TOKEN)
# Порядок dict сохраняется и используется UI «Настройки» как источник сортировки строк
# в группе (см. registry_to_public()). Для group in (monitoring, proxy) поле ``subgroup`` —
# подзаголовок по сервису (Prometheus, Langfuse, …); UI сортирует строки по subgroup.
_STACK_KEY_REGISTRY: dict[str, KeyMeta] = {
    # ----- 1. Сеть Docker и compose-проекты -----
    "SLGPU_NETWORK_NAME": _e(
        "SLGPU_NETWORK_NAME",
        "network",
        "Имя внешней Docker-сети slgpu (общая для web + monitoring + proxy + LLM-слотов).",
        "web_up", *S_LLM, *S_ALL_COMPOSE,
    ),
    "WEB_COMPOSE_PROJECT_INFER": _e(
        "WEB_COMPOSE_PROJECT_INFER",
        "network",
        "Имя docker compose-проекта для слотов инференса (vLLM/SGLang); то же имя в снимке портов для проб и runtime.",
        *S_LLM,
        *S_ALL_COMPOSE,
        "probes",
    ),
    "WEB_COMPOSE_PROJECT_MONITORING": _e("WEB_COMPOSE_PROJECT_MONITORING", "network", "Имя compose-проекта стека мониторинга (Prometheus/Grafana/Loki/Promtail/DCGM/NodeExporter).", *S_ALL_COMPOSE, "probes"),
    "WEB_COMPOSE_PROJECT_PROXY": _e("WEB_COMPOSE_PROJECT_PROXY", "network", "Имя compose-проекта стека прокси (Langfuse + LiteLLM + хранилища).", *S_ALL_COMPOSE, "probes"),

    # ----- 2. Web UI (slgpu-web) -----
    "WEB_DOCKER_IMAGE": _e("WEB_DOCKER_IMAGE", "web", "Тег Docker-образа slgpu-web (сборка `./slgpu web build`).", "web_up"),
    "WEB_CONTAINER_NAME": _e("WEB_CONTAINER_NAME", "web", "Имя контейнера slgpu-web (по нему backend ищет себя для health/restart hooks).", "web_up"),
    "WEB_INTERNAL_PORT": _e("WEB_INTERNAL_PORT", "web", "Внутренний порт slgpu-web в контейнере (uvicorn). Правая часть mapping ${WEB_BIND}:${WEB_PORT}:${WEB_INTERNAL_PORT}.", "web_up"),
    "WEB_BIND": _e("WEB_BIND", "web", "Bind-адрес опубликованного порта slgpu-web на хосте (0.0.0.0 / 127.0.0.1 / IP).", *S_ALL_COMPOSE),
    "WEB_PORT": _e("WEB_PORT", "web", "Опубликованный порт slgpu-web на хосте (ссылка на UI).", *S_ALL_COMPOSE),
    "WEB_LOG_LEVEL": _e("WEB_LOG_LEVEL", "web", "Уровень логов uvicorn (DEBUG/INFO/WARNING/ERROR/CRITICAL).", *S_ALL_COMPOSE),
    "WEB_LOG_FILE_ENABLED": _e(
        "WEB_LOG_FILE_ENABLED",
        "web",
        "true/false: включить запись логов в файл ${WEB_DATA_DIR}/.slgpu/app.log (UI «Логи» работает и без файла).",
        *S_ALL_COMPOSE,
        allow_empty=True,
    ),
    "WEB_PUBLIC_HOST": _e(
        "WEB_PUBLIC_HOST",
        "web",
        "Запасной hostname для публичных ссылок UI (если в HTTP-запросе нет host). Пусто — определять по запросу.",
        "probes",
        allow_empty=True,
    ),
    "WEB_MONITORING_HTTP_HOST": _e(
        "WEB_MONITORING_HTTP_HOST",
        "web",
        "Hostname для health-проб мониторинга **из контейнера** slgpu-web (host.docker.internal на Linux compose).",
        *S_ALL_COMPOSE, "probes",
        allow_empty=True,
    ),
    "WEB_LLM_HTTP_HOST": _e(
        "WEB_LLM_HTTP_HOST",
        "web",
        "Hostname для health-проб LLM (vllm/sglang) **из контейнера** slgpu-web.",
        *S_ALL_COMPOSE, "probes",
        allow_empty=True,
    ),

    # ----- 3. Пути на хосте (bind mount) -----
    "SLGPU_HOST_REPO": _e("SLGPU_HOST_REPO", "paths", "Абсолютный путь к репозиторию slgpu на хосте (bind для slgpu-web и подкоманд compose).", *S_LLM, *S_ALL_COMPOSE),
    "MODELS_DIR": _e("MODELS_DIR", "paths", "Каталог хранилища весов моделей (bind в slgpu-web и в LLM-слот → /models; pull пишет сюда).", *S_LLM, *S_ALL_COMPOSE, "pull"),
    "PRESETS_DIR": _e("PRESETS_DIR", "paths", "Каталог пресетов *.env (рабочие копии на диске; источник правды — БД `presets`).", *S_LLM, *S_ALL_COMPOSE),
    "WEB_DATA_DIR": _e("WEB_DATA_DIR", "paths", "Каталог данных Web UI (SQLite, секреты, снимки compose-service.env).", *S_LLM, *S_ALL_COMPOSE),
    "SLGPU_MODEL_ROOT": _e("SLGPU_MODEL_ROOT", "paths", "Путь к корню весов **внутри** контейнера слота инференса (обычно /models).", *S_LLM, *S_ALL_COMPOSE),
    "PROMETHEUS_DATA_DIR": _e("PROMETHEUS_DATA_DIR", "paths", "Каталог TSDB Prometheus на хосте.", *S_MON, "fix_perms"),
    "GRAFANA_DATA_DIR": _e("GRAFANA_DATA_DIR", "paths", "Каталог данных Grafana на хосте.", *S_MON, "fix_perms"),
    "LOKI_DATA_DIR": _e("LOKI_DATA_DIR", "paths", "Каталог данных Loki на хосте.", *S_MON, "fix_perms"),
    "PROMTAIL_DATA_DIR": _e("PROMTAIL_DATA_DIR", "paths", "Каталог positions Promtail на хосте.", *S_MON, "fix_perms"),
    "LANGFUSE_POSTGRES_DATA_DIR": _e("LANGFUSE_POSTGRES_DATA_DIR", "paths", "Каталог Postgres (Langfuse/LiteLLM) на хосте.", *S_MON, "fix_perms"),
    "LANGFUSE_CLICKHOUSE_DATA_DIR": _e("LANGFUSE_CLICKHOUSE_DATA_DIR", "paths", "Каталог данных ClickHouse на хосте.", *S_MON, "fix_perms"),
    "LANGFUSE_CLICKHOUSE_LOGS_DIR": _e("LANGFUSE_CLICKHOUSE_LOGS_DIR", "paths", "Каталог логов ClickHouse на хосте.", *S_MON, "fix_perms"),
    "LANGFUSE_MINIO_DATA_DIR": _e("LANGFUSE_MINIO_DATA_DIR", "paths", "Каталог MinIO на хосте.", *S_MON, "fix_perms"),
    "LANGFUSE_REDIS_DATA_DIR": _e("LANGFUSE_REDIS_DATA_DIR", "paths", "Каталог Redis (Langfuse) на хосте.", *S_MON, "fix_perms"),

    # ----- 4. Образы Docker (LLM + monitoring + proxy) -----
    "SLGPU_BENCH_CHOWN_IMAGE": _e(
        "SLGPU_BENCH_CHOWN_IMAGE",
        "images",
        "Образ для эфемерного chown в `monitoring fix-perms` и bench-job (alpine:3.21 / любой образ с chown).",
        "fix_perms",
    ),
    "VLLM_DOCKER_IMAGE": _e("VLLM_DOCKER_IMAGE", "images", "Образ vLLM (OpenAI-совместимый сервер); пресет может перекрыть.", *S_LLM, *S_ALL_COMPOSE),
    "SGLANG_DOCKER_IMAGE": _e("SGLANG_DOCKER_IMAGE", "images", "Образ SGLang.", *S_LLM, *S_ALL_COMPOSE),
    "DCGM_EXPORTER_IMAGE": _e("DCGM_EXPORTER_IMAGE", "images", "Образ DCGM exporter (метрики GPU).", *S_MON),
    "NODE_EXPORTER_IMAGE": _e("NODE_EXPORTER_IMAGE", "images", "Образ node-exporter.", *S_MON),
    "LOKI_IMAGE": _e("LOKI_IMAGE", "images", "Образ Loki.", *S_MON, "fix_perms"),
    "PROMTAIL_IMAGE": _e("PROMTAIL_IMAGE", "images", "Образ Promtail.", *S_MON),
    "PROMETHEUS_IMAGE": _e("PROMETHEUS_IMAGE", "images", "Образ Prometheus.", *S_MON, "fix_perms"),
    "GRAFANA_IMAGE": _e("GRAFANA_IMAGE", "images", "Образ Grafana.", *S_MON, "fix_perms"),
    "LANGFUSE_IMAGE": _e("LANGFUSE_IMAGE", "images", "Образ Langfuse web.", *S_MON),
    "LANGFUSE_WORKER_IMAGE": _e("LANGFUSE_WORKER_IMAGE", "images", "Образ Langfuse worker.", *S_MON),
    "LANGFUSE_POSTGRES_IMAGE": _e("LANGFUSE_POSTGRES_IMAGE", "images", "Образ Postgres (Langfuse + LiteLLM).", *S_MON, "fix_perms"),
    "LANGFUSE_REDIS_IMAGE": _e("LANGFUSE_REDIS_IMAGE", "images", "Образ Redis (Langfuse).", *S_MON, "fix_perms"),
    "LANGFUSE_CLICKHOUSE_IMAGE": _e("LANGFUSE_CLICKHOUSE_IMAGE", "images", "Образ ClickHouse (Langfuse).", *S_MON),
    "MINIO_IMAGE": _e("MINIO_IMAGE", "images", "Образ MinIO.", *S_MON, "fix_perms"),
    "MINIO_MC_IMAGE": _e("MINIO_MC_IMAGE", "images", "Образ MinIO mc (bucket-init).", *S_MON),
    "LITELLM_IMAGE": _e("LITELLM_IMAGE", "images", "Образ LiteLLM.", *S_MON),

    # ----- 5. Инференс — LLM API, движок, vLLM, SGLang, кеши -----
    # 8.0.0: SLGPU_ENGINE / SERVED_MODEL_NAME / MODEL_ID / MODEL_REVISION / MAX_MODEL_LEN / TP / GPU_MEM_UTIL
    # удалены из реестра — берутся ТОЛЬКО из пресета (карточка модели в БД).
    # Если пресет не задаёт обязательное поле, merge_llm_stack_env поднимает MissingStackParams("preset").
    "LLM_API_BIND": _e("LLM_API_BIND", "inference", "Bind-адрес опубликованного порта LLM API на хосте (0.0.0.0 / 127.0.0.1).", *S_LLM, *S_ALL_COMPOSE),
    "LLM_API_PORT": _e(
        "LLM_API_PORT",
        "inference",
        "Порт публикации vLLM на хосте и listen внутри контейнера (типично 1:1, например 8111:8111).",
        *S_LLM,
        *S_ALL_COMPOSE,
        "probes",
    ),
    "LLM_API_PORT_SGLANG": _e(
        "LLM_API_PORT_SGLANG",
        "inference",
        "Порт публикации SGLang на хосте и listen внутри контейнера (аналогично vLLM).",
        *S_LLM,
        *S_ALL_COMPOSE,
        "probes",
    ),
    "LLM_HOST_PORT_RANGE_VLLM_START": _e("LLM_HOST_PORT_RANGE_VLLM_START", "inference", "Первый хост-порт авто-диапазона для vLLM-слотов.", *S_LLM, "port_allocation"),
    "LLM_HOST_PORT_RANGE_VLLM_END": _e("LLM_HOST_PORT_RANGE_VLLM_END", "inference", "Последний хост-порт авто-диапазона для vLLM-слотов.", *S_LLM, "port_allocation"),
    "LLM_HOST_PORT_RANGE_SGLANG_START": _e("LLM_HOST_PORT_RANGE_SGLANG_START", "inference", "Первый хост-порт авто-диапазона для SGLang-слотов.", *S_LLM, "port_allocation"),
    "LLM_HOST_PORT_RANGE_SGLANG_END": _e("LLM_HOST_PORT_RANGE_SGLANG_END", "inference", "Последний хост-порт авто-диапазона для SGLang-слотов.", *S_LLM, "port_allocation"),
    "KV_CACHE_DTYPE": _e("KV_CACHE_DTYPE", "inference", "Dtype KV cache (fp8_e4m3 / fp8 / auto / bfloat16).", *S_LLM, *S_ALL_COMPOSE),
    "MAX_NUM_BATCHED_TOKENS": _e("MAX_NUM_BATCHED_TOKENS", "inference", "vLLM --max-num-batched-tokens (chunked prefill).", *S_LLM, *S_ALL_COMPOSE),
    "MAX_NUM_SEQS": _e("MAX_NUM_SEQS", "inference", "vLLM --max-num-seqs (одновременных последовательностей); пусто = default.", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "BLOCK_SIZE": _e("BLOCK_SIZE", "inference", "vLLM --block-size (KV block size); пусто = default.", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "ENFORCE_EAGER": _e("ENFORCE_EAGER", "inference", "1 = vLLM --enforce-eager (без CUDA graphs); 0 — обычный режим.", *S_LLM, *S_ALL_COMPOSE),
    "DISABLE_CUSTOM_ALL_REDUCE": _e("DISABLE_CUSTOM_ALL_REDUCE", "inference", "1 = vLLM --disable-custom-all-reduce (NCCL вместо custom AR).", *S_LLM, *S_ALL_COMPOSE),
    "ENABLE_PREFIX_CACHING": _e("ENABLE_PREFIX_CACHING", "inference", "1 = vLLM --enable-prefix-caching.", *S_LLM, *S_ALL_COMPOSE),
    "ENABLE_EXPERT_PARALLEL": _e("ENABLE_EXPERT_PARALLEL", "inference", "1 = vLLM --enable-expert-parallel (для MoE с EP на нескольких GPU).", *S_LLM, *S_ALL_COMPOSE),
    "ENABLE_CHUNKED_PREFILL": _e("ENABLE_CHUNKED_PREFILL", "inference", "1 = vLLM --enable-chunked-prefill.", *S_LLM, *S_ALL_COMPOSE),
    "ENABLE_AUTO_TOOL_CHOICE": _e("ENABLE_AUTO_TOOL_CHOICE", "inference", "1 = vLLM --enable-auto-tool-choice (auto tool routing).", *S_LLM, *S_ALL_COMPOSE),
    "TRUST_REMOTE_CODE": _e("TRUST_REMOTE_CODE", "inference", "1 = vLLM --trust-remote-code (исполнение кода из репо модели).", *S_LLM, *S_ALL_COMPOSE),
    "TOOL_CALL_PARSER": _e("TOOL_CALL_PARSER", "inference", "vLLM tool-call parser (hermes / qwen3_xml / qwen3_coder / pythonic / glm47 / openai). Пусто — без парсинга.", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "REASONING_PARSER": _e("REASONING_PARSER", "inference", "vLLM reasoning parser (qwen3 / deepseek_r1 / glm45 / kimi_k2). Пусто — выкл.", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "CHAT_TEMPLATE_CONTENT_FORMAT": _e("CHAT_TEMPLATE_CONTENT_FORMAT", "inference", "vLLM --chat-template-content-format (string / openai). Пусто — авто.", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "COMPILATION_CONFIG": _e("COMPILATION_CONFIG", "inference", "vLLM --compilation-config (JSON-объект). Пусто — выкл.", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "SPECULATIVE_CONFIG": _e("SPECULATIVE_CONFIG", "inference", "vLLM --speculative-config (опции спекулятивного декодинга).", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "DATA_PARALLEL_SIZE": _e("DATA_PARALLEL_SIZE", "inference", "vLLM --data-parallel-size; пусто — выкл.", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "MM_ENCODER_TP_MODE": _e("MM_ENCODER_TP_MODE", "inference", "vLLM --mm-encoder-tp-mode (data | tensor).", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "TOKENIZER_MODE": _e("TOKENIZER_MODE", "inference", "vLLM --tokenizer-mode (auto / slow / mistral).", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "ATTENTION_BACKEND": _e("ATTENTION_BACKEND", "inference", "vLLM --attention-backend (FLASHINFER_MLA_SPARSE и др.). Пусто — не передавать.", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "NVIDIA_VISIBLE_DEVICES": _e("NVIDIA_VISIBLE_DEVICES", "inference", "Маска видимых GPU контейнеру (0,1,2,3 / 0,1,…,7). Пусто — драйвер решает.", *S_LLM, *S_ALL_COMPOSE),
    "VLLM_LOGGING_LEVEL": _e("VLLM_LOGGING_LEVEL", "inference", "Уровень логов Python в vLLM-контейнере (DEBUG / INFO / WARNING).", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS": _e("VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS", "inference", "vLLM memory profiler — оценка CUDA graphs при старте (0/1).", *S_LLM, *S_ALL_COMPOSE),
    "SGLANG_TRUST_REMOTE_CODE": _e("SGLANG_TRUST_REMOTE_CODE", "inference", "1 = SGLang --trust-remote-code.", *S_LLM, *S_ALL_COMPOSE),
    "SGLANG_MEM_FRACTION_STATIC": _e("SGLANG_MEM_FRACTION_STATIC", "inference", "SGLang --mem-fraction-static (0.7–0.95).", *S_LLM, *S_ALL_COMPOSE),
    "SGLANG_CUDA_GRAPH_MAX_BS": _e("SGLANG_CUDA_GRAPH_MAX_BS", "inference", "SGLang --cuda-graph-max-bs (1 / 2 / 4 / 8 / 16 / 32).", *S_LLM, *S_ALL_COMPOSE, allow_empty=True),
    "SGLANG_ENABLE_TORCH_COMPILE": _e("SGLANG_ENABLE_TORCH_COMPILE", "inference", "0/1 — torch compile в SGLang.", *S_LLM, *S_ALL_COMPOSE),
    "SGLANG_DISABLE_CUDA_GRAPH": _e("SGLANG_DISABLE_CUDA_GRAPH", "inference", "0/1 — отключить CUDA graph в SGLang.", *S_LLM, *S_ALL_COMPOSE),
    "SGLANG_DISABLE_CUSTOM_ALL_REDUCE": _e("SGLANG_DISABLE_CUSTOM_ALL_REDUCE", "inference", "0/1 — SGLang --disable-custom-all-reduce.", *S_LLM, *S_ALL_COMPOSE),
    "SGLANG_ENABLE_METRICS": _e("SGLANG_ENABLE_METRICS", "inference", "0/1 — HTTP-метрики SGLang (/metrics).", *S_LLM, *S_ALL_COMPOSE),
    "SGLANG_ENABLE_MFU_METRICS": _e("SGLANG_ENABLE_MFU_METRICS", "inference", "0/1 — MFU-метрики SGLang.", *S_LLM, *S_ALL_COMPOSE),

    # ----- 6. Мониторинг — Prometheus, Grafana, Loki, Promtail, DCGM, NodeExporter -----
    "PROMETHEUS_SERVICE_NAME": _e(
        "PROMETHEUS_SERVICE_NAME", "monitoring", "DNS-имя Prometheus в сети slgpu (используется в *.tmpl рендерах).", *S_MON, subgroup="prometheus"
    ),
    "GRAFANA_SERVICE_NAME": _e("GRAFANA_SERVICE_NAME", "monitoring", "DNS-имя Grafana в сети slgpu.", *S_MON, subgroup="grafana"),
    "LOKI_SERVICE_NAME": _e("LOKI_SERVICE_NAME", "monitoring", "DNS-имя Loki в сети slgpu.", *S_MON, subgroup="loki"),
    "PROMTAIL_SERVICE_NAME": _e("PROMTAIL_SERVICE_NAME", "monitoring", "DNS-имя Promtail в сети slgpu.", *S_MON, subgroup="promtail"),
    "DCGM_EXPORTER_SERVICE_NAME": _e(
        "DCGM_EXPORTER_SERVICE_NAME", "monitoring", "DNS-имя dcgm-exporter в сети slgpu.", *S_MON, subgroup="dcgm_exporter"
    ),
    "NODE_EXPORTER_SERVICE_NAME": _e(
        "NODE_EXPORTER_SERVICE_NAME", "monitoring", "DNS-имя node-exporter в сети slgpu.", *S_MON, subgroup="node_exporter"
    ),
    "PROMETHEUS_INTERNAL_PORT": _e(
        "PROMETHEUS_INTERNAL_PORT", "monitoring", "Внутренний порт Prometheus в контейнере.", *S_MON, subgroup="prometheus"
    ),
    "GRAFANA_INTERNAL_PORT": _e("GRAFANA_INTERNAL_PORT", "monitoring", "Внутренний порт Grafana.", *S_MON, subgroup="grafana"),
    "LOKI_INTERNAL_PORT": _e("LOKI_INTERNAL_PORT", "monitoring", "Внутренний порт Loki.", *S_MON, subgroup="loki"),
    "DCGM_EXPORTER_INTERNAL_PORT": _e(
        "DCGM_EXPORTER_INTERNAL_PORT", "monitoring", "Внутренний порт dcgm-exporter.", *S_MON, subgroup="dcgm_exporter"
    ),
    "NODE_EXPORTER_INTERNAL_PORT": _e(
        "NODE_EXPORTER_INTERNAL_PORT", "monitoring", "Внутренний порт node-exporter.", *S_MON, subgroup="node_exporter"
    ),
    "PROMETHEUS_CONTAINER_NAME": _e(
        "PROMETHEUS_CONTAINER_NAME",
        "monitoring",
        "Имя контейнера Prometheus (по нему backend ищет статусы и логи).",
        *S_MON,
        subgroup="prometheus",
    ),
    "GRAFANA_CONTAINER_NAME": _e("GRAFANA_CONTAINER_NAME", "monitoring", "Имя контейнера Grafana.", *S_MON, subgroup="grafana"),
    "LOKI_CONTAINER_NAME": _e("LOKI_CONTAINER_NAME", "monitoring", "Имя контейнера Loki.", *S_MON, subgroup="loki"),
    "PROMTAIL_CONTAINER_NAME": _e("PROMTAIL_CONTAINER_NAME", "monitoring", "Имя контейнера Promtail.", *S_MON, subgroup="promtail"),
    "DCGM_EXPORTER_CONTAINER_NAME": _e(
        "DCGM_EXPORTER_CONTAINER_NAME", "monitoring", "Имя контейнера dcgm-exporter.", *S_MON, subgroup="dcgm_exporter"
    ),
    "NODE_EXPORTER_CONTAINER_NAME": _e(
        "NODE_EXPORTER_CONTAINER_NAME", "monitoring", "Имя контейнера node-exporter.", *S_MON, subgroup="node_exporter"
    ),
    "PROMETHEUS_BIND": _e(
        "PROMETHEUS_BIND",
        "monitoring",
        "Bind Prometheus UI/API на хосте (0.0.0.0 — снаружи; 127.0.0.1 — только SSH-туннель).",
        *S_MON,
        subgroup="prometheus",
    ),
    "PROMETHEUS_PORT": _e(
        "PROMETHEUS_PORT", "monitoring", "Опубликованный порт Prometheus на хосте.", *S_MON, "probes", subgroup="prometheus"
    ),
    "GRAFANA_BIND": _e("GRAFANA_BIND", "monitoring", "Bind Grafana на хосте.", *S_MON, subgroup="grafana"),
    "GRAFANA_PORT": _e(
        "GRAFANA_PORT", "monitoring", "Опубликованный порт Grafana на хосте.", *S_MON, "probes", subgroup="grafana"
    ),
    "LOKI_BIND": _e("LOKI_BIND", "monitoring", "Bind Loki HTTP push API на хосте.", *S_MON, subgroup="loki"),
    "LOKI_PORT": _e(
        "LOKI_PORT", "monitoring", "Опубликованный порт Loki на хосте.", *S_MON, "probes", subgroup="loki"
    ),
    "DCGM_BIND": _e(
        "DCGM_BIND", "monitoring", "Bind DCGM exporter (метрики GPU) на хосте.", *S_MON, subgroup="dcgm_exporter"
    ),
    "NODE_EXPORTER_BIND": _e(
        "NODE_EXPORTER_BIND", "monitoring", "Bind node-exporter (host-метрики) на хосте.", *S_MON, subgroup="node_exporter"
    ),
    "PROMETHEUS_RETENTION_TIME": _e(
        "PROMETHEUS_RETENTION_TIME",
        "monitoring",
        "Срок хранения TSDB Prometheus (--storage.tsdb.retention.time): 7d / 30d / 1y / 100y.",
        *S_MON,
        subgroup="prometheus",
    ),
    "PROMETHEUS_RETENTION_SIZE": _e(
        "PROMETHEUS_RETENTION_SIZE",
        "monitoring",
        "Макс. размер TSDB Prometheus (0 = без лимита; 20GB / 100GB).",
        *S_MON,
        subgroup="prometheus",
    ),
    "GRAFANA_ADMIN_USER": _e("GRAFANA_ADMIN_USER", "monitoring", "Логин администратора Grafana.", *S_MON, subgroup="grafana"),
    "GRAFANA_ADMIN_PASSWORD": _e(
        "GRAFANA_ADMIN_PASSWORD", "monitoring", "Пароль администратора Grafana (в проде сменить).", *S_MON, subgroup="grafana"
    ),
    "GF_SERVER_ROOT_URL": _e(
        "GF_SERVER_ROOT_URL",
        "monitoring",
        "GF_SERVER_ROOT_URL (если Grafana за reverse proxy). Пусто — http://<host>:GRAFANA_PORT.",
        *S_MON,
        allow_empty=True,
        subgroup="grafana",
    ),

    # ----- 7. Прокси — Langfuse + LiteLLM + Postgres + Redis + ClickHouse + MinIO -----
    # Langfuse: блок строк без Postgres между собой — dns/name/container/internal/bind/host-port парами для UI («Настройки»).
    "LANGFUSE_WEB_SERVICE_NAME": _e(
        "LANGFUSE_WEB_SERVICE_NAME", "proxy", "DNS-имя langfuse-web в сети slgpu.", *S_MON, subgroup="langfuse"
    ),
    "LANGFUSE_WEB_CONTAINER_NAME": _e(
        "LANGFUSE_WEB_CONTAINER_NAME", "proxy", "Имя контейнера langfuse-web.", *S_MON, subgroup="langfuse"
    ),
    "LANGFUSE_WEB_INTERNAL_PORT": _e(
        "LANGFUSE_WEB_INTERNAL_PORT", "proxy", "Внутренний порт langfuse-web в контейнере.", *S_MON, subgroup="langfuse"
    ),
    "LANGFUSE_BIND": _e("LANGFUSE_BIND", "proxy", "Bind Langfuse Web (UI) на хосте.", *S_MON, subgroup="langfuse"),
    "LANGFUSE_PORT": _e(
        "LANGFUSE_PORT", "proxy", "Опубликованный порт Langfuse Web на хосте.", *S_MON, "probes", subgroup="langfuse"
    ),
    "LANGFUSE_WORKER_SERVICE_NAME": _e(
        "LANGFUSE_WORKER_SERVICE_NAME", "proxy", "DNS-имя langfuse-worker в сети slgpu.", *S_MON, subgroup="langfuse"
    ),
    "LANGFUSE_WORKER_CONTAINER_NAME": _e(
        "LANGFUSE_WORKER_CONTAINER_NAME", "proxy", "Имя контейнера langfuse-worker.", *S_MON, subgroup="langfuse"
    ),
    "LANGFUSE_WORKER_INTERNAL_PORT": _e(
        "LANGFUSE_WORKER_INTERNAL_PORT", "proxy", "Внутренний порт langfuse-worker.", *S_MON, subgroup="langfuse"
    ),
    "LANGFUSE_WORKER_BIND": _e(
        "LANGFUSE_WORKER_BIND", "proxy", "Bind Langfuse Worker на хосте.", *S_MON, subgroup="langfuse"
    ),
    "LANGFUSE_WORKER_PORT": _e(
        "LANGFUSE_WORKER_PORT", "proxy", "Опубликованный порт Langfuse Worker.", *S_MON, subgroup="langfuse"
    ),
    "NEXTAUTH_URL": _e(
        "NEXTAUTH_URL",
        "proxy",
        "Канонический URL Langfuse в браузере (NextAuth, cookies, редиректы); должен совпадать с адресной строкой клиента.",
        *S_MON,
        subgroup="langfuse",
    ),
    "POSTGRES_SERVICE_NAME": _e("POSTGRES_SERVICE_NAME", "proxy", "DNS-имя Postgres в сети slgpu.", *S_MON, subgroup="postgresql"),
    "POSTGRES_INTERNAL_PORT": _e(
        "POSTGRES_INTERNAL_PORT", "proxy", "Внутренний порт Postgres в контейнере.", *S_MON, subgroup="postgresql"
    ),
    "POSTGRES_CONTAINER_NAME": _e(
        "POSTGRES_CONTAINER_NAME", "proxy", "Имя контейнера Postgres.", *S_MON, subgroup="postgresql"
    ),
    "REDIS_SERVICE_NAME": _e("REDIS_SERVICE_NAME", "proxy", "DNS-имя Redis в сети slgpu.", *S_MON, subgroup="redis"),
    "REDIS_INTERNAL_PORT": _e(
        "REDIS_INTERNAL_PORT", "proxy", "Внутренний порт Redis в контейнере.", *S_MON, subgroup="redis"
    ),
    "REDIS_CONTAINER_NAME": _e("REDIS_CONTAINER_NAME", "proxy", "Имя контейнера Redis.", *S_MON, subgroup="redis"),
    "CLICKHOUSE_SERVICE_NAME": _e(
        "CLICKHOUSE_SERVICE_NAME", "proxy", "DNS-имя ClickHouse в сети slgpu.", *S_MON, subgroup="clickhouse"
    ),
    "CLICKHOUSE_HTTP_INTERNAL_PORT": _e(
        "CLICKHOUSE_HTTP_INTERNAL_PORT", "proxy", "HTTP-порт ClickHouse в контейнере.", *S_MON, subgroup="clickhouse"
    ),
    "CLICKHOUSE_TCP_INTERNAL_PORT": _e(
        "CLICKHOUSE_TCP_INTERNAL_PORT", "proxy", "TCP/native-порт ClickHouse в контейнере.", *S_MON, subgroup="clickhouse"
    ),
    "CLICKHOUSE_CONTAINER_NAME": _e(
        "CLICKHOUSE_CONTAINER_NAME", "proxy", "Имя контейнера ClickHouse.", *S_MON, subgroup="clickhouse"
    ),
    # MinIO: в UI подряд — dns/контейнеры, затем API (internal+bind+host), Console (то же), учётка root.
    "MINIO_SERVICE_NAME": _e("MINIO_SERVICE_NAME", "proxy", "DNS-имя MinIO в сети slgpu.", *S_MON, subgroup="minio"),
    "MINIO_CONTAINER_NAME": _e("MINIO_CONTAINER_NAME", "proxy", "Имя контейнера MinIO.", *S_MON, subgroup="minio"),
    "MINIO_BUCKET_INIT_CONTAINER_NAME": _e(
        "MINIO_BUCKET_INIT_CONTAINER_NAME",
        "proxy",
        "Имя bootstrap-контейнера minio bucket-init.",
        *S_MON,
        subgroup="minio",
    ),
    "MINIO_API_INTERNAL_PORT": _e(
        "MINIO_API_INTERNAL_PORT", "proxy", "S3 API-порт MinIO внутри контейнера.", *S_MON, subgroup="minio"
    ),
    "MINIO_API_BIND": _e("MINIO_API_BIND", "proxy", "Bind MinIO API на хосте.", *S_MON, subgroup="minio"),
    "MINIO_API_HOST_PORT": _e(
        "MINIO_API_HOST_PORT", "proxy", "Опубликованный порт MinIO API на хосте.", *S_MON, subgroup="minio"
    ),
    "MINIO_CONSOLE_INTERNAL_PORT": _e(
        "MINIO_CONSOLE_INTERNAL_PORT", "proxy", "Консольный порт MinIO внутри контейнера.", *S_MON, subgroup="minio"
    ),
    "MINIO_CONSOLE_BIND": _e("MINIO_CONSOLE_BIND", "proxy", "Bind консоли MinIO на хосте.", *S_MON, subgroup="minio"),
    "MINIO_CONSOLE_HOST_PORT": _e(
        "MINIO_CONSOLE_HOST_PORT",
        "proxy",
        "Опубликованный порт консоли MinIO на хосте.",
        *S_MON,
        subgroup="minio",
    ),
    "MINIO_ROOT_USER": _e("MINIO_ROOT_USER", "proxy", "MinIO root user.", *S_MON, subgroup="minio"),
    "MINIO_ROOT_PASSWORD": _e("MINIO_ROOT_PASSWORD", "proxy", "MinIO root password.", *S_MON, subgroup="minio"),
    "LITELLM_SERVICE_NAME": _e("LITELLM_SERVICE_NAME", "proxy", "DNS-имя LiteLLM в сети slgpu.", *S_MON, subgroup="litellm"),
    "LITELLM_CONTAINER_NAME": _e("LITELLM_CONTAINER_NAME", "proxy", "Имя контейнера LiteLLM.", *S_MON, subgroup="litellm"),
    "LITELLM_PG_INIT_CONTAINER_NAME": _e(
        "LITELLM_PG_INIT_CONTAINER_NAME",
        "proxy",
        "Имя bootstrap-контейнера litellm-pg-init (создаёт ${LITELLM_POSTGRES_DB}).",
        *S_MON,
        subgroup="postgresql",
    ),
    "LITELLM_BIND": _e(
        "LITELLM_BIND",
        "proxy",
        "Bind LiteLLM proxy (OpenAI-совместимый шлюз) на хосте.",
        *S_MON,
        subgroup="litellm",
    ),
    "LITELLM_PORT": _e(
        "LITELLM_PORT",
        "proxy",
        "Опубликованный порт LiteLLM на хосте.",
        *S_MON,
        "probes",
        subgroup="litellm",
    ),
    "LITELLM_POSTGRES_DB": _e(
        "LITELLM_POSTGRES_DB",
        "proxy",
        "Имя БД LiteLLM в общем Postgres (создаётся litellm-pg-init).",
        *S_MON,
        subgroup="postgresql",
    ),
    "LITELLM_LOG": _e(
        "LITELLM_LOG", "proxy", "Уровень логов прокси LiteLLM (INFO / DEBUG как --detailed_debug).", *S_MON, allow_empty=True, subgroup="litellm"
    ),
    "LITELLM_LLM_ID": _e(
        "LITELLM_LLM_ID",
        "proxy",
        "id маршрута LiteLLM в Admin UI / БД (опционально, при STORE_MODEL_IN_DB).",
        *S_MON,
        allow_empty=True,
        subgroup="litellm",
    ),
    "STORE_MODEL_IN_DB": _e(
        "STORE_MODEL_IN_DB",
        "proxy",
        "True = хранить список моделей LiteLLM в Postgres (Admin UI редактирует).",
        *S_MON,
        subgroup="litellm",
    ),
    "UI_USERNAME": _e(
        "UI_USERNAME", "proxy", "Учётка Admin UI LiteLLM (/ui).", *S_MON, allow_empty=True, subgroup="litellm"
    ),
    "UI_PASSWORD": _e(
        "UI_PASSWORD", "proxy", "Пароль Admin UI LiteLLM (/ui).", *S_MON, allow_empty=True, subgroup="litellm"
    ),
    "LANGFUSE_POSTGRES_USER": _e(
        "LANGFUSE_POSTGRES_USER",
        "proxy",
        "Учётка общего Postgres (Langfuse, LiteLLM); placeholder для dev.",
        *S_MON,
        subgroup="postgresql",
    ),
    "LANGFUSE_POSTGRES_PASSWORD": _e(
        "LANGFUSE_POSTGRES_PASSWORD", "proxy", "Пароль общего Postgres.", *S_MON, subgroup="postgresql"
    ),
    "LANGFUSE_POSTGRES_DB": _e(
        "LANGFUSE_POSTGRES_DB",
        "proxy",
        "Имя основной БД Postgres (Langfuse).",
        *S_MON,
        subgroup="postgresql",
    ),
    "LANGFUSE_REDIS_AUTH": _e(
        "LANGFUSE_REDIS_AUTH",
        "proxy",
        "Пароль Redis (используется Langfuse).",
        *S_MON,
        subgroup="redis",
    ),
    "LANGFUSE_CLICKHOUSE_USER": _e(
        "LANGFUSE_CLICKHOUSE_USER", "proxy", "Учётка ClickHouse (Langfuse).", *S_MON, subgroup="clickhouse"
    ),
    "LANGFUSE_CLICKHOUSE_PASSWORD": _e(
        "LANGFUSE_CLICKHOUSE_PASSWORD",
        "proxy",
        "Пароль ClickHouse (Langfuse).",
        *S_MON,
        subgroup="clickhouse",
    ),
    "LANGFUSE_SALT": _e(
        "LANGFUSE_SALT",
        "proxy",
        "Соль Langfuse (для хеширования). В проде — длинная случайная строка.",
        *S_MON,
        subgroup="langfuse",
    ),
    "LANGFUSE_ENCRYPTION_KEY": _e(
        "LANGFUSE_ENCRYPTION_KEY",
        "proxy",
        "32-байтный ключ шифрования Langfuse (hex, 64 символа). `openssl rand -hex 32`.",
        *S_MON,
        subgroup="langfuse",
    ),
    "NEXTAUTH_SECRET": _e(
        "NEXTAUTH_SECRET",
        "proxy",
        "NEXTAUTH_SECRET (cookie session). `openssl rand -base64 32`.",
        *S_MON,
        subgroup="langfuse",
    ),
    "LANGFUSE_S3_EVENT_UPLOAD_BUCKET": _e(
        "LANGFUSE_S3_EVENT_UPLOAD_BUCKET",
        "proxy",
        "Имя S3-бакета Langfuse для events в MinIO.",
        *S_MON,
        subgroup="langfuse",
    ),
    "LANGFUSE_S3_MEDIA_BUCKET": _e(
        "LANGFUSE_S3_MEDIA_BUCKET",
        "proxy",
        "Имя S3-бакета Langfuse для media в MinIO.",
        *S_MON,
        subgroup="langfuse",
    ),
    "LANGFUSE_TELEMETRY": _e(
        "LANGFUSE_TELEMETRY",
        "proxy",
        "true/false — отправлять анонимную телеметрию Langfuse в их API.",
        *S_MON,
        subgroup="langfuse",
    ),
    "LANGFUSE_PUBLIC_KEY": _e(
        "LANGFUSE_PUBLIC_KEY",
        "proxy",
        "Langfuse public key для интеграции LiteLLM → Langfuse (OTEL); создаётся в Langfuse → Settings → API Keys.",
        *S_MON,
        allow_empty=True,
        subgroup="langfuse",
    ),
    "LANGFUSE_SECRET_KEY": _e(
        "LANGFUSE_SECRET_KEY",
        "proxy",
        "Langfuse secret key для интеграции LiteLLM → Langfuse (OTEL).",
        *S_MON,
        allow_empty=True,
        subgroup="langfuse",
    ),

    # ----- 8. Секреты приложения -----
    "HF_TOKEN": _e("HF_TOKEN", "secrets", "HuggingFace токен для приватных или gated моделей. Пусто = без аутентификации.", "pull", allow_empty=True),
}

CANONICAL_STACK_KEYS: frozenset[str] = frozenset(_STACK_KEY_REGISTRY.keys())

STACK_KEY_REGISTRY: dict[str, KeyMeta] = _STACK_KEY_REGISTRY


class MissingKeyInfo(TypedDict):
    key: str
    group: str
    description: str


def _non_empty(s: str | None) -> bool:
    if s is None:
        return False
    return str(s).strip() != ""


def validate_required(merged: dict[str, str], scope: StackScope) -> list[MissingKeyInfo]:
    out: list[MissingKeyInfo] = []
    for key, meta in STACK_KEY_REGISTRY.items():
        if scope not in meta.required_for:
            continue
        v = merged.get(key)
        if meta.allow_empty:
            continue
        if not _non_empty(v):
            out.append(
                {
                    "key": key,
                    "group": meta.group,
                    "description": meta.description,
                }
            )
    return out


def raise_if_missing(merged: dict[str, str], scope: StackScope) -> None:
    missing = validate_required(merged, scope)
    if missing:
        raise MissingStackParams([m["key"] for m in missing], scope)


def missing_keys_in_db(merged: dict[str, str]) -> list[str]:
    """Keys in registry with no value (for startup WARN), respecting allow_empty."""
    out: list[str] = []
    for k in CANONICAL_STACK_KEYS:
        meta = STACK_KEY_REGISTRY.get(k)
        if meta and meta.allow_empty:
            continue
        if not _non_empty(merged.get(k)):
            out.append(k)
    return out


def registry_to_public() -> list[dict[str, Any]]:
    # Порядок ключей соответствует порядку объявления в _STACK_KEY_REGISTRY,
    # который, в свою очередь, повторяет порядок секций в `configs/main.env`.
    # UI «Настройки» использует именно этот порядок для сортировки строк
    # внутри группы (group == раздел main.env).
    return [
        {
            "key": m.key,
            "group": m.group,
            "description": m.description,
            "is_secret": m.is_secret,
            "allow_empty": m.allow_empty,
            "required_for": sorted(m.required_for),
            "ui_hidden": m.ui_hidden,
            "subgroup": m.subgroup,
        }
        for m in STACK_KEY_REGISTRY.values()
    ]


__all__ = [
    "CANONICAL_STACK_KEYS",
    "KeyMeta",
    "MissingKeyInfo",
    "STACK_KEY_REGISTRY",
    "StackScope",
    "is_secret_key",
    "missing_keys_in_db",
    "raise_if_missing",
    "registry_to_public",
    "validate_required",
]
