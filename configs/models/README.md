# Пресеты моделей

Каждый файл `<slug>.env` задаёт параметры **конкретной модели**. Используется с **`-m <slug>`** в командах `./slgpu`:

```bash
./slgpu pull qwen3.6-35b-a3b               # hf download по MODEL_ID из пресета
# либо ./slgpu pull Qwen/Qwen3.6-35B-A3B   # то же, если есть configs/models/qwen3.6-35b-a3b.env
./slgpu up vllm -m qwen3.6-35b-a3b
./slgpu bench sglang -m qwen3.6-35b-a3b
```

Для **`./slgpu up`**, **`./slgpu bench`**, **`./slgpu load`**, **`./slgpu restart`** флаг **`-m <slug>`** обязателен (где команда его поддерживает).

## Параметры пресета (справочник)

- **`MODEL_ID`** — репозиторий Hugging Face и подкаталог в `MODELS_DIR` после `./slgpu pull`.
- **`MODEL_REVISION`** — SHA/тег на HF; пусто — ветка по умолчанию.
- **`MAX_MODEL_LEN`** — окно контекста (`--max-model-len` / `--context-length`). Задаёте **вручную** (ориентиры: **262144** у многих 256k-моделей; **131072** — Qwen3-30B / gpt-oss; **202752** / **200704** — GLM / MiniMax M2 — см. репозитарии и [рецепты](https://github.com/vllm-project/recipes) vLLM). **GLM-5.1** bf16 на 8×~140 GB — в [`glm-5.1.env`](glm-5.1.env) **65536**; **GLM-5.1-FP8** — [`glm-5.1-fp8.env`](glm-5.1-fp8.env). **`SLGPU_ENABLE_PREFIX_CACHING=0`** в пресетах GLM; при OOM снижайте `MAX_MODEL_LEN` / `GPU_MEM_UTIL` / batched tokens.
- **`KV_CACHE_DTYPE`** — `fp8_e4m3`, `fp8`, `auto`, …; у Qwen3 Next/3.6 избегайте `fp8_e5m2`. У **zai-org/GLM-5.1** (sparse MLA) в vLLM 0.19 используйте **`auto`** (или не-fp8 KV) — иначе `No valid attention backend` при старте.
- **`GPU_MEM_UTIL`** — vLLM `--gpu-memory-utilization`.
- **`SLGPU_MAX_NUM_BATCHED_TOKENS`** — только vLLM (chunked prefill; не `VLLM_*`, чтобы vLLM 0.19+ не предупреждал о неизвестных переменных).
- **`SLGPU_DISABLE_CUSTOM_ALL_REDUCE`** — только vLLM: `1` (дефолт) — `--disable-custom-all-reduce` (NCCL); `0` — custom all-reduce (иногда быстрее, но на части моделей/образов vLLM — `custom_all_reduce.cuh` / `invalid argument` при graph capture; тогда оставьте `1`) (см. `serve.sh`, `docker-compose`).
- **`SGLANG_MEM_FRACTION_STATIC`** — только SGLang.
- **`SGLANG_CUDA_GRAPH_MAX_BS`**, **`SGLANG_ENABLE_TORCH_COMPILE`**, **`SGLANG_DISABLE_CUDA_GRAPH`**, **`SGLANG_DISABLE_CUSTOM_ALL_REDUCE`** — только SGLang: обход OOM/ошибок **CUDA graph capture** и сбоев **custom all-reduce** (см. `main.env`, `scripts/serve.sh`); при «Capture cuda graph failed» SGLang подсказывает понижать mem / max-bs, отключать torch compile, в крайнем случае граф; при ошибках в `custom_all_reduce` — `SGLANG_DISABLE_CUSTOM_ALL_REDUCE=1` (откат на NCCL).
- **`REASONING_PARSER`**, **`TOOL_CALL_PARSER`** — vLLM и SGLang (`launch_server`); см. таблицу ниже.
- **`CHAT_TEMPLATE_CONTENT_FORMAT`** — только vLLM (`--chat-template-content-format`); у **GLM-5.1-FP8** в пресете [`glm-5.1-fp8.env`](glm-5.1-fp8.env) задано **`string`**, как в [рецепте vLLM GLM5](https://github.com/vllm-project/recipes/blob/main/GLM/GLM5.md).
- **`SLGPU_VLLM_COMPILATION_CONFIG`** — только vLLM: JSON для **`--compilation-config`**; у **MiniMax M2** см. [`minimax-m2.7.env`](minimax-m2.7.env) и [рецепт MiniMax-M2](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md) (`fuse_minimax_qk_norm`).
- **`SLGPU_ENABLE_EXPERT_PARALLEL`** — только vLLM: **`1`** → **`--enable-expert-parallel`** (типично 8×GPU при **TP=4** для M2.7).
- **`SLGPU_VLLM_DATA_PARALLEL_SIZE`** — только vLLM: при необходимости **`--data-parallel-size`** (сценарий **DP8+EP** в рецепте MiniMax).
- **`MM_ENCODER_TP_MODE`** — только vLLM (`--mm-encoder-tp-mode`); для **moonshotai/Kimi-K2.6** в репозитории в пресете задано **`data`** (референс Moonshot).
- **`TP`** — tensor parallel; согласуйте с числом GPU. В шаблонах репозитория по умолчанию **8**; на 4 GPU — **4** в файле или **`./slgpu up vllm -m <preset> --tp 4`** (без флага в пресете — **8** в `serve.sh`).
- **`BENCH_MODEL_NAME`** — поле `model` в бенче; пусто — первая модель из `/v1/models`.
- **`VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS`** — `0` или `1` (в пресете для тяжёлых MoE при необходимости).

## Соответствие семейств и парсеров (vLLM)

| Семейство                  | `REASONING_PARSER` | `TOOL_CALL_PARSER`                 |
|----------------------------|--------------------|------------------------------------|
| Qwen3 / Qwen2.5            | `qwen3`            | `hermes`                           |
| Qwen3-Coder / Qwen3.6      | `qwen3`            | `qwen3_xml` (или `qwen3_coder`)    |
| Qwen3-*-Thinking           | `qwen3-thinking`   | `hermes`                           |
| DeepSeek R1              | `deepseek_r1`      | `pythonic`         |
| openai/gpt-oss-*         | `openai_gptoss`    | `openai`           |
| zai-org/GLM* (bf16)     | `glm45`            | `glm45`            |
| zai-org/GLM*FP8         | `glm45`            | `glm47`            |
| MiniMaxAI/MiniMax-*      | `minimax_m2`       | `minimax_m2`       |
| moonshotai/Kimi-K2*      | `kimi_k2`          | `kimi_k2`          |
| Llama 3.x                | (пусто)            | `llama3_json`                      |

**MiniMax M2 (vLLM):** «чистый» **TP8** не поддерживается — [`minimax-m2.7.env`](minimax-m2.7.env), [рецепт](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md).

**Qwen3.6 / Qwen3-Coder**: семейство эмитит tool calls в XML-формате (`<tool_call><function=…><parameter=…>…</tool_call>`). Парсер `hermes` ждёт JSON и падает `JSONDecodeError` на таких ответах — стрим не закрывается, клиент получает таймаут. Рекомендация vLLM docs (≥0.12, `qwen3_xml`, streaming-safe, см. vllm-project/vllm#25028); официальная карточка [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) предлагает `qwen3_coder` (non-streaming fallback). Проверить список доступных tool-парсеров в образе:

```bash
docker compose exec vllm python -c "from vllm.entrypoints.openai.tool_parsers import ToolParserManager; print(list(ToolParserManager.tool_parsers))"
```

Проверка списка reasoning-парсеров в образе vLLM:

```bash
docker compose exec vllm python -c "from vllm.reasoning import ReasoningParserManager; print(list(ReasoningParserManager.reasoning_parsers))"
```

## Добавить свой пресет

```bash
cp configs/models/qwen3.6-35b-a3b.env configs/models/my-model.env
$EDITOR configs/models/my-model.env
./slgpu up vllm -m my-model
```

**`MAX_MODEL_LEN`**, как и парсеры, задаёте **в пресете** (скопируйте пример и отредактируйте), ориентируясь на `config.json` / карточку HF и рецепты vLLM. До пресета: [`main.env`](../../main.env) (дефолты хоста и движка), затем пресет.
