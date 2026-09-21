#!/usr/bin/env bash
set -Eeuo pipefail

MODE=${1:?Usage: test_update_smoke.sh sqlite|postgresql|mariadb}
ROOT=${2:?repository root required}
STATE=${WHO_COULD_STATE_DIR:?}
: "${COMPOSE_PROJECT_NAME:?}"
TMP=$(mktemp -d "${RUNNER_TEMP:-/tmp}/who-could-update-${MODE}.XXXXXX")
trap 'rm -rf "$TMP"' EXIT

state_read() {
  sudo cat "$STATE/state/$1"
}

state_file_exists() {
  sudo test -f "$1"
}

state_readlink() {
  sudo readlink "$1"
}

latest_backup() {
  sudo find "$STATE/backups" -maxdepth 1 -type f -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-
}

echo 'update-smoke: preparing release A'
mkdir -p "$TMP/source"
git -C "$ROOT" archive HEAD | tar -x -C "$TMP/source"
git -C "$TMP/source" init -q -b main
git -C "$TMP/source" config user.name 'Who could CI'
git -C "$TMP/source" config user.email 'ci@example.invalid'
# Make release A's generated Nginx configuration observable.
sed -i '/server_name __HOSTNAME__;/a\\  add_header X-Release-Marker A always;' "$TMP/source/docker/nginx/site-http.conf.template"
git -C "$TMP/source" add -A
git -C "$TMP/source" commit -qm 'test: release A nginx marker'
A=$(git -C "$TMP/source" rev-parse HEAD)
[[ "$(git -C "$TMP/source" rev-parse --is-shallow-repository)" == false ]]
if git -C "$TMP/source" rev-parse "$A^" >/dev/null 2>&1; then
  echo 'release A fixture unexpectedly has a parent' >&2
  exit 1
fi
git init --bare -q "$TMP/origin.git"
git -C "$TMP/source" remote add origin "$TMP/origin.git"
git -C "$TMP/source" push -q origin HEAD:refs/heads/main

# Existing smoke images are exact build equivalents of release A. Tag them so
# automatic recovery can prove that it returns to the release-specific images.
docker tag who-could-backend:ci "who-could-backend:$A"
docker tag who-could-web:ci "who-could-web:$A"
sed -i '/^BACKEND_IMAGE=/d;/^WEB_IMAGE=/d' "$STATE/config/deployment.env"
printf '%s\n' "$A" > "$STATE/state/installed_git_sha"
sudo git config --global --add safe.directory "$TMP/source"
sudo git config --global protocol.file.allow always

printf 'release B fixture\n' > "$TMP/source/deploy/.update-smoke-release"
echo 'update-smoke: preparing release B'
sed -i 's/X-Release-Marker A/X-Release-Marker B/' "$TMP/source/docker/nginx/site-http.conf.template"
cat > "$TMP/source/backend/migrations/versions/ci_release_b.py" <<'PY'
"""CI-only migration used to prove exact rollback revision checks."""
from alembic import op
import sqlalchemy as sa

revision = "ci_release_b"
down_revision = "0008_master_service_board"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("ci_release_b", sa.Column("id", sa.Integer(), primary_key=True))

def downgrade():
    op.drop_table("ci_release_b")
PY
cat >> "$TMP/source/backend/app/models.py" <<'PY'


class CIReleaseB(Base):
    __tablename__ = "ci_release_b"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
PY
git -C "$TMP/source" add deploy/.update-smoke-release
git -C "$TMP/source" add docker/nginx/site-http.conf.template backend/app/models.py backend/migrations/versions/ci_release_b.py
git -C "$TMP/source" commit -qm 'test: healthy update candidate'
B=$(git -C "$TMP/source" rev-parse HEAD)
git -C "$TMP/source" push -q origin HEAD:refs/heads/main

