#!/bin/sh
# shellcheck disable=SC2039
# Генерация /tmp/litellm.config.yaml и запуск litellm (образ BerriAI).
set -e
export LLM_API_PORT="${LLM_API_PORT:-8111}"
MID="${LITELLM_LLM_ID:-}"
if [ -z "${MID}" ] || [ "${MID}" = "" ]; then
  echo "litellm: LITELLM_LLM_ID пуст в main.env — подставляю плейсхолдер «unknown-model»." >&2
  echo "  Задайте LITELLM_LLM_ID = id из curl http://127.0.0.1:\${LLM_API_PORT}/v1/models" >&2
  MID="unknown-model"
fi
export LITELLM_LLM_ID="${MID}"
# host.docker.internal + extra_hosts (как у Prometheus) — vLLM на хосте
python3 - <<'PY'
import os
from pathlib import Path
mid = os.environ.get("LITELLM_LLM_ID", "unknown-model")
p = int(os.environ.get("LLM_API_PORT", "8111"))
base = f"http://host.docker.internal:{p}/v1"
src = Path("/etc/slgpu/litellm.config.yaml.template").read_text()
src = src.replace("__LITELLM_LLM_ID__", mid)
src = src.replace("__LITELLM_VLLM_API_BASE__", base)
Path("/tmp/litellm.config.yaml").write_text(src)
PY
if [ -z "${LANGFUSE_SECRET_KEY:-}" ] || [ -z "${LANGFUSE_PUBLIC_KEY:-}" ]; then
  unset LANGFUSE_SECRET_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_HOST
fi
exec litellm --config /tmp/litellm.config.yaml --host 0.0.0.0 --port 4000 "$@"
