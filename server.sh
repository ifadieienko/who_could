#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
DEPLOY_SOURCE_DIR="$SCRIPT_DIR"
STATE_DIR="${WHO_COULD_STATE_DIR:-/opt/who-could}"
[[ "$STATE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] || { printf 'Error: WHO_COULD_STATE_DIR must be a safe absolute path\n' >&2; exit 1; }
CONFIG_FILE="$STATE_DIR/config/deployment.env"
CURRENT_STAGE=initialization
TEMP_FILES=()
NON_INTERACTIVE=false
PRESEED=""
ACTION=""
LOCK_FD=""

# Host security is deliberately kept out of the application Compose stack.
# shellcheck source=deploy/security/host_security.sh
source "$SCRIPT_DIR/deploy/security/host_security.sh"
# shellcheck source=deploy/update_rollback.sh
source "$SCRIPT_DIR/deploy/update_rollback.sh"
# shellcheck source=deploy/runtime_hardening.sh
source "$SCRIPT_DIR/deploy/runtime_hardening.sh"

cleanup() { if ((${#TEMP_FILES[@]})); then rm -f -- "${TEMP_FILES[@]}"; fi; }
failure() { local rc=$? label=Installation help='./server.sh logs and ./server.sh doctor' stage=$CURRENT_STAGE; [[ "$ACTION" == security-* ]] && { label='Security installation'; help='./server.sh security-status and ./server.sh doctor'; }; [[ "$ACTION" == update ]] && stage=$UPDATE_FAILURE_STAGE; cleanup; printf '%s failed at: %s\nRun: %s\n' "$label" "$stage" "$help" >&2; exit "$rc"; }
trap cleanup EXIT
trap failure ERR

die() { printf 'Error: %s\nInstallation failed at: %s\nRun: ./server.sh logs and ./server.sh doctor\n' "$*" "$CURRENT_STAGE" >&2; exit 1; }
info() { printf '%s\n' "$*"; }
valid_key() { [[ "$1" =~ ^[A-Z][A-Z0-9_]*$ ]]; }
valid_value() { [[ "$1" != *$'\n'* && "$1" != *$'\r'* ]]; }
cfg() {
  local wanted=$1 line key value
  [[ -f "$CONFIG_FILE" ]] || return 1
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]] || continue
    key=${BASH_REMATCH[1]}; value=${BASH_REMATCH[2]}
    [[ "$key" == "$wanted" ]] && { printf '%s' "$value"; return 0; }
  done < "$CONFIG_FILE"
  return 1
}
preseed() {
  local wanted=$1 line
  [[ -n "$PRESEED" && -f "$PRESEED" ]] || return 1
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^${wanted}=(.*)$ ]] && { printf '%s' "${BASH_REMATCH[1]}"; return 0; }
  done < "$PRESEED"
  return 1
}
ask() {
  local key=$1 prompt=$2 default=$3 answer
  if answer=$(preseed "$key"); then :
  elif $NON_INTERACTIVE; then answer=$default
  else read -r -p "$prompt [$default]: " answer; answer=${answer:-$default}; fi
  valid_value "$answer" || die "Invalid newline in $key"
  printf '%s' "$answer"
}
ask_secret() {
  local key=$1 path=$2 policy=${3:-generate} answer choice input_file perms
  if input_file=$(preseed "${key}_FILE"); then
    [[ -f "$input_file" ]] || die "Protected input file for $key was not found"
    perms=$(stat -c '%a' "$input_file")
    (( (8#$perms & 8#077) == 0 )) || die "Protected input file for $key is accessible by group/others"
    answer=$(cat -- "$input_file")
  elif [[ "$ACTION" == configure && -s "$path" ]]; then
    if [[ "$policy" == local ]]; then
      info "$key [keeping existing; use rotate-db-password for supported local rotation]" >&2
      return 0
    fi
    if $NON_INTERACTIVE; then return 0; fi
    read -r -p "$key [keep existing/change] (keep): " choice
    [[ "${choice:-keep}" == change ]] || return 0
    read -r -s -p "$key (hidden): " answer; printf '\n' >&2
  elif [[ "$policy" == external ]]; then
    if $NON_INTERACTIVE; then die "$key requires a protected ${key}_FILE preseed in external database mode"; fi
    read -r -s -p "$key (hidden): " answer; printf '\n' >&2
  elif answer=$(preseed "$key"); then
    info "Warning: inline secret preseed is intended for disposable CI only; prefer ${key}_FILE" >&2
  elif [[ -s "$path" ]]; then return 0
  elif $NON_INTERACTIVE; then answer=$(secure_random)
  else
    read -r -p "$key: 1 Generate automatically, 2 Enter manually. Choice [1]: " choice
    if [[ "${choice:-1}" == 2 ]]; then read -r -s -p "$key (hidden): " answer; printf '\n'; else answer=$(secure_random); fi
  fi
  if [[ "$key" != WHO_COULD_SECRET && -z "$answer" ]]; then die "$key cannot be empty"; fi
  (umask 027; printf '%s' "$answer" > "$path")
}
secure_random() { python3 -c 'import secrets; print(secrets.token_urlsafe(48))'; }
validate_port() { if [[ ! "$1" =~ ^[0-9]+$ ]] || ((10#$1 < 1 || 10#$1 > 65535)); then die "Invalid port: $1"; fi; }
validate_host() { [[ "$1" =~ ^([A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?|localhost|[0-9a-fA-F:]+)$ ]] || die "Invalid hostname: $1"; }
validate_identifier() { [[ "$1" =~ ^[A-Za-z_][A-Za-z0-9_-]{0,62}$ ]] || die "Invalid database identifier: $1"; }
validate_email() { [[ "$1" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || die "Invalid email: $1"; }

supported_ubuntu_release() {
  [[ -r /etc/os-release ]] || return 1
  local os_id version_id
  os_id=$(sed -n 's/^ID=//p' /etc/os-release | tr -d '"')
  version_id=$(sed -n 's/^VERSION_ID=//p' /etc/os-release | tr -d '"')
  [[ "$os_id" == ubuntu && "$version_id" =~ ^(22\.04|24\.04|26\.04)$ ]]
}
ensure_host_dependencies() {
  local required_commands=(awk curl cut df find flock git grep install mktemp openssl python3 sed sort stat tar tr)
  local missing=() command_name
  for command_name in "${required_commands[@]}"; do
    command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
  done
  ((${#missing[@]} == 0)) && return 0
  ((EUID == 0)) || die "Missing host dependencies: ${missing[*]}. Re-run installation as root so supported Ubuntu dependencies can be installed."
  supported_ubuntu_release || die "Missing host dependencies: ${missing[*]}. Automatic dependency installation supports Ubuntu 22.04, 24.04 and 26.04 only."
  command -v apt-get >/dev/null || die "apt-get is required to install missing host dependencies"
  CURRENT_STAGE='host-dependencies'
  info "Installing required host dependencies: ${missing[*]}"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates coreutils curl findutils gawk git grep openssl python3 sed tar util-linux
  missing=()
  for command_name in "${required_commands[@]}"; do
    command -v "$command_name" >/dev/null 2>&1 || missing+=("$command_name")
  done
  ((${#missing[@]} == 0)) || die "Required host dependencies are still unavailable: ${missing[*]}"
}
check_install_source() {
  local sha dirty
  sha=$(git -C "$SCRIPT_DIR" rev-parse --verify 'HEAD^{commit}' 2>/dev/null) || die "Server installation must run from a Git checkout with an identifiable HEAD commit. Clone the repository instead of deploying an extracted archive."
  valid_release_sha "$sha" || die "Git returned an invalid installation release identity"
  git -C "$SCRIPT_DIR" remote get-url origin >/dev/null 2>&1 || die "The installation checkout has no origin remote. A fetchable origin is required for safe update/rollback operations."
  dirty=$(git -C "$SCRIPT_DIR" status --porcelain --untracked-files=normal)
  [[ -z "$dirty" ]] || die "Installation checkout contains uncommitted/untracked files. Commit, remove, or ignore them so the image matches the recorded Git SHA."
}
deployment_complete() {
  local installed
  [[ -s "$STATE_DIR/state/last_successful_deployment" && -s "$STATE_DIR/state/installed_git_sha" ]] || return 1
  IFS= read -r installed < "$STATE_DIR/state/installed_git_sha"
  valid_release_sha "$installed" || return 1
  [[ -L "$STATE_DIR/current" && -d "$STATE_DIR/releases/$installed" ]]
}

docker_cmd() { if docker info >/dev/null 2>&1; then docker "$@"; elif [[ $EUID -ne 0 ]] && sudo docker info >/dev/null 2>&1; then sudo docker "$@"; else die "Docker daemon is unavailable; run as root or configure Docker explicitly"; fi; }
compose_files() {
  local mode version
  version=$(cfg CONFIG_VERSION)
  [[ "$version" == 2 ]] || die "Unsupported CONFIG_VERSION: $version"
  mode=$(cfg DATABASE_MODE)
  COMPOSE_ARGS=(-f "$DEPLOY_SOURCE_DIR/compose.yaml")
  case "$mode" in
    mariadb-local) COMPOSE_ARGS+=(-f "$DEPLOY_SOURCE_DIR/compose.mariadb.yaml");;
    mariadb-external) COMPOSE_ARGS+=(-f "$DEPLOY_SOURCE_DIR/compose.external.yaml");;
    *) die "Only mariadb-local or mariadb-external DATABASE_MODE is supported";;
  esac
  if [[ "$(cfg HTTPS_MODE)" != disabled ]]; then
    COMPOSE_ARGS+=(-f "$DEPLOY_SOURCE_DIR/compose.https.yaml")
  fi
}
dc() {
  compose_files
  if [[ -n "${RUNTIME_BACKEND_IMAGE:-}" ]]; then
    APP_SETTINGS_ENV="${APP_SETTINGS_ENV:-$STATE_DIR/config/workshop.env}" DEPLOYMENT_ENV="$CONFIG_FILE" BACKEND_IMAGE="$RUNTIME_BACKEND_IMAGE" WEB_IMAGE="$RUNTIME_WEB_IMAGE" NGINX_SITE_CONFIG="$RUNTIME_NGINX_CONFIG" docker_cmd compose --env-file "$CONFIG_FILE" "${COMPOSE_ARGS[@]}" "$@"
  else
    APP_SETTINGS_ENV="${APP_SETTINGS_ENV:-$STATE_DIR/config/workshop.env}" DEPLOYMENT_ENV="$CONFIG_FILE" docker_cmd compose --env-file "$CONFIG_FILE" "${COMPOSE_ARGS[@]}" "$@"
  fi
}
install_docker() {
  [[ -r /etc/os-release ]] || die "Cannot identify operating system"
  local os_id version_id codename
  os_id=$(sed -n 's/^ID=//p' /etc/os-release | tr -d '"')
  version_id=$(sed -n 's/^VERSION_ID=//p' /etc/os-release | tr -d '"')
  codename=$(sed -n 's/^VERSION_CODENAME=//p' /etc/os-release | tr -d '"')
  [[ "$os_id" == ubuntu && "$version_id" =~ ^(22\.04|24\.04|26\.04)$ ]] || die "Automatic Docker installation supports Ubuntu 22.04, 24.04 and 26.04 only"
  local yes=Y
  $NON_INTERACTIVE || read -r -p "Install Docker Engine from Docker's official APT repository? [Y/n]: " yes
  [[ "${yes:-Y}" =~ ^[Yy]$ ]] || die "Docker is required"
  apt-get update; apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/ubuntu/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$(dpkg --print-architecture)" "$codename" > /etc/apt/sources.list.d/docker.list
  apt-get update; apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}
check_docker() {
  command -v docker >/dev/null || install_docker
  docker_cmd version >/dev/null
  local compose_version
  compose_version=$(docker_cmd compose version --short)
  compose_version=${compose_version#v}
  [[ "$(printf '%s\n' 2.24.0 "$compose_version" | sort -V | head -1)" == 2.24.0 ]] || die 'Docker Compose >= 2.24 is required'
}
prepare_dirs() {
  [[ -w "$(dirname "$STATE_DIR")" || -d "$STATE_DIR" ]] || die "Run as root (recommended: sudo ./server.sh install)"
  install -d -m 0750 "$STATE_DIR"/{config,secrets,certs,backups,state,logs,state/acme}
  chown root:10002 "$STATE_DIR/certs"
  chmod 0750 "$STATE_DIR/certs"
  touch "$STATE_DIR/config/database-ca.pem"
  chmod 0644 "$STATE_DIR/config/database-ca.pem"
  migrate_legacy_database_secret
  touch "$STATE_DIR/secrets/"{mariadb_local_password,mariadb_root_password,external_database_password}
  chmod 0440 "$STATE_DIR/secrets/"{mariadb_local_password,mariadb_root_password,external_database_password}
  if [[ -f "$CONFIG_FILE" ]]; then
    local previous_mode
    previous_mode=$(cfg DATABASE_MODE 2>/dev/null || true)
    record_local_identity "$previous_mode"
  fi
}

acquire_state_lock() {
  command -v flock >/dev/null || die "flock is required for state-changing commands"
  install -d -m 0750 "$STATE_DIR/state"
  exec {LOCK_FD}>"$STATE_DIR/state/server.lock"
  flock -n "$LOCK_FD" || die "Another deployment/security operation holds $STATE_DIR/state/server.lock"
}

ensure_config_v2() {
  [[ -f "$CONFIG_FILE" ]] || return 0
  local version
  version=$(cfg CONFIG_VERSION 2>/dev/null || true)
  case "$version" in
    2) return 0;;
    1)
      local held=false
      [[ -n "$LOCK_FD" ]] && held=true
      $held || acquire_state_lock
      security_migrate_config_v1_to_v2 "$CONFIG_FILE"
      info "Migrated deployment configuration safely from version 1 to 2."
      ;;
    *) die "Unsupported CONFIG_VERSION: ${version:-missing}";;
  esac
}
migrate_legacy_database_secret() {
  local legacy="$STATE_DIR/secrets/database_password" destination="" previous_mode=""
  [[ -s "$legacy" ]] || return 0
  if [[ -f "$CONFIG_FILE" ]]; then previous_mode=$(cfg DATABASE_MODE 2>/dev/null || true); fi
  case "$previous_mode" in
    mariadb-local) destination="$STATE_DIR/secrets/mariadb_local_password";;
    mariadb-external) destination="$STATE_DIR/secrets/external_database_password";;
  esac
  if [[ -n "$destination" && ! -s "$destination" ]]; then
    install -m 0440 "$legacy" "$destination"
    info "Migrated the legacy database credential into MariaDB protected storage."
  fi
}
identity_value() {
  local mode=$1 key=$2 line
  local file="$STATE_DIR/state/${mode}.identity"
  [[ -f "$file" ]] || return 1
  while IFS= read -r line; do
    if [[ "$line" =~ ^${key}=(.*)$ ]]; then printf '%s' "${BASH_REMATCH[1]}"; return 0; fi
  done < "$file"
  return 1
}
record_local_identity() {
  local mode=$1 file
  [[ "$mode" == mariadb-local ]] || return 0
  file="$STATE_DIR/state/${mode}.identity"
  if [[ ! -f "$file" ]]; then
    (umask 027; printf 'DATABASE_NAME=%s\nDATABASE_USER=%s\n' "$(cfg DATABASE_NAME)" "$(cfg DATABASE_USER)" > "$file")
  fi
}
normalize_tls_permissions() {
  find "$STATE_DIR/certs" -type d -exec chown root:10002 {} + -exec chmod 0750 {} +
  find "$STATE_DIR/certs" -type f -exec chown root:10002 {} + -exec chmod 0640 {} +
}
port_in_use() {
  local address=$1 port=$2
  python3 - "$address" "$port" <<'PY'
import socket, sys
s = socket.socket()
try:
    s.bind((sys.argv[1], int(sys.argv[2])))
except OSError:
    raise SystemExit(0)
finally:
    s.close()
raise SystemExit(1)
PY
}
check_ports() {
  dc stop web >/dev/null 2>&1 || true
  local bind port
  bind=$(cfg BIND_ADDRESS 2>/dev/null || echo 0.0.0.0); validate_bind_address "$bind"
  port=$(cfg HTTP_PORT)
  if port_in_use "$bind" "$port"; then die "Port $bind:$port is already in use or the bind address is unavailable."; fi
  if [[ "$(cfg HTTPS_MODE)" != disabled ]]; then
    port=$(cfg HTTPS_PORT)
    if port_in_use "$bind" "$port"; then die "Port $bind:$port is already in use or the bind address is unavailable."; fi
  fi
}
choose_database_ca() {
  local required=$1 choice source
  if [[ "$ACTION" == configure && -s "$STATE_DIR/config/database-ca.pem" ]]; then
    if $NON_INTERACTIVE; then printf '/run/config/database-ca.pem'; return 0; fi
    read -r -p "Database CA [keep existing/change] (keep): " choice
    if [[ "${choice:-keep}" != change ]]; then printf '/run/config/database-ca.pem'; return 0; fi
  fi
  source=$(ask DATABASE_SSL_CA_SOURCE "Database CA host path" "")
  if [[ -z "$source" && "$required" == no ]]; then printf ''; return 0; fi
  [[ -f "$source" ]] || die "A readable database CA file is required"
  install -m 0644 "$source" "$STATE_DIR/config/database-ca.pem"
  printf '/run/config/database-ca.pem'
}
render_nginx() {
  local force=${1:-} output=${2:-$STATE_DIR/config/site.conf} host https port template cert key tmp
  host=$(cfg PUBLIC_HOSTNAME); https=$(cfg HTTPS_MODE); port=$(cfg HTTPS_PORT)
  if [[ "$force" == locked ]]; then template="$DEPLOY_SOURCE_DIR/docker/nginx/site-locked.conf.template"; cert=unused; key=unused
  elif [[ "$https" == disabled || "$force" == http ]]; then template="$DEPLOY_SOURCE_DIR/docker/nginx/site-http.conf.template"; cert=unused; key=unused
  elif [[ "$https" == custom ]]; then template="$DEPLOY_SOURCE_DIR/docker/nginx/site-https.conf.template"; cert=/etc/letsencrypt/custom/fullchain.pem; key=/etc/letsencrypt/custom/privkey.pem
  else template="$DEPLOY_SOURCE_DIR/docker/nginx/site-https.conf.template"; cert="/etc/letsencrypt/live/$host/fullchain.pem"; key="/etc/letsencrypt/live/$host/privkey.pem"; fi
  install -d -m 0750 "$(dirname "$output")"
  tmp=$(mktemp "$(dirname "$output")/.site.conf.XXXXXX")
  sed -e "s|__HOSTNAME__|$host|g" -e "s|__HTTPS_PORT__|$port|g" -e "s|__CERTIFICATE__|$cert|g" -e "s|__PRIVATE_KEY__|$key|g" "$template" > "$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$output"
}
write_config() {
  local mode host bind_address http_port https_port https dbhost dbport dbname dbuser ca email saved_name saved_user host_security current_security default_security insecure_http backup_export crowdsec firewall ssh_port
  mode=$(ask DATABASE_MODE "MariaDB mode (mariadb-local/mariadb-external)" "$(cfg DATABASE_MODE 2>/dev/null || echo mariadb-local)")
  [[ "$mode" =~ ^mariadb-(local|external)$ ]] || die "Only mariadb-local or mariadb-external is supported"
  host=$(ask PUBLIC_HOSTNAME "Public hostname/domain" "$(cfg PUBLIC_HOSTNAME 2>/dev/null || echo localhost)"); validate_host "$host"
  bind_address=$(ask BIND_ADDRESS "Host bind address (127.0.0.1 local-only, 0.0.0.0 public)" "$(cfg BIND_ADDRESS 2>/dev/null || echo 127.0.0.1)"); validate_bind_address "$bind_address"
  http_port=$(ask HTTP_PORT "HTTP port" "$(cfg HTTP_PORT 2>/dev/null || echo 80)"); validate_port "$http_port"
  https_port=$(ask HTTPS_PORT "HTTPS port" "$(cfg HTTPS_PORT 2>/dev/null || echo 443)"); validate_port "$https_port"
  https=$(ask HTTPS_MODE "HTTPS (acme/custom/disabled)" "$(cfg HTTPS_MODE 2>/dev/null || echo disabled)")
  [[ "$https" =~ ^(acme|custom|disabled)$ ]] || die "Invalid HTTPS mode"
  insecure_http=false
  if ! is_loopback_address "$bind_address" && [[ "$https" == disabled ]]; then
    insecure_http=$(ask ALLOW_INSECURE_PUBLIC_HTTP "Public plaintext HTTP is unsafe. Explicitly allow it? (true/false)" "$(cfg ALLOW_INSECURE_PUBLIC_HTTP 2>/dev/null || echo false)")
    security_bool "$insecure_http" || die "ALLOW_INSECURE_PUBLIC_HTTP must be true or false"
    [[ "$insecure_http" == true ]] || die "Public bind with HTTPS disabled requires explicit ALLOW_INSECURE_PUBLIC_HTTP=true"
  fi
  saved_name=""; saved_user=""
  if [[ "$mode" == mariadb-local ]]; then
    saved_name=$(identity_value "$mode" DATABASE_NAME 2>/dev/null || true)
    saved_user=$(identity_value "$mode" DATABASE_USER 2>/dev/null || true)
  fi
  dbname=$(ask DATABASE_NAME "Database name" "${saved_name:-$(cfg DATABASE_NAME 2>/dev/null || echo who_could)}"); validate_identifier "$dbname"
  dbuser=$(ask DATABASE_USER "Database user" "${saved_user:-$(cfg DATABASE_USER 2>/dev/null || echo who_could)}"); validate_identifier "$dbuser"
  if [[ -n "$saved_name" && ( "$dbname" != "$saved_name" || "$dbuser" != "$saved_user" ) ]]; then
    die "Local MariaDB is already initialized. Changing DATABASE_USER/DATABASE_NAME requires an explicit database migration and is not supported by configure."
  fi
  dbhost=""; dbport=""; ca=""; email=""
  case "$mode" in
    mariadb-local) dbhost=mariadb; dbport=3306;;
    mariadb-external) dbhost=$(ask DATABASE_HOST Host "$(cfg DATABASE_HOST 2>/dev/null || true)"); validate_host "$dbhost"; dbport=$(ask DATABASE_PORT Port "$(cfg DATABASE_PORT 2>/dev/null || echo 3306)"); ca=$(choose_database_ca yes);;
  esac
  validate_port "$dbport"
  if [[ "$https" == acme ]]; then
    [[ "$host" != localhost && ! "$host" =~ ^[0-9.]+$ && "$host" != *:* ]] || die "ACME requires a public DNS hostname, not localhost or an IP address"
    ! is_loopback_address "$bind_address" || die "ACME requires a public BIND_ADDRESS"
    [[ "$http_port" == 80 ]] || die "ACME HTTP-01 requires HTTP host port 80"
    email=$(ask ACME_EMAIL "Let's Encrypt email" "$(cfg ACME_EMAIL 2>/dev/null || true)")
    validate_email "$email"
    local ready
    ready=$(ask ACME_HTTP01_READY "DNS points here and inbound public port 80 reaches this host (yes/no)" no)
    [[ "$ready" == yes ]] || die "ACME requires confirmed DNS and inbound HTTP-01 reachability"
  fi
  default_security=false; is_loopback_address "$bind_address" || default_security=true
  host_security=$(ask HOST_SECURITY_REQUESTED "Enable host CrowdSec/firewall security? (true/false)" "$(cfg HOST_SECURITY_REQUESTED 2>/dev/null || cfg HOST_SECURITY_ENABLED 2>/dev/null || echo "$default_security")")
  security_bool "$host_security" || die "HOST_SECURITY_REQUESTED must be true or false"
  current_security=$(cfg HOST_SECURITY_ENABLED 2>/dev/null || echo false); security_bool "$current_security" || current_security=false
  crowdsec=$(cfg CROWDSEC_ENABLED 2>/dev/null || echo false); firewall=$(cfg HOST_FIREWALL_ENABLED 2>/dev/null || echo false); ssh_port=$(cfg SSH_PORT 2>/dev/null || echo 22)
  backup_export=$(ask BACKUP_EXPORT_DIR "Mounted off-host backup directory (optional)" "$(cfg BACKUP_EXPORT_DIR 2>/dev/null || true)")
  if [[ -n "$backup_export" ]]; then
    [[ "$backup_export" =~ ^/[A-Za-z0-9._/-]+$ ]] || die "BACKUP_EXPORT_DIR must be a safe absolute path"
    [[ "$backup_export" != "$STATE_DIR" && "$backup_export" != "$STATE_DIR/"* ]] || die "BACKUP_EXPORT_DIR must be outside deployment state"
    [[ -d "$backup_export" && -w "$backup_export" ]] || die "BACKUP_EXPORT_DIR must already be a writable mounted directory"
  fi
  local tmp password_container
  tmp=$(mktemp)
  TEMP_FILES+=("$tmp")
  if [[ "$mode" == mariadb-local ]]; then password_container=/run/secrets/mariadb_local_password; else password_container=/run/secrets/external_database_password; fi
  {
    printf 'CONFIG_VERSION=2\nHOST_SECURITY_REQUESTED=%s\nHOST_SECURITY_ENABLED=%s\nCROWDSEC_ENABLED=%s\nHOST_FIREWALL_ENABLED=%s\nSSH_PORT=%s\n' "$host_security" "$current_security" "$crowdsec" "$firewall" "$ssh_port"
    printf 'DATABASE_MODE=%s\nDATABASE_ENGINE=mariadb\nDATABASE_HOST=%s\nDATABASE_PORT=%s\nDATABASE_NAME=%s\nDATABASE_USER=%s\nDATABASE_SSLMODE=\nDATABASE_SSL_CA=%s\n' "$mode" "$dbhost" "$dbport" "$dbname" "$dbuser" "$ca"
    printf 'PUBLIC_HOSTNAME=%s\nBIND_ADDRESS=%s\nALLOW_INSECURE_PUBLIC_HTTP=%s\nHTTP_PORT=%s\nHTTPS_PORT=%s\nHTTPS_MODE=%s\nACME_EMAIL=%s\nBACKUP_EXPORT_DIR=%s\n' "$host" "$bind_address" "$insecure_http" "$http_port" "$https_port" "$https" "$email" "$backup_export"
    printf 'APP_SECRET_FILE=%s/secrets/app_secret\nMARIADB_LOCAL_PASSWORD_FILE=%s/secrets/mariadb_local_password\nMARIADB_ROOT_PASSWORD_FILE=%s/secrets/mariadb_root_password\nEXTERNAL_DATABASE_PASSWORD_FILE=%s/secrets/external_database_password\nDATABASE_PASSWORD_CONTAINER_FILE=%s\nDATABASE_SSL_CA_FILE=%s/config/database-ca.pem\nCERTS_DIR=%s/certs\nACME_WEBROOT=%s/state/acme\nNGINX_SITE_CONFIG=%s/config/site.conf\n' "$STATE_DIR" "$STATE_DIR" "$STATE_DIR" "$STATE_DIR" "$password_container" "$STATE_DIR" "$STATE_DIR" "$STATE_DIR" "$STATE_DIR"
    printf 'SECRETS_GID=10001\nTLS_READER_GID=10002\nBACKEND_MEMORY_LIMIT=512m\nWEB_MEMORY_LIMIT=256m\nDATABASE_MEMORY_LIMIT=1g\nCERTBOT_MEMORY_LIMIT=256m\nBACKEND_CPU_LIMIT=1.0\nWEB_CPU_LIMIT=0.5\nDATABASE_CPU_LIMIT=2.0\nCERTBOT_CPU_LIMIT=0.5\nBACKEND_PIDS_LIMIT=256\nWEB_PIDS_LIMIT=128\nDATABASE_PIDS_LIMIT=512\nCERTBOT_PIDS_LIMIT=128\n'
  } > "$tmp"
  while IFS='=' read -r key value; do
    if ! valid_key "$key" || ! valid_value "$value"; then die "Unsafe generated configuration"; fi
  done < "$tmp"
  install -m 0640 "$tmp" "$CONFIG_FILE"
}
prepare_secrets() {
  ask_secret WHO_COULD_SECRET "$STATE_DIR/secrets/app_secret"
  (($(wc -c < "$STATE_DIR/secrets/app_secret") >= 32)) || die "Application secret must be at least 32 characters"
  case "$(cfg DATABASE_MODE)" in
    mariadb-local)
      ask_secret DATABASE_PASSWORD "$STATE_DIR/secrets/mariadb_local_password" local
      ask_secret MARIADB_ROOT_PASSWORD "$STATE_DIR/secrets/mariadb_root_password" local
      ;;
    mariadb-external) ask_secret DATABASE_PASSWORD "$STATE_DIR/secrets/external_database_password" external;;
    *) die "Only MariaDB database modes are supported";;
  esac
  chown root:10001 "$STATE_DIR/secrets/"* 2>/dev/null || chgrp 10001 "$STATE_DIR/secrets/"*
  chmod 0440 "$STATE_DIR/secrets/"*
}
custom_cert() {
  local cert key
  cert=$(ask CERTIFICATE_FILE "Certificate file" "")
  key=$(ask PRIVATE_KEY_FILE "Private key file" "")
  [[ -f "$cert" && -f "$key" ]] || die "Certificate and private key must exist"
  validate_custom_tls_files "$cert" "$key" "$(cfg PUBLIC_HOSTNAME)"
  install -d -m 0750 "$STATE_DIR/certs/custom"; install -m 0644 "$cert" "$STATE_DIR/certs/custom/fullchain.pem"; install -m 0640 "$key" "$STATE_DIR/certs/custom/privkey.pem"
  normalize_tls_permissions
}
ensure_custom_cert() {
  if [[ -s "$STATE_DIR/certs/custom/fullchain.pem" && -s "$STATE_DIR/certs/custom/privkey.pem" ]]; then
    validate_custom_tls_files "$STATE_DIR/certs/custom/fullchain.pem" "$STATE_DIR/certs/custom/privkey.pem" "$(cfg PUBLIC_HOSTNAME)"
    normalize_tls_permissions
  else
    custom_cert
  fi
}
local_health_target() {
  local target
  target=$(cfg BIND_ADDRESS 2>/dev/null || echo 0.0.0.0)
  [[ "$target" == 0.0.0.0 ]] && target=127.0.0.1
  printf '%s' "$target"
}
acme_issue() {
  CURRENT_STAGE=acme
  local host target
  host=$(cfg PUBLIC_HOSTNAME); target=$(local_health_target)
  dc --profile acme run --rm certbot certonly --webroot -w /var/www/certbot -d "$host" --email "$(cfg ACME_EMAIL)" --agree-tos --non-interactive
  normalize_tls_permissions
  render_nginx
  dc up -d --force-recreate --wait web
  dc exec -T web nginx -t
  curl --resolve "$host:$(cfg HTTPS_PORT):$target" -fsS "https://$host:$(cfg HTTPS_PORT)/api/health" >/dev/null
  install_timer
}
install_timer() {
  local manager
  command -v systemctl >/dev/null || return 0
  manager=$(cert_manager_path)
  cat > /etc/systemd/system/who-could-cert-renew.service <<EOF
[Unit]
Description=Renew Who could TLS certificate
[Service]
Type=oneshot
Environment="WHO_COULD_STATE_DIR=$STATE_DIR"
ExecStart="$manager" cert-renew
NoNewPrivileges=true
PrivateTmp=true
EOF
  cat > /etc/systemd/system/who-could-cert-renew.timer <<'EOF'
[Unit]
Description=Twice-daily Who could certificate renewal check
[Timer]
OnCalendar=*-*-* 03,15:17:00
RandomizedDelaySec=1h
Persistent=true
[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload; systemctl enable --now who-could-cert-renew.timer
}
cert_manager_path() {
  if [[ -x "$STATE_DIR/current/server.sh" ]]; then printf '%s' "$STATE_DIR/current/server.sh"; else printf '%s' "$SCRIPT_DIR/server.sh"; fi
}
remove_timer() {
  command -v systemctl >/dev/null || return 0
  systemctl disable --now who-could-cert-renew.timer 2>/dev/null || true
  rm -f /etc/systemd/system/who-could-cert-renew.{service,timer}
  systemctl daemon-reload 2>/dev/null || true
}
deployment_runtime() {
  CURRENT_STAGE=disk-check
  (($(df -Pk "$STATE_DIR" | awk 'NR==2{print $4}') >= 2097152)) || die "At least 2 GiB free disk space is required"
  CURRENT_STAGE='port-check'; check_ports
  CURRENT_STAGE=build; dc build
  local dbmode
  dbmode=$(cfg DATABASE_MODE)
  CURRENT_STAGE=database
  if [[ "$dbmode" == mariadb-local ]]; then dc up -d --wait --remove-orphans mariadb; fi
  CURRENT_STAGE=database-connectivity; dc run --rm --no-deps backend python -c 'from app.database import engine; from sqlalchemy import text; c=engine.connect(); c.execute(text("SELECT 1")); c.close()'
  record_local_identity "$dbmode"
  CURRENT_STAGE=migrations; dc run --rm --no-deps backend alembic upgrade head; dc run --rm --no-deps backend alembic check
  CURRENT_STAGE=backend; dc up -d --wait --remove-orphans backend
  CURRENT_STAGE=nginx; dc up -d --wait --remove-orphans web
}
mark_deployment_success() {
  CURRENT_STAGE=health; health
  local installed_sha active_sha
  active_sha=$(release_read active_release 2>/dev/null || true)
  if valid_release_sha "$active_sha"; then installed_sha=$active_sha; else installed_sha=$(git -C "$SCRIPT_DIR" rev-parse --verify 'HEAD^{commit}' 2>/dev/null || true); fi
  if ! valid_release_sha "$installed_sha"; then
    [[ "$ACTION" == install ]] && die "Cannot identify the installed Git release; refusing to mark a fresh installation successful"
    info "Warning: deployment health is good, but release identity is unavailable; update/rollback cannot be bootstrapped." >&2
  else
    printf '%s\n' "$installed_sha" > "$STATE_DIR/state/installed_git_sha"
    bootstrap_release_state
    [[ "$(cfg HTTPS_MODE)" == acme ]] && install_timer
  fi
  date -u +%FT%TZ > "$STATE_DIR/state/last_successful_deployment"
  info "Installation successful."
}
secure_deploy() {
  local locked=false
  if [[ "$(cfg HTTPS_MODE)" == acme ]] || { host_security_requested && ! bind_is_loopback; }; then locked=true; fi
  if $locked; then render_nginx locked; else render_nginx; fi
  deployment_runtime
  if host_security_requested; then
    CURRENT_STAGE='host-security'
    security_install
  fi
  if $locked; then
    if [[ "$(cfg HTTPS_MODE)" == acme ]]; then
      acme_issue
    else
      render_nginx
      dc up -d --force-recreate --wait web
      dc exec -T web nginx -t
    fi
  fi
  mark_deployment_success
}
deploy() { secure_deploy; }
health() {
  local hp host target
  hp=$(cfg HTTP_PORT); host=$(cfg PUBLIC_HOSTNAME); target=$(local_health_target)
  curl -H "Host: $host" -fsS "http://$target:$hp/" >/dev/null
  if [[ "$(cfg HTTPS_MODE)" == disabled ]]; then
    curl -H "Host: $host" -fsS "http://$target:$hp/api/health" >/dev/null
  elif [[ "$(cfg HTTPS_MODE)" == custom ]]; then
    curl --resolve "$host:$(cfg HTTPS_PORT):$target" --cacert "$STATE_DIR/certs/custom/fullchain.pem" -fsS "https://$host:$(cfg HTTPS_PORT)/api/health" >/dev/null
  else
    curl --resolve "$host:$(cfg HTTPS_PORT):$target" -fsS "https://$host:$(cfg HTTPS_PORT)/api/health" >/dev/null
  fi
  info "Frontend and API health: OK"
}
install_cmd() {
  info "Who could — Server Setup"
  ensure_host_dependencies
  check_install_source
  acquire_state_lock
  check_docker
  prepare_dirs
  if [[ -f "$CONFIG_FILE" ]]; then
    ensure_config_v2
    if deployment_complete; then
      info "Who could is already installed successfully. Use status, configure, update, or start."
      return 0
    fi
    info "Incomplete previous installation detected; resuming with the existing validated configuration."
  else
    write_config
  fi
  prepare_secrets
  if [[ "$(cfg HTTPS_MODE)" == custom ]]; then ensure_custom_cert; fi
  secure_deploy
}
backup() {
  local mode stamp out
  mode=$(cfg DATABASE_MODE)
  [[ "$mode" == mariadb-local ]] || die "Backups for external MariaDB are managed by the database provider/operator"
  stamp=$(date -u +%Y%m%dT%H%M%S%NZ)
  out="$STATE_DIR/backups/mariadb_${stamp}.sql"
  # Variables intentionally expand in the container shell, not on the host.
  # shellcheck disable=SC2016
  dc exec -T mariadb sh -ceu 'f=$(mktemp); trap '\''rm -f "$f"'\'' EXIT; umask 077; printf "[client]\npassword=%s\n" "$(cat /run/secrets/mariadb_local_password)" > "$f"; mariadb-dump --defaults-extra-file="$f" --single-transaction -u "$MARIADB_USER" "$MARIADB_DATABASE"' > "$out"
  mkdir -p "$out.assets"
  chmod 0700 "$out.assets"
  # Old releases keep photos in SQL and have no attachment volume yet.
  dc run --rm --no-deps backend python -c 'import importlib.util,runpy,sys,tarfile; sys.argv=["backup_uploads","export"]; runpy.run_module("app.backup_uploads",run_name="__main__") if importlib.util.find_spec("app.backup_uploads") else tarfile.open(fileobj=sys.stdout.buffer,mode="w|").close()' > "$out.assets/uploads.tar"
  chmod 0600 "$out.assets/uploads.tar"
  chmod 0600 "$out"; backup_export "$out"; info "Backup created: $out (copy companion $out.assets as well)"
}
native_restore() {
  local mode=$1 file=$2
  [[ "$mode" == mariadb-local ]] || die "Native restore is available only for local MariaDB"
  # A snapshot restore must replace the database, not overlay it. Otherwise
  # objects introduced after the snapshot survive and break rollback checks.
  # Variables intentionally expand in the container shell, not on the host.
  # shellcheck disable=SC2016
  dc exec -T mariadb sh -ceu 'app=$(mktemp); root=$(mktemp); trap '\''rm -f "$app" "$root"'\'' EXIT; umask 077; printf "[client]\npassword=%s\n" "$(cat /run/secrets/mariadb_local_password)" > "$app"; printf "[client]\npassword=%s\n" "$(cat /run/secrets/mariadb_root_password)" > "$root"; mariadb --defaults-extra-file="$root" -uroot -e "DROP DATABASE IF EXISTS \`$MARIADB_DATABASE\`; CREATE DATABASE \`$MARIADB_DATABASE\`;"; mariadb --defaults-extra-file="$app" -u "$MARIADB_USER" "$MARIADB_DATABASE"' < "$file"
}
recover_restore() {
  local mode=$1 emergency=$2 recovered=true
  info "Restore pipeline failed; attempting recovery from $emergency" >&2
  native_restore "$mode" "$emergency" || recovered=false
  if $recovered; then dc run --rm --no-deps backend alembic upgrade head || recovered=false; fi
  if $recovered; then dc run --rm --no-deps backend alembic check || recovered=false; fi
  if $recovered; then dc up -d --wait backend web || recovered=false; else dc up -d backend web >/dev/null 2>&1 || true; fi
  if $recovered; then health || recovered=false; fi
  if $recovered; then
    die "Requested restore failed, but the emergency backup was restored and service health recovered. Emergency backup: $emergency"
  fi
  dc up -d backend web >/dev/null 2>&1 || true
  die "Restore and automatic recovery failed. Emergency backup: $emergency. Recover with: sudo WHO_COULD_STATE_DIR='$STATE_DIR' ./server.sh restore '$emergency'"
}
restore() {
  local file=${1:-} mode emergency
  [[ -f "$file" ]] || die "Backup file not found"
  mode=$(cfg DATABASE_MODE)
  [[ "$mode" == mariadb-local ]] || die "External MariaDB restore is managed by its provider/operator"
  [[ "$file" == *.sql && -s "$file" ]] || die "Expected non-empty .sql backup"
  grep -Eq '^-- (MariaDB|MySQL) dump' "$file" || die "Unrecognized MariaDB dump header"
  info "Target database: $mode / $(cfg DATABASE_NAME)"
  local answer
  read -r -p "Type RESTORE to continue: " answer
  [[ "$answer" == RESTORE ]] || die "Restore cancelled"
  backup
  emergency=$(find "$STATE_DIR/backups" -maxdepth 1 -type f -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
  dc stop backend
  native_restore "$mode" "$file" || recover_restore "$mode" "$emergency"
  if [[ -f "$file.assets/uploads.tar" ]]; then
    dc run --rm --no-deps backend python -m app.backup_uploads restore < "$file.assets/uploads.tar" || recover_restore "$mode" "$emergency"
  fi
  dc run --rm --no-deps backend alembic upgrade head || recover_restore "$mode" "$emergency"
  dc run --rm --no-deps backend alembic check || recover_restore "$mode" "$emergency"
  dc up -d --wait backend web || recover_restore "$mode" "$emergency"
  health || recover_restore "$mode" "$emergency"
}
doctor() {
  info "Who could — diagnostics"
  release_diagnostics
  printf 'Operating system       %s\n' "$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release | tr -d '"')"
  docker_cmd version >/dev/null && echo 'Docker Engine          OK'
  docker_cmd compose version >/dev/null && echo 'Docker Compose         OK'
  printf 'Disk space             %s KB free\n' "$(df -Pk "$STATE_DIR" | awk 'NR==2{print $4}')"
  printf 'Memory                 %s KB\n' "$(awk '/MemTotal/{print $2}' /proc/meminfo)"
  printf 'Config version         %s\nDatabase mode          %s\nBind address           %s\n' "$(cfg CONFIG_VERSION)" "$(cfg DATABASE_MODE)" "$(cfg BIND_ADDRESS 2>/dev/null || echo legacy-public-default)"
  if [[ -n "$(cfg BACKUP_EXPORT_DIR 2>/dev/null || true)" ]]; then echo 'Backup export          CONFIGURED'; else echo 'Backup export          WARN (local-only backups)'; fi
  security_doctor
  if find "$STATE_DIR/secrets" -type f -perm /007 -print -quit | grep -q .; then echo 'Secrets permissions    FAIL'; else echo 'Secrets permissions    OK'; fi
  dc ps; health
}
cert_renew() { [[ "$(cfg HTTPS_MODE)" == acme ]] || die "ACME is not configured"; dc --profile acme run --rm certbot renew --webroot -w /var/www/certbot; normalize_tls_permissions; openssl x509 -in "$STATE_DIR/certs/live/$(cfg PUBLIC_HOSTNAME)/fullchain.pem" -checkend 86400 -noout >/dev/null; dc exec -T web nginx -t; dc exec -T web nginx -s reload; }
usage() { cat <<'EOF'
Usage: ./server.sh COMMAND [options]
Commands: install, configure, start, stop, restart, status, logs [service],
          health, doctor, mail, backup, restore FILE, rotate-db-password, cert-renew,
          uninstall, update [--check] [--ref REF] [--external-db-backup-confirmed],
          rollback [RELEASE] [--restore-database], releases,
          security-install, security-status, security-test, security-remove
Options for install/configure: --non-interactive --config FILE
Database: MariaDB only (local container or external MariaDB).
Runtime state defaults to /opt/who-could (override with WHO_COULD_STATE_DIR).
EOF
}

main() {
  local active
  COMMAND=${1:---help}; ACTION=$COMMAND; shift || true
  while (($#)); do case "$1" in --non-interactive) NON_INTERACTIVE=true;; --config) shift; PRESEED=${1:-}; [[ -f "$PRESEED" ]] || die "Preseed file not found";; *) break;; esac; shift; done
  case "$COMMAND" in
    configure|restore|rollback|rotate-db-password|security-install|security-remove|uninstall) acquire_state_lock;;
    update) [[ "${1:-}" == --check ]] || acquire_state_lock;;
  esac
  case "$COMMAND:${1:-}" in --help:*|-h:*|help:*|install:*|update:--check) :;; *) ensure_config_v2;; esac
  case "$COMMAND" in
    --help|-h|help|install|update) :;;
    status|doctor) activate_active_release_runtime diagnostic;;
    configure|restore|rollback|rotate-db-password|security-install|security-remove|uninstall) activate_active_release_runtime reconcile;;
    *) activate_active_release_runtime readonly;;
  esac
  case "$COMMAND" in
  install) install_cmd;;
  configure) ensure_host_dependencies; check_docker; prepare_dirs; write_config; prepare_secrets; if [[ "$(cfg HTTPS_MODE)" == custom ]]; then ensure_custom_cert; fi; if active=$(release_read active_release 2>/dev/null || true); then prepare_release_nginx "$active"; fi; secure_deploy;;
  start) dc up -d --wait; health;; stop) dc down;; restart) dc restart; health;;
  status) info "Who could — service status"; release_diagnostics; dc ps;;
  logs) service=${1:-}; if [[ "$service" == database ]]; then if [[ "$(cfg DATABASE_MODE)" == mariadb-local ]]; then service=mariadb; else die "External MariaDB has no local database service logs"; fi; fi; if [[ -n "$service" ]]; then dc logs --tail=200 "$service"; else dc logs --tail=200; fi;;
  health) health;; doctor) doctor;; backup) backup;; mail) dc exec -T backend python -m app.mail_worker --once;; restore) restore "${1:-}";; rotate-db-password) rotate_local_database_password;; cert-renew) cert_renew;;
  update) update_command "$@";; rollback) rollback_command "$@";; releases) releases_command;;
  security-install) security_set_config HOST_SECURITY_REQUESTED true; security_install;; security-status) security_status;; security-test) security_test;; security-remove) security_remove; security_set_config HOST_SECURITY_REQUESTED false;;
  uninstall) dc down; remove_timer; info "Containers removed. Data and configuration preserved in $STATE_DIR";;
    --help|-h|help) usage;; *) usage; die "Unknown command: $COMMAND";;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
