#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
mkdir -p "$STATE/config"
cat > "$STATE/config/deployment.env" <<EOF
CONFIG_VERSION=1
DATABASE_MODE=postgresql-local
PUBLIC_HOSTNAME=secure.example.test
HTTP_PORT=8080
HTTPS_PORT=8443
HTTPS_MODE=custom
BACKEND_IMAGE=registry.example/backend:v7
WEB_IMAGE=registry.example/web:v7
EOF

export WHO_COULD_STATE_DIR=$STATE
STATE_DIR=$STATE
SCRIPT_DIR=$ROOT
ACTION=static-test
CONFIG_FILE="$STATE/config/deployment.env"
TEMP_FILES=()
valid_key() { [[ "$1" =~ ^[A-Z][A-Z0-9_]*$ ]]; }
valid_value() { [[ "$1" != *$'\n'* && "$1" != *$'\r'* ]]; }
validate_port() { [[ "$1" =~ ^[0-9]+$ ]] && ((10#$1 >= 1 && 10#$1 <= 65535)); }
die() { echo "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }
cfg() { sed -n "s/^$1=//p" "$CONFIG_FILE" | head -1; }
dc() { [[ "$*" == 'ps -q web' ]] && printf 'mock-web-container\n'; }
# The following globals are the documented interface consumed by the sourced
# host-security module.
# shellcheck source=deploy/security/host_security.sh
source "$ROOT/deploy/security/host_security.sh"
security_migrate_config_v1_to_v2 "$CONFIG_FILE"
test "$(cfg CONFIG_VERSION)" = 2
test "$(cfg DATABASE_MODE)" = postgresql-local
test "$(cfg PUBLIC_HOSTNAME)" = secure.example.test
test "$(cfg HTTP_PORT)" = 8080
test "$(cfg HTTPS_PORT)" = 8443
test "$(cfg HTTPS_MODE)" = custom
test "$(cfg BACKEND_IMAGE)" = registry.example/backend:v7
test "$(cfg WEB_IMAGE)" = registry.example/web:v7
test "$(cfg HOST_SECURITY_ENABLED)" = false
test "$(cfg CROWDSEC_ENABLED)" = false
test "$(cfg HOST_FIREWALL_ENABLED)" = false
test "$(cfg SSH_PORT)" = 22
before=$(sha256sum "$CONFIG_FILE")
security_migrate_config_v1_to_v2 "$CONFIG_FILE"
test "$before" = "$(sha256sum "$CONFIG_FILE")"

# A preexisting engine, bouncer and exact local override survive managed
# removal. Only namespaced acquisitions are removed.
MOCK="$STATE/mock-bin"; mkdir -p "$MOCK" "$STATE/acquis" "$STATE/bouncers" "$STATE/state/security"
cat > "$MOCK/cscli" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${MOCK_LOG:?}"
if [[ "$*" == 'bouncers list -o raw' ]]; then printf 'crowdsec-firewall-bouncer valid\n'; fi
EOF
cat > "$MOCK/systemctl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${SYSTEMCTL_LOG:?}"
exit 0
EOF
cat > "$MOCK/ufw" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${UFW_LOG:?}"
if [[ "$1" == status ]]; then
  printf 'Status: active\n'
  printf '22/tcp ALLOW IN 203.0.113.4 # restricted operator SSH\n'
fi
EOF
cat > "$MOCK/iptables" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == '-nL DOCKER-USER' || "$*" == '-w -nL DOCKER-USER' ]]; then printf '%s\n' "$*" >> "${IPTABLES_LOG:?}"; exit 0; fi
if [[ "$*" == '-w -S DOCKER-USER' ]]; then
  [[ "${MOCK_DOCKER_RULE:-present}" == present ]] && printf '%s\n' '-A DOCKER-USER -m set --match-set crowdsec-blacklists src -j DROP'
  exit 0
fi
exit 1
EOF
cat > "$MOCK/ip6tables" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == '-w -nL DOCKER-USER' ]]; then printf '%s\n' "$*" >> "${IP6TABLES_LOG:?}"; [[ "${MOCK_IPV6_RULE:-present}" == present ]]; exit; fi
if [[ "$*" == '-w -S DOCKER-USER' ]]; then
  [[ "${MOCK_IPV6_RULE:-present}" == present ]] && printf '%s\n' '-A DOCKER-USER -m set --match-set crowdsec6-blacklists src -j DROP'
  exit 0
fi
exit 1
EOF
cat > "$MOCK/docker" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == ps ]]; then printf 'mock-web-container\n'; exit 0; fi
if [[ "$1" == inspect ]]; then printf '::\n'; exit 0; fi
exit 1
EOF
cat > "$MOCK/ipset" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == list && "$2" == crowdsec-blacklists ]]; then
  printf 'Name: crowdsec-blacklists\nType: hash:ip\nHeader: family inet hashsize 1024\n'
  exit 0
