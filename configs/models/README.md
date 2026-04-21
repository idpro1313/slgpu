# Пресеты моделей

Каждый файл `<slug>.env` задаёт параметры **конкретной модели**, переопределяя значения из корневого `.env`. Используется через флаг `-m <slug>` в скриптах:

```bash
./scripts/download-model.sh -m qwen3.6-35b-a3b
./scripts/up.sh vllm -m qwen3.6-35b-a3b
./scripts/up.sh sglang -m qwen3.6-35b-a3b
./scripts/bench.sh vllm -m qwen3.6-35b-a3b
```

Или через переменную окружения:

```bash
MODEL=qwen3.6-35b-a3b ./scripts/up.sh vllm
```

Если `-m` не указан — скрипты берут значения из корневого `.env`.

## Параметры пресета (справочник)

Ниже — для чего переменная и какие значения бывают. То же продублировано комментариями внутри каждого `*.env`.

- **`MODEL_ID`** — Для чего: репозиторий Hugging Face и подкаталог весов на диске (`MODELS_DIR`). Варианты: строка `владелец/имя` с HF, должна совпадать с фактически скачанной моделью.

- **`MODEL_REVISION`** — Для чего: зафиксировать версию файлов весов. Варианты: commit SHA, тег или ветка; пусто — ревизия по умолчанию на Hub.

- **`MAX_MODEL_LEN`** — Для чего: верхняя граница контекста в токенах для `--max-model-len` (vLLM) и `--context-length` (SGLang). Варианты: целое ≤ заявленного для модели; выше — OOM или ошибки; сумма prompt + max_tokens в запросе не должна превышать это значение.

- **`KV_CACHE_DTYPE`** — Для чего: формат KV-кэша. Варианты: `fp8_e4m3`, `fp8`, `fp8_e5m2` (осторожно с qwen3_next — см. README), `auto` для MXFP4 и др.

- **`GPU_MEM_UTIL`** — Для чего: `--gpu-memory-utilization` в vLLM. Варианты: 0.0–1.0; типично 0.90–0.95; при OOM снижать; с профайлером CUDA graphs см. подсказки в логе vLLM.

- **`VLLM_MAX_NUM_BATCHED_TOKENS`** — Для чего: только vLLM, `--max-num-batched-tokens` (chunked prefill). Варианты: 4096–32768+; больше — выше пропускная способность при нагрузке, выше потребление памяти.

- **`SGLANG_MEM_FRACTION_STATIC`** — Для чего: только SGLang, доля VRAM под статические буферы. Варианты: обычно 0.88–0.92; при нехватке памяти под KV — уменьшать.

- **`REASONING_PARSER`** — Для чего: парсер thinking/reasoning; передаётся в оба движка, но списки имён могут различаться. Варианты: см. таблицу ниже и `docker compose logs` при «Unknown reasoning parser».

- **`TOOL_CALL_PARSER`** — Для чего: только vLLM, парсер tool calls. Варианты: `hermes`, `openai`, `glm45`, … по таблице и семейству модели.

- **`VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS`** — Для чего: переопределить учёт CUDA Graph при профилировании памяти vLLM (через environment в compose). Варианты: `0` или `1`; для тяжёлых MoE иногда `0`.

- **`TP`** — Для чего: tensor parallel (число GPU под шард). Варианты: целое, согласованное с `device_ids` в `docker-compose.yml`.

- **`BENCH_MODEL_NAME`** — Для чего: поле `model` в запросах бенчмарка. Варианты: строка как в `/v1/models`; пусто — бенч берёт первую модель из списка.

## Соответствие моделей и парсеров (vLLM)

| Семейство                  | `REASONING_PARSER` | `TOOL_CALL_PARSER` |
|----------------------------|--------------------|--------------------|
| Qwen3 / Qwen3-Next / 3.6   | `qwen3`            | `hermes`           |
| Qwen3-*-Thinking           | `qwen3-thinking`   | `hermes`           |
| DeepSeek R1                | `deepseek_r1`      | `pythonic`         |
| openai/gpt-oss-*           | `openai_gptoss`    | `openai` (Harmony) |
| zai-org/GLM-4.5 / 4.6 / 5.x| `glm45`            | `glm45`            |
| MiniMaxAI/MiniMax-M1 / M2  | `minimax_m2`       | `minimax_m2`       |
| moonshotai/Kimi-K2 / K2.5 / K2.6 | `kimi_k2`          | `kimi_k2`          |
| Llama 3.x                  | (пусто)            | `llama3_json`      |

Имена `*_PARSER` зависят от версии vLLM. Если при старте ловите `Unknown reasoning parser`, обновите образ (`vllm/vllm-openai:latest`) или проверьте актуальные имена: `docker compose exec vllm python -c "from vllm.reasoning import ReasoningParserManager; print(list(ReasoningParserManager.reasoning_parsers))"`.

## Добавить свой

```bash
cp configs/models/qwen3.6-35b-a3b.env configs/models/my-model.env
$EDITOR configs/models/my-model.env
./scripts/up.sh vllm -m my-model
```
