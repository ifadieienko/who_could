#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
PYTHON=.venv/bin/python; [ -x "$PYTHON" ] || PYTHON=python3
if [ "${1:-}" = "--reset" ]; then
  "$PYTHON" -m app.database --reset
else
  "$PYTHON" -m alembic upgrade head
fi
