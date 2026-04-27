#!/bin/sh
# Идемпотентно создаёт бакеты S3 в MinIO для Langfuse (events/media). См. docker-compose: minio-bucket-init.
set -e
if [ -z "${MINIO_ROOT_USER:-}" ] || [ -z "${MINIO_ROOT_PASSWORD:-}" ]; then
  echo "minio-bucket-init: MINIO_ROOT_USER and MINIO_ROOT_PASSWORD must be set (см. compose / main.env)" >&2
  exit 1
fi
: "${BUCKET_EVENT:=langfuse}"
: "${BUCKET_MEDIA:=langfuse}"
mc alias set s3 "http://minio:9000" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"
for b in $(printf '%s\n' "$BUCKET_EVENT" "$BUCKET_MEDIA" | sort -u); do
  mc mb --ignore-existing "s3/${b}"
  echo "minio-bucket-init: бакет ${b} готов"
done
