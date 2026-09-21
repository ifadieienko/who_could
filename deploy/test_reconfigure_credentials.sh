#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/input"
cat > "$TMP/bin/docker" <<'EOF'
#!/bin/sh
exit 0
EOF
cat > "$TMP/bin/curl" <<'EOF'
#!/bin/sh
exit 0
EOF
chmod +x "$TMP/bin/docker" "$TMP/bin/curl"
printf '%s' 'app-secret-marker-with-more-than-thirty-two-characters' > "$TMP/input/app"
printf '%s' 'mariadb-original-password' > "$TMP/input/mariadb"
printf '%s' 'mariadb-root-password' > "$TMP/input/root"
printf '%s' 'external-mariadb-password' > "$TMP/input/external"
printf '%s' 'dummy-ca' > "$TMP/input/ca.pem"
chmod 0600 "$TMP/input/"*

write_preseed() {
  local mode=$1 name=$2 user=$3 password_file=$4
  cat > "$TMP/preseed" <<EOF
DATABASE_MODE=$mode
PUBLIC_HOSTNAME=localhost
HTTP_PORT=19080
HTTPS_PORT=19443
HTTPS_MODE=disabled
DATABASE_NAME=$name
DATABASE_USER=$user
WHO_COULD_SECRET_FILE=$TMP/input/app
DATABASE_PASSWORD_FILE=$password_file
EOF
  if [[ "$mode" == mariadb-local ]]; then
    printf 'MARIADB_ROOT_PASSWORD_FILE=%s\n' "$TMP/input/root" >> "$TMP/preseed"
  else
    cat >> "$TMP/preseed" <<EOF
DATABASE_HOST=db.example.test
DATABASE_PORT=3306
DATABASE_SSL_CA_SOURCE=$TMP/input/ca.pem
EOF
  fi
}
run_manager() {
  PATH="$TMP/bin:$PATH" WHO_COULD_STATE_DIR="$TMP/state" "$ROOT/server.sh" "$@" --non-interactive --config "$TMP/preseed"
}

write_preseed mariadb-local maria_database maria_user "$TMP/input/mariadb"
run_manager install
maria_hash=$(sha256sum "$TMP/state/secrets/mariadb_local_password" | cut -d' ' -f1)
grep -qx 'DATABASE_NAME=maria_database' "$TMP/state/state/mariadb-local.identity"
grep -qx 'DATABASE_USER=maria_user' "$TMP/state/state/mariadb-local.identity"

write_preseed mariadb-local maria_database maria_user "$TMP/input/mariadb"
run_manager configure
test "$(sha256sum "$TMP/state/secrets/mariadb_local_password" | cut -d' ' -f1)" = "$maria_hash"

write_preseed mariadb-local forbidden_new_name forbidden_new_user "$TMP/input/mariadb"
if run_manager configure >/dev/null 2>&1; then
  echo 'Local MariaDB identity mutation was unexpectedly accepted' >&2
  exit 1
fi
