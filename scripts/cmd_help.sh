#!/usr/bin/env bash
cat <<'EOF'
slgpu — стенд vLLM vs SGLang в Docker (Linux VM).

Использование:
  ./slgpu <команда> [аргументы]

Команды:
  prepare [1–6]        Подготовка хоста (Docker, NVIDIA toolkit, каталог моделей, …)
  pull <HF_ID|preset>   Скачать веса (hf download); пресет не создаётся — см. configs/models/README.md (эталоны: examples/presets/, рабочие: data/presets/)
  up [vllm|sglang] [-m <preset>] [-p <порт>] [--tp <N>]   (без арг. — выбор в TTY)
  monitoring up|down|restart|bootstrap|fix-perms   Мониторинг; bootstrap — повтор init MinIO/LiteLLM DB; fix-perms — chown данных
  web up|down|restart|logs|build|install   Web UI (slgpu-web); install — после up, POST /api/v1/app-config/install
  down [--all]           Остановить vllm/sglang; --all — мониторинг и slgpu-web
  restart -m <preset> [--tp <N>]  Перезапуск running vllm|sglang с новым пресетом
  bench [vllm|sglang] [-m <preset>]
  load [vllm|sglang] [-m <preset>] [опции]
                         Длительный нагрузочный тест (200-300 пользователей, 15-20 мин)
  help                  Эта справка

Вне CLI: `docker compose -f docker/docker-compose.llm.yml logs -f vllm`, проверка API — `curl` на порт vLLM/SGLang; артефакты бенчей — `data/bench/results/<engine>/<timestamp>/`.

Примеры:
  ./slgpu pull Qwen/Qwen3.6-35B-A3B
  ./slgpu monitoring fix-perms
  ./slgpu monitoring up
  ./slgpu web up
  ./slgpu up                       # TTY: выбор vLLM/SGLang, затем пресета
  ./slgpu up vllm -m qwen3.6-35b-a3b
  ./slgpu up sglang -m qwen3-30b-a3b --tp 4
  ./slgpu bench vllm -m qwen3.6-35b-a3b

Документация: README.md
EOF
