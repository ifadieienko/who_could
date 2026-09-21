#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
"$ROOT/scripts/start-database.sh"
"$ROOT/scripts/start-backend.sh" & BACKEND=$!
trap 'kill "$BACKEND" "$FRONTEND" 2>/dev/null || true' EXIT INT TERM
"$ROOT/scripts/start-frontend.sh" & FRONTEND=$!
wait
