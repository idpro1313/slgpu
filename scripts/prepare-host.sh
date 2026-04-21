#!/usr/bin/env bash
# Подготовка хоста по разделу «1. Подготовка хоста» в README.md
# Запуск на Ubuntu/Debian (желательно 22.04/24.04 LTS), от root или через sudo.
#
# Использование:
#   sudo ./scripts/prepare-host.sh          # все шаги 1–6 (где возможно автоматизировать)
#   sudo ./scripts/prepare-host.sh 1       # только п.1: проверка драйвера NVIDIA
#   sudo STEPS=3,4 ./scripts/prepare-host.sh   # только перечисленные шаги (через запятую)
#
# П.1 (драйвер) не ставится автоматически — только проверка и подсказки (установка драйвера
# зависит от ядра/образа и часто требует отдельной процедуры от NVIDIA / дистрибутива).

set -euo pipefail

MIN_DRIVER_MAJOR=560
MODELS_DIR="${MODELS_DIR:-/opt/models}"

if [[ "${EUID:-0}" -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf '\n[%s] %s\n' "$(date -Iseconds)" "$*"; }

die() { printf 'Ошибка: %s\n' "$*" >&2; exit 1; }

want_step() {
  local n="$1"
  if [[ -n "${STEPS:-}" ]]; then
    [[ ",${STEPS}," == *",${n},"* ]] && return 0
    return 1
  fi
  if [[ -n "${ONLY:-}" ]]; then
    [[ "${ONLY}" == "${n}" ]] && return 0
    return 1
  fi
  return 0
}

# Аргумент «1» → только шаг 1; иначе STEPS из env или все шаги
ONLY=""
if [[ "${1:-}" =~ ^[1-6]$ ]]; then
  ONLY="$1"
elif [[ -n "${1:-}" ]]; then
  die "Неизвестный аргумент: $1 (ожидается пусто или цифра 1–6)"
fi

if ! [[ -f /etc/os-release ]]; then
  die "Ожидается Linux с /etc/os-release (Ubuntu/Debian)."
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" && "${ID:-}" != "debian" ]]; then
  log "Предупреждение: скрипт заточен под Ubuntu/Debian (сейчас ID=${ID:-?}). Продолжаем на свой риск."
fi

# --- п.1: драйвер NVIDIA ---
if want_step 1; then
  log "Шаг 1: драйвер NVIDIA (ожидается ≥ ${MIN_DRIVER_MAJOR}, см. README)"
  if ! command -v nvidia-smi &>/dev/null; then
    cat <<EOF >&2
nvidia-smi не найден. Установите драйвер NVIDIA с сайта NVIDIA или из репозитория дистрибутива,
затем перезагрузите сервер при необходимости.

  Ubuntu (проприетарный драйвер из репозитория, пример):
    sudo ubuntu-drivers autoinstall
    # или выбор конкретной ветки через «Software & Updates» → Additional Drivers

  Документация: https://docs.nvidia.com/cuda/cuda-installation-guide-linux/

После установки снова запустите: sudo $0 1
EOF
    exit 1
  fi
  mapfile -t drv_lines < <(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>/dev/null || true)
  [[ "${#drv_lines[@]}" -gt 0 ]] || die "nvidia-smi не вернул версию драйвера"
  ver="${drv_lines[0]// /}"
  major="${ver%%.*}"
  [[ "${major}" =~ ^[0-9]+$ ]] || die "Не удалось разобрать версию драйвера: ${ver}"
  if (( major < MIN_DRIVER_MAJOR )); then
    cat <<EOF >&2
Текущая версия драйвера: ${ver} (major=${major})
Рекомендуется ≥ ${MIN_DRIVER_MAJOR} для Hopper/H200 и FP8 (см. README).

Обновите драйвер вручную, затем повторите: sudo $0 1
EOF
    exit 1
  fi
  log "Драйвер OK: ${ver} (GPU: $(nvidia-smi -L | wc -l) шт.)"
  nvidia-smi | head -n 15 || true
fi

# --- п.2: Docker + Compose v2 + NVIDIA Container Toolkit ---
if want_step 2; then
  log "Шаг 2: Docker Engine, Compose v2, NVIDIA Container Toolkit"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg lsb-release

  if ! command -v docker &>/dev/null; then
    log "Устанавливаю Docker через get.docker.com …"
    curl -fsSL https://get.docker.com | sh
  else
    log "Docker уже установлен: $(docker --version)"
  fi

  if ! docker compose version &>/dev/null; then
    die "docker compose недоступен после установки Docker. Проверьте пакет docker-compose-plugin."
  fi
  log "Compose: $(docker compose version)"

  if ! dpkg -l | grep -q '^ii  nvidia-container-toolkit '; then
    log "Добавляю репозиторий NVIDIA Container Toolkit …"
    install -d /usr/share/keyrings
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
      | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    NV_LIST="https://nvidia.github.io/libnvidia-container/${ID}${VERSION_ID}/libnvidia-container.list"
    set +e
    NV_BODY="$(curl -fsSL "$NV_LIST" 2>/dev/null)"
    NV_EC=$?
    set -e
    if [[ $NV_EC -eq 0 ]] && grep -q '^deb ' <<<"$NV_BODY"; then
      sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' <<<"$NV_BODY" \
        > /etc/apt/sources.list.d/nvidia-container-toolkit.list
    else
      log "Нет репозитория toolkit для ${ID}${VERSION_ID}, пробую ubuntu22.04 …"
      curl -fsSL "https://nvidia.github.io/libnvidia-container/ubuntu22.04/libnvidia-container.list" \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        > /etc/apt/sources.list.d/nvidia-container-toolkit.list
    fi
    apt-get update -qq
    apt-get install -y -qq nvidia-container-toolkit
  else
    log "nvidia-container-toolkit уже установлен."
  fi

  log "Настраиваю Docker runtime для NVIDIA …"
  nvidia-ctk runtime configure --runtime=docker

  # cgroupdriver=systemd (рекомендация README) — аккуратно дописываем daemon.json
  DAEMON_JSON="/etc/docker/daemon.json"
  if command -v python3 &>/dev/null; then
    python3 - "${DAEMON_JSON}" <<'PY'
import json, os, sys

path = sys.argv[1]
data = {}
if os.path.isfile(path):
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = {}
data.setdefault("exec-opts", ["native.cgroupdriver=systemd"])
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
  else
    log "Предупреждение: нет python3 — проверьте вручную exec-opts в ${DAEMON_JSON}"
  fi

  systemctl enable docker
  systemctl restart docker
  log "Проверка GPU внутри контейнера …"
  docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi -L || log "Предупреждение: тестовый контейнер nvidia/cuda не запустился (сеть/образ)."
fi

# --- п.3: persistence mode ---
if want_step 3; then
  log "Шаг 3: nvidia-smi persistence mode"
  if command -v nvidia-smi &>/dev/null; then
    nvidia-smi -pm 1 || log "Предупреждение: nvidia-smi -pm 1 завершился с ошибкой (некоторые образы VM запрещают)."
  else
    log "Пропуск: nvidia-smi нет (сначала шаг 1)."
  fi
fi

# --- п.4: /opt/models ---
if want_step 4; then
  log "Шаг 4: каталог моделей ${MODELS_DIR}"
  install -d -m 0755 "${MODELS_DIR}"
  log "Создано: ${MODELS_DIR} (mode 755). При необходимости: chown для пользователя Docker."
fi

# --- п.5: sysctl + limits ---
if want_step 5; then
  log "Шаг 5: sysctl и limits (nofile)"
  cat >/etc/sysctl.d/99-slgpu.conf <<'EOF'
# slgpu / README п.5
vm.swappiness=10
EOF
  sysctl --system >/dev/null || sysctl -p /etc/sysctl.d/99-slgpu.conf

  cat >/etc/security/limits.d/99-slgpu-nofile.conf <<'EOF'
# slgpu / README п.5
* soft nofile 1048576
* hard nofile 1048576
root soft nofile 1048576
root hard nofile 1048576
EOF
  log "limits: /etc/security/limits.d/99-slgpu-nofile.conf (новый лимит в сессии после перелогина)."
fi

# --- п.6: firewall (только напоминание) ---
if want_step 6; then
  log "Шаг 6: firewall (вручную)"
  cat <<'EOF'
Публично откройте только нужные порты (например LLM API **8111** за reverse-proxy).
Prometheus (9090) и Grafana (3000) в compose привязаны к 127.0.0.1 — снаружи не слушают.

Пример UFW (после настройки политик по умолчанию):
  ufw allow OpenSSH
  ufw allow 8111/tcp   # при необходимости OpenAI API снаружи
  ufw enable

Скрипт не включает UFW автоматически.
EOF
fi

log "Готово. Перезайдите в SSH для применения limits, при смене драйвера — перезагрузка."
