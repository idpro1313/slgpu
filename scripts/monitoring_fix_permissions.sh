#!/usr/bin/env bash
# Выставить владельца каталогов данных мониторинга по uid:gid **из образов** (Grafana, Prometheus, Loki;
# Langfuse: Postgres, ClickHouse, MinIO, Redis) — bind mount в main.env, см. LANGFUSE_*_DATA_DIR.
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
LF_PDIR="${LANGFUSE_POSTGRES_DATA_DIR:-/opt/mon/langfuse/postgres}"
LF_CDIR="${LANGFUSE_CLICKHOUSE_DATA_DIR:-/opt/mon/langfuse/clickhouse}"
LF_CLDIR="${LANGFUSE_CLICKHOUSE_LOGS_DIR:-/opt/mon/langfuse/clickhouse-logs}"
LF_MDIR="${LANGFUSE_MINIO_DATA_DIR:-/opt/mon/langfuse/minio}"
LF_RDIR="${LANGFUSE_REDIS_DATA_DIR:-/opt/mon/langfuse/redis}"
GIMG="${SLGPU_GRAFANA_IMAGE:-grafana/grafana:latest}"
PIMG="${SLGPU_PROMETHEUS_IMAGE:-prom/prometheus:latest}"
LIMG="${SLGPU_LOKI_IMAGE:-grafana/loki:2.9.8}"
PGSQL_IMG="${SLGPU_LANGFUSE_POSTGRES_IMAGE:-postgres:17}"
MINIO_IMG="${SLGPU_MINIO_IMAGE:-minio/minio:latest}"
REDIS_IMG="${SLGPU_LANGFUSE_REDIS_IMAGE:-redis:7}"

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

uid_g_from_image_user() {
  # uid и gid учётки в образе: docker run --entrypoint sh
  local img="$1" user="${2:-}"
  local u g
  u="$(docker run --rm --entrypoint sh "${img}" -c "id -u ${user}" 2>/dev/null || true)"
  g="$(docker run --rm --entrypoint sh "${img}" -c "id -g ${user}" 2>/dev/null || true)"
  if [[ -z "${u}" || -z "${g}" ]]; then
    echo "" ""
    return 1
  fi
  echo "${u} ${g}"
}

read -r GU GG <<<"$(id_from_image Grafana "${GIMG}")"
read -r PU PG <<<"$(id_from_image Prometheus "${PIMG}")"
read -r LU LG <<<"$(loki_id_or_default "${LIMG}")"

# ClickHouse в compose: user 101:101 (образ)
CHU="101"
CHG="101"

# Postgres: пользователь postgres в образе
if read -r PGU PGG <<<"$(uid_g_from_image_user "${PGSQL_IMG}" postgres)" && [[ -n "${PGU}" ]]; then
  : # ok
else
  PGU="999"
  PGG="999"
  echo "Предупреждение: uid postgres в ${PGSQL_IMG} не прочитан, используем ${PGU}:${PGG}." >&2
fi

# Redis: пользователь redis
if read -r RU RG <<<"$(uid_g_from_image_user "${REDIS_IMG}" redis)" && [[ -n "${RU}" ]]; then
  : # ok
else
  RU="999"
  RG="999"
  echo "Предупреждение: uid redis в ${REDIS_IMG} не прочитан, используем ${RU}:${RG}." >&2
fi

# MinIO: часто minio, иначе root — проверяем minio, затем текущий uid
MU=""
MG=""
if read -r MU MG <<<"$(uid_g_from_image_user "${MINIO_IMG}" minio)" && [[ -n "${MU}" ]]; then
  :
else
  MU="1000"
  MG="1000"
  echo "Предупреждение: uid minio в ${MINIO_IMG} не прочитан, используем ${MU}:${MG}." >&2
fi

echo "Grafana (${GIMG}): uid=${GU} gid=${GG}  →  ${GDIR}"
echo "Prometheus (${PIMG}): uid=${PU} gid=${PG}  →  ${PDIR}"
echo "Loki (${LIMG}): uid=${LU} gid=${LG}  →  ${LDIR}"
echo "Promtail (positions, root):  →  ${PTDIR}"
echo "Langfuse Postgres (${PGSQL_IMG}): uid=${PGU} gid=${PGG}  →  ${LF_PDIR}"
echo "Langfuse ClickHouse: uid=${CHU} gid=${CHG}  →  ${LF_CDIR}  и  ${LF_CLDIR}"
echo "Langfuse MinIO (${MINIO_IMG}): uid=${MU} gid=${MG}  →  ${LF_MDIR}"
echo "Langfuse Redis (${REDIS_IMG}): uid=${RU} gid=${RG}  →  ${LF_RDIR}"
"${SUDO[@]}" mkdir -p "${GDIR}" "${PDIR}" "${LDIR}" "${PTDIR}" \
  "${LF_PDIR}" "${LF_CDIR}" "${LF_CLDIR}" "${LF_MDIR}" "${LF_RDIR}"
"${SUDO[@]}" chown -R "${GU}:${GG}" "${GDIR}"
"${SUDO[@]}" chown -R "${PU}:${PG}" "${PDIR}"
"${SUDO[@]}" chown -R "${LU}:${LG}" "${LDIR}"
"${SUDO[@]}" chown -R root:root "${PTDIR}"
"${SUDO[@]}" chown -R "${PGU}:${PGG}" "${LF_PDIR}"
"${SUDO[@]}" chown -R "${CHU}:${CHG}" "${LF_CDIR}" "${LF_CLDIR}"
"${SUDO[@]}" chown -R "${MU}:${MG}" "${LF_MDIR}"
"${SUDO[@]}" chown -R "${RU}:${RG}" "${LF_RDIR}"
echo "Готово. Далее: ./slgpu monitoring up  или  ./slgpu monitoring restart"