fi
if [[ "$1" == list && "$2" == crowdsec6-blacklists ]]; then
  printf 'Name: crowdsec6-blacklists\nType: hash:ip\nHeader: family inet6 hashsize 1024\n'
  exit 0
fi
exit 1
EOF
chmod +x "$MOCK/cscli" "$MOCK/systemctl" "$MOCK/ufw" "$MOCK/iptables" "$MOCK/ip6tables" "$MOCK/ipset" "$MOCK/docker"
export MOCK_LOG="$STATE/cscli.log" SYSTEMCTL_LOG="$STATE/systemctl.log" UFW_LOG="$STATE/ufw.log" IPTABLES_LOG="$STATE/iptables.log" IP6TABLES_LOG="$STATE/ip6tables.log" PATH="$MOCK:$PATH"
touch "$MOCK_LOG" "$SYSTEMCTL_LOG" "$UFW_LOG" "$IPTABLES_LOG" "$IP6TABLES_LOG"
CROWDSEC_ACQUIS_DIR="$STATE/acquis"; CROWDSEC_BOUNCER_DIR="$STATE/bouncers"
BOUNCER_LOCAL_OVERRIDE="$CROWDSEC_BOUNCER_DIR/crowdsec-firewall-bouncer.yaml.local"
BOUNCER_DROPIN_DIR="$STATE/systemd/crowdsec-firewall-bouncer.service.d"
BOUNCER_DROPIN="$BOUNCER_DROPIN_DIR/who-could-docker.conf"
DOCKER_WAIT_HELPER="$STATE/lib/who-could/wait-docker-user"
CROWDSEC_APT_PREFERENCE="$STATE/who-could-crowdsec.pref"
touch "$CROWDSEC_ACQUIS_DIR/who-could-nginx.yaml" "$CROWDSEC_ACQUIS_DIR/who-could-host.yaml"
printf 'operator: exact config\n' > "$BOUNCER_LOCAL_OVERRIDE"
printf 'CROWDSEC_PREEXISTING=true\nBOUNCER_PREEXISTING=true\nBOUNCER_LOCAL_OVERRIDE_PREEXISTING=true\nBOUNCER_DROPIN_PREEXISTING=true\nAPT_PREFERENCE_PREEXISTING=false\n' > "$STATE/state/security/install-state"
if (security_preflight 2>/dev/null); then
  echo 'preexisting bouncer override conflict was not rejected' >&2
  exit 1
fi
test "$(cat "$BOUNCER_LOCAL_OVERRIDE")" = 'operator: exact config'
security_remove
if [[ -e "$CROWDSEC_ACQUIS_DIR/who-could-nginx.yaml" ]]; then echo 'managed acquisition was not removed' >&2; exit 1; fi
test "$(cat "$BOUNCER_LOCAL_OVERRIDE")" = 'operator: exact config'
if grep -q 'bouncers delete' "$MOCK_LOG"; then echo 'preexisting bouncer registration was deleted' >&2; exit 1; fi
if grep -q 'disable.*crowdsec-firewall-bouncer' "$SYSTEMCTL_LOG"; then echo 'preexisting bouncer service was disabled' >&2; exit 1; fi

# Ownership is immutable across repeat installs and clean-host removal owns
# only the local override/bouncer that Who could originally created.
printf 'CROWDSEC_PREEXISTING=false\nBOUNCER_PREEXISTING=false\nBOUNCER_LOCAL_OVERRIDE_PREEXISTING=false\nBOUNCER_DROPIN_PREEXISTING=false\nAPT_PREFERENCE_PREEXISTING=false\n' > "$STATE/state/security/install-state"
ownership_before=$(sha256sum "$STATE/state/security/install-state")
security_initialize_ownership
test "$ownership_before" = "$(sha256sum "$STATE/state/security/install-state")"
printf 'managed\n' > "$BOUNCER_LOCAL_OVERRIDE"
security_install_bouncer_dropin
grep -Fqx 'Wants=docker.service' "$BOUNCER_DROPIN"
grep -Fqx 'After=docker.service' "$BOUNCER_DROPIN"
grep -Fqx "ExecStartPre=$DOCKER_WAIT_HELPER" "$BOUNCER_DROPIN"
security_remove
if [[ -e "$BOUNCER_LOCAL_OVERRIDE" ]]; then echo 'managed bouncer override was not removed' >&2; exit 1; fi
if [[ -e "$BOUNCER_DROPIN" ]]; then echo 'managed systemd drop-in was not removed' >&2; exit 1; fi
if [[ -e "$DOCKER_WAIT_HELPER" ]]; then echo 'managed pre-start helper was not removed' >&2; exit 1; fi
grep -q 'disable --now crowdsec-firewall-bouncer' "$SYSTEMCTL_LOG"
if grep -q 'bouncers delete' "$MOCK_LOG"; then echo 'retained package registration was deleted' >&2; exit 1; fi

