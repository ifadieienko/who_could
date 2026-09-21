#!/usr/bin/env bash
set -Eeuo pipefail

MODE=${1:-mariadb}
[[ "$MODE" == mariadb ]] || { echo "Only MariaDB smoke testing is supported" >&2; exit 2; }
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STATE=${RUNNER_TEMP:-/tmp}/who-could-smoke-mariadb
export WHO_COULD_STATE_DIR=$STATE COMPOSE_PROJECT_NAME=who-could-ci-mariadb
CURRENT_CHECK=setup
FILES=(-f "$ROOT/compose.yaml" -f "$ROOT/compose.mariadb.yaml")
compose() { DEPLOYMENT_ENV="$STATE/config/deployment.env" docker compose --env-file "$STATE/config/deployment.env" "${FILES[@]}" "$@"; }

diagnostics() {
  echo "::error::FAILED: $CURRENT_CHECK"
  compose ps || true
  compose logs --tail=150 backend web mariadb || true
  local service container
  for service in backend web mariadb; do
    container=$(compose ps -q "$service" 2>/dev/null || true)
    if [[ -n "$container" ]]; then docker inspect --format '{{json .State.Health}}' "$container" || true; fi
  done
}
cleanup() { compose down -v --remove-orphans >/dev/null 2>&1 || true; sudo rm -rf "$STATE"; }
finish() { local rc=$?; if ((rc)); then diagnostics; fi; cleanup; exit "$rc"; }
trap finish EXIT
run_check() {
  local name=$1
  shift
  CURRENT_CHECK=$name
  echo "::group::$name"
  "$@"
  echo "PASS: $name"
  echo "::endgroup::"
}

rm -rf "$STATE"
mkdir -p "$STATE"/{config,secrets,certs,state/acme,backups}
touch "$STATE/config/database-ca.pem"
printf '%s' 'APP_SECRET_MARKER_0123456789abcdef0123456789' > "$STATE/secrets/app_secret"
printf '%s' 'MARIADB_PASSWORD_MARKER_0123456789abcdef012' > "$STATE/secrets/mariadb_local_password"
printf '%s' 'MARIADB_ROOT_MARKER_0123456789abcdef0123' > "$STATE/secrets/mariadb_root_password"
printf '%s' 'EXTERNAL_PASSWORD_MARKER_0123456789abcdef01' > "$STATE/secrets/external_database_password"
chgrp "$(id -g)" "$STATE/secrets/"*
chmod 0440 "$STATE/secrets/"*
sed 's/__HOSTNAME__/localhost/g' "$ROOT/docker/nginx/site-http.conf.template" > "$STATE/config/site.conf"
cat > "$STATE/config/deployment.env" <<EOF
CONFIG_VERSION=2
HOST_SECURITY_REQUESTED=false
HOST_SECURITY_ENABLED=false
CROWDSEC_ENABLED=false
HOST_FIREWALL_ENABLED=false
SSH_PORT=22
DATABASE_MODE=mariadb-local
DATABASE_ENGINE=mariadb
DATABASE_HOST=mariadb
DATABASE_PORT=3306
DATABASE_NAME=who_could
DATABASE_USER=who_could
DATABASE_SSLMODE=
DATABASE_SSL_CA=
PUBLIC_HOSTNAME=localhost
BIND_ADDRESS=0.0.0.0
ALLOW_INSECURE_PUBLIC_HTTP=true
HTTP_PORT=18080
HTTPS_PORT=18443
HTTPS_MODE=disabled
APP_SECRET_FILE=$STATE/secrets/app_secret
MARIADB_LOCAL_PASSWORD_FILE=$STATE/secrets/mariadb_local_password
MARIADB_ROOT_PASSWORD_FILE=$STATE/secrets/mariadb_root_password
EXTERNAL_DATABASE_PASSWORD_FILE=$STATE/secrets/external_database_password
DATABASE_PASSWORD_CONTAINER_FILE=/run/secrets/mariadb_local_password
CERTS_DIR=$STATE/certs
ACME_WEBROOT=$STATE/state/acme
NGINX_SITE_CONFIG=$STATE/config/site.conf
DATABASE_SSL_CA_FILE=$STATE/config/database-ca.pem
SECRETS_GID=$(id -g)
TLS_READER_GID=$(id -g)
BACKEND_IMAGE=who-could-backend:ci
WEB_IMAGE=who-could-web:ci
EOF

