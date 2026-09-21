"""Fast CI assertions for MariaDB-only Compose/security invariants."""
from pathlib import Path
import re

root = Path(__file__).parents[1]
for name in ("compose.yaml", "compose.https.yaml", "compose.mariadb.yaml", "compose.external.yaml"):
    text = (root / name).read_text()
    assert not re.search(r'[-" ](?:8000|3306):(?:8000|3306)', text), name
    assert "latest" not in text, name

assert not (root / "compose.sqlite.yaml").exists()
assert not (root / "compose.postgres.yaml").exists()
assert not (root / "docker/postgres").exists()

base = (root / "compose.yaml").read_text()
assert "WHO_COULD_SECRET_FILE: /run/secrets/app_secret" in base
assert "DATABASE_PASSWORD_FILE: ${DATABASE_PASSWORD_CONTAINER_FILE:-/run/secrets/mariadb_local_password}" in base
for secret in ("mariadb_local_password", "external_database_password"):
    assert secret in base
assert "postgres_local_password" not in base
assert "postgres_admin_password" not in base

backend_block = base.split("  backend:", 1)[1].split("  web:", 1)[0]
web_block = base.split("  web:", 1)[1].split("  certbot:", 1)[0]
certbot_block = base.split("  certbot:", 1)[1].split("\nnetworks:\n", 1)[0]
# Base backend mounts only the application secret. Database overlays add exactly
# the credential required by the selected MariaDB mode.
assert "secrets: [app_secret]" in backend_block
assert not re.search(r"^\s*secrets:\s*\[[^\]]*(mariadb_local_password|external_database_password)", backend_block, re.MULTILINE)
assert "networks: [frontend_network, database_network]" in backend_block
assert "edge_network" not in backend_block
assert "networks: [edge_network, frontend_network]" in web_block
assert "networks: [edge_network]" in certbot_block

mariadb = (root / "compose.mariadb.yaml").read_text()
assert "secrets: [mariadb_local_password]" in mariadb
assert "mariadb_root_password" in mariadb
assert "secrets: [external_database_password]" in (root / "compose.external.yaml").read_text()
assert "edge_network: {}" in base
assert "frontend_network: { internal: true }" in base
assert "database_network: { internal: true }" in base
assert "ports:" not in mariadb
assert '"${BIND_ADDRESS:-0.0.0.0}:${HTTP_PORT:-80}:8080"' in base
https_overlay = (root / "compose.https.yaml").read_text()
assert '"${BIND_ADDRESS:-0.0.0.0}:${HTTPS_PORT:-443}:8443"' in https_overlay

for template in ("site-http.conf.template", "site-https.conf.template"):
    nginx = (root / "docker/nginx" / template).read_text()
    assert "location ~ ^/api/auth" not in nginx
    assert "location = /api/auth/login" in nginx
    assert "proxy_pass http://backend:8000/auth/login;" in nginx
    assert "location /api/" in nginx
    assert "proxy_pass http://backend:8000/;" in nginx
assert "COPY docker/nginx/proxy_params /etc/nginx/proxy_params" in (root / "docker/web.Dockerfile").read_text()
https = (root / "docker/nginx/site-https.conf.template").read_text()
redirect_server = https.split("server {", 2)[1]
assert "location = /healthz" in redirect_server

manager = (root / "server.sh").read_text()
for secret in ("mariadb_local_password", "mariadb_root_password", "external_database_password"):
    assert f"secrets/{secret}" in manager
assert "postgresql" not in manager.lower()
assert "sqlite" not in manager.lower()
assert 'state/${mode}.identity' in manager
assert "Changing DATABASE_USER/DATABASE_NAME requires an explicit database migration" in manager
assert "--remove-orphans" in manager and "down -v" not in manager
