#!/bin/sh
# Идемпотентно создаёт бакеты S3 в MinIO для Langfuse (events/media). См. docker-compose: minio-bucket-init.
set -e
: "${MINIO_ROOT_USER:=minio}"
: "${MINIO_ROOT_PASSWORD:=miniosecret}"
: "${BUCKET_EVENT:=langfuse}"
: "${BUCKET_MEDIA:=langfuse}"
mc alias set s3 "http://minio:9000" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"
for b in $(printf '%s\n' "$BUCKET_EVENT" "$BUCKET_MEDIA" | sort -u); do
  mc mb --ignore-existing "s3/${b}"
  echo "minio-bucket-init: бакет ${b} готов"
done
