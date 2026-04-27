#!/bin/sh
# Однократно (идемпотентно) создаёт БД litellm в сервисе postgres (Langfuse). См. docker-compose: litellm-pg-init.
set -e
: "${POSTGRES_USER:=postgres}"
: "${LITELLM_DB_NAME:=litellm}"
if [ -z "${POSTGRES_SERVICE_NAME:-}" ] || [ -z "${POSTGRES_INTERNAL_PORT:-}" ]; then
  echo "init-litellm-db: POSTGRES_SERVICE_NAME / POSTGRES_INTERNAL_PORT must be set (compose env)" >&2
  exit 1
fi
case "$LITELLM_DB_NAME" in
  ''|*[![:alnum:]_]*)
    echo "init-litellm-db: LITELLM_DB_NAME must be a simple identifier [A-Za-z0-9_]" >&2
    exit 1
    ;;
esac
export PGUSER="${POSTGRES_USER}"
export PGPASSWORD="${POSTGRES_PASSWORD:-postgres}"
echo "init-litellm-db: ждём ${POSTGRES_SERVICE_NAME}:${POSTGRES_INTERNAL_PORT}…"
i=0
while ! psql -h "${POSTGRES_SERVICE_NAME}" -p "${POSTGRES_INTERNAL_PORT}" -d postgres -c "SELECT 1" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 120 ]; then
    echo "init-litellm-db: таймаут" >&2
    exit 1
  fi
  sleep 1
done
exists=$(psql -h "${POSTGRES_SERVICE_NAME}" -p "${POSTGRES_INTERNAL_PORT}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${LITELLM_DB_NAME}'" | tr -d '[:space:]')
if [ "$exists" = "1" ]; then
  echo "init-litellm-db: БД ${LITELLM_DB_NAME} уже есть"
  exit 0
fi
psql -h "${POSTGRES_SERVICE_NAME}" -p "${POSTGRES_INTERNAL_PORT}" -d postgres -c "CREATE DATABASE ${LITELLM_DB_NAME}"
echo "init-litellm-db: создана БД ${LITELLM_DB_NAME}"
