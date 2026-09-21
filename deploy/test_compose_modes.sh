#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT
mkdir -p "$STATE"/{config,secrets,certs,state/acme}
touch "$STATE/config/"{site.conf,database-ca.pem} "$STATE/secrets/"{app_secret,mariadb_local_password,external_database_password,mariadb_root_password}

validate_mode() {
  local mode=$1 overlay=$2 host=$3 password=$4 extra=${5:-}
  cat > "$STATE/config/deployment.env" <<EOF
CONFIG_VERSION=2
DATABASE_MODE=$mode
DATABASE_ENGINE=mariadb
DATABASE_HOST=$host
DATABASE_PORT=3306
DATABASE_NAME=who_could
DATABASE_USER=who_could
DATABASE_SSL_CA=/run/config/database-ca.pem
HTTPS_MODE=disabled
HTTP_PORT=18080
HTTPS_PORT=18443
APP_SECRET_FILE=$STATE/secrets/app_secret
MARIADB_LOCAL_PASSWORD_FILE=$STATE/secrets/mariadb_local_password
EXTERNAL_DATABASE_PASSWORD_FILE=$STATE/secrets/external_database_password
MARIADB_ROOT_PASSWORD_FILE=$STATE/secrets/mariadb_root_password
DATABASE_PASSWORD_CONTAINER_FILE=/run/secrets/$password
DATABASE_SSL_CA_FILE=$STATE/config/database-ca.pem
NGINX_SITE_CONFIG=$STATE/config/site.conf
CERTS_DIR=$STATE/certs
ACME_WEBROOT=$STATE/state/acme
EOF
  local files=(-f "$ROOT/compose.yaml" -f "$ROOT/$overlay")
  if [[ -n "$extra" ]]; then files+=(-f "$ROOT/$extra"); fi
  DEPLOYMENT_ENV="$STATE/config/deployment.env" docker compose --env-file "$STATE/config/deployment.env" "${files[@]}" config --quiet
  if [[ "$mode" == mariadb-external ]]; then
    local mounted
    mounted=$(DEPLOYMENT_ENV="$STATE/config/deployment.env" docker compose --env-file "$STATE/config/deployment.env" "${files[@]}" config --format json | python3 -c 'import json,sys; print(" ".join(x["source"] for x in json.load(sys.stdin)["services"]["backend"]["secrets"]))')
    grep -qw app_secret <<<"$mounted"
    grep -qw external_database_password <<<"$mounted"
    ! grep -qw mariadb_local_password <<<"$mounted"
  fi
}

validate_mode mariadb-local compose.mariadb.yaml mariadb mariadb_local_password
validate_mode mariadb-external compose.external.yaml db.example.test external_database_password
validate_mode mariadb-local compose.mariadb.yaml mariadb mariadb_local_password compose.https.yaml
