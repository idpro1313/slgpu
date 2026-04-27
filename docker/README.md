# Docker Compose (slgpu)

Файлы запуска стека:

| Файл | Назначение |
|------|------------|
| `docker-compose.llm.yml` | vLLM / SGLang — **в основном из Develonica.LLM** (`native.slot.*`); ручной compose — **legacy** (см. комментарии в YAML) |
| `docker-compose.monitoring.yml` | Prometheus, Grafana, Loki, … — из UI / `native.monitoring.*` |
| `docker-compose.proxy.yml` | Langfuse + LiteLLM — из UI / `native.litellm.*` / proxy jobs |
| `docker-compose.web.yml` | **slgpu-web** (`./slgpu web up`) |
| `Dockerfile.web` | образ slgpu-web (`context: ./web`) |

Всегда вызывайте `docker compose` с **`--project-directory` = корень репозитория** (так делают `scripts/_lib.sh:slgpu_docker_compose` и backend при jobs), иначе относительные пути в YAML и `env_file` не сойдутся.

**Подстановка `${VAR}` в `docker-compose.llm.yml`:** при запуске из web/CLI с пресетом пишется снимок в temp-файл и `docker compose --env-file …` под очищенным env, чтобы shell не перебил пресет. В корневом **`.env`** не дублируйте поля пресета (`MAX_MODEL_LEN`, `GPU_MEM_UTIL`, …), если они задаются только в БД/пресете.
