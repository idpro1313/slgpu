# Docker Compose (slgpu)

Файлы запуска стека:

| Файл | Назначение |
|------|------------|
| `docker-compose.llm.yml` | vLLM / SGLang (`./slgpu up`) |
| `docker-compose.monitoring.yml` | мониторинг, Langfuse, LiteLLM (`./slgpu monitoring up`) |
| `docker-compose.web.yml` | slgpu-web UI (`./slgpu web up`) |
| `Dockerfile.web` | образ slgpu-web (`context: ./web`, исходники в `web/`) |

Всегда вызывайте `docker compose` с **`--project-directory` = корень репозитория** (так делают `scripts/_lib.sh:slgpu_docker_compose` и `scripts/cmd_up.sh:compose_llm_env`), иначе относительные пути в YAML и `env_file: main.env` не сойдутся.

**Подстановка `${VAR}` в `docker-compose.llm.yml`:** `./slgpu up` пишет снимок переменных после `main.env` + пресет в временный файл и вызывает `docker compose --env-file …` под «чистым» `env -i`, чтобы родитель (в т.ч. **slgpu-web**) не перебивал пресет через свой shell environment. В корневом **`.env`** проекта не дублируйте **`MAX_MODEL_LEN`**, **`GPU_MEM_UTIL`**, **`KV_CACHE_DTYPE`**, **`TOOL_CALL_PARSER`**, **`REASONING_PARSER`** и т.п., если они должны задаваться только пресетом — иначе приоритет может остаться за `.env` в зависимости от версии Compose.
