#!/usr/bin/env bash
# Выставить владельца каталогов данных мониторинга по uid:gid **из образов** (Grafana, Prometheus, Loki);
# Promtail: каталог с positions (root, т.к. user: root в compose).
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

GDIR="${GRAFANA_DATA_DIR:-/opt/mon/grafana}"
PDIR="${PROMETHEUS_DATA_DIR:-/opt/mon/prometheus}"
LDIR="${LOKI_DATA_DIR:-/opt/mon/loki}"
PTDIR="${PROMTAIL_DATA_DIR:-/opt/mon/promtail}"
GIMG="${SLGPU_GRAFANA_IMAGE:-grafana/grafana:latest}"
PIMG="${SLGPU_PROMETHEUS_IMAGE:-prom/prometheus:latest}"
LIMG="${SLGPU_LOKI_IMAGE:-grafana/loki:2.9.8}"

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

# Loki (образ иногда без sh) — с fallback на uid, принятый в grafana/loki
loki_id_or_default() {
  local img="$1" u g
  u="$(docker run --rm --entrypoint sh "${img}" -c 'id -u' 2>/dev/null || true)"
  g="$(docker run --rm --entrypoint sh "${img}" -c 'id -g' 2>/dev/null || true)"
  if [[ -n "${u}" && -n "${g}" ]]; then
    echo "${u} ${g}"
  else
    echo "10001 10001"
  fi
}

read -r GU GG <<<"$(id_from_image Grafana "${GIMG}")"
read -r PU PG <<<"$(id_from_image Prometheus "${PIMG}")"
read -r LU LG <<<"$(loki_id_or_default "${LIMG}")"

echo "Grafana (${GIMG}): uid=${GU} gid=${GG}  →  ${GDIR}"
echo "Prometheus (${PIMG}): uid=${PU} gid=${PG}  →  ${PDIR}"
echo "Loki (${LIMG}): uid=${LU} gid=${LG}  →  ${LDIR}"
echo "Promtail (positions, root):  →  ${PTDIR}"
"${SUDO[@]}" mkdir -p "${GDIR}" "${PDIR}" "${LDIR}" "${PTDIR}"
"${SUDO[@]}" chown -R "${GU}:${GG}" "${GDIR}"
"${SUDO[@]}" chown -R "${PU}:${PG}" "${PDIR}"
"${SUDO[@]}" chown -R "${LU}:${LG}" "${LDIR}"
"${SUDO[@]}" chown -R root:root "${PTDIR}"
echo "Готово. Далее: ./slgpu monitoring up  или  ./slgpu monitoring restart"