run_check "compose config (mariadb)" compose config --quiet
run_check "mariadb database healthy" compose up -d --wait mariadb
run_check "Alembic upgrade (mariadb)" compose run --rm --no-deps backend alembic upgrade head
run_check "Alembic check (mariadb)" compose run --rm --no-deps backend alembic check
run_check "backend and web healthy (mariadb)" compose up -d --wait backend web
run_check "nginx config (mariadb)" compose exec -T web nginx -t
run_check "frontend HTTP (mariadb)" curl --retry 10 --retry-connrefused -fsS http://127.0.0.1:18080/ -o /dev/null
run_check "API health (mariadb)" curl -fsS http://127.0.0.1:18080/api/health -o /dev/null
run_check "register user (mariadb)" curl -fsS -X POST -H 'Content-Type: application/json' --data '{"name":"Backup Test","email":"backup@example.com","password":"safe-password-123","city":null,"bio":null,"skills":null}' http://127.0.0.1:18080/api/auth/register -o /dev/null

container_port_unpublished() {
  local service=$1 port=$2 container
  container=$(compose ps -q "$service")
  docker inspect "$container" | python3 -c 'import json,sys; data=json.load(sys.stdin)[0]; port=sys.argv[1]; assert not data["NetworkSettings"]["Ports"].get(f"{port}/tcp")' "$port"
}
check_backend_port() { container_port_unpublished backend 8000; }
check_db_port() { container_port_unpublished mariadb 3306; }
check_non_root() { [[ "$(compose exec -T backend id -u)" != 0 ]]; }
check_secret_mounts() {
  compose exec -T backend sh -ceu '
    test -f /run/secrets/app_secret
    test -f /run/secrets/mariadb_local_password
    test ! -e /run/secrets/external_database_password'
}
check_inspect_leaks() {
  local service inspect secret marker
  for service in backend web mariadb; do
    inspect=$(docker inspect "$(compose ps -q "$service")")
    for secret in "$STATE/secrets/"*; do
      marker=$(cat "$secret")
      if [[ -n "$marker" ]] && grep -Fq "$marker" <<<"$inspect"; then return 1; fi
    done
  done
}
run_check "backend host port unpublished (mariadb)" check_backend_port
run_check "database host port unpublished (mariadb)" check_db_port
run_check "backend non-root (mariadb)" check_non_root
run_check "least-privilege secret mounts (mariadb)" check_secret_mounts
run_check "secret values absent from inspect (mariadb)" check_inspect_leaks

backup_restore() {
  sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME "$ROOT/server.sh" backup
  local backup
  backup=$(find "$STATE/backups" -type f | sort | tail -1)
  compose exec -T backend python -c 'from app.database import engine; from app.models import User; from sqlalchemy import delete; c=engine.connect(); t=c.begin(); c.execute(delete(User).where(User.email == "backup@example.com")); t.commit(); c.close()'
  [[ "$(curl -sS -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' --data '{"email":"backup@example.com","password":"safe-password-123"}' http://127.0.0.1:18080/api/auth/login)" == 401 ]]
  printf 'RESTORE\n' | sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME "$ROOT/server.sh" restore "$backup"
  curl -fsS -X POST -H 'Content-Type: application/json' --data '{"email":"backup@example.com","password":"safe-password-123"}' http://127.0.0.1:18080/api/auth/login -o /dev/null
  compose run --rm --no-deps backend alembic check
  curl -fsS http://127.0.0.1:18080/api/health -o /dev/null
}
run_check "backup and restore round trip (mariadb)" backup_restore
run_check "transactional update and rollback (mariadb)" "$ROOT/deploy/test_update_smoke.sh" mariadb "$ROOT"
