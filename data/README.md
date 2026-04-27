# Локальные данные на сервере

Каталог **`data/`** в корне репозитория — соглашение по умолчанию для **персистентных path** на хосте (не коммитятся в git, кроме этого README и `.gitkeep`).

| Подкаталог | Назначение |
|------------|------------|
| **`models/`** | Веса Hugging Face (`MODELS_DIR=./data/models` в `main.env`) — то же дерево, что монтируется в vLLM/SGLang и в `slgpu-web`. |
| **`presets/`** | Файлы пресетов `*.env` (`PRESETS_DIR=./data/presets`); **Develonica.LLM** и импорт `install` читают/пишут сюда. `*.env` **не в git**. Эталоны — **`examples/presets/`** (`cp examples/presets/*.env data/presets/`). Формат: [`configs/models/README.md`](../configs/models/README.md). |
| **`web/`** | SQLite и рабочие файлы web UI (`WEB_DATA_DIR=./data/web`). Подкаталог **`web/secrets/langfuse-litellm.env`** — для compose (OTEL → Langfuse); путь в YAML: **`${WEB_DATA_DIR}/secrets/...`**. |
| **`monitoring/`** | TSDB, Loki, Grafana, Langfuse, MinIO и т.д. — пути задаются в `main.env` (`PROMETHEUS_DATA_DIR`, `LOKI_DATA_DIR`, `LANGFUSE_*_DATA_DIR`, …), по умолчанию подкаталоги **`./data/monitoring/...`**. |
| **`bench/`** | Результаты **UI/API** и `scripts/bench_*.py`: **`data/bench/results/<engine>/<timestamp>/`**. В git — [`.gitkeep`](bench/.gitkeep). **slgpu-web** делает `chown` на **`data/bench`** (`web/docker-entrypoint.sh`). |

Каталоги `./data/...` создаются при **`./slgpu web up`** / `slgpu_ensure_data_dirs` (`scripts/_lib.sh`). Права на тома мониторинга — UI «Стек мониторинга» → «Чинить права» (job `native.monitoring.fix-perms`).

Абсолютные пути в `main.env` (например отдельный диск `/mnt/models`) допустимы и перекрывают defaults.
