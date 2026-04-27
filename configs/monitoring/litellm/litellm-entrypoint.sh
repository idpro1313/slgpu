#!/bin/sh
# shellcheck disable=SC2039
# Копия config.yaml в /tmp (writable); плейсхолдер __LLM_API_PORT__ в репозитории не используется — маршруты в БД / Admin UI.
set -e
cp /etc/slgpu/config.yaml /tmp/litellm.config.yaml
if [ -z "${LANGFUSE_SECRET_KEY:-}" ] || [ -z "${LANGFUSE_PUBLIC_KEY:-}" ]; then
  unset LANGFUSE_SECRET_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_HOST LANGFUSE_OTEL_HOST
fi
# Пустой LITELLM_MASTER_KEY: убрать из окружения. Иначе LiteLLM считает, что мастер-ключ
# «задан» (пустая строка ≠ unset), и отвечает 401 «No api key passed in».
if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
  unset LITELLM_MASTER_KEY
fi
# LITELLM_LOG=DEBUG в env — подробные логи (дублируем --detailed_debug из docs)
_extra=""
if [ "${LITELLM_LOG:-}" = "DEBUG" ] || [ "${LITELLM_LOG:-}" = "debug" ]; then
  _extra="--detailed_debug"
fi
PORT="${LITELLM_PORT:-4000}"
# shellcheck disable=SC2086
exec litellm --config /tmp/litellm.config.yaml --host 0.0.0.0 --port "${PORT}" ${_extra} "$@"
