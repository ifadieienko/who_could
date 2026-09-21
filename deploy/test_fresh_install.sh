#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STATE=${RUNNER_TEMP:-/tmp}/who-could-fresh-install
PRESEED=${RUNNER_TEMP:-/tmp}/who-could-fresh-install.env
PORT_FILE=${RUNNER_TEMP:-/tmp}/who-could-fresh-install.port
BLOCK_LOG=${RUNNER_TEMP:-/tmp}/who-could-port-blocker.log
REQUESTED_PORT=${WHO_COULD_FRESH_INSTALL_PORT:-0}
PORT=""
export WHO_COULD_STATE_DIR=$STATE COMPOSE_PROJECT_NAME=who-could-ci-fresh-install
BLOCK_PID=""

compose_cleanup() {
  if sudo test -f "$STATE/config/deployment.env"; then
    sudo env DEPLOYMENT_ENV="$STATE/config/deployment.env" \
      docker compose --env-file "$STATE/config/deployment.env" \
      -f "$ROOT/compose.yaml" -f "$ROOT/compose.mariadb.yaml" \
      down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
cleanup() {
  if [[ -n "$BLOCK_PID" ]]; then
    kill "$BLOCK_PID" >/dev/null 2>&1 || true
    wait "$BLOCK_PID" 2>/dev/null || true
  fi
  compose_cleanup
  sudo rm -rf "$STATE" "$PRESEED" "$PORT_FILE" "$BLOCK_LOG"
}
trap cleanup EXIT

port_is_free() {
  python3 - "$PORT" <<'PY'
import socket
import sys

sock = socket.socket()
try:
    sock.bind(("0.0.0.0", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
}

sudo rm -rf "$STATE" "$PRESEED" "$PORT_FILE" "$BLOCK_LOG"

python3 - "$PORT_FILE" "$REQUESTED_PORT" >"$BLOCK_LOG" 2>&1 <<'PY' &
import signal
import socket
import sys

port_file, requested_port = sys.argv[1], int(sys.argv[2])
sock = socket.socket()
sock.bind(("0.0.0.0", requested_port))
sock.listen(1)
with open(port_file, "w", encoding="ascii") as handle:
    handle.write(str(sock.getsockname()[1]))
    handle.flush()
while True:
    signal.pause()
PY
BLOCK_PID=$!

for _ in {1..50}; do
  [[ -s "$PORT_FILE" ]] && break
  if ! kill -0 "$BLOCK_PID" 2>/dev/null; then
    cat "$BLOCK_LOG" >&2 || true
    echo 'Port blocker exited before publishing its port.' >&2
    exit 1
  fi
  sleep 0.1
done
[[ -s "$PORT_FILE" ]] || { echo 'Timed out waiting for the port blocker.' >&2; exit 1; }
PORT=$(cat "$PORT_FILE")
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo 'Port blocker returned an invalid port.' >&2; exit 1; }

cat > "$PRESEED" <<EOF
DATABASE_MODE=mariadb-local
PUBLIC_HOSTNAME=localhost
HTTP_PORT=$PORT
HTTPS_PORT=18444
HTTPS_MODE=disabled
DATABASE_NAME=who_could
DATABASE_USER=who_could
HOST_SECURITY_ENABLED=false
EOF
chmod 0600 "$PRESEED"

# Force a real first-install failure after configuration/secrets are persisted.
# The second invocation must resume that incomplete transaction rather than
# treating a deployment.env file as proof that installation finished.
if sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME \
  "$ROOT/server.sh" install --non-interactive --config "$PRESEED"; then
  echo 'Expected the first fresh install to fail while its HTTP port is occupied.' >&2
  exit 1
fi
sudo test -f "$STATE/config/deployment.env"
sudo test -s "$STATE/secrets/app_secret"
sudo test -s "$STATE/secrets/mariadb_local_password"
sudo test -s "$STATE/secrets/mariadb_root_password"
sudo test ! -s "$STATE/state/last_successful_deployment"

kill "$BLOCK_PID"
wait "$BLOCK_PID" 2>/dev/null || true
BLOCK_PID=""

for _ in {1..50}; do
  port_is_free && break
  sleep 0.1
done
port_is_free || { echo "Port $PORT did not become free after stopping the blocker." >&2; exit 1; }

sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME \
  "$ROOT/server.sh" install --non-interactive --config "$PRESEED"

sudo test -s "$STATE/state/last_successful_deployment"
sudo test -s "$STATE/state/installed_git_sha"
sudo test -L "$STATE/current"
installed_sha=$(sudo cat "$STATE/state/installed_git_sha")
[[ "$installed_sha" =~ ^[0-9a-f]{40}$ ]]
sudo test -d "$STATE/releases/$installed_sha"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$installed_sha" ]]

sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME \
  "$STATE/current/server.sh" health
curl -fsS -X POST -H 'Content-Type: application/json' \
  --data '{"name":"Fresh Install","email":"fresh-install@example.com","password":"safe-password-123","city":null,"bio":null,"skills":null}' \
  "http://127.0.0.1:$PORT/api/auth/register" -o /dev/null

config_hash=$(sudo sha256sum "$STATE/config/deployment.env" | awk '{print $1}')
secret_hash=$(sudo sha256sum "$STATE/secrets/app_secret" | awk '{print $1}')
sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME \
  "$ROOT/server.sh" install --non-interactive --config "$PRESEED"
[[ "$(sudo sha256sum "$STATE/config/deployment.env" | awk '{print $1}')" == "$config_hash" ]]
[[ "$(sudo sha256sum "$STATE/secrets/app_secret" | awk '{print $1}')" == "$secret_hash" ]]

sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME \
  "$STATE/current/server.sh" stop
sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME \
  "$STATE/current/server.sh" start
sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME \
  "$STATE/current/server.sh" health
curl -fsS -X POST -H 'Content-Type: application/json' \
  --data '{"email":"fresh-install@example.com","password":"safe-password-123"}' \
  "http://127.0.0.1:$PORT/api/auth/login" -o /dev/null

echo 'Fresh MariaDB install, interrupted-install resume, idempotence, and restart persistence: PASS'
