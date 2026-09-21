#!/usr/bin/env bash
# Sourced by server.sh. CrowdSec runs on the host; no application container is
# granted the Docker socket or firewall capabilities.

SECURITY_STATE_DIR="$STATE_DIR/state/security"
CROWDSEC_ACQUIS_DIR="${CROWDSEC_ACQUIS_DIR:-/etc/crowdsec/acquis.d}"
CROWDSEC_BOUNCER_DIR="${CROWDSEC_BOUNCER_DIR:-/etc/crowdsec/bouncers}"
TEST_DECISION_IP=192.0.2.1
TEST_DECISION_IPV6=2001:db8::1
BOUNCER_LOCAL_OVERRIDE="$CROWDSEC_BOUNCER_DIR/crowdsec-firewall-bouncer.yaml.local"
UFW_MANAGED_STATE="$SECURITY_STATE_DIR/ufw-managed-rules"
BOUNCER_DROPIN_DIR="${BOUNCER_DROPIN_DIR:-/etc/systemd/system/crowdsec-firewall-bouncer.service.d}"
BOUNCER_DROPIN="$BOUNCER_DROPIN_DIR/who-could-docker.conf"
DOCKER_WAIT_HELPER="${DOCKER_WAIT_HELPER:-/usr/local/lib/who-could/wait-docker-user}"
CROWDSEC_APT_PREFERENCE="${CROWDSEC_APT_PREFERENCE:-/etc/apt/preferences.d/who-could-crowdsec}"

security_bool() { [[ "$1" == true || "$1" == false ]]; }

