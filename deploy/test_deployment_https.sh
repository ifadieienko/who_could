#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STATE=${RUNNER_TEMP:-/tmp}/who-could-smoke-https
export COMPOSE_PROJECT_NAME=who-could-ci-https
FILES=(-f "$ROOT/compose.yaml" -f "$ROOT/compose.mariadb.yaml" -f "$ROOT/compose.https.yaml")
compose() { DEPLOYMENT_ENV="$STATE/config/deployment.env" docker compose --env-file "$STATE/config/deployment.env" "${FILES[@]}" "$@"; }
cleanup() { compose down -v --remove-orphans >/dev/null 2>&1 || true; sudo rm -rf "$STATE"; }
failed() { local rc=$?; if ((rc)); then echo '::error::FAILED: custom HTTPS smoke'; compose ps || true; compose logs --tail=150 mariadb backend web || true; fi; cleanup; exit "$rc"; }
trap failed EXIT

mkdir -p "$STATE"/{config,secrets,certs/custom,state/acme}
printf '%s' 'APP_SECRET_MARKER_TLS_0123456789abcdef012345' > "$STATE/secrets/app_secret"
printf '%s' 'MARIADB_PASSWORD_MARKER_TLS_0123456789abcdef' > "$STATE/secrets/mariadb_local_password"
printf '%s' 'MARIADB_ROOT_MARKER_TLS_0123456789abcdef01' > "$STATE/secrets/mariadb_root_password"
printf '%s' 'EXTERNAL_PASSWORD_MARKER_TLS_0123456789abcd' > "$STATE/secrets/external_database_password"
chmod 0440 "$STATE/secrets/"*; chgrp "$(id -g)" "$STATE/secrets/"*
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost -keyout "$STATE/certs/custom/privkey.pem" -out "$STATE/certs/custom/fullchain.pem"
chgrp -R "$(id -g)" "$STATE/certs"; find "$STATE/certs" -type d -exec chmod 0750 {} +; chmod 0640 "$STATE/certs/custom/"*
sed -e 's/__HOSTNAME__/localhost/g' -e 's/__HTTPS_PORT__/18443/g' -e 's|__CERTIFICATE__|/etc/letsencrypt/custom/fullchain.pem|g' -e 's|__PRIVATE_KEY__|/etc/letsencrypt/custom/privkey.pem|g' "$ROOT/docker/nginx/site-https.conf.template" > "$STATE/config/site.conf"
touch "$STATE/config/database-ca.pem"
cat > "$STATE/config/deployment.env" <<EOF
CONFIG_VERSION=2
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
ALLOW_INSECURE_PUBLIC_HTTP=false
HTTP_PORT=18080
HTTPS_PORT=18443
HTTPS_MODE=custom
APP_SECRET_FILE=$STATE/secrets/app_secret
MARIADB_LOCAL_PASSWORD_FILE=$STATE/secrets/mariadb_local_password
MARIADB_ROOT_PASSWORD_FILE=$STATE/secrets/mariadb_root_password
EXTERNAL_DATABASE_PASSWORD_FILE=$STATE/secrets/external_database_password
DATABASE_PASSWORD_CONTAINER_FILE=/run/secrets/mariadb_local_password
DATABASE_SSL_CA_FILE=$STATE/config/database-ca.pem
CERTS_DIR=$STATE/certs
ACME_WEBROOT=$STATE/state/acme
NGINX_SITE_CONFIG=$STATE/config/site.conf
SECRETS_GID=$(id -g)
TLS_READER_GID=$(id -g)
BACKEND_IMAGE=who-could-backend:ci
WEB_IMAGE=who-could-web:ci
EOF
compose config --quiet
compose up -d --wait mariadb
compose run --rm --no-deps backend alembic upgrade head
compose up -d --wait backend web
[[ "$(compose exec -T web id -u)" != 0 ]]
compose exec -T web nginx -t
[[ "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/)" == 301 ]]
curl -kfsS https://127.0.0.1:18443/ -o /dev/null
curl -kfsS https://127.0.0.1:18443/api/health -o /dev/null
! find "$STATE/certs" -type f -perm /007 -print -quit | grep -q .
