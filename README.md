# slgpu — A/B инференс vLLM vs SGLang (4×GPU)

Стенд для сравнения **vLLM** и **SGLang** на одной локальной модели в `/opt/models`. OpenAI-совместимый API:

| Движок | Порт | URL |
|--------|------|-----|
| vLLM   | 8111 | `http://<host>:8111/v1` |
| SGLang | 8222 | `http://<host>:8222/v1` |

Поддерживаются два режима запуска:

- **Последовательный A/B** (по умолчанию): один движок на все 4 GPU, **TP=4**. Максимальная производительность на запрос, движки бенчатся по очереди.
- **Параллельный co-run**: оба движка одновременно, по 2 GPU каждому (**TP=2**). vLLM прибивается к GPU `0,1`, SGLang — к `2,3`. Удобно для стриминговых сравнений «вживую» на одинаковых входах.

Prometheus / Grafana / DCGM работают постоянно в любом режиме.

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
# В .env — только серверное: HF_TOKEN, пути, Grafana/биндинги.
# Модель выбираем ПРЕСЕТОМ: configs/models/<name>.env (или fallback-дефолт в .env).

# Актуальный Hugging Face CLI (команда hf):
#   pip install -U "huggingface_hub[cli]"
./scripts/download-model.sh -m qwen3-30b-a3b

# Инференс + мониторинг (TP=4, все GPU)
./scripts/up.sh vllm  -m qwen3-30b-a3b
./scripts/up.sh sglang -m qwen3-30b-a3b

# Co-run: оба движка параллельно, по 2 GPU каждому (TP=2)
./scripts/up.sh both -m qwen3-30b-a3b

curl -s http://127.0.0.1:8111/v1/models   # vLLM
curl -s http://127.0.0.1:8222/v1/models   # SGLang
```

### Пресеты моделей

Всё, что специфично для **модели** (ID, окно, KV-dtype, reasoning-парсер, TP), живёт в `configs/models/<preset>.env`. В `.env` — только серверные вещи. Переключение между моделями — без правки `.env`.

```bash
ls configs/models/
# qwen3-30b-a3b.env
# qwen3.6-35b-a3b.env
# qwen3-next-80b-thinking.env
# llama-3.1-70b-instruct.env
# deepseek-r1-distill-qwen-32b.env
# gpt-oss-120b.env
# kimi-k2.5.env
# glm-5.1.env
# minimax-m2.7.env
```

Примеры:

```bash
# Скачать и запустить Llama 3.1 70B
./scripts/download-model.sh -m llama-3.1-70b-instruct
./scripts/up.sh vllm -m llama-3.1-70b-instruct

# Сменить модель «на лету» — просто другой пресет
./scripts/up.sh vllm -m qwen3.6-35b-a3b

# Через переменную окружения (удобно в systemd / CI)
MODEL=deepseek-r1-distill-qwen-32b ./scripts/up.sh sglang
```

Добавить свой: `cp configs/models/qwen3-30b-a3b.env configs/models/my-model.env` и отредактировать. Подробнее — [configs/models/README.md](configs/models/README.md).

Если `-m` не задан, скрипты берут `MODEL_ID`/`MAX_MODEL_LEN`/… из `.env` (fallback).

### Co-run подробно

`scripts/up.sh both` под капотом выполняет:

```bash
TP=2 docker compose \
  -f docker-compose.yml \
  -f docker-compose.both.yml \
  --profile vllm --profile sglang up -d
```

Распределение GPU задано в [`docker-compose.both.yml`](docker-compose.both.yml) через `deploy.resources.reservations.devices.device_ids`. Чтобы поменять, например, на `0,2` / `1,3` — отредактируйте этот overlay.

Проверка, что контейнеры видят только свою пару карт:

```bash
docker compose exec vllm nvidia-smi -L
docker compose exec sglang nvidia-smi -L
```

VRAM на карту: ~16.5 GiB веса + KV-кэш; при `MAX_MODEL_LEN=262144` запас по KV остаётся огромным (десятки миллионов токенов совокупно на пару).

## 3. Бенчмарк и сравнение

**A/B (TP=4 по очереди):**

```bash
M=qwen3-30b-a3b
./scripts/up.sh vllm   -m $M && ./scripts/bench.sh vllm   -m $M
./scripts/up.sh sglang -m $M && ./scripts/bench.sh sglang -m $M

python3 scripts/compare.py   # → bench/report.md
```

**Co-run (TP=2 одновременно):**

```bash
M=qwen3-30b-a3b
./scripts/up.sh both -m $M
./scripts/bench.sh vllm   -m $M &
./scripts/bench.sh sglang -m $M &
wait

