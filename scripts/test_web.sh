#!/usr/bin/env bash
# Web stack static checks: backend unit tests + frontend tsc (no dev server).
# Run from repo root on Linux: ./scripts/test_web.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/web/backend" && python -m pytest -q
cd "$ROOT/web/frontend" && npm run typecheck
echo "OK: web backend pytest + frontend tsc"