security_set_config() {
  local key=$1 value=$2 tmp
  valid_key "$key" && valid_value "$value" || die "Unsafe security configuration value"
  tmp=$(mktemp); TEMP_FILES+=("$tmp")
  awk -F= -v key="$key" -v value="$value" '
    BEGIN { found=0 }
    $1 == key { print key "=" value; found=1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$CONFIG_FILE" > "$tmp"
  install -m 0640 "$tmp" "$CONFIG_FILE"
}

security_migrate_config_v1_to_v2() {
  local file=$1 tmp
  [[ "$(sed -n 's/^CONFIG_VERSION=//p' "$file")" == 1 ]] || return 0
  tmp=$(mktemp "${file}.migration.XXXXXX")
  awk '
    /^CONFIG_VERSION=1$/ {
      print "CONFIG_VERSION=2"
      print "HOST_SECURITY_ENABLED=false"
      print "CROWDSEC_ENABLED=false"
      print "HOST_FIREWALL_ENABLED=false"
      print "SSH_PORT=22"
      next
    }
    { print }
  ' "$file" > "$tmp"
  chmod --reference="$file" "$tmp" 2>/dev/null || chmod 0640 "$tmp"
  chown --reference="$file" "$tmp" 2>/dev/null || true
  mv -f "$tmp" "$file"
}

security_require_root() { ((EUID == 0)) || die "Host security commands must run as root (sudo ./server.sh $ACTION)"; }
security_has() { command -v "$1" >/dev/null 2>&1; }
security_service_active() { systemctl is-active --quiet "$1" 2>/dev/null; }

security_firewall_backend() {
  # Docker's experimental native nftables backend has no DOCKER-USER chain.
  if docker info --format '{{json .DriverStatus}}' 2>/dev/null | grep -qi nftables || \
     { [[ -r /etc/docker/daemon.json ]] && grep -Eq '"firewall-backend"[[:space:]]*:[[:space:]]*"nftables"' /etc/docker/daemon.json; }; then
    printf nftables-native
  elif security_has iptables && iptables -nL DOCKER-USER >/dev/null 2>&1; then
    printf iptables
  elif security_has nft && nft list ruleset 2>/dev/null | grep -q 'table inet crowdsec'; then
    printf nftables
  elif [[ -r "$SECURITY_STATE_DIR/firewall_backend" ]]; then
    cat "$SECURITY_STATE_DIR/firewall_backend"
  else
    printf unsupported
  fi
}

security_detect_ssh_port() {
  local port=""
  if security_has sshd; then
    port=$(sshd -T 2>/dev/null | awk '$1=="port" {print $2; exit}')
  fi
  if [[ -z "$port" && -f "$CONFIG_FILE" ]]; then port=$(cfg SSH_PORT 2>/dev/null || true); fi
  [[ -n "$port" ]] || port=22
  validate_port "$port"
  printf '%s' "$port"
}

security_backup_firewall() {
  local stamp out
  install -d -m 0700 "$SECURITY_STATE_DIR"
  [[ -e "$SECURITY_STATE_DIR/firewall_snapshot_created" ]] && return 0
  stamp=$(date -u +%Y%m%dT%H%M%SZ); out="$SECURITY_STATE_DIR/firewall-$stamp"
  install -d -m 0700 "$out"
  security_has ufw && ufw status verbose > "$out/ufw.txt" 2>&1 || true
  security_has iptables-save && iptables-save > "$out/iptables.txt" 2>&1 || true
  security_has nft && nft list ruleset > "$out/nftables.txt" 2>&1 || true
  date -u +%FT%TZ > "$SECURITY_STATE_DIR/firewall_snapshot_created"
}

security_state_value() {
  local key=$1
  sed -n "s/^${key}=//p" "$SECURITY_STATE_DIR/install-state" 2>/dev/null | head -1
}

security_initialize_ownership() {
  local tmp crowdsec_preexisting=false bouncer_preexisting=false override_preexisting=false dropin_preexisting=false apt_preference_preexisting=false
  install -d -m 0700 "$SECURITY_STATE_DIR"
  [[ -f "$SECURITY_STATE_DIR/install-state" ]] && return 0
  if security_has cscli; then crowdsec_preexisting=true; fi
  # ${Status} is dpkg-query syntax and must not be expanded by this shell.
  # shellcheck disable=SC2016
  if dpkg-query -W -f='${Status}' crowdsec-firewall-bouncer-iptables 2>/dev/null | grep -q 'install ok installed'; then bouncer_preexisting=true; fi
  if [[ -e "$BOUNCER_LOCAL_OVERRIDE" ]]; then override_preexisting=true; fi
  if [[ -e "$BOUNCER_DROPIN" || -e "$DOCKER_WAIT_HELPER" ]]; then dropin_preexisting=true; fi
  if [[ -e "$CROWDSEC_APT_PREFERENCE" ]]; then apt_preference_preexisting=true; fi
  tmp=$(mktemp "$SECURITY_STATE_DIR/install-state.XXXXXX")
  printf 'CROWDSEC_PREEXISTING=%s\nBOUNCER_PREEXISTING=%s\nBOUNCER_LOCAL_OVERRIDE_PREEXISTING=%s\nBOUNCER_DROPIN_PREEXISTING=%s\nAPT_PREFERENCE_PREEXISTING=%s\n' \
    "$crowdsec_preexisting" "$bouncer_preexisting" "$override_preexisting" "$dropin_preexisting" "$apt_preference_preexisting" > "$tmp"
  chmod 0600 "$tmp"
  mv "$tmp" "$SECURITY_STATE_DIR/install-state"
}

security_preflight() {
  security_initialize_ownership
  if [[ "$(security_state_value BOUNCER_LOCAL_OVERRIDE_PREEXISTING)" == true ]]; then
    die "Existing $BOUNCER_LOCAL_OVERRIDE is user-managed; resolve the conflict before security installation"
  fi
  if [[ "$(security_state_value BOUNCER_DROPIN_PREEXISTING)" == true ]]; then
    die "Existing Who could-named bouncer boot drop-in/helper is not owned by this installation"
  fi
  if [[ "$(security_state_value APT_PREFERENCE_PREEXISTING)" == true ]]; then
    die "Existing $CROWDSEC_APT_PREFERENCE is not owned by Who could; refusing to replace it"
  fi
  [[ "$(security_firewall_backend)" == iptables ]] || die "A supported Docker iptables/DOCKER-USER topology is required"
  if security_ipv6_exposed && ! security_ipv6_chain_available; then
    die "Docker publishes the application over IPv6 but ip6tables DOCKER-USER remediation is unavailable"
  fi
}

security_candidate_is_official() {
  local candidate=$1
  apt-cache madison crowdsec | awk -F'|' -v candidate="$candidate" '
    { version=$2; source=$3; gsub(/^[[:space:]]+|[[:space:]]+$/, "", version) }
    version == candidate && source ~ /(packagecloud\.io\/crowdsec|packages\.crowdsec\.net)/ { found=1 }
    END { exit !found }
  '
}

security_ensure_official_candidate() {
  local policy candidate
  policy=$(apt-cache policy crowdsec)
  candidate=$(sed -n 's/^[[:space:]]*Candidate:[[:space:]]*//p' <<<"$policy")
  [[ -n "$candidate" && "$candidate" != '(none)' ]] || die "The official repository did not provide a CrowdSec package candidate"
  if ! security_candidate_is_official "$candidate"; then
    cat > "$CROWDSEC_APT_PREFERENCE" <<'EOF'
# Managed by Who could: CrowdSec's Ubuntu Pro/ESM repository priority guidance.
Package: *
Pin: release o=packagecloud.io/crowdsec/crowdsec,a=any,n=any,c=main
Pin-Priority: 1001
EOF
    chmod 0644 "$CROWDSEC_APT_PREFERENCE"
    apt-get update
    policy=$(apt-cache policy crowdsec)
    candidate=$(sed -n 's/^[[:space:]]*Candidate:[[:space:]]*//p' <<<"$policy")
  fi
  [[ -n "$candidate" && "$candidate" != '(none)' ]] && security_candidate_is_official "$candidate" || \
    die "CrowdSec APT candidate is not supplied by the official CrowdSec repository"
}

security_install_crowdsec() {
  local bootstrap
  if [[ "$(security_state_value CROWDSEC_PREEXISTING)" == false ]] && ! security_has cscli; then
    [[ -r /etc/os-release ]] || die "Cannot identify host OS"
    . /etc/os-release
    [[ "${ID:-}" == ubuntu || "${ID:-}" == debian ]] || die "Automatic CrowdSec installation supports Debian/Ubuntu only"
    apt-get update
    apt-get install -y ca-certificates curl gnupg
    bootstrap=$(mktemp); TEMP_FILES+=("$bootstrap")
    # Official CrowdSec repository bootstrap, downloaded first so transport
    # errors cannot be hidden by a curl-to-shell pipeline.
    curl --proto '=https' --tlsv1.2 -fsS https://install.crowdsec.net -o "$bootstrap"
    grep -q 'packagecloud.io/crowdsec' "$bootstrap" || die "Unexpected CrowdSec repository bootstrap content"
    bash "$bootstrap"
    apt-get update
    security_ensure_official_candidate
    DEBIAN_FRONTEND=noninteractive apt-get install -y crowdsec
  fi
  cscli version | sed -n '1{s/^[^0-9]*//;p;q}' > "$SECURITY_STATE_DIR/crowdsec_version"
  [[ -s "$SECURITY_STATE_DIR/crowdsec_version" ]] || cscli version > "$SECURITY_STATE_DIR/crowdsec_version"
  chmod 0600 "$SECURITY_STATE_DIR/crowdsec_version"
}

security_install_collections() {
  local collection
  for collection in crowdsecurity/linux crowdsecurity/nginx; do
    cscli collections list -o raw 2>/dev/null | grep -Fq "$collection" || cscli collections install "$collection"
  done
}

security_test_nginx_parser() {
  local output
  output=$(cscli explain --file "$SCRIPT_DIR/deploy/security/fixtures/nginx-access.log" --type nginx 2>&1) || {
    printf '%s\n' "$output" >&2
    die "CrowdSec could not explain the Nginx fixture"
  }
  grep -Eq 'crowdsecurity/nginx-logs|http_path|evt\.Meta\.http' <<<"$output" || die "CrowdSec Nginx parser did not enrich the fixture"
}

security_write_acquisitions() {
  install -d -m 0755 "$CROWDSEC_ACQUIS_DIR"
  install -m 0644 "$SCRIPT_DIR/deploy/security/crowdsec/who-could-nginx.yaml" "$CROWDSEC_ACQUIS_DIR/who-could-nginx.yaml"
  if [[ -r /var/log/auth.log ]]; then
    install -m 0644 "$SCRIPT_DIR/deploy/security/crowdsec/who-could-host-authlog.yaml" "$CROWDSEC_ACQUIS_DIR/who-could-host.yaml"
  elif security_has journalctl; then
    install -m 0644 "$SCRIPT_DIR/deploy/security/crowdsec/who-could-host-journal.yaml" "$CROWDSEC_ACQUIS_DIR/who-could-host.yaml"
  else
    die "Neither readable /var/log/auth.log nor journalctl is available for SSH acquisition"
  fi
  chmod 0644 "$CROWDSEC_ACQUIS_DIR"/who-could-{nginx,host}.yaml
}

security_verify_docker_socket_access() {
  local socket=/var/run/docker.sock service_user
  [[ -S "$socket" ]] || die "Docker socket is unavailable; Nginx Docker log acquisition cannot be configured"
  service_user=$(systemctl show crowdsec --property=User --value 2>/dev/null || true)
  if [[ -z "$service_user" || "$service_user" == root ]]; then
    [[ -r "$socket" ]] || die "CrowdSec's root service cannot read the Docker socket"
  else
    security_has runuser || die "Cannot verify Docker socket access for CrowdSec service user $service_user"
    runuser -u "$service_user" -- test -r "$socket" || die "CrowdSec service user $service_user cannot read Docker logs; refusing to weaken Docker socket permissions"
  fi
  # World-readable Docker control access is never an acceptable workaround.
  (( (8#$(stat -c '%a' "$socket") & 8#004) == 0 )) || die "Docker socket is world-readable; repair its permissions before security installation"
}

security_validate_crowdsec() {
  crowdsec -c /etc/crowdsec/config.yaml -t
  systemctl restart crowdsec
  security_service_active crowdsec || die "CrowdSec failed to become active"
  cscli metrics >/dev/null
}

security_install_bouncer() {
  local backend=$1
  if [[ "$backend" == nftables-native ]]; then
    die "Docker native nftables web-port remediation is not automatically configured by this version"
  fi
  [[ "$backend" == iptables ]] || die "No supported Docker firewall topology was detected; refusing to claim web-port protection"
  if [[ "$(security_state_value BOUNCER_LOCAL_OVERRIDE_PREEXISTING)" == true ]]; then
    die "Existing $BOUNCER_LOCAL_OVERRIDE is user-managed; refusing to overwrite it"
  fi
  DEBIAN_FRONTEND=noninteractive apt-get install -y crowdsec-firewall-bouncer-iptables
  install -d -m 0750 "$CROWDSEC_BOUNCER_DIR"
  cat > "$BOUNCER_LOCAL_OVERRIDE" <<EOF
# Managed by Who could. INPUT protects host services; DOCKER-USER sees
# forwarded traffic before Docker accepts a published port.
mode: iptables
iptables_v4_chains:
  - INPUT
  - DOCKER-USER
iptables_v6_chains:
  - INPUT
$(security_ipv6_chain_available && printf '  - DOCKER-USER\n')
EOF
  chmod 0600 "$BOUNCER_LOCAL_OVERRIDE"
  security_install_bouncer_dropin
  systemctl enable --now crowdsec-firewall-bouncer
  systemctl restart crowdsec-firewall-bouncer
  security_service_active crowdsec-firewall-bouncer || die "CrowdSec firewall bouncer is not active"
  cscli bouncers list -o raw | grep -q 'crowdsec-firewall-bouncer' || die "Firewall bouncer is not registered with LAPI"
}

security_install_bouncer_dropin() {
  install -d -m 0755 "$(dirname "$DOCKER_WAIT_HELPER")" "$BOUNCER_DROPIN_DIR"
  install -m 0755 "$SCRIPT_DIR/deploy/security/wait-docker-user.sh" "$DOCKER_WAIT_HELPER"
  cat > "$BOUNCER_DROPIN" <<EOF
# Managed by Who could. Package unit remains untouched.
[Unit]
Wants=docker.service
After=docker.service

[Service]
Environment=WHO_COULD_BOUNCER_CONFIG=$BOUNCER_LOCAL_OVERRIDE
ExecStartPre=$DOCKER_WAIT_HELPER
EOF
  chmod 0644 "$BOUNCER_DROPIN"
  systemctl daemon-reload
}

security_bouncer_boot_config_ok() {
  [[ -f "$BOUNCER_DROPIN" && -x "$DOCKER_WAIT_HELPER" ]] || return 1
  grep -Fqx 'Wants=docker.service' "$BOUNCER_DROPIN" && \
    grep -Fqx 'After=docker.service' "$BOUNCER_DROPIN" && \
    grep -Fqx "Environment=WHO_COULD_BOUNCER_CONFIG=$BOUNCER_LOCAL_OVERRIDE" "$BOUNCER_DROPIN" && \
    grep -Fqx "ExecStartPre=$DOCKER_WAIT_HELPER" "$BOUNCER_DROPIN"
}

security_ufw_add_managed() {
  local port=$1 comment=$2
  ufw status | grep -F "$comment" >/dev/null 2>&1 && return 0
  ufw allow "$port/tcp" comment "$comment"
  install -d -m 0700 "$SECURITY_STATE_DIR"
  grep -Fqx "$port|$comment" "$UFW_MANAGED_STATE" 2>/dev/null || printf '%s|%s\n' "$port" "$comment" >> "$UFW_MANAGED_STATE"
  chmod 0600 "$UFW_MANAGED_STATE"
}

security_ufw_remove_managed() {
  local port comment
  [[ -f "$UFW_MANAGED_STATE" ]] || return 0
  while IFS='|' read -r port comment; do
    [[ "$comment" == 'Who could HTTP' || "$comment" == 'Who could HTTPS' ]] || continue
    validate_port "$port"
    ufw --force delete allow "$port/tcp" comment "$comment" >/dev/null 2>&1 || true
  done < "$UFW_MANAGED_STATE"
  rm -f "$UFW_MANAGED_STATE"
}

security_configure_ufw() {
  security_has ufw || return 0
  local status ssh_port answer
  status=$(ufw status | head -1); ssh_port=$(security_detect_ssh_port)
  security_set_config SSH_PORT "$ssh_port"
  if [[ "$status" == *active* && "$status" != *inactive* ]]; then
    # Never broaden an existing source-restricted SSH policy.
    security_ufw_add_managed "$(cfg HTTP_PORT)" 'Who could HTTP'
    [[ "$(cfg HTTPS_MODE)" == disabled ]] || security_ufw_add_managed "$(cfg HTTPS_PORT)" 'Who could HTTPS'
    security_set_config HOST_FIREWALL_ENABLED true
  elif ! $NON_INTERACTIVE; then
    read -r -p 'UFW is currently disabled. Enable host firewall? [y/N]: ' answer
    if [[ "${answer:-N}" =~ ^[Yy]$ ]]; then
      # SSH is allowed first. Never change sshd policy or remove this rule.
      ufw allow "$ssh_port/tcp" comment 'Who could SSH safety'
      security_ufw_add_managed "$(cfg HTTP_PORT)" 'Who could HTTP'
      [[ "$(cfg HTTPS_MODE)" == disabled ]] || security_ufw_add_managed "$(cfg HTTPS_PORT)" 'Who could HTTPS'
      ufw --force enable
      security_set_config HOST_FIREWALL_ENABLED true
    fi
  fi
}

security_ipv6_exposed() {
  local container
  container=$(dc ps -q web 2>/dev/null || true)
  [[ -n "$container" ]] || return 1
  docker inspect --format '{{range $port, $bindings := .NetworkSettings.Ports}}{{range $bindings}}{{println .HostIp}}{{end}}{{end}}' "$container" 2>/dev/null | grep -q ':' && return 0
  return 1
}

security_ipv6_chain_available() { security_has ip6tables && ip6tables -w -nL DOCKER-USER >/dev/null 2>&1; }

security_crowdsec_docker_set() {
  local family=${1:-ipv4} rule set_name command=iptables set_data
  [[ "$family" == ipv6 ]] && command=ip6tables
  while IFS= read -r rule; do
    [[ "$rule" =~ --match-set[[:space:]]+([^[:space:]]+)[[:space:]]+src ]] || continue
    set_name=${BASH_REMATCH[1]}
    [[ "$set_name" == crowdsec* ]] || continue
    set_data=$(ipset list "$set_name" 2>/dev/null) || continue
    if [[ "$family" == ipv6 ]]; then grep -q 'family inet6' <<<"$set_data" || continue
    else grep -q 'family inet6' <<<"$set_data" && continue
    fi
    printf '%s' "$set_name"
    return 0
  done < <("$command" -w -S DOCKER-USER 2>/dev/null)
  return 1
}

security_docker_ipv4_integration_ok() {
  [[ "$(security_firewall_backend)" == iptables ]] || return 1
  security_has iptables && security_has ipset || return 1
  security_crowdsec_docker_set ipv4 >/dev/null
}

security_docker_ipv6_state() {
  if ! security_ipv6_exposed; then printf DISABLED; return 0; fi
  if security_ipv6_chain_available && security_crowdsec_docker_set ipv6 >/dev/null; then printf OK; else printf FAIL; fi
}

security_install() {
  security_require_root; prepare_dirs; ensure_config_v2
  info "Who could — Host Security Setup"
  security_set_config HOST_SECURITY_ENABLED false
  security_set_config CROWDSEC_ENABLED false
  CURRENT_STAGE='security preflight'; security_preflight
  CURRENT_STAGE='firewall snapshot'; security_backup_firewall
  CURRENT_STAGE='CrowdSec installation'; security_install_crowdsec
  CURRENT_STAGE='CrowdSec collections'; security_install_collections
  CURRENT_STAGE='Nginx parser fixture'; security_test_nginx_parser
  CURRENT_STAGE='log acquisition'; security_write_acquisitions
  CURRENT_STAGE='Docker socket access'; security_verify_docker_socket_access
  CURRENT_STAGE='CrowdSec validation'; security_validate_crowdsec
  local backend; backend=$(security_firewall_backend)
  printf '%s\n' "$backend" > "$SECURITY_STATE_DIR/firewall_backend"
  CURRENT_STAGE='firewall bouncer'; security_install_bouncer "$backend"
  CURRENT_STAGE='UFW safety'; security_configure_ufw
  CURRENT_STAGE='security diagnostics'; security_test
  security_set_config HOST_SECURITY_ENABLED true
  security_set_config CROWDSEC_ENABLED true
  info "Security diagnostics          OK"
}

security_bouncer_active() { security_service_active crowdsec-firewall-bouncer || security_service_active crowdsec-firewall-bouncer-iptables; }

security_status() {
  security_require_root
  local backend decisions=unknown ssh_port engine=INACTIVE bouncer=INACTIVE ufw_state=unavailable
  backend=$(security_firewall_backend); ssh_port=$(security_detect_ssh_port)
  security_service_active crowdsec && engine=ACTIVE
  security_bouncer_active && bouncer=ACTIVE
  security_has cscli && decisions=$(cscli decisions list -o raw 2>/dev/null | awk 'NR>1{n++} END{print n+0}')
  security_has ufw && ufw_state=$(ufw status 2>/dev/null | awk 'NR==1{print $2}')
  info "Who could — host security"
  printf 'CrowdSec                  %s\n' "$engine"
  printf 'CrowdSec version          %s\n' "$(cat "$SECURITY_STATE_DIR/crowdsec_version" 2>/dev/null || echo unavailable)"
  printf 'Linux collection          %s\n' "$(cscli collections list -o raw 2>/dev/null | grep -Fq crowdsecurity/linux && echo OK || echo MISSING)"
  printf 'Nginx collection          %s\n' "$(cscli collections list -o raw 2>/dev/null | grep -Fq crowdsecurity/nginx && echo OK || echo MISSING)"
  printf 'Host acquisition          %s\n' "$([[ -f "$CROWDSEC_ACQUIS_DIR/who-could-host.yaml" ]] && echo OK || echo MISSING)"
  printf 'Docker Nginx acquisition  %s\n' "$([[ -f "$CROWDSEC_ACQUIS_DIR/who-could-nginx.yaml" ]] && echo OK || echo MISSING)"
  printf 'Firewall backend          %s\nFirewall bouncer          %s\n' "$backend" "$bouncer"
  printf 'Bouncer boot config       %s\n' "$(security_bouncer_boot_config_ok && echo OK || echo FAIL)"
  printf 'Bouncer API               %s\n' "$(cscli bouncers list -o raw 2>/dev/null | grep -q crowdsec-firewall-bouncer && echo OK || echo MISSING)"
  printf 'Docker IPv4 integration   %s\n' "$(security_docker_ipv4_integration_ok && echo OK || echo FAIL)"
  printf 'Docker IPv6 integration   %s\n' "$(security_docker_ipv6_state)"
  printf 'UFW                       %s\nSSH port                  %s\nActive decisions          %s\n' "$ufw_state" "$ssh_port" "$decisions"
}

security_test() (
  set -Eeuo pipefail
  security_require_root
  security_service_active crowdsec || die "CrowdSec engine is inactive"
  cscli lapi status >/dev/null
  cscli collections list -o raw | grep -Fq crowdsecurity/linux
  cscli collections list -o raw | grep -Fq crowdsecurity/nginx
  [[ -f "$CROWDSEC_ACQUIS_DIR/who-could-nginx.yaml" && -f "$CROWDSEC_ACQUIS_DIR/who-could-host.yaml" ]] || die "Managed acquisition is missing"
  security_bouncer_active || die "Firewall bouncer is inactive"
  security_docker_ipv4_integration_ok || die "DOCKER-USER does not reference a CrowdSec IPv4 firewall set"
  [[ "$(security_docker_ipv6_state)" != FAIL ]] || die "Public Docker IPv6 remediation is not verified"
  cleanup_security_decision() {
    cscli decisions delete --ip "$TEST_DECISION_IP" >/dev/null 2>&1 || true
    cscli decisions delete --ip "$TEST_DECISION_IPV6" >/dev/null 2>&1 || true
  }
  trap cleanup_security_decision EXIT
  cleanup_security_decision
  cscli decisions add --ip "$TEST_DECISION_IP" --duration 2m --reason who-could-security-test >/dev/null
  cscli decisions list -o raw | grep -q "$TEST_DECISION_IP" || die "Temporary TEST-NET decision was not accepted"
  local set_name deadline
  set_name=$(security_crowdsec_docker_set ipv4) || die "CrowdSec Docker IPv4 firewall set was not found"
  deadline=$((SECONDS + 30))
  until ipset list "$set_name" 2>/dev/null | grep -Fq "$TEST_DECISION_IP"; do
    ((SECONDS < deadline)) || die "Temporary decision did not reach CrowdSec set $set_name within 30 seconds"
    sleep 1
  done
  if [[ "$(security_docker_ipv6_state)" == OK ]]; then
    cscli decisions add --ip "$TEST_DECISION_IPV6" --duration 2m --reason who-could-security-test-ipv6 >/dev/null
    cscli decisions list -o raw | grep -Fq "$TEST_DECISION_IPV6" || die "Temporary IPv6 documentation decision was not accepted"
    set_name=$(security_crowdsec_docker_set ipv6) || die "CrowdSec Docker IPv6 firewall set was not found"
    deadline=$((SECONDS + 30))
    until ipset list "$set_name" 2>/dev/null | grep -Fq "$TEST_DECISION_IPV6"; do
      ((SECONDS < deadline)) || die "Temporary IPv6 decision did not reach CrowdSec set $set_name within 30 seconds"
      sleep 1
    done
  fi
  cleanup_security_decision
  trap - EXIT
  info "CrowdSec decisions            working"
)

security_remove() {
  security_require_root
  rm -f "$CROWDSEC_ACQUIS_DIR/who-could-nginx.yaml" "$CROWDSEC_ACQUIS_DIR/who-could-host.yaml"
  if [[ "$(security_state_value BOUNCER_LOCAL_OVERRIDE_PREEXISTING)" == false ]]; then rm -f "$BOUNCER_LOCAL_OVERRIDE"; fi
  if [[ "$(security_state_value BOUNCER_DROPIN_PREEXISTING)" == false ]]; then
    rm -f "$BOUNCER_DROPIN" "$DOCKER_WAIT_HELPER"
    rmdir "$BOUNCER_DROPIN_DIR" "$(dirname "$DOCKER_WAIT_HELPER")" 2>/dev/null || true
    systemctl daemon-reload 2>/dev/null || true
  fi
  if security_has cscli && [[ "$(security_state_value BOUNCER_PREEXISTING)" == false ]]; then
    # Keep package config/API key/LAPI registration consistent so a later
    # security-install can re-enable the retained package without key rotation.
    systemctl disable --now crowdsec-firewall-bouncer >/dev/null 2>&1 || true
  elif security_service_active crowdsec-firewall-bouncer; then
    systemctl restart crowdsec-firewall-bouncer >/dev/null 2>&1 || true
  fi
  if [[ "$(security_state_value APT_PREFERENCE_PREEXISTING)" == false ]] && grep -Fq '# Managed by Who could' "$CROWDSEC_APT_PREFERENCE" 2>/dev/null; then
    rm -f "$CROWDSEC_APT_PREFERENCE"
  fi
  security_has ufw && security_ufw_remove_managed
  security_has systemctl && systemctl restart crowdsec 2>/dev/null || true
  security_set_config HOST_SECURITY_ENABLED false
  security_set_config CROWDSEC_ENABLED false
  # Never reset/disable UFW, remove the SSH allow, purge packages, or touch app data.
  info "Who could managed security configuration removed. CrowdSec packages and host firewall were preserved."
}

security_doctor() {
  local backend engine=INACTIVE bouncer=INACTIVE ufw_state=unavailable
  backend=$(security_firewall_backend)
  security_service_active crowdsec && engine=ACTIVE
  security_bouncer_active && bouncer=ACTIVE
  security_has ufw && ufw_state=$(ufw status 2>/dev/null | awk 'NR==1{print $2}')
  printf 'Host security enabled  %s\nCrowdSec engine        %s\n' "$(cfg HOST_SECURITY_ENABLED 2>/dev/null || echo false)" "$engine"
  printf 'CrowdSec acquisition   %s\n' "$([[ -f "$CROWDSEC_ACQUIS_DIR/who-could-nginx.yaml" && -f "$CROWDSEC_ACQUIS_DIR/who-could-host.yaml" ]] && echo OK || echo NOT-CONFIGURED)"
  printf 'Firewall backend       %s\nFirewall bouncer       %s\n' "$backend" "$bouncer"
  printf 'Bouncer boot config    %s\n' "$(security_bouncer_boot_config_ok && echo OK || echo FAIL)"
  printf 'Docker IPv4 integration %s\nDocker IPv6 integration %s\nUFW                    %s\nSSH port               %s\n' \
    "$(security_docker_ipv4_integration_ok && echo OK || echo FAIL)" "$(security_docker_ipv6_state)" "$ufw_state" "$(security_detect_ssh_port)"
}
