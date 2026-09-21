#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
# WHO_COULD_STATE_DIR is consumed by the sourced deployment library.
export WHO_COULD_STATE_DIR="$TMP"
# shellcheck source=server.sh
source "$ROOT/server.sh"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP"/{state,releases,state/releases}

expect_ref_rejected() { if valid_update_ref "$1"; then echo "unsafe ref accepted: $1" >&2; exit 1; fi; }
valid_update_ref origin/main
valid_update_ref refs/tags/v1.2.3
expect_ref_rejected --upload-pack=evil
expect_ref_rejected 'main; touch /tmp/unsafe'
expect_ref_rejected 'refs/heads/x@{1}'
expect_ref_rejected '../main'

sha=0123456789abcdef0123456789abcdef01234567
mkdir "$TMP/releases/$sha"
atomic_current_switch "$sha"
[[ -L "$TMP/current" && "$(readlink "$TMP/current")" == "releases/$sha" ]]
mkdir -p "$TMP/releases/${sha%?}8"
atomic_current_switch "${sha%?}8"
[[ "$(readlink "$TMP/current")" == "releases/${sha%?}8" ]]

release_write active_release "$sha"
[[ "$(release_read active_release)" == "$sha" ]]
chmod 0640 "$TMP/state/active_release"
[[ "$(stat -c %a "$TMP/state/active_release")" == 640 ]]

cat > "$TMP/config.env" <<EOF
BACKEND_IMAGE=registry.example/backend:v1
WEB_IMAGE=registry.example/web:v1
EOF
CONFIG_FILE="$TMP/config.env" # consumed by cfg() in the sourced library
if managed_images_only; then echo 'custom images were accepted' >&2; exit 1; fi
cat > "$TMP/config.env" <<EOF
BACKEND_IMAGE=who-could-backend:$sha
WEB_IMAGE=who-could-web:$sha
EOF
managed_images_only

active_sha="${sha%?}8"
mkdir -p "$TMP/state/releases/$active_sha"
printf 'active=%s\n' "$sha" > "$TMP/backup.db"
cat > "$TMP/state/releases/$active_sha/pre-update-backup" <<EOF
release_being_left=$sha
candidate_release=$active_sha
backup_path=$TMP/backup.db
EOF
release_write active_release "$active_sha"
release_write previous_release "$sha"
guard_output=$( (NON_INTERACTIVE=true; confirm_rollback_snapshot "$sha") 2>&1 || true)
if grep -q 'Non-interactive destructive rollback is not supported' <<<"$guard_output"; then :; else
  echo 'destructive rollback guard failed' >&2; exit 1
fi
older_sha="${sha%?}9"
wrong_output=$( (confirm_rollback_snapshot "$older_sha") 2>&1 || true)
grep -q 'only for the immediately previous release' <<<"$wrong_output"

acquire_state_lock
if flock -n "$TMP/state/server.lock" true; then echo 'exclusive state lock was not held' >&2; exit 1; fi
grep -Eq 'update\|rollback.*acquire_state_lock|update\).*acquire_state_lock' "$ROOT/server.sh"

if grep -En 'git (pull|reset --hard)|docker system prune -a|alembic downgrade|credential.helper|github.*token|PAT=' "$ROOT/server.sh" "$ROOT/deploy/update_rollback.sh"; then
  echo 'forbidden update operation found' >&2; exit 1
fi
grep -Eq 'EXTERNAL BACKUP CONFIRMED' "$ROOT/deploy/update_rollback.sh"
grep -Eq 'merge-base --is-ancestor' "$ROOT/deploy/update_rollback.sh"
grep -Eq 'mv -Tf' "$ROOT/deploy/update_rollback.sh"
expected_managed_tag="who-could-backend:\$sha"
grep -Fq "$expected_managed_tag" "$ROOT/deploy/update_rollback.sh"
[[ "$(cert_manager_path)" == "$ROOT/server.sh" ]]
cp "$ROOT/server.sh" "$TMP/current/server.sh"
chmod 0755 "$TMP/current/server.sh"
[[ "$(cert_manager_path)" == "$TMP/current/server.sh" ]]
printf 'server {}\n' > "$TMP/state/releases/$active_sha/site.conf"
cat > "$TMP/state/releases/$active_sha/successful" <<EOF
release=$active_sha
deployed_at=2026-08-30T02:00:00Z
status=healthy
EOF
mkdir -p "$TMP/state/releases/$sha"
printf 'server {}\n' > "$TMP/state/releases/$sha/site.conf"
cat > "$TMP/state/releases/$sha/successful" <<EOF
release=$sha
deployed_at=2026-08-30T01:00:00Z
status=healthy
EOF
# Case A: a prepared A -> B transition before the commit point must preserve Z.
previous_sha="${sha%?}6"
atomic_current_switch "$sha"
release_write active_release "$sha"
release_write installed_git_sha "$sha"
release_write previous_release "$previous_sha"
release_write last_successful_deployment '2026-08-30T01:00:00Z'
prepare_release_transition "$sha" "$active_sha" update
diagnostic_prepared=$(release_diagnostics)
grep -q "Current symlink        $sha" <<<"$diagnostic_prepared"
grep -q "Recorded previous      $previous_sha" <<<"$diagnostic_prepared"
grep -q 'Release state          CONSISTENT' <<<"$diagnostic_prepared"
activate_active_release_runtime reconcile
[[ "$(release_read previous_release)" == "$previous_sha" ]]

