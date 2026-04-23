#!/usr/bin/env bash
# Выставить владельца GRAFANA_DATA_DIR и PROMETHEUS_DATA_DIR по uid:gid внутри
# grafana/grafana и prom/prometheus (bind mount иначе: GF_PATHS_DATA not writable, queries.active, …)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

# shellcheck disable=SC1091
if [[ -f "${ROOT}/main.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ROOT}/main.env"
  set +a
fi

GDIR="${GRAFANA_DATA_DIR:-/var/lib/slgpu/grafana}"
PDIR="${PROMETHEUS_DATA_DIR:-/var/lib/slgpu/prometheus}"
GIMG="${SLGPU_GRAFANA_IMAGE:-grafana/grafana:latest}"
PIMG="${SLGPU_PROMETHEUS_IMAGE:-prom/prometheus:latest}"

SUDO=()
if [[ "${EUID:-0}" -ne 0 ]]; then
  SUDO=(sudo)
fi

need_docker() {
  if ! command -v docker &>/dev/null; then
    echo "Нужен docker в PATH." >&2
    exit 1
  fi
}

id_from_image() {
  local name="$1" img="$2"
  local u g
  u="$(docker run --rm --entrypoint sh "${img}" -c 'id -u' 2>/dev/null || true)"
  g="$(docker run --rm --entrypoint sh "${img}" -c 'id -g' 2>/dev/null || true)"
  if [[ -z "${u}" || -z "${g}" ]]; then
    echo "Не удалось прочитать uid:gid в образе ${name} (${img}). Проверьте docker pull, сеть, образ." >&2
    exit 1
  fi
  echo "${u} ${g}"
}

need_docker

read -r GU GG <<<"$(id_from_image Grafana "${GIMG}")"
read -r PU PG <<<"$(id_from_image Prometheus "${PIMG}")"

echo "Grafana (${GIMG}): uid=${GU} gid=${GG}  →  ${GDIR}"
echo "Prometheus (${PIMG}): uid=${PU} gid=${PG}  →  ${PDIR}"
"${SUDO[@]}" mkdir -p "${GDIR}" "${PDIR}"
"${SUDO[@]}" chown -R "${GU}:${GG}" "${GDIR}"
"${SUDO[@]}" chown -R "${PU}:${PG}" "${PDIR}"
echo "Готово. Далее: ./slgpu monitoring up  или  ./slgpu monitoring restart"