python3 scripts/compare.py
```

> Внимание: цифры из `both` нельзя сравнивать с TP=4 напрямую — у каждого движка вдвое меньше GPU. Режим полезен для параллельного функционального теста и сравнений при идентичной нагрузке.

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

Переопределение режима и модели:

```bash
sudo systemctl edit slgpu.service
# [Service]
# Environment=SLGPU_MODE=both          # vllm | sglang | both
# Environment=MODEL=qwen3-30b-a3b      # пресет из configs/models/
```

`ExecStop` в юните останавливает только `vllm`/`sglang`, чтобы **Prometheus/Grafana** продолжали работать.

## Thinking-режим Qwen3

Включён по умолчанию: оба движка стартуют с `--reasoning-parser ${REASONING_PARSER:-qwen3}`. Парсер выделяет блок `<think>...</think>` в отдельное поле OpenAI-ответа (`choices[0].message.reasoning_content`), оставляя в `content` только финальный ответ.

Управление per-request — стандартный для Qwen3 chat-template:

```bash
# C thinking (по умолчанию для Qwen3)
curl -s http://<host>:8111/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
        "model": "Qwen/Qwen3-30B-A3B",
        "messages": [{"role":"user","content":"Сколько будет 17*23? Покажи рассуждение."}],
        "chat_template_kwargs": {"enable_thinking": true},
        "max_tokens": 1024
      }' | jq '.choices[0].message'

# Без thinking (быстрее, без <think> блока)
curl -s http://<host>:8111/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
        "model": "Qwen/Qwen3-30B-A3B",
        "messages": [{"role":"user","content":"/no_think Hi!"}],
        "chat_template_kwargs": {"enable_thinking": false},
        "max_tokens": 256
      }'
```

Совместимый OpenAI Python-клиент:

```python
from openai import OpenAI
c = OpenAI(base_url="http://<host>:8111/v1", api_key="dummy")
r = c.chat.completions.create(
    model="Qwen/Qwen3-30B-A3B",
    messages=[{"role":"user","content":"prove sqrt(2) is irrational"}],
    extra_body={"chat_template_kwargs": {"enable_thinking": True}},
)
print("reasoning:", r.choices[0].message.reasoning_content)
print("answer:", r.choices[0].message.content)
```

Изменить парсер (например, `qwen3-thinking` для моделей с суффиксом `-Thinking`, `deepseek_r1` для DeepSeek): задайте `REASONING_PARSER` в `.env` и пересоздайте контейнер.

> Примечание: для **`Qwen3-Next-80B-A3B-Thinking`** в SGLang встречаются известные проблемы выделения reasoning ([sgl-project/sglang#16653](https://github.com/sgl-project/sglang/issues/16653)) — попробуйте `REASONING_PARSER=qwen3-thinking`. У vLLM это работает штатно.

## Устранение неполадок

**vLLM + Qwen3 Next (`qwen3_next`):** `assert self.kv_cache_dtype in {"fp8", "fp8_e4m3"}` / Dynamo при `fp8_e5m2`. В `.env` задайте `KV_CACHE_DTYPE=fp8_e4m3` (или `fp8`), перезапустите контейнер. Дефолт в `docker-compose` и `.env.example` уже `fp8_e4m3`.

**`ContextOverflowError: maximum context length is N`** — сумма `prompt + max_tokens` превышает серверный `--max-model-len`. Поднимите `MAX_MODEL_LEN` в `.env` (по умолчанию `262144` — максимум для Qwen3 Next) и пересоздайте контейнер: `docker compose up -d --force-recreate vllm` (или `sglang`). При OOM уменьшайте окно или `GPU_MEM_UTIL`. В клиенте — уменьшите `max_tokens`. Бенч `scripts/bench.sh` уважает `MAX_MODEL_LEN` из `.env` и сам ужимает `max_tokens` под окно.

## Структура

```
docker-compose.yml          # A/B (TP=4)
docker-compose.both.yml     # overlay для co-run (TP=2, split GPU)
.env.example                # серверные настройки + fallback для модели
configs/
├── vllm/args.env
├── sglang/args.env
└── models/                 # пресеты моделей (MODEL_ID, MAX_MODEL_LEN, ...)
    ├── README.md
    ├── qwen3-30b-a3b.env
    ├── qwen3.6-35b-a3b.env
    ├── qwen3-next-80b-thinking.env
    ├── llama-3.1-70b-instruct.env
    └── deepseek-r1-distill-qwen-32b.env
scripts/
├── _lib.sh                 # общий загрузчик .env + пресета
├── up.sh                   # [-m <preset>]
├── bench.sh                # [-m <preset>]
├── download-model.sh       # [-m <preset>]
└── ...
monitoring/
bench/results/
systemd/
```

## Лицензии образов

Используются публичные образы `vllm/vllm-openai`, `lmsysorg/sglang`, `prom/prometheus`, `grafana/grafana`, `nvidia/dcgm-exporter` — ознакомьтесь с их лицензиями для продакшена.
