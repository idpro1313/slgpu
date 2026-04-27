# Формат пресетов модели (`.env`)

Рабочие файлы: **`data/presets/<slug>.env`** (не в git). Эталоны: **[`examples/presets/`](../examples/presets/)** — копируйте в `data/presets/` после клона.

## Поля (канон v5+)

- **`MODEL_ID`** — Hugging Face id (`org/model`).
- **`VLLM_DOCKER_IMAGE`** / **`SGLANG_DOCKER_IMAGE`** — образ движка (для vLLM обычно теги `*-cu130` и т.д.).
- **`TP`**, **`MAX_MODEL_LEN`**, **`GPU_MEM_UTIL`**, **`KV_CACHE_DTYPE`**, парсеры **`REASONING_PARSER`**, **`TOOL_CALL_PARSER`**, иные параметры, которые читает [`scripts/serve.sh`](../scripts/serve.sh) и передаёт в контейнер слота.

Старые имена с префиксом `SLGPU_*` для vLLM/образов нормализуются при импорте в БД (см. `env_key_aliases` в web backend).

## Импорт в БД

Сид из диска — при **`POST /api/v1/app-config/install`** (читает `data/presets/*.env` в каталоге из `PRESETS_DIR`). Дальше источник правды — **SQLite** (`presets` / `stack_params`).

## См. также

- [`web/CONTRACT.md`](../../web/CONTRACT.md) — API и сущности.
- [`README.md`](../../README.md) — обзор стенда (v5: только **`./slgpu web`** на хосте).
