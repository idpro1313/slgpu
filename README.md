# slgpu — A/B инференс vLLM vs SGLang (4×GPU, TP=4)

Стенд для сравнения **vLLM** и **SGLang** на одной локальной модели в `/opt/models`, с **tensor parallel = 4** на все GPU. OpenAI-совместимый API:

| Движок | Порт | URL |
|--------|------|-----|
| vLLM   | 8111 | `http://<host>:8111/v1` |
| SGLang | 8222 | `http://<host>:8222/v1` |

Одновременно оба LLM-сервиса не запускаются (каждый занимает все GPU). Prometheus / Grafana / DCGM могут работать постоянно.

## 1. Подготовка хоста (чек-лист)

Выполняется на **Linux-сервере** с NVIDIA (целевая конфигурация: 4×H200, Ubuntu 22.04/24.04).

Автоматизация (Ubuntu/Debian, от **root** или через **sudo**):

```bash
chmod +x scripts/prepare-host.sh
sudo ./scripts/prepare-host.sh        # шаги 1–6, где возможно
sudo ./scripts/prepare-host.sh 1      # только п.1: проверка драйвера NVIDIA
sudo STEPS=2,4 ./scripts/prepare-host.sh   # выборочно (через запятую)
```

Скрипт: [scripts/prepare-host.sh](scripts/prepare-host.sh). Установку самого драйвера (п.1) скрипт **не выполняет** — только проверка версии и подсказки; остальное (Docker, toolkit, каталог, sysctl, limits) ставит/настраивает по возможности.

1. **Драйвер NVIDIA** ≥ 560 (Hopper/H200 + FP8). Проверка: `nvidia-smi`.
2. **Docker Engine** + **Compose v2** + [**NVIDIA Container Toolkit**](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
   - В `/etc/docker/daemon.json` при необходимости: `"default-runtime": "nvidia"`, `"exec-opts": ["native.cgroupdriver=systemd"]`, перезапуск Docker.
3. **Persistence mode** (опционально): `sudo nvidia-smi -pm 1`.
4. **Локальные модели**: каталог **`/opt/models`** (желательно отдельный раздел ext4, `noatime`), права на чтение для пользователя, от которого крутится Docker.
5. **Sysctl** (рекомендации): `vm.swappiness=10`, достаточный `ulimit -n` (например 1048576).
6. **Firewall**: наружу при необходимости только нужные порты; служебные (Prometheus 9090, Grafana 3000) лучше оставить на `127.0.0.1` (см. compose).

Скопируйте репозиторий на сервер (или клонируйте), перейдите в каталог проекта.

```bash
chmod +x scripts/*.sh
# при необходимости: sudo ./scripts/prepare-host.sh
```

## 2. Быстрый старт

```bash
cp .env.example .env
# Отредактируйте .env: HF_TOKEN, MODEL_ID, MODEL_REVISION, MAX_MODEL_LEN и т.д.

# Актуальный Hugging Face CLI (команда hf):
#   pip install -U "huggingface_hub[cli]"
./scripts/download-model.sh

# Только инференс + мониторинг (профиль vllm или sglang)
./scripts/up.sh vllm
# или
./scripts/up.sh sglang

curl -s http://127.0.0.1:8111/v1/models   # vLLM
curl -s http://127.0.0.1:8222/v1/models   # SGLang
```

## 3. Бенчмарк и сравнение

После того как поднят нужный движок:

```bash
./scripts/bench.sh vllm
./scripts/up.sh sglang
./scripts/bench.sh sglang

python3 scripts/compare.py
# Отчёт: bench/report.md
```

Сценарии: concurrency `1, 8, 32, 128` × длины prompt/output из плана; результаты в `bench/results/<engine>/<timestamp>/`.

## 4. Мониторинг

- **Prometheus**: `http://127.0.0.1:9090` (по умолчанию приватный — `PROMETHEUS_BIND=127.0.0.1`).
- **Grafana**: `http://<host>:3000` (по умолчанию доступна снаружи — `GRAFANA_BIND=0.0.0.0`). Логин/пароль: `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` из `.env`. **Перед публичным доступом обязательно смените пароль и при необходимости задайте `GF_SERVER_ROOT_URL`.**
- Если стенд доступен из интернета — закройте порт **3000** firewall’ом и пускайте через reverse-proxy с TLS, либо оставьте `GRAFANA_BIND=127.0.0.1` и ходите по SSH-туннелю: `ssh -L 3000:127.0.0.1:3000 user@host`.
- Метрики vLLM / SGLang: `/metrics` на том же порту, что и API.
- **DCGM exporter**: телеметрия GPU.

Импорт дашбордов вручную в Grafana (опционально): NVIDIA DCGM [ID 12239](https://grafana.com/grafana/dashboards/12239), дашборды vLLM — по поиску в Grafana.com по запросу `vllm`.

Подробности конфигов: [monitoring/README.md](monitoring/README.md).

## 5. Автозапуск (systemd)

Пример юнита: [systemd/slgpu.service](systemd/slgpu.service). Скопируйте проект в `/opt/slgpu` (или поправьте пути), задайте пользователя с правами на Docker.

Переопределение профиля (vllm/sglang):

```bash
sudo systemctl edit slgpu.service
# [Service]
# Environment=SLGPU_PROFILE=sglang
```

`ExecStop` в юните останавливает только `vllm`/`sglang`, чтобы **Prometheus/Grafana** продолжали работать.

## Устранение неполадок

**vLLM + Qwen3 Next (`qwen3_next`):** `assert self.kv_cache_dtype in {"fp8", "fp8_e4m3"}` / Dynamo при `fp8_e5m2`. В `.env` задайте `KV_CACHE_DTYPE=fp8_e4m3` (или `fp8`), перезапустите контейнер. Дефолт в `docker-compose` и `.env.example` уже `fp8_e4m3`.

**`ContextOverflowError: maximum context length is N`** — сумма `prompt + max_tokens` превышает серверный `--max-model-len`. Поднимите `MAX_MODEL_LEN` в `.env` (по умолчанию `262144` — максимум для Qwen3 Next) и пересоздайте контейнер: `docker compose up -d --force-recreate vllm` (или `sglang`). При OOM уменьшайте окно или `GPU_MEM_UTIL`. В клиенте — уменьшите `max_tokens`. Бенч `scripts/bench.sh` уважает `MAX_MODEL_LEN` из `.env` и сам ужимает `max_tokens` под окно.

## Структура

```
docker-compose.yml
.env.example
configs/vllm/args.env
configs/sglang/args.env
scripts/
monitoring/
bench/results/
systemd/
```

## Лицензии образов

Используются публичные образы `vllm/vllm-openai`, `lmsysorg/sglang`, `prom/prometheus`, `grafana/grafana`, `nvidia/dcgm-exporter` — ознакомьтесь с их лицензиями для продакшена.
