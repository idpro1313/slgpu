# Пресеты моделей (формат и справка по полям)

Эталонные примеры пресетов `*.env` в репозитории — **[`examples/presets/`](../../examples/presets/)**. Рабочий каталог на стенде задаётся **`PRESETS_DIR`** в [`main.env`](../main.env) (по умолчанию **`./data/presets`**); файлы там **не отслеживаются** git’ом. Web UI и CLI читают и пишут в `PRESETS_DIR`. На новом клоне: `cp examples/presets/*.env data/presets/`.

Каждый файл `<slug>.env` задаёт параметры **конкретной модели**. В **v5** пресет выбирается в **Develonica.LLM** (страницы **Пресеты** / **Слоты**); загрузка весов — job **`native.model.pull`**, запуск движка — **`native.slot.*`**. Для ручного `docker compose` / бенч-скриптов на хосте укажите тот же пресет через env-файлы, что и в UI.

## Параметры пресета (справочник)

- **`VLLM_DOCKER_IMAGE`** — образ vLLM для `docker compose` (см. [`docker/docker-compose.llm.yml`](../docker/docker-compose.llm.yml)); в репозитории задаётся **в пресете**, не в `main.env` (теги вида `*-cu130` — CUDA 13.x **в контейнере**; ориентиры на [vllm/vllm-openai](https://hub.docker.com/r/vllm/vllm-openai/tags), семейные теги `qwen3_5_…`, `glm51_…`, `deepseekv4_…`, `minimax27_…`, см. также [`mimo-v2.5.env`](../../examples/presets/mimo-v2.5.env), [`gemma-4-31b-it.env`](../../examples/presets/gemma-4-31b-it.env)). Fallback в compose, если переменная не задана.
- **`MODEL_ID`** — репозиторий Hugging Face и подкаталог в `MODELS_DIR` после загрузки (`native.model.pull` / `hf download`). **С 7.0.4:** в БД поля пресета (**`hf_id`**, **`tp`**, **`served_model_name`**) при merge в рантайме **имеют приоритет** над теми же ключами внутри JSON **`parameters`** (чтобы устаревший **`TP`** из эталонного `.env` не отменял TP из UI слота).
- **`MODEL_REVISION`** — SHA/тег на HF; пусто — ветка по умолчанию.
- **`MAX_MODEL_LEN`** — окно контекста (`--max-model-len` / `--context-length`). Задаёте **вручную** (ориентиры: **262144** у многих 256k-моделей; **131072** — Qwen3-30B / gpt-oss; **202752** / **200704** — GLM / MiniMax M2 — см. репозитарии и [рецепты](https://github.com/vllm-project/recipes) vLLM). **GLM-5.1** bf16 на 8×~140 GB — в [`glm-5.1.env`](../../examples/presets/glm-5.1.env) **65536**; **GLM-5.1-FP8** — [`glm-5.1-fp8.env`](../../examples/presets/glm-5.1-fp8.env). **`ENABLE_PREFIX_CACHING=0`** в пресетах GLM; при OOM снижайте `MAX_MODEL_LEN` / `GPU_MEM_UTIL` / batched tokens.
- **`KV_CACHE_DTYPE`** — `fp8_e4m3`, `fp8`, `auto`, …; у Qwen3 Next/3.6 избегайте `fp8_e5m2`. У **DeepSeek V4** (Flash/Pro) в vLLM — **`fp8_e4m3`** или `fp8`, не **`auto`** (иначе `DeepseekV4 only supports fp8 kv-cache… got auto`). У **zai-org/GLM-5.1** (sparse MLA) в vLLM 0.19 используйте **`auto`** (или не-fp8 KV) — иначе `No valid attention backend` при старте.
- **`ATTENTION_BACKEND`** (только vLLM, опционально) — если задано, в `serve.sh` передаётся `--attention-backend`. У **DeepSeek V4** по умолчанию в логе: fp8_ds_mla KV; для пути с «стандартным» fp8 vLLM подсказывает `FLASHINFER_MLA_SPARSE` (см. [`scripts/serve.sh`](../scripts/serve.sh), пресеты deepseek-v4-*.env). Старое имя: `SLGPU_VLLM_ATTENTION_BACKEND`.
- **`GPU_MEM_UTIL`** — vLLM `--gpu-memory-utilization`.
- **`MAX_NUM_BATCHED_TOKENS`** — только vLLM (chunked prefill; в .env **не** используйте префикс `VLLM_*` — vLLM 0.19+ ругается на неизвестные `VLLM_*`). Старое: `SLGPU_MAX_NUM_BATCHED_TOKENS`, `VLLM_MAX_NUM_BATCHED_TOKENS`.
- **`MAX_NUM_SEQS`** — только vLLM: **`--max-num-seqs`**; верхняя граница одновременных последовательностей (упирается в KV; сначала снизьте **`MAX_MODEL_LEN`** под реальный контекст). Старое: `SLGPU_VLLM_MAX_NUM_SEQS`.
- **`BLOCK_SIZE`** — только vLLM: **`--block-size`**; у **DeepSeek V4** в блоге/логе ориентир **256** (см. [`deepseek-v4-pro.env`](../../examples/presets/deepseek-v4-pro.env)). Старое: `SLGPU_VLLM_BLOCK_SIZE`.
- **`COMPILATION_CONFIG`** — JSON для **`--compilation-config`**; **DeepSeek V4 Pro** — ориентир в пресете по [блогу vLLM](https://vllm.ai/blog/deepseek-v4) (`cudagraph_mode` + `custom_ops`); при ошибке старта упростить или убрать. У **V4 Flash** в репо по умолчанию **не** задано (см. [`deepseek-v4-flash.env`](../../examples/presets/deepseek-v4-flash.env)). У **MiniMax M2** см. [`minimax-m2.7.env`](../../examples/presets/minimax-m2.7.env) и [рецепт MiniMax-M2](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md) (`fuse_minimax_qk_norm`). Старое: `SLGPU_VLLM_COMPILATION_CONFIG`.
- **`ENFORCE_EAGER`** — только vLLM: **`1`** → **`--enforce-eager`**, обход `torch._inductor` при **InductorError** / `profile_run` (см. README §14). В [deepseek-v4-flash.env](../../examples/presets/deepseek-v4-flash.env) по умолчанию **`1`**. Старое: `SLGPU_VLLM_ENFORCE_EAGER`.
- **`DISABLE_CUSTOM_ALL_REDUCE`** — только vLLM: `1` (дефолт) — `--disable-custom-all-reduce` (NCCL); `0` — custom all-reduce (иногда быстрее, но на части моделей/образов vLLM — `custom_all_reduce.cuh` / `invalid argument` при graph capture; тогда оставьте `1`) (см. `serve.sh`, `docker-compose`). Старое: `SLGPU_DISABLE_CUSTOM_ALL_REDUCE`.
- **`SGLANG_MEM_FRACTION_STATIC`** — только SGLang.
- **`SGLANG_CUDA_GRAPH_MAX_BS`**, **`SGLANG_ENABLE_TORCH_COMPILE`**, **`SGLANG_DISABLE_CUDA_GRAPH`**, **`SGLANG_DISABLE_CUSTOM_ALL_REDUCE`** — только SGLang: обход OOM/ошибок **CUDA graph capture** и сбоев **custom all-reduce** (см. `main.env`, `scripts/serve.sh`); при «Capture cuda graph failed» SGLang подсказывает понижать mem / max-bs, отключать torch compile, в крайнем случае граф; при ошибках в `custom_all_reduce` — `SGLANG_DISABLE_CUSTOM_ALL_REDUCE=1` (откат на NCCL).
- **`REASONING_PARSER`**, **`TOOL_CALL_PARSER`** — vLLM и SGLang (`launch_server`); см. таблицу ниже.
- **`CHAT_TEMPLATE_CONTENT_FORMAT`** — только vLLM (`--chat-template-content-format`); у **GLM-5.1-FP8** в пресете [`glm-5.1-fp8.env`](../../examples/presets/glm-5.1-fp8.env) задано **`string`**, как в [рецепте vLLM GLM5](https://github.com/vllm-project/recipes/blob/main/GLM/GLM5.md).
- **`SPECULATIVE_CONFIG`** — только vLLM: JSON для **`--speculative-config`**; у **GLM-5.1-FP8** в [`glm-5.1-fp8.env`](../../examples/presets/glm-5.1-fp8.env) задано **MTP** (`method` + `num_speculative_tokens`) по [GLM/GLM5.md](https://github.com/vllm-project/recipes/blob/main/GLM/GLM5.md). Старое: `SLGPU_VLLM_SPECULATIVE_CONFIG`.
- **`ENABLE_EXPERT_PARALLEL`** — только vLLM: **`1`** → **`--enable-expert-parallel`** (типично 8×GPU при **TP=4** для M2.7). Старое: `SLGPU_ENABLE_EXPERT_PARALLEL`.
- **`DATA_PARALLEL_SIZE`** — только vLLM: при необходимости **`--data-parallel-size`** (сценарий **DP8+EP** в рецепте MiniMax). Старое: `SLGPU_VLLM_DATA_PARALLEL_SIZE`.
- **`MM_ENCODER_TP_MODE`** — только vLLM (`--mm-encoder-tp-mode`); для **moonshotai/Kimi-K2.6** в репозитории в пресете задано **`data`** (референс Moonshot).
- **`TP`** — tensor parallel; согласуйте с числом GPU. В шаблонах репозитория по умолчанию **8**; на 4 GPU — **4** в пресете (в UI при создании слота).
- **`BENCH_MODEL_NAME`** — поле `model` в бенче; пусто — первая модель из `/v1/models`.
- **`VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS`** — `0` или `1` (в пресете для тяжёлых MoE при необходимости).

## Соответствие семейств и парсеров (vLLM)

| Семейство                  | `REASONING_PARSER` | `TOOL_CALL_PARSER`                 |
|----------------------------|--------------------|------------------------------------|
| Qwen3 / Qwen2.5            | `qwen3`            | `hermes`                           |
| Qwen3-Coder / Qwen3.6      | `qwen3`            | `qwen3_xml` (или `qwen3_coder`)    |
| Qwen3-*-Thinking           | `qwen3-thinking`   | `hermes`                           |
| DeepSeek R1              | `deepseek_r1`      | `pythonic`         |
| deepseek-ai/DeepSeek-V4-* (Flash/Pro) | `deepseek_v4` | `deepseek_v4` (рецепт [vLLM DeepSeek V4](https://vllm.ai/blog/deepseek-v4); не путать с `deepseek_r1` для R1) |
| openai/gpt-oss-*         | `openai_gptoss`    | `openai`           |
| zai-org/GLM* (bf16)     | `glm45`            | `glm45`            |
| zai-org/GLM*FP8         | `glm45`            | `glm47`            |
| MiniMaxAI/MiniMax-*      | `minimax_m2`       | `minimax_m2`       |
| moonshotai/Kimi-K2*      | `kimi_k2`          | `kimi_k2`          |
| XiaomiMiMo/MiMo-V2.5*     | `qwen3`            | `mimo` (ориентир SGLang [карточка HF](https://huggingface.co/XiaomiMiMo/MiMo-V2.5); пример [`mimo-v2.5.env`](../../examples/presets/mimo-v2.5.env)) |
| google/gemma-4-*          | `gemma4`           | `gemma4` ([рецепт vLLM Gemma 4](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html); пример [`gemma-4-31b-it.env`](../../examples/presets/gemma-4-31b-it.env), слот **vLLM**) |
| Llama 3.x                | (пусто)            | `llama3_json`                      |

**MiniMax M2 (vLLM):** «чистый» **TP8** не поддерживается — [`minimax-m2.7.env`](../../examples/presets/minimax-m2.7.env), [рецепт](https://github.com/vllm-project/recipes/blob/main/MiniMax/MiniMax-M2.md).

**Qwen3.6 / Qwen3-Coder**: семейство эмитит tool calls в XML-формате (`<tool_call><function=…><parameter=…>…</tool_call>`). Парсер `hermes` ждёт JSON и падает `JSONDecodeError` на таких ответах — стрим не закрывается, клиент получает таймаут. Рекомендация vLLM docs (≥0.12, `qwen3_xml`, streaming-safe, см. vllm-project/vllm#25028); официальная карточка [Qwen/Qwen3.6-27B](https://huggingface.co/Qwen/Qwen3.6-27B) предлагает `qwen3_coder` (non-streaming fallback). Проверить список доступных tool-парсеров в образе:

```bash
docker compose -f docker/docker-compose.llm.yml exec vllm python -c "from vllm.entrypoints.openai.tool_parsers import ToolParserManager; print(list(ToolParserManager.tool_parsers))"
```

Проверка списка reasoning-парсеров в образе vLLM:

```bash
docker compose -f docker/docker-compose.llm.yml exec vllm python -c "from vllm.reasoning import ReasoningParserManager; print(list(ReasoningParserManager.reasoning_parsers))"
```

## Добавить свой пресет

```bash
cp examples/presets/qwen3.6-35b-a3b.env data/presets/my-model.env
$EDITOR data/presets/my-model.env
# Затем: импорт/синхронизация в Develonica.LLM (install или UI) и создание слота с пресетом my-model
```

**`MAX_MODEL_LEN`**, **`VLLM_DOCKER_IMAGE`**, как и парсеры, задаёте **в пресете** (скопируйте пример и отредактируйте), ориентируясь на `config.json` / карточку HF и рецепты vLLM. До пресета: [`main.env`](../../main.env) (дефолты хоста и движка, **без** образа vLLM), затем пресет.
