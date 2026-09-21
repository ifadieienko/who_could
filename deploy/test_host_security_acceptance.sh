#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
FLAG=${1:-}
PHASE=${2:-prepare}
if [[ "$FLAG" != --i-understand-this-modifies-firewall ]]; then
  cat <<EOF
DRY RUN: disposable Ubuntu VM host-security acceptance
Would run: sudo $ROOT/server.sh security-install --non-interactive
Would run: sudo $ROOT/server.sh security-status
Would run: sudo $ROOT/server.sh security-test
Would repeat installation, prepare a reboot marker, and optionally reboot.
After reboot run this script with --i-understand-this-modifies-firewall --post-reboot.
No firewall or CrowdSec state was changed.
Re-run with --i-understand-this-modifies-firewall on a disposable VM only.
EOF
  exit 0
fi
((EUID == 0)) || { echo 'Run acceptance as root.' >&2; exit 1; }
[[ -f /etc/os-release ]] && . /etc/os-release
[[ "${ID:-}" == ubuntu ]] || { echo 'Acceptance requires a disposable Ubuntu VM.' >&2; exit 1; }
MARKER=/opt/who-could/state/security/acceptance-awaiting-reboot
decisions_clean() {
  if cscli decisions list -o raw | grep -Eq '192\.0\.2\.1|2001:db8::1'; then
    echo 'TEST-NET decision cleanup failed' >&2
    return 1
  fi
}
if [[ "$PHASE" == --post-reboot ]]; then
  [[ -f "$MARKER" ]] || { echo 'Pre-reboot acceptance phase was not completed.' >&2; exit 1; }
  for _ in {1..60}; do
    if systemctl is-active --quiet docker crowdsec crowdsec-firewall-bouncer; then break; fi
    sleep 1
  done
  systemctl is-active --quiet docker crowdsec crowdsec-firewall-bouncer
  "$ROOT/server.sh" security-status | tee /tmp/who-could-security-status.txt
  grep -Fq 'Docker IPv4 integration   OK' /tmp/who-could-security-status.txt
  if grep -Fq 'Docker IPv6 integration   FAIL' /tmp/who-could-security-status.txt; then
    echo 'IPv6 is exposed without verified post-reboot remediation' >&2
    exit 1
  fi
  grep -Eq '^Docker IPv6 integration[[:space:]]+(OK|DISABLED)$' /tmp/who-could-security-status.txt
  "$ROOT/server.sh" security-test
  decisions_clean
  "$ROOT/server.sh" security-remove
  rm -f "$MARKER" /tmp/who-could-security-status.txt
  echo 'Disposable VM reboot host-security acceptance: PASS'
  exit 0
fi
[[ "$PHASE" == prepare || "$PHASE" == --reboot-now ]] || { echo 'Use prepare, --reboot-now, or --post-reboot.' >&2; exit 2; }
"$ROOT/server.sh" security-install --non-interactive
"$ROOT/server.sh" security-status
"$ROOT/server.sh" security-test
decisions_clean
"$ROOT/server.sh" security-install --non-interactive
"$ROOT/server.sh" security-test
decisions_clean
install -d -m 0700 "$(dirname "$MARKER")"
date -u +%FT%TZ > "$MARKER"
if [[ "$PHASE" == --reboot-now ]]; then systemctl reboot; fi
echo 'Pre-reboot acceptance: PASS. Reboot, then run with --post-reboot.'