run_server() { sudo --preserve-env=WHO_COULD_STATE_DIR,COMPOSE_PROJECT_NAME "$TMP/source/server.sh" "$@"; }
assert_fixture_user() {
  local container
  container=$(docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --filter 'label=com.docker.compose.service=backend' | head -1)
  [[ -n "$container" ]]
  docker exec -i "$container" python - <<'PY'
from sqlalchemy import func, select
from app.database import SessionLocal
from app.models import User
from app.security import verify_password

with SessionLocal() as session:
    users = session.scalars(select(User).where(func.lower(User.email) == "backup@example.com")).all()
print(f"update-smoke: fixture user rows={len(users)}")
assert len(users) == 1, "backup fixture user is missing or duplicated"
assert verify_password("safe-password-123", users[0].password_hash), "backup fixture password hash no longer verifies"
PY
}

echo 'update-smoke: verify fixture before update'
assert_fixture_user
echo 'update-smoke: update --check'
run_server update --check | grep -F "Available release   $B"
echo 'update-smoke: update B'
run_server update
[[ "$(state_read active_release)" == "$B" ]]
[[ "$(state_read previous_release)" == "$A" ]]
echo 'update-smoke: verify fixture after update'
assert_fixture_user
curl -fsS -X POST -H 'Content-Type: application/json' --data '{"email":"backup@example.com","password":"safe-password-123"}' http://127.0.0.1:18080/api/auth/login -o /dev/null
curl -fsSI http://127.0.0.1:18080/ | grep -qi '^X-Release-Marker: B'

assert_release_images() {
  local release=$1 backend_container web_container
  backend_container=$(docker ps -aq --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --filter 'label=com.docker.compose.service=backend' | head -1)
  web_container=$(docker ps -aq --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --filter 'label=com.docker.compose.service=web' | head -1)
  [[ "$(docker inspect -f '{{.Image}}' "$backend_container")" == "$(docker image inspect -f '{{.Id}}' "who-could-backend:$release")" ]]
  [[ "$(docker inspect -f '{{.Image}}' "$web_container")" == "$(docker image inspect -f '{{.Id}}' "who-could-web:$release")" ]]
}

run_server stop
run_server start
run_server health
[[ "$(state_read active_release)" == "$B" ]]
assert_release_images "$B"
curl -fsSI http://127.0.0.1:18080/ | grep -qi '^X-Release-Marker: B'

run_server backup
restore_backup=$(latest_backup)
printf 'RESTORE\n' | run_server restore "$restore_backup"
[[ "$(state_read active_release)" == "$B" ]]
assert_release_images "$B"
curl -fsSI http://127.0.0.1:18080/ | grep -qi '^X-Release-Marker: B'

run_server configure --non-interactive
[[ "$(state_read active_release)" == "$B" ]]
[[ "$(state_read installed_git_sha)" == "$B" ]]
assert_release_images "$B"
curl -fsSI http://127.0.0.1:18080/ | grep -qi '^X-Release-Marker: B'

if run_server rollback "$A"; then echo 'revision-incompatible code rollback unexpectedly succeeded' >&2; exit 1; fi
[[ "$(state_read active_release)" == "$B" ]]
assert_release_images "$B"
run_server health

printf 'ROLLBACK WITH DATA LOSS\n' | run_server rollback "$A" --restore-database
[[ "$(state_read active_release)" == "$A" ]]
curl -fsS -X POST -H 'Content-Type: application/json' --data '{"email":"backup@example.com","password":"safe-password-123"}' http://127.0.0.1:18080/api/auth/login -o /dev/null
curl -fsSI http://127.0.0.1:18080/ | grep -qi '^X-Release-Marker: A'

# This candidate builds and migrates, then its deliberately failing web health
# check forces the post-migration automatic database recovery path.
python3 - "$TMP/source/compose.yaml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
needle = "healthcheck: { test: [CMD, wget, -qO-, http://127.0.0.1:8080/healthz],"
assert needle in s
p.write_text(s.replace(needle, 'healthcheck: { test: [CMD, "false"],'))
p.write_text(p.read_text().replace("interval: 10s, timeout: 5s, retries: 12 }", "interval: 1s, timeout: 1s, retries: 3 }"))
PY
cat > "$TMP/source/backend/migrations/versions/ci_update_probe.py" <<'PY'
"""CI-only portable migration proving snapshot recovery after DB mutation."""
from alembic import op
import sqlalchemy as sa

