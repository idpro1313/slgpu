# Локальные данные на сервере

Каталог **`data/`** в корне репозитория — соглашение по умолчанию для **персистентных path** на хосте (не коммитятся в git, кроме этого README и `.gitkeep`).

| Подкаталог | Назначение |
|------------|------------|
| **`models/`** | Веса Hugging Face (`MODELS_DIR=./data/models` в `main.env`) — то же дерево, что монтируется в vLLM/SGLang и в `slgpu-web`. |
| **`presets/`** | Файлы пресетов `*.env` (`PRESETS_DIR=./data/presets` в `main.env`); web UI и `./slgpu` читают и пишут сюда. Каталог `*.env` **не в git** (чтобы `git pull` на сервере не конфликтовал с локальными правками). Эталонные примеры — **`examples/presets/`** (`cp examples/presets/*.env data/presets/` на чистом клоне). Формат полей: `configs/models/README.md`. |
| **`web/`** | SQLite и рабочие файлы web UI (`WEB_DATA_DIR=./data/web`). Подкаталог **`web/secrets/`** — сгенерированный для compose **`langfuse-litellm.env`** (ключи Langfuse для LiteLLM OTEL), не путать с read-only `configs/secrets/` на хосте. |
| **`monitoring/`** | TSDB, Loki, Grafana, Langfuse, MinIO и т.д. — пути задаются в `main.env` (`PROMETHEUS_DATA_DIR`, `LOKI_DATA_DIR`, `LANGFUSE_*_DATA_DIR`, …), по умолчанию подкаталоги **`./data/monitoring/...`**. |
| **`bench/`** | Результаты `./slgpu bench` / `./slgpu load` и прогонов из web UI: **`data/bench/results/<engine>/<timestamp>/`** (`summary.json`, для load — ещё `time_series.csv`, `users.jsonl`). В git — только маркер каталога [`.gitkeep`](bench/.gitkeep). Контейнер **slgpu-web** при старте делает `chown` на **`data/bench`**, чтобы запись шла от uid 10001 (см. `web/docker-entrypoint.sh`). |

Каталоги с относительными путями `./data/...` создаются скриптами при `up` там, где это уместно (`slgpu_ensure_data_dirs` в `scripts/_lib.sh`). Перед первым **`./slgpu monitoring up`** по-прежнему рекомендуется **`sudo ./slgpu monitoring fix-perms`** для владельцев uid:gid из образов.

Абсолютные пути в `main.env` (например отдельный диск `/mnt/models`) допустимы и перекрывают defaults.
