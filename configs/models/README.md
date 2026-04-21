# Пресеты моделей

Каждый файл `<slug>.env` задаёт параметры **конкретной модели**. Используется с **`-m <slug>`** в командах `./slgpu`:

```bash
./slgpu pull Qwen/Qwen3.6-35B-A3B          # создаст qwen3.6-35b-a3b.env и скачает веса
./slgpu pull -m qwen3.6-35b-a3b            # только скачивание по существующему пресету
./slgpu up vllm -m qwen3.6-35b-a3b
./slgpu bench sglang -m qwen3.6-35b-a3b
```

Для **`./slgpu up`**, **`./slgpu bench`**, **`./slgpu restart`**, **`./slgpu ab`**, **`./slgpu config`** флаг **`-m <slug>`** обязателен.

## Параметры пресета (справочник)

- **`MODEL_ID`** — репозиторий Hugging Face и подкаталог в `MODELS_DIR` после `./slgpu pull`.
- **`MODEL_REVISION`** — SHA/тег на HF; пусто — ветка по умолчанию.
- **`MAX_MODEL_LEN`** — окно контекста (`--max-model-len` / `--context-length`).
- **`KV_CACHE_DTYPE`** — `fp8_e4m3`, `fp8`, `auto`, …; у Qwen3 Next/3.6 избегайте `fp8_e5m2`.
- **`GPU_MEM_UTIL`** — vLLM `--gpu-memory-utilization`.
- **`SLGPU_MAX_NUM_BATCHED_TOKENS`** — только vLLM (chunked prefill; не `VLLM_*`, чтобы vLLM 0.19+ не предупреждал о неизвестных переменных).
- **`SGLANG_MEM_FRACTION_STATIC`** — только SGLang.
- **`REASONING_PARSER`**, **`TOOL_CALL_PARSER`** — vLLM и SGLang (`launch_server`); см. таблицу ниже.
- **`MM_ENCODER_TP_MODE`** — только vLLM (`--mm-encoder-tp-mode`); для **moonshotai/Kimi-K2.6** при `./slgpu pull` подставляется **`data`** по референсу Moonshot.
- **`TP`** — tensor parallel; должен согласовываться с числом GPU в `docker-compose.yml`. В шаблонах репозитория и в **`./slgpu pull`** без `--tp` по умолчанию **8**; на 4 GPU задайте **4**.
- **`BENCH_MODEL_NAME`** — поле `model` в бенче; пусто — первая модель из `/v1/models`.
- **`VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS`** — `0` или `1` (в пресете для тяжёлых MoE при необходимости).

## Соответствие семейств и парсеров (vLLM)

| Семейство                  | `REASONING_PARSER` | `TOOL_CALL_PARSER` |
|----------------------------|--------------------|--------------------|
| Qwen3 / Qwen3.6            | `qwen3`            | `hermes`           |
| Qwen3-*-Thinking           | `qwen3-thinking`   | `hermes`           |
| DeepSeek R1              | `deepseek_r1`      | `pythonic`         |
| openai/gpt-oss-*         | `openai_gptoss`    | `openai`           |
| zai-org/GLM-*            | `glm45`            | `glm45`            |
| MiniMaxAI/MiniMax-*      | `minimax_m2`       | `minimax_m2`       |
| moonshotai/Kimi-K2*      | `kimi_k2`          | `kimi_k2`          |
| Llama 3.x                | (пусто)            | `llama3_json`      |

Проверка списка парсеров в образе vLLM:

```bash
docker compose exec vllm python -c "from vllm.reasoning import ReasoningParserManager; print(list(ReasoningParserManager.reasoning_parsers))"
```

## Добавить свой пресет

```bash
cp configs/models/qwen3.6-35b-a3b.env configs/models/my-model.env
$EDITOR configs/models/my-model.env
./slgpu up vllm -m my-model
```

Или сгенерировать черновик через `./slgpu pull org/model --slug my-model`.
