#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
[ -d node_modules ] || { echo 'Сначала запустите: python3 install.py'; exit 1; }
exec npm run dev
