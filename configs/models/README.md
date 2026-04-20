# Пресеты моделей

Каждый файл `<slug>.env` задаёт параметры **конкретной модели**, переопределяя значения из корневого `.env`. Используется через флаг `-m <slug>` в скриптах:

```bash
./scripts/download-model.sh -m qwen3-30b-a3b
./scripts/up.sh vllm -m qwen3-30b-a3b
./scripts/up.sh both -m qwen3-next-80b-thinking
./scripts/bench.sh vllm -m qwen3-30b-a3b
```

Или через переменную окружения:

```bash
MODEL=qwen3-next-80b-thinking ./scripts/up.sh vllm
```

Если `-m` не указан — скрипты работают как раньше, по значениям из `.env`.

## Что кладём в пресет

- `MODEL_ID` — HF-репозиторий, он же путь в `/opt/models/<MODEL_ID>`.
- `MODEL_REVISION` — commit/tag для воспроизводимости (или пусто).
- `MAX_MODEL_LEN` — максимальное окно контекста для `--max-model-len` / `--context-length`.
- `KV_CACHE_DTYPE` — `fp8_e4m3` для большинства Qwen3 и Qwen3-Next; `fp8_e5m2` — для моделей, которые его принимают.
- `GPU_MEM_UTIL` — доля VRAM под vLLM; 0.9–0.94 типично.
- `SGLANG_MEM_FRACTION_STATIC` — аналог для SGLang (обычно 0.88–0.92).
- `REASONING_PARSER` — `qwen3`, `qwen3-thinking`, `deepseek_r1` или пусто.
- `TP` — tensor-parallel для режима `up.sh <engine>` (в `both` скрипт форсит TP=2).
- `BENCH_MODEL_NAME` — имя в запросах бенча; если пусто, бенч сам подтянет из `/v1/models`.

## Добавить свой

```bash
cp configs/models/qwen3-30b-a3b.env configs/models/my-model.env
$EDITOR configs/models/my-model.env
./scripts/up.sh vllm -m my-model
```
