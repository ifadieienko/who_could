#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
[ -x .venv/bin/uvicorn ] || { echo 'Сначала запустите: python3 install.py'; exit 1; }
exec .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
