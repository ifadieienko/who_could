#!/usr/bin/env bash
# Sourced by server.sh. Keep host validation and privileged database maintenance
# out of application containers.

validate_bind_address() {
  if ! python3 - "$1" <<'PY'
import ipaddress, sys
try:
    address = ipaddress.ip_address(sys.argv[1])
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if address.version == 4 else 1)
PY
  then
    die "BIND_ADDRESS must be a valid IPv4 address"
  fi
}

is_loopback_address() {
  python3 - "$1" <<'PY'
import ipaddress, sys
raise SystemExit(0 if ipaddress.ip_address(sys.argv[1]).is_loopback else 1)
PY
}

bind_is_loopback() {
  is_loopback_address "$(cfg BIND_ADDRESS 2>/dev/null || echo 0.0.0.0)"
}

host_security_requested() {
  local requested
  requested=$(cfg HOST_SECURITY_REQUESTED 2>/dev/null || true)
  if [[ -z "$requested" ]]; then requested=$(cfg HOST_SECURITY_ENABLED 2>/dev/null || echo false); fi
  [[ "$requested" == true ]]
}

validate_custom_tls_files() {
  local cert=$1 key=$2 host=$3 cert_pub key_pub
  openssl x509 -in "$cert" -noout >/dev/null 2>&1 || die "Custom certificate is not a valid PEM X.509 certificate"
  openssl pkey -in "$key" -passin pass: -noout >/dev/null 2>&1 || die "Custom private key must be a valid unencrypted PEM key"
  openssl x509 -in "$cert" -checkend 604800 -noout >/dev/null 2>&1 || die "Custom certificate is expired or expires in less than 7 days"
  if python3 - "$host" <<'PY'
import ipaddress, sys
try: ipaddress.ip_address(sys.argv[1])
except ValueError: raise SystemExit(1)
PY
  then
    openssl x509 -in "$cert" -checkip "$host" -noout >/dev/null 2>&1 || die "Custom certificate does not cover configured IP $host"
  else
    openssl x509 -in "$cert" -checkhost "$host" -noout >/dev/null 2>&1 || die "Custom certificate does not cover configured hostname $host"
  fi
  cert_pub=$(openssl x509 -in "$cert" -pubkey -noout | openssl pkey -pubin -outform DER 2>/dev/null | sha256sum | awk '{print $1}')
  key_pub=$(openssl pkey -in "$key" -passin pass: -pubout -outform DER 2>/dev/null | sha256sum | awk '{print $1}')
  [[ -n "$cert_pub" && "$cert_pub" == "$key_pub" ]] || die "Custom certificate and private key do not match"
}

backup_export() {
  local file=$1 target
  target=$(cfg BACKUP_EXPORT_DIR 2>/dev/null || true)
  [[ -n "$target" ]] || return 0
  [[ "$target" =~ ^/[A-Za-z0-9._/-]+$ ]] || die "BACKUP_EXPORT_DIR must be a safe absolute path"
  [[ "$target" != "$STATE_DIR" && "$target" != "$STATE_DIR/"* ]] || die "BACKUP_EXPORT_DIR must be outside the local deployment state"
  [[ -d "$target" && -w "$target" ]] || die "BACKUP_EXPORT_DIR must be an existing writable mounted directory"
  install -m 0600 "$file" "$target/${file##*/}"
  info "Backup exported: $target/${file##*/}"
}

# The generic update library predates MariaDB-only deployments and used the
# old SQLite data directory as part of its disk estimate. MariaDB data lives in
# a Docker volume, so that path must not be required. Keep a conservative 1 GiB
# safety margin in addition to the source/image build estimate.
check_update_disk() {
  local source_kb required free
  source_kb=$(du -sk "$SCRIPT_DIR" | awk '{print $1}')
  required=$((source_kb * 3 + 1048576))
  free=$(df -Pk "$STATE_DIR" | awk 'NR==2 {print $4}')
  ((free >= required)) || die "Insufficient disk space: ${required} KiB required for source, images, and MariaDB backup safety margin; ${free} KiB available."
}

rotate_local_database_password() {
  local mode old_file tmp old new
  mode=$(cfg DATABASE_MODE)
  [[ "$mode" == mariadb-local ]] || die "Database password rotation is supported only for local MariaDB"
  old_file="$STATE_DIR/secrets/mariadb_local_password"
  old=$(cat "$old_file")
  new=$(secure_random)
  tmp=$(mktemp "$STATE_DIR/secrets/.database-password.XXXXXX")
  TEMP_FILES+=("$tmp")
  printf '%s' "$new" > "$tmp"
  chown root:10001 "$tmp"; chmod 0440 "$tmp"
  dc exec -T mariadb sh -ceu 'root=$(mktemp); trap '\''rm -f "$root"'\'' EXIT; umask 077; printf "[client]\npassword=%s\n" "$(cat /run/secrets/mariadb_root_password)" > "$root"; mariadb --defaults-extra-file="$root" -uroot -e "ALTER USER '\''$MARIADB_USER'\''@'\''%'\'' IDENTIFIED BY '\''$1'\'';"' sh "$new"
  mv -f "$tmp" "$old_file"
  if dc up -d --force-recreate --wait backend && health; then
    info "Local MariaDB password rotated successfully."
    return 0
  fi
  info "Password rotation health check failed; restoring the previous credential." >&2
  dc exec -T mariadb sh -ceu 'root=$(mktemp); trap '\''rm -f "$root"'\'' EXIT; umask 077; printf "[client]\npassword=%s\n" "$(cat /run/secrets/mariadb_root_password)" > "$root"; mariadb --defaults-extra-file="$root" -uroot -e "ALTER USER '\''$MARIADB_USER'\''@'\''%'\'' IDENTIFIED BY '\''$1'\'';"' sh "$old" || true
  printf '%s' "$old" > "$old_file"; chown root:10001 "$old_file"; chmod 0440 "$old_file"
  dc up -d --force-recreate --wait backend >/dev/null 2>&1 || true
  die "Database password rotation failed and was rolled back"
}
