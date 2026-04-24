#!/bin/sh
# shellcheck disable=SC2039
# Подстановка __LLM_API_PORT__ в config.yaml, затем litellm.
set -e
P="${LLM_API_PORT:-8111}"
sed "s/__LLM_API_PORT__/${P}/g" /etc/slgpu/config.yaml > /tmp/litellm.config.yaml
if [ -z "${LANGFUSE_SECRET_KEY:-}" ] || [ -z "${LANGFUSE_PUBLIC_KEY:-}" ]; then
  unset LANGFUSE_SECRET_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_HOST
fi
exec litellm --config /tmp/litellm.config.yaml --host 0.0.0.0 --port 4000 "$@"
