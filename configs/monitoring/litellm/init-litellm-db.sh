#!/bin/sh
# Однократно (идемпотентно) создаёт БД litellm в сервисе postgres (Langfuse). См. docker-compose: litellm-pg-init.
set -e
: "${POSTGRES_USER:=postgres}"
: "${LITELLM_DB_NAME:=litellm}"
export PGUSER="${POSTGRES_USER}"
export PGPASSWORD="${POSTGRES_PASSWORD:-postgres}"
echo "init-litellm-db: ждём postgres…"
i=0
while ! psql -h postgres -d postgres -c "SELECT 1" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -gt 120 ]; then
    echo "init-litellm-db: таймаут" >&2
    exit 1
  fi
  sleep 1
done
exists=$(psql -h postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${LITELLM_DB_NAME}'" | tr -d '[:space:]')
if [ "$exists" = "1" ]; then
  echo "init-litellm-db: БД ${LITELLM_DB_NAME} уже есть"
  exit 0
fi
psql -h postgres -d postgres -c "CREATE DATABASE ${LITELLM_DB_NAME}"
echo "init-litellm-db: создана БД ${LITELLM_DB_NAME}"
