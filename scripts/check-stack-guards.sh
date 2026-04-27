#!/usr/bin/env bash
# Проверки v5.0.0: нет ${VAR:- в docker YAML; нет DEFAULT_STACK в backend.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if rg '\$\{[A-Z_][A-Z0-9_]*:-' docker/ --glob '*.yml' 2>/dev/null | head -1 | grep -q .; then
  echo "FAIL: found \${VAR:-...} in docker/*.yml" >&2
  rg '\$\{[A-Z_][A-Z0-9_]*:-' docker/ --glob '*.yml' >&2
  exit 1
fi
if rg '\bDEFAULT_STACK\b' web/backend/ 2>/dev/null | head -1 | grep -q .; then
  echo "FAIL: DEFAULT_STACK in web/backend" >&2
  exit 1
fi
echo "OK: stack guards"
