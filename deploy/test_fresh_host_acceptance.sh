#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
FLAG=${1:-}
PHASE=${2:-prepare}
STATE=${WHO_COULD_ACCEPTANCE_STATE_DIR:-/opt/who-could-fresh-host-acceptance}
PRESEED=${WHO_COULD_ACCEPTANCE_PRESEED:-/root/who-could-fresh-host-acceptance.env}
PROJECT=who-could-fresh-host-acceptance
HTTP_PORT=${WHO_COULD_ACCEPTANCE_HTTP_PORT:-18082}
HTTPS_PORT=${WHO_COULD_ACCEPTANCE_HTTPS_PORT:-18445}
DOMAIN=${WHO_COULD_ACCEPTANCE_DOMAIN:-}
EMAIL=${WHO_COULD_ACCEPTANCE_EMAIL:-}
MARKER="$STATE/state/fresh-host-acceptance-awaiting-reboot"

if [[ "$FLAG" != --i-understand-this-modifies-host ]]; then
  cat <<EOF
DRY RUN: disposable Ubuntu fresh-host deployment acceptance
Would test the real server.sh install path, persistent login data, Docker restart
policy across a host reboot, doctor/health, and optional ACME renewal.

Run on a disposable Ubuntu VM only:
  sudo bash deploy/test_fresh_host_acceptance.sh --i-understand-this-modifies-host prepare
  sudo reboot
  sudo bash deploy/test_fresh_host_acceptance.sh --i-understand-this-modifies-host --post-reboot

Or use --reboot-now instead of prepare to reboot automatically.
To include real ACME issuance, set WHO_COULD_ACCEPTANCE_DOMAIN and
WHO_COULD_ACCEPTANCE_EMAIL to a disposable public DNS name pointing at this VM.
That mode uses the real ACME service and ports 80/443, so observe CA rate limits.
No host changes were made by this dry run.
EOF
  exit 0
fi

((EUID == 0)) || { echo 'Run fresh-host acceptance as root.' >&2; exit 1; }
[[ -f /etc/os-release ]] && . /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" =~ ^(22\.04|24\.04|26\.04)$ ]] || {
  echo 'Fresh-host acceptance requires disposable Ubuntu 22.04, 24.04, or 26.04.' >&2
  exit 1
}
[[ "$PHASE" == prepare || "$PHASE" == --reboot-now || "$PHASE" == --post-reboot ]] || {
  echo 'Use prepare, --reboot-now, or --post-reboot.' >&2
  exit 2
}

export WHO_COULD_STATE_DIR=$STATE COMPOSE_PROJECT_NAME=$PROJECT
manager() { "$STATE/current/server.sh" "$@"; }
login_check() {
  local port=$HTTP_PORT
  if [[ -n "$DOMAIN" ]]; then port=80; fi
  curl -fsS -X POST -H 'Content-Type: application/json' \
    --data '{"email":"fresh-host@example.com","password":"safe-password-123"}' \
    "http://127.0.0.1:$port/api/auth/login" -o /dev/null
}

if [[ "$PHASE" == --post-reboot ]]; then
  [[ -f "$MARKER" ]] || { echo 'Pre-reboot acceptance phase was not completed.' >&2; exit 1; }
  for _ in {1..90}; do
    if docker info >/dev/null 2>&1 && manager health >/dev/null 2>&1; then break; fi
    sleep 1
  done
  docker info >/dev/null
  manager health
  login_check
  manager doctor
  if grep -q '^HTTPS_MODE=acme$' "$STATE/config/deployment.env"; then
    manager cert-renew
    manager health
  fi
  rm -f "$MARKER"
  echo 'Disposable VM fresh-install reboot acceptance: PASS'
  echo "Acceptance deployment intentionally remains at $STATE for inspection."
  exit 0
fi

[[ ! -e "$STATE/config/deployment.env" ]] || {
  echo "Acceptance state already exists at $STATE. Remove it on this disposable VM before a new prepare run." >&2
  exit 1
}

if [[ -n "$DOMAIN" ]]; then
  [[ -n "$EMAIL" ]] || { echo 'WHO_COULD_ACCEPTANCE_EMAIL is required with WHO_COULD_ACCEPTANCE_DOMAIN.' >&2; exit 1; }
  HTTP_PORT=80
  HTTPS_PORT=443
  cat > "$PRESEED" <<EOF
DATABASE_MODE=postgresql-local
PUBLIC_HOSTNAME=$DOMAIN
HTTP_PORT=80
HTTPS_PORT=443
HTTPS_MODE=acme
ACME_EMAIL=$EMAIL
ACME_HTTP01_READY=yes
DATABASE_NAME=who_could
DATABASE_USER=who_could
HOST_SECURITY_ENABLED=false
EOF
else
  cat > "$PRESEED" <<EOF
DATABASE_MODE=postgresql-local
PUBLIC_HOSTNAME=localhost
HTTP_PORT=$HTTP_PORT
HTTPS_PORT=$HTTPS_PORT
HTTPS_MODE=disabled
DATABASE_NAME=who_could
DATABASE_USER=who_could
HOST_SECURITY_ENABLED=false
EOF
fi
chmod 0600 "$PRESEED"

"$ROOT/server.sh" install --non-interactive --config "$PRESEED"
manager health

port=$HTTP_PORT
if [[ -n "$DOMAIN" ]]; then port=80; fi
curl -fsS -X POST -H 'Content-Type: application/json' \
  --data '{"name":"Fresh Host","email":"fresh-host@example.com","password":"safe-password-123","city":null,"bio":null,"skills":null}' \
  "http://127.0.0.1:$port/api/auth/register" -o /dev/null
login_check
manager doctor
install -d -m 0750 "$(dirname "$MARKER")"
date -u +%FT%TZ > "$MARKER"

if [[ "$PHASE" == --reboot-now ]]; then
  systemctl reboot
fi

echo 'Pre-reboot fresh-host acceptance: PASS.'
echo 'Reboot this disposable VM, then run the same script with --post-reboot.'