revision = "ci_update_probe"
down_revision = "ci_release_b"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("ci_update_probe", sa.Column("id", sa.Integer(), primary_key=True))

def downgrade():
    op.drop_table("ci_update_probe")
PY
cat >> "$TMP/source/backend/app/models.py" <<'PY'


class CIUpdateProbe(Base):
    __tablename__ = "ci_update_probe"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
PY
git -C "$TMP/source" add compose.yaml backend/app/models.py backend/migrations/versions/ci_update_probe.py
git -C "$TMP/source" commit -qm 'test: post-migration health failure candidate'
C=$(git -C "$TMP/source" rev-parse HEAD)
echo 'update-smoke: preparing broken candidate C'
git -C "$TMP/source" push -q origin HEAD:refs/heads/main

failure_log="$TMP/failed-update.log"
echo 'update-smoke: verifying post-migration recovery'
if run_server update 2>&1 | tee "$failure_log"; then echo 'broken candidate unexpectedly succeeded' >&2; exit 1; fi
python3 - "$failure_log" <<'PY'
from pathlib import Path
import sys
s = Path(sys.argv[1]).read_text()
ordered = ["backend stopped", "backup validated", "migration started"]
positions = [s.index(item) for item in ordered]
assert positions == sorted(positions), positions
assert "Update failed at: web health" in s
assert "Automatic rollback: SUCCESS" in s
PY
[[ "$(state_read active_release)" == "$A" ]]
if state_file_exists "$STATE/state/releases/$C/successful"; then
  echo 'failed candidate C was unexpectedly marked successful' >&2
  exit 1
fi
state_file_exists "$STATE/state/releases/$C/pre-update-backup"
curl -fsS -X POST -H 'Content-Type: application/json' --data '{"email":"backup@example.com","password":"safe-password-123"}' http://127.0.0.1:18080/api/auth/login -o /dev/null
container=$(docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT_NAME" --filter 'label=com.docker.compose.service=backend' | head -1)
[[ -n "$container" ]]
docker exec "$container" python -c 'from app.database import engine; from sqlalchemy import inspect; tables=set(inspect(engine).get_table_names()); assert "ci_update_probe" not in tables; assert "ci_release_b" not in tables'

# A code-only rollback target that passes the exact revision guard but fails web
# health must recover the still-active release A without committing target state.
git -C "$TMP/source" checkout -q --detach "$A"
python3 - "$TMP/source/compose.yaml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
needle = "healthcheck: { test: [CMD, wget, -qO-, http://127.0.0.1:8080/healthz],"
assert needle in s
p.write_text(s.replace(needle, 'healthcheck: { test: [CMD, "false"],'))
p.write_text(p.read_text().replace("interval: 10s, timeout: 5s, retries: 12 }", "interval: 1s, timeout: 1s, retries: 3 }"))
PY
git -C "$TMP/source" add compose.yaml
git -C "$TMP/source" commit -qm 'test: failing code rollback target'
D=$(git -C "$TMP/source" rev-parse HEAD)
sudo mkdir -p "$STATE/releases/$D" "$STATE/state/releases/$D"
git -C "$TMP/source" archive "$D" | sudo tar -x -C "$STATE/releases/$D"
sudo cp "$STATE/state/releases/$A/site.conf" "$STATE/state/releases/$D/site.conf"
printf 'release=%s\ndeployed_at=2026-08-30T00:00:00Z\nstatus=healthy\n' "$D" | sudo tee "$STATE/state/releases/$D/successful" >/dev/null
sudo chmod 0640 "$STATE/state/releases/$D/successful"
docker tag "who-could-backend:$A" "who-could-backend:$D"
docker tag "who-could-web:$A" "who-could-web:$D"
if run_server rollback "$D"; then echo 'broken rollback target unexpectedly succeeded' >&2; exit 1; fi
[[ "$(state_read active_release)" == "$A" ]]
[[ "$(state_readlink "$STATE/current")" == "releases/$A" ]]
assert_release_images "$A"
run_server health
curl -fsSI http://127.0.0.1:18080/ | grep -qi '^X-Release-Marker: A'

echo "Update and post-migration recovery smoke ($MODE): PASS"