# Case B: power loss after the commit point reconciles all mirrors from A -> B.
atomic_current_switch "$active_sha"
diagnostic_before=$(release_diagnostics)
grep -q "Current symlink        $active_sha" <<<"$diagnostic_before"
grep -q "Recorded active        $sha" <<<"$diagnostic_before"
grep -q "Expected previous      $sha" <<<"$diagnostic_before"
grep -q 'Recorded deployment    2026-08-30T01:00:00Z' <<<"$diagnostic_before"
grep -q 'Expected deployment    2026-08-30T02:00:00Z' <<<"$diagnostic_before"
grep -q 'Release state          INCONSISTENT' <<<"$diagnostic_before"
[[ "$(release_read active_release)" == "$sha" ]]
history_before=$(releases_command)
grep -A1 '^ACTIVE$' <<<"$history_before" | grep -q "${active_sha:0:12}"
grep -A1 '^PREVIOUS$' <<<"$history_before" | grep -q "${sha:0:12}"
[[ "$(release_read active_release)" == "$sha" ]]
[[ "$(release_read previous_release)" == "$previous_sha" ]]
activate_active_release_runtime reconcile
[[ "$(release_read active_release)" == "$active_sha" ]]
[[ "$(release_read installed_git_sha)" == "$active_sha" ]]
[[ "$(release_read previous_release)" == "$sha" ]]
[[ "$(release_read last_successful_deployment)" == '2026-08-30T02:00:00Z' ]]
[[ "$RUNTIME_BACKEND_IMAGE" == "who-could-backend:$active_sha" ]]
[[ "$RUNTIME_WEB_IMAGE" == "who-could-web:$active_sha" ]]
[[ "$RUNTIME_NGINX_CONFIG" == "$TMP/state/releases/$active_sha/site.conf" ]]

malformed_sha="${sha%?}9"
mkdir -p "$TMP/releases/$malformed_sha" "$TMP/state/releases/$malformed_sha"
printf 'server {}\n' > "$TMP/state/releases/$malformed_sha/site.conf"
ln -sfn "releases/$malformed_sha" "$TMP/current.new"
mv -Tf "$TMP/current.new" "$TMP/current"
malformed_output=$( (activate_active_release_runtime reconcile) 2>&1 || true)
grep -q 'invalid or does not point to a marked successful release' <<<"$malformed_output"
[[ "$(release_read active_release)" == "$active_sha" ]]
atomic_current_switch "$active_sha"

# Rollback INT/TERM share the same deterministic interruption recovery helper.
interrupt_calls="$TMP/rollback-interrupt-calls"
recover_failed_rollback() { printf '%s\n' "$*" >> "$interrupt_calls"; }
ROLLBACK_CURRENT=$active_sha ROLLBACK_TARGET=$sha ROLLBACK_EMERGENCY='' ROLLBACK_DATABASE_MUTATED=false ROLLBACK_STAGE='target health'
if (rollback_interrupted) >/dev/null 2>&1; then echo 'rollback interruption unexpectedly succeeded' >&2; exit 1; else [[ $? == 130 ]]; fi
grep -qx "$active_sha" "$interrupt_calls"
: > "$interrupt_calls"
ROLLBACK_CURRENT=$active_sha ROLLBACK_TARGET=$sha ROLLBACK_EMERGENCY="$TMP/backup.db" ROLLBACK_DATABASE_MUTATED=true ROLLBACK_STAGE='database restore'
if (rollback_interrupted) >/dev/null 2>&1; then echo 'destructive rollback interruption unexpectedly succeeded' >&2; exit 1; else [[ $? == 130 ]]; fi
grep -qx "$active_sha $TMP/backup.db" "$interrupt_calls"

# A pre-migration failure only starts/checks the previous release. It must not
# invoke native_restore or print external-provider restore guidance.
pre_mutation_calls="$TMP/pre-mutation-calls"
release_runtime() { printf 'release %s\n' "$1" >> "$pre_mutation_calls"; }
dc() { printf 'compose %s\n' "$*" >> "$pre_mutation_calls"; }
full_release_health() { printf 'health\n' >> "$pre_mutation_calls"; }
recover_pre_mutation_failure "$sha" connectivity 2> "$TMP/pre-mutation-output"
if grep -Eq 'native_restore|provider snapshot|Restore the provider' "$pre_mutation_calls" "$TMP/pre-mutation-output"; then
  echo 'pre-mutation recovery attempted database/provider restore' >&2; exit 1
fi

echo 'Update/rollback static safety tests: PASS'
