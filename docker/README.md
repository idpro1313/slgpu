# Docker Compose (slgpu)

Файлы запуска стека:

| Файл | Назначение |
|------|------------|
| `docker-compose.llm.yml` | vLLM / SGLang (`./slgpu up`) |
| `docker-compose.monitoring.yml` | мониторинг, Langfuse, LiteLLM (`./slgpu monitoring up`) |
| `docker-compose.web.yml` | slgpu-web UI (`./slgpu web up`; сборка: `web/Dockerfile`, `context: ./web`) |

Всегда вызывайте `docker compose` с **`--project-directory` = корень репозитория** (так делают `scripts/_lib.sh:slgpu_docker_compose` и `scripts/cmd_up.sh:compose_llm_env`), иначе относительные пути в YAML и `env_file: main.env` не сойдутся.