# Retained package registration supports repeated install and remove->install.
cat > "$MOCK/apt-get" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$MOCK/apt-get"
security_install_bouncer iptables
security_install_bouncer iptables
security_remove
security_install_bouncer iptables
grep -q 'bouncers list -o raw' "$MOCK_LOG"
grep -q 'enable --now crowdsec-firewall-bouncer' "$SYSTEMCTL_LOG"
if grep -q 'bouncers delete' "$MOCK_LOG"; then echo 'reinstall path deleted the retained registration' >&2; exit 1; fi

# Boot helper waits for IPv6 only when the managed v6 chain is configured.
printf 'iptables_v6_chains:\n  - INPUT\n  - DOCKER-USER\n' > "$BOUNCER_LOCAL_OVERRIDE"
: > "$IPTABLES_LOG"; : > "$IP6TABLES_LOG"
WHO_COULD_BOUNCER_CONFIG="$BOUNCER_LOCAL_OVERRIDE" "$ROOT/deploy/security/wait-docker-user.sh"
grep -q -- '-w -nL DOCKER-USER' "$IPTABLES_LOG"
grep -q -- '-w -nL DOCKER-USER' "$IP6TABLES_LOG"
printf 'iptables_v6_chains:\n  - INPUT\n' > "$BOUNCER_LOCAL_OVERRIDE"
: > "$IPTABLES_LOG"; : > "$IP6TABLES_LOG"
WHO_COULD_BOUNCER_CONFIG="$BOUNCER_LOCAL_OVERRIDE" "$ROOT/deploy/security/wait-docker-user.sh"
grep -q -- '-w -nL DOCKER-USER' "$IPTABLES_LOG"
if [[ -s "$IP6TABLES_LOG" ]]; then echo 'boot helper waited for unconfigured IPv6' >&2; exit 1; fi

# Active UFW with a source-restricted SSH rule must never gain ALLOW Anywhere.
: > "$UFW_LOG"
NON_INTERACTIVE=true
security_configure_ufw
if grep -Eq '^allow 22/tcp' "$UFW_LOG"; then echo 'active UFW SSH policy was broadened' >&2; exit 1; fi
grep -q '^allow 8080/tcp comment Who could HTTP$' "$UFW_LOG"
grep -q '^allow 8443/tcp comment Who could HTTPS$' "$UFW_LOG"
security_ufw_remove_managed
grep -q '^--force delete allow 8080/tcp comment Who could HTTP$' "$UFW_LOG"
grep -q '^--force delete allow 8443/tcp comment Who could HTTPS$' "$UFW_LOG"
if grep -Eq 'delete allow 22/tcp' "$UFW_LOG"; then echo 'SSH safety rule was deleted' >&2; exit 1; fi

# Docker integration is not inferred from chain existence: it requires a
# DOCKER-USER match-set rule referencing a real CrowdSec ipset.
printf 'iptables\n' > "$STATE/state/security/firewall_backend"
MOCK_DOCKER_RULE=present security_docker_ipv4_integration_ok
if MOCK_DOCKER_RULE=missing security_docker_ipv4_integration_ok; then
  echo 'bare DOCKER-USER chain was incorrectly accepted' >&2
  exit 1
fi
test "$(MOCK_IPV6_RULE=present security_docker_ipv6_state)" = OK
test "$(MOCK_IPV6_RULE=missing security_docker_ipv6_state)" = FAIL

grep -q '^source: docker$' "$ROOT/deploy/security/crowdsec/who-could-nginx.yaml"
grep -q 'type: nginx' "$ROOT/deploy/security/crowdsec/who-could-nginx.yaml"
if grep -q "'+_SYSTEMD_UNIT" "$ROOT/deploy/security/crowdsec/who-could-host-journal.yaml"; then echo 'invalid journal conjunction found' >&2; exit 1; fi
grep -Fq 'cfg HOST_SECURITY_ENABLED 2>/dev/null || echo false' "$ROOT/server.sh"
grep -Fq "deadline=\$((SECONDS + 30))" "$ROOT/deploy/security/host_security.sh"
grep -Fq 'iptables_v4_chains:' "$ROOT/deploy/security/host_security.sh"
grep -Fq 'iptables_v6_chains:' "$ROOT/deploy/security/host_security.sh"
grep -Eq '^192\.0\.2\.|^198\.51\.100\.' "$ROOT/deploy/security/fixtures/nginx-access.log"
if git -C "$ROOT" grep -En '(api[_-]?key|password)[=:][[:space:]]*[A-Za-z0-9+/]{24,}' -- ':!frontend/package-lock.json'; then echo 'possible tracked secret found' >&2; exit 1; fi

# Destructive firewall operations are forbidden in the managed implementation.
if grep -E 'iptables[[:space:]]+-F|nft[[:space:]]+flush[[:space:]]+ruleset|ufw[[:space:]]+(reset|disable)|chmod[[:space:]]+666.*docker.sock' "$ROOT/server.sh" "$ROOT/deploy/security/host_security.sh"; then
  echo 'destructive firewall operation found' >&2
  exit 1
fi
echo 'Host security static checks: PASS'
