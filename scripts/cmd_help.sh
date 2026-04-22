#!/usr/bin/env bash
cat <<'EOF'
slgpu — стенд vLLM vs SGLang в Docker (Linux VM).

Использование:
  ./slgpu <команда> [аргументы]

Команды:
  prepare [1–6]        Подготовка хоста (Docker, NVIDIA toolkit, каталог моделей, …)
  pull <HF_ID|preset>    Скачать модель; HF id (org/name) создаёт configs/models/<slug>.env
  up <vllm|sglang> -m <preset> [-p <порт API на хосте, по умолчанию 8111>]
  down [--all]          Остановить LLM (--all — весь compose)
  restart -m <preset>   Перезапуск текущего running-движка с новым пресетом
   bench <vllm|sglang> -m <preset>
   load <vllm|sglang> -m <preset> [опции]
                         Длительный нагрузочный тест (200-300 пользователей, 15-20 мин)
   ab -m <preset>        Полный A/B: vllm→bench→sglang→bench→compare
   compare               Свести последние summary.json → bench/report.md
   logs [SERVICE]        Логи сервиса (по умолчанию — активный vllm|sglang)
   status                docker compose ps, /v1/models, nvidia-smi
   config <vllm|sglang> -m <preset>
   help                  Эта справка

Примеры:
  ./slgpu pull Qwen/Qwen3.6-35B-A3B
  ./slgpu up vllm -m qwen3.6-35b-a3b
  ./slgpu bench vllm -m qwen3.6-35b-a3b
  ./slgpu ab -m qwen3.6-35b-a3b

Документация: README.md
EOF
