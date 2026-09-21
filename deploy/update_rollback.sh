#!/usr/bin/env bash
# Transactional release/update support. This file is sourced by server.sh.

UPDATE_TRANSACTION_ACTIVE=false
UPDATE_DATABASE_MUTATED=false
UPDATE_PREVIOUS=''
UPDATE_CANDIDATE=''
UPDATE_BACKUP=''
UPDATE_FAILURE_STAGE='interruption'
ROLLBACK_SNAPSHOT=''
ROLLBACK_CURRENT=''
ROLLBACK_TARGET=''
ROLLBACK_EMERGENCY=''
ROLLBACK_DATABASE_MUTATED=false
ROLLBACK_STAGE='initialization'

update_interrupted() {
  trap - INT TERM
  if $UPDATE_TRANSACTION_ACTIVE; then
    if $UPDATE_DATABASE_MUTATED; then
      recover_failed_update "$UPDATE_PREVIOUS" "$UPDATE_CANDIDATE" "$UPDATE_BACKUP" "$UPDATE_FAILURE_STAGE" || true
    else
      recover_pre_mutation_failure "$UPDATE_PREVIOUS" "$UPDATE_FAILURE_STAGE" || true
    fi
  fi
  cleanup
  printf 'Update interrupted at: %s\n' "$UPDATE_FAILURE_STAGE" >&2
  exit 130
}

rollback_interrupted() {
  trap - INT TERM
  if [[ -n "$ROLLBACK_CURRENT" ]]; then
    if $ROLLBACK_DATABASE_MUTATED; then
      recover_failed_rollback "$ROLLBACK_CURRENT" "$ROLLBACK_EMERGENCY" || true
    else
      recover_failed_rollback "$ROLLBACK_CURRENT" || true
    fi
  fi
  printf 'Rollback interrupted at: %s\nCurrent release: %s\nTarget release: %s\nEmergency backup: %s\nManual recovery: WHO_COULD_STATE_DIR=%q %q start\n' "$ROLLBACK_STAGE" "$ROLLBACK_CURRENT" "$ROLLBACK_TARGET" "${ROLLBACK_EMERGENCY:-not-created}" "$STATE_DIR" "$STATE_DIR/current/server.sh" >&2
  exit 130
}

release_read() {
  local name=$1 value
  [[ "$name" =~ ^[a-z_]+$ && -f "$STATE_DIR/state/$name" ]] || return 1
  IFS= read -r value < "$STATE_DIR/state/$name"
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || return 1
  printf '%s' "$value"
}

release_write() {
  local name=$1 value=$2 tmp
  [[ "$name" =~ ^[a-z_]+$ ]] || die "Invalid release state name"
  tmp=$(mktemp "$STATE_DIR/state/.${name}.XXXXXX")
  TEMP_FILES+=("$tmp")
  printf '%s\n' "$value" > "$tmp"
  chmod 0640 "$tmp"
  mv -f -- "$tmp" "$STATE_DIR/state/$name"
}

transition_value() {
  local file=$1 wanted=$2 line key value
  [[ -f "$file" && "$wanted" =~ ^[a-z_]+$ ]] || return 1
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^([a-z_]+)=(.*)$ ]] || continue
    key=${BASH_REMATCH[1]}; value=${BASH_REMATCH[2]}
    if [[ "$key" == "$wanted" ]]; then printf '%s' "$value"; return 0; fi
  done < "$file"
  return 1
}

prepare_release_transition() {
  local from=$1 to=$2 kind=$3 prepared_at record_dir record tmp pointer_tmp
  if ! valid_release_sha "$from" || ! valid_release_sha "$to"; then
    die "Cannot prepare transition with invalid release identity."
  fi
  [[ "$kind" == update || "$kind" == rollback ]] || die "Invalid release transition kind."
  prepared_at=$(date -u +%Y%m%dT%H%M%S%NZ)
  record_dir="$STATE_DIR/state/releases/$to/transitions"
  install -d -m 0750 "$record_dir"
  tmp=$(mktemp "$record_dir/.transition.XXXXXX")
  printf 'from_release=%s\nto_release=%s\nkind=%s\nprepared_at=%s\nstatus=prepared\n' "$from" "$to" "$kind" "$prepared_at" > "$tmp"
  chmod 0440 "$tmp"
  record="$record_dir/${prepared_at}-${from}-${kind}"
  mv -- "$tmp" "$record"
  pointer_tmp=$(mktemp "$STATE_DIR/state/.prepared_transition.XXXXXX")
  cat "$record" > "$pointer_tmp"
  printf 'metadata_path=state/releases/%s/transitions/%s\n' "$to" "${record##*/}" >> "$pointer_tmp"
  chmod 0640 "$pointer_tmp"
  mv -f "$pointer_tmp" "$STATE_DIR/state/prepared_transition"
}

committed_transition_previous() {
  local canonical=$1 file="$STATE_DIR/state/prepared_transition" from to kind status metadata relative key
  [[ -f "$file" ]] || return 1
  from=$(transition_value "$file" from_release 2>/dev/null || true)
  to=$(transition_value "$file" to_release 2>/dev/null || true)
  kind=$(transition_value "$file" kind 2>/dev/null || true)
  status=$(transition_value "$file" status 2>/dev/null || true)
  relative=$(transition_value "$file" metadata_path 2>/dev/null || true)
  if ! valid_release_sha "$from" || ! valid_release_sha "$to"; then return 2; fi
  if [[ "$kind" != update && "$kind" != rollback ]] || [[ "$status" != prepared ]]; then return 2; fi
  [[ "$relative" == state/releases/"$to"/transitions/* && "$relative" != *..* ]] || return 2
  metadata="$STATE_DIR/$relative"
  [[ -f "$metadata" ]] || return 2
  for key in from_release to_release kind prepared_at status; do
    [[ "$(transition_value "$metadata" "$key" 2>/dev/null || true)" == "$(transition_value "$file" "$key" 2>/dev/null || true)" ]] || return 2
  done
  [[ "$to" == "$canonical" ]] || return 1
  printf '%s' "$from"
}

valid_release_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }
valid_update_ref() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._/@{}^~:+-]{0,254}$ && "$1" != *..* && "$1" != *'@{'* ]]; }

release_git() {
  if [[ -d "$STATE_DIR/state/repository.git" ]]; then
    git --git-dir="$STATE_DIR/state/repository.git" "$@"
  else
    git -C "$SCRIPT_DIR" "$@"
  fi
}

fetch_update_source() {
  release_git remote get-url origin >/dev/null 2>&1 || die "Cannot fetch update source using existing Git credentials."
  release_git fetch --prune origin >/dev/null 2>&1 || die "Cannot fetch update source using existing Git credentials."
}

current_release_sha() {
  local sha
  if [[ -e "$STATE_DIR/current" || -L "$STATE_DIR/current" ]]; then
    sha=$(canonical_current_release 2>/dev/null) || die "current does not identify a valid successful release. Run ./server.sh status for recovery guidance."
  else
    sha=$(release_read active_release 2>/dev/null || release_read installed_git_sha 2>/dev/null || true)
  fi
  valid_release_sha "$sha" || die "installed_git_sha is unknown or invalid. Restore the exact installed Git object and write its full SHA to $STATE_DIR/state/installed_git_sha."
  printf '%s' "$sha"
}

resolve_candidate() {
  local ref=$1 sha
  valid_update_ref "$ref" || die "Invalid update ref."
  sha=$(release_git rev-parse --verify "$ref^{commit}" 2>/dev/null) || die "Update ref does not resolve to a commit: $ref"
  valid_release_sha "$sha" || die "Git returned an invalid candidate commit."
  printf '%s' "$sha"
}

update_check() {
  local ref=origin/main current candidate available=no
  while (($#)); do
    case "$1" in --ref) shift; ref=${1:-}; [[ -n "$ref" ]] || die "--ref requires a value";; *) die "Unknown update --check option: $1";; esac
    shift
  done
  fetch_update_source
  current=$(current_release_sha)
  candidate=$(resolve_candidate "$ref")
  if [[ "$current" != "$candidate" ]]; then available=yes; fi
  printf 'Who could — Update check\n\nCurrent release     %s\nAvailable release   %s\nSource              %s\nUpdate available    %s\n' "$current" "$candidate" "$ref" "$available"
}

init_release_repository() {
  local repo="$STATE_DIR/state/repository.git" origin_url
  if [[ -d "$repo" ]]; then return 0; fi
  git -C "$SCRIPT_DIR" rev-parse --git-dir >/dev/null 2>&1 || die "The installed Git object database is unavailable; cannot bootstrap an exact release."
  git init --bare -q "$repo"
  git --git-dir="$repo" fetch -q "$SCRIPT_DIR" '+refs/heads/*:refs/heads/*' '+refs/tags/*:refs/tags/*'
  git --git-dir="$repo" fetch -q "$SCRIPT_DIR" HEAD
  if origin_url=$(git -C "$SCRIPT_DIR" remote get-url origin 2>/dev/null); then
    git --git-dir="$repo" remote add origin "$origin_url"
  fi
  chmod -R go-w "$repo"
}

archive_release() {
  local sha=$1 candidate=${2:-true} destination="$STATE_DIR/releases/$1" staging
  if [[ -d "$destination" ]]; then return 0; fi
  staging=$(mktemp -d "$STATE_DIR/releases/.staging-${sha}-XXXXXX")
  TEMP_FILES+=("$staging")
  release_git archive "$sha" | tar -x -C "$staging"
  if $candidate; then validate_candidate "$staging"; else validate_release_base "$staging"; fi
  mv -- "$staging" "$destination"
  chmod -R a-w "$destination"
}

validate_candidate() {
  local dir=$1 file
  for file in server.sh compose.yaml docker/backend.Dockerfile docker/web.Dockerfile deploy/update_rollback.sh; do
    [[ -f "$dir/$file" ]] || die "Candidate is missing required file: $file"
  done
  while IFS= read -r -d '' file; do bash -n "$file"; done < <(find "$dir/deploy" -type f -name '*.sh' -print0)
  bash -n "$dir/server.sh"
  local old=$DEPLOY_SOURCE_DIR
  DEPLOY_SOURCE_DIR=$dir
  dc config --quiet
  DEPLOY_SOURCE_DIR=$old
  [[ "$(cfg CONFIG_VERSION)" == 2 ]] || die "Candidate cannot read the current CONFIG_VERSION."
}

validate_release_base() {
  local dir=$1 file
  for file in server.sh compose.yaml docker/backend.Dockerfile docker/web.Dockerfile; do
    [[ -f "$dir/$file" ]] || die "Installed release is missing required file: $file"
  done
  bash -n "$dir/server.sh"
}

bootstrap_release_state() {
  local current
  install -d -m 0750 "$STATE_DIR/releases" "$STATE_DIR/state/releases"
  init_release_repository
  current=$(current_release_sha)
  release_git cat-file -e "$current^{commit}" 2>/dev/null || die "Installed commit $current is unavailable. Fetch/restore that exact Git object before updating."
  archive_release "$current" false
  prepare_release_nginx "$current"
  tag_installed_images "$current"
  mark_release_success "$current" "$(release_read last_successful_deployment 2>/dev/null || date -u +%FT%TZ)"
  if [[ ! -L "$STATE_DIR/current" ]]; then atomic_current_switch "$current"; fi
  release_write active_release "$current"
}

tag_installed_images() {
  local sha=$1 backend_id web_id
  if docker_cmd image inspect "who-could-backend:$sha" >/dev/null 2>&1 && docker_cmd image inspect "who-could-web:$sha" >/dev/null 2>&1; then return 0; fi
  backend_id=$(dc images -q backend 2>/dev/null | head -1)
  web_id=$(dc images -q web 2>/dev/null | head -1)
  [[ -n "$backend_id" && -n "$web_id" ]] || die "Cannot identify installed images for release bootstrap."
  docker_cmd tag "$backend_id" "who-could-backend:$sha"
  docker_cmd tag "$web_id" "who-could-web:$sha"
}

atomic_current_switch() {
  local sha=$1 link="$STATE_DIR/current.new"
  valid_release_sha "$sha" || die "Refusing invalid release symlink target."
  [[ -d "$STATE_DIR/releases/$sha" ]] || die "Release directory does not exist: $sha"
  ln -sfn "releases/$sha" "$link"
  mv -Tf "$link" "$STATE_DIR/current"
}

mark_release_success() {
  local sha=$1 timestamp=$2 dir="$STATE_DIR/state/releases/$1" tmp
  install -d -m 0750 "$dir"
  tmp=$(mktemp "$dir/.successful.XXXXXX")
  printf 'release=%s\ndeployed_at=%s\nstatus=healthy\n' "$sha" "$timestamp" > "$tmp"
  chmod 0640 "$tmp"
  mv -f "$tmp" "$dir/successful"
}

managed_images_only() {
  local backend web
  backend=$(cfg BACKEND_IMAGE 2>/dev/null || true); web=$(cfg WEB_IMAGE 2>/dev/null || true)
  [[ -z "$backend" || "$backend" =~ ^who-could-backend:(local|[0-9a-f]{40})$ ]] || return 1
  [[ -z "$web" || "$web" =~ ^who-could-web:(local|[0-9a-f]{40})$ ]] || return 1
}

check_update_disk() {
  local source_kb data_kb required free
  source_kb=$(du -sk "$SCRIPT_DIR" | awk '{print $1}')
  data_kb=$(du -sk "$STATE_DIR/data" 2>/dev/null | awk '{print $1}')
  required=$((source_kb * 3 + data_kb * 2 + 1048576))
  free=$(df -Pk "$STATE_DIR" | awk 'NR==2 {print $4}')
  ((free >= required)) || die "Insufficient disk space: ${required} KiB required for source, two images, and backup; ${free} KiB available."
}

validate_backup_file() {
  local mode=$1 file=$2
  case "$mode" in
    sqlite) python3 - "$file" <<'PY'
import sqlite3, sys
db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
db.close()
PY
      ;;
    postgresql-local) dc exec -T postgres pg_restore --list < "$file" >/dev/null;;
    mariadb-local) if [[ -s "$file" ]]; then grep -Eq '^-- (MariaDB|MySQL) dump' "$file"; else return 1; fi;;
    *) return 1;;
  esac
}

create_update_backup() {
  local previous=$1 candidate=$2 mode before backup_path meta
  meta="$STATE_DIR/state/releases/$candidate"
  mode=$(cfg DATABASE_MODE)
  before=$(find "$STATE_DIR/backups" -maxdepth 1 -type f -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 || true)
  quiesced_backup >&2
  backup_path=$(find "$STATE_DIR/backups" -maxdepth 1 -type f -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
  [[ -n "$backup_path" && "$before" != *" $backup_path" ]] || die "Pre-update backup was not created."
  validate_backup_file "$mode" "$backup_path" || die "Pre-update backup validation failed."
  install -d -m 0750 "$meta"
  { printf 'release_being_left=%s\ncandidate_release=%s\nbackup_path=%s\ntimestamp=%s\n' "$previous" "$candidate" "$backup_path" "$(date -u +%FT%TZ)"; } > "$meta/pre-update-backup.tmp"
  chmod 0640 "$meta/pre-update-backup.tmp"
  mv -f "$meta/pre-update-backup.tmp" "$meta/pre-update-backup"
  printf '%s' "$backup_path"
}

quiesced_backup() {
  local mode stamp out source
  mode=$(cfg DATABASE_MODE)
  if [[ "$mode" != sqlite ]]; then backup; return; fi
  stamp=$(date -u +%Y%m%dT%H%M%S%NZ)
  out="$STATE_DIR/backups/${mode}_${stamp}.db"
  source="$STATE_DIR/data/sqlite/who_could.db"
  python3 - "$source" "$out" <<'PY'
import sqlite3, sys
source, output = sys.argv[1:]
src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
dst = sqlite3.connect(output)
src.backup(dst)
dst.close()
src.close()
PY
  chmod 0600 "$out"
  info "Backup created: $out"
}

release_runtime() {
  local sha=$1
  DEPLOY_SOURCE_DIR="$STATE_DIR/releases/$sha"
  RUNTIME_BACKEND_IMAGE="who-could-backend:$sha"
  RUNTIME_WEB_IMAGE="who-could-web:$sha"
  RUNTIME_NGINX_CONFIG="$STATE_DIR/state/releases/$sha/site.conf"
  [[ -f "$RUNTIME_NGINX_CONFIG" ]] || die "Release-specific Nginx configuration is unavailable for $sha."
}

successful_release_valid() {
  local sha=$1 file recorded status deployed
  file="$STATE_DIR/state/releases/$sha/successful"
  valid_release_sha "$sha" || return 1
  [[ -d "$STATE_DIR/releases/$sha" && -f "$STATE_DIR/state/releases/$sha/site.conf" && -f "$file" ]] || return 1
  recorded=$(sed -n 's/^release=//p' "$file")
  status=$(sed -n 's/^status=//p' "$file")
  deployed=$(sed -n 's/^deployed_at=//p' "$file")
  [[ "$recorded" == "$sha" && "$status" == healthy && "$deployed" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$ ]]
}

successful_release_deployed_at() {
  local sha=$1
  successful_release_valid "$sha" || return 1
  sed -n 's/^deployed_at=//p' "$STATE_DIR/state/releases/$sha/successful"
}

canonical_current_release() {
  local target sha
  [[ -L "$STATE_DIR/current" ]] || return 1
  target=$(readlink "$STATE_DIR/current")
  [[ "$target" =~ ^releases/([0-9a-f]{40})$ ]] || return 1
  sha=${BASH_REMATCH[1]}
  successful_release_valid "$sha" || return 1
  [[ "$(readlink -f "$STATE_DIR/current")" == "$(readlink -f "$STATE_DIR/releases/$sha")" ]] || return 1
  printf '%s' "$sha"
}

activate_active_release_runtime() {
  local mode=${1:-readonly} canonical recorded installed previous recorded_deployment expected_previous='' expected_deployment transition_rc=1 mirror_mismatch=false deployment_mismatch=false
  if [[ ! -e "$STATE_DIR/current" && ! -L "$STATE_DIR/current" ]]; then return 0; fi
  if canonical=$(canonical_current_release); then :; else
    [[ "$mode" == diagnostic ]] && return 0
    die "current is invalid or does not point to a marked successful release. Run ./server.sh status for recovery guidance."
  fi
  recorded=$(release_read active_release 2>/dev/null || true)
  installed=$(release_read installed_git_sha 2>/dev/null || true)
  previous=$(release_read previous_release 2>/dev/null || true)
  recorded_deployment=$(release_read last_successful_deployment 2>/dev/null || true)
  expected_deployment=$(successful_release_deployed_at "$canonical") || die "Canonical release deployment timestamp is invalid."
  if expected_previous=$(committed_transition_previous "$canonical"); then transition_rc=0; else transition_rc=$?; fi
  if [[ "$mode" == reconcile ]] && ((transition_rc == 2)); then die "Prepared transition metadata is malformed; automatic reconciliation is refused."; fi
  [[ "$recorded" != "$canonical" || "$installed" != "$canonical" ]] && mirror_mismatch=true
  if ((transition_rc == 0)) && [[ "$previous" != "$expected_previous" ]]; then mirror_mismatch=true; fi
  [[ "$recorded_deployment" != "$expected_deployment" ]] && deployment_mismatch=true
  if [[ "$mode" == reconcile ]] && $mirror_mismatch; then
    ((transition_rc == 0)) || die "Release mirrors differ from current without a valid committed transition; automatic reconciliation is ambiguous."
    release_write previous_release "$expected_previous"
    release_write active_release "$canonical"
    release_write installed_git_sha "$canonical"
  fi
  if [[ "$mode" == reconcile ]] && $deployment_mismatch; then
    release_write last_successful_deployment "$expected_deployment"
  fi
  if [[ "$mode" == reconcile ]] && { $mirror_mismatch || $deployment_mismatch; }; then
    info "Reconciled release mirrors to canonical current release $canonical."
  fi
  release_runtime "$canonical"
}

prepare_release_nginx() {
  local sha=$1 old_source=$DEPLOY_SOURCE_DIR output="$STATE_DIR/state/releases/$1/site.conf"
  DEPLOY_SOURCE_DIR="$STATE_DIR/releases/$sha"
  render_nginx '' "$output"
  DEPLOY_SOURCE_DIR=$old_source
}

full_release_health() { dc ps --status running backend web >/dev/null; dc exec -T web nginx -t; health; }

recover_pre_mutation_failure() {
  local previous=$1 stage=$2
  release_runtime "$previous"
  if dc up -d --wait backend web && full_release_health; then
    printf 'Update failed before database mutation at: %s\nPrevious release remains healthy: %s\nDatabase restore: not required\n' "$stage" "$previous" >&2
    return 0
  fi
  printf 'Update failed before database mutation at: %s\nPrevious release health recovery: FAILED\nActive release: %s\n' "$stage" "$previous" >&2
  return 1
}

recover_failed_update() {
  local previous=$1 candidate=$2 backup_path=$3 stage=$4 mode recovered=true
  mode=$(cfg DATABASE_MODE)
  dc stop backend web >/dev/null 2>&1 || true
  if [[ "$mode" == *-external ]]; then
    printf 'Update failed at: %s\nAutomatic rollback: UNAVAILABLE (external database)\nPrevious release: %s\nCandidate release: %s\nRestore the provider snapshot if migration changed the database.\n' "$stage" "$previous" "$candidate" >&2
    return 1
  fi
  native_restore "$mode" "$backup_path" || recovered=false
  release_runtime "$previous"
  if $recovered; then dc run --rm --no-deps backend alembic upgrade head || recovered=false; fi
  if $recovered; then dc run --rm --no-deps backend alembic check || recovered=false; fi
  if $recovered; then atomic_current_switch "$previous"; dc up -d --wait backend web || recovered=false; fi
  if $recovered; then full_release_health || recovered=false; fi
  if $recovered; then
    release_write active_release "$previous"
    release_write installed_git_sha "$previous"
    printf 'Update failed at: %s\nAutomatic rollback: SUCCESS\nActive release: %s\nBackup: %s\n' "$stage" "$previous" "$backup_path" >&2
    return 0
  fi
  printf 'Update failed at: %s\nAutomatic rollback: FAILED\nPrevious release: %s\nCandidate release: %s\nBackup: %s\nManual recovery: WHO_COULD_STATE_DIR=%q %q rollback %s --restore-database\n' "$stage" "$previous" "$candidate" "$backup_path" "$STATE_DIR" "$STATE_DIR/current/server.sh" "$previous" >&2
  return 1
}

update_pipeline() {
  local previous=$1 candidate=$2 external_confirmed=$3 backup_path=external-provider-snapshot stage=build timestamp answer
  UPDATE_TRANSACTION_ACTIVE=true; UPDATE_PREVIOUS=$previous; UPDATE_CANDIDATE=$candidate
  trap update_interrupted INT TERM
  check_update_disk
  archive_release "$candidate"
  prepare_release_nginx "$candidate"
  release_runtime "$candidate"
  UPDATE_FAILURE_STAGE='candidate build'
  docker_cmd build -f "$DEPLOY_SOURCE_DIR/docker/backend.Dockerfile" -t "$RUNTIME_BACKEND_IMAGE" "$DEPLOY_SOURCE_DIR" || return 1
  docker_cmd build -f "$DEPLOY_SOURCE_DIR/docker/web.Dockerfile" -t "$RUNTIME_WEB_IMAGE" "$DEPLOY_SOURCE_DIR" || return 1
  UPDATE_FAILURE_STAGE='candidate nginx config'
  dc run --rm --no-deps web nginx -t || return 1
  case "$(cfg DATABASE_MODE)" in
    *-external)
      info "External database detected. A provider-managed backup must be confirmed before migration."
      if $external_confirmed; then :; else
        if $NON_INTERACTIVE; then die "External database backup confirmation is required: use --external-db-backup-confirmed"; fi
        read -r -p "Type EXTERNAL BACKUP CONFIRMED: " answer
        [[ "$answer" == 'EXTERNAL BACKUP CONFIRMED' ]] || die "Update cancelled; external backup was not confirmed."
      fi;;
    *) :;;
  esac
  stage='database connectivity'; UPDATE_FAILURE_STAGE=$stage
  if dc run --rm --no-deps backend python -c 'from app.database import engine; from sqlalchemy import text; c=engine.connect(); c.execute(text("SELECT 1")); c.close()'; then :; else
    recover_pre_mutation_failure "$previous" "$stage" || true
    return 1
  fi
  stage='backend quiesce'; UPDATE_FAILURE_STAGE=$stage
  if dc stop backend; then :; else recover_pre_mutation_failure "$previous" "$stage" || true; return 1; fi
  info 'Update stage        backend stopped'
  if [[ "$(cfg DATABASE_MODE)" != *-external ]]; then
    stage='pre-update backup'; UPDATE_FAILURE_STAGE=$stage
    if backup_path=$(create_update_backup "$previous" "$candidate"); then :; else
      recover_pre_mutation_failure "$previous" "$stage" || true
      return 1
    fi
    info 'Update stage        backup validated'
  fi
  UPDATE_BACKUP=$backup_path
  stage=migration; UPDATE_FAILURE_STAGE=$stage
  # From this exact boundary Alembic may have partially changed the schema.
  UPDATE_DATABASE_MUTATED=true
  info 'Update stage        migration started'
  dc run --rm --no-deps backend alembic upgrade head || { recover_failed_update "$previous" "$candidate" "$backup_path" "$stage"; return 1; }
  dc run --rm --no-deps backend alembic check || { recover_failed_update "$previous" "$candidate" "$backup_path" "$stage"; return 1; }
  stage='backend health'; UPDATE_FAILURE_STAGE=$stage
  dc up -d --wait --remove-orphans backend || { recover_failed_update "$previous" "$candidate" "$backup_path" "$stage"; return 1; }
  stage='web health'; UPDATE_FAILURE_STAGE=$stage
  dc up -d --wait --remove-orphans web || { recover_failed_update "$previous" "$candidate" "$backup_path" "$stage"; return 1; }
  full_release_health || { recover_failed_update "$previous" "$candidate" "$backup_path" "$stage"; return 1; }
  timestamp=$(date -u +%FT%TZ)
  stage='preparing release commit'; UPDATE_FAILURE_STAGE=$stage
  mark_release_success "$candidate" "$timestamp" || { recover_failed_update "$previous" "$candidate" "$backup_path" "$stage"; return 1; }
  prepare_release_transition "$previous" "$candidate" update || { recover_failed_update "$previous" "$candidate" "$backup_path" "$stage"; return 1; }
  # Canonical commit point: mirrors written after this may be reconciled safely.
  atomic_current_switch "$candidate" || { recover_failed_update "$previous" "$candidate" "$backup_path" "$stage"; return 1; }
  UPDATE_TRANSACTION_ACTIVE=false; UPDATE_DATABASE_MUTATED=false
  trap - INT TERM
  release_write previous_release "$previous"
  release_write active_release "$candidate"
  release_write installed_git_sha "$candidate"
  release_write last_successful_deployment "$timestamp"
  if [[ "$(cfg HTTPS_MODE)" == acme ]]; then install_timer; fi
  printf 'Active release      %s\n\nUpdate successful.\n' "$candidate"
}

update_command() {
  local check=false ref=origin/main explicit=false external_confirmed=false current candidate
  while (($#)); do
    case "$1" in
      --check) check=true;;
      --ref) shift; ref=${1:-}; [[ -n "$ref" ]] || die "--ref requires a value"; explicit=true;;
      --external-db-backup-confirmed) external_confirmed=true;;
      --non-interactive) NON_INTERACTIVE=true;;
      *) die "Unknown update option: $1";;
    esac
    shift
  done
  if $check; then
    if $explicit; then update_check --ref "$ref"; else update_check; fi
    return
  fi
  activate_active_release_runtime reconcile
  info "Who could — Update"
  managed_images_only || die "Managed source update is unavailable while custom images are configured."
  bootstrap_release_state
  fetch_update_source
  current=$(current_release_sha); candidate=$(resolve_candidate "$ref")
  if $explicit; then :
  elif release_git merge-base --is-ancestor "$current" "$candidate"; then :
  else
    die "Candidate is not a descendant of the installed release. Use an explicit advanced/manual procedure."
  fi
  printf '\nCurrent release     %s\nCandidate release   %s\nDatabase            %s\n' "$current" "$candidate" "$(cfg DATABASE_MODE)"
  [[ "$current" != "$candidate" ]] || { info "Already at requested release."; return 0; }
  update_pipeline "$current" "$candidate" "$external_confirmed"
}

database_heads_compatible() {
  local target=$1
  release_runtime "$target"
  dc run --rm --no-deps backend python - <<'PY'
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.database import engine

target = set(ScriptDirectory.from_config(Config("/app/alembic.ini")).get_heads())
with engine.connect() as connection:
    current = set(MigrationContext.configure(connection).get_current_heads())
if current != target:
    raise SystemExit(f"database heads {sorted(current)} do not exactly match target heads {sorted(target)}")
PY
}

confirm_rollback_snapshot() {
  local target=$1 active previous meta backup_path answer left recorded_candidate
  active=$(release_read active_release)
  previous=$(release_read previous_release 2>/dev/null || true)
  [[ "$target" == "$previous" ]] || die "Database restore is allowed only for the immediately previous release with an exact transition snapshot."
  meta="$STATE_DIR/state/releases/$active/pre-update-backup"
  [[ -f "$meta" ]] || die "No associated pre-update backup exists for the active release."
  backup_path=$(sed -n 's/^backup_path=//p' "$meta")
  left=$(sed -n 's/^release_being_left=//p' "$meta")
  recorded_candidate=$(sed -n 's/^candidate_release=//p' "$meta")
  [[ "$left" == "$target" && "$recorded_candidate" == "$active" ]] || die "Pre-update backup does not match the requested release transition."
  [[ -f "$backup_path" ]] || die "Associated pre-update backup is unavailable."
  printf 'This will restore the database snapshot taken before the update.\nAll writes after that snapshot will be LOST.\n'
  if $NON_INTERACTIVE; then die "Non-interactive destructive rollback is not supported."; fi
  read -r -p "Type ROLLBACK WITH DATA LOSS: " answer
  [[ "$answer" == 'ROLLBACK WITH DATA LOSS' ]] || die "Destructive rollback cancelled."
  ROLLBACK_SNAPSHOT=$backup_path
}

create_rollback_emergency_backup() {
  local mode backup_path
  mode=$(cfg DATABASE_MODE)
  quiesced_backup >&2
  backup_path=$(find "$STATE_DIR/backups" -maxdepth 1 -type f -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
  [[ -n "$backup_path" ]] || return 1
  validate_backup_file "$mode" "$backup_path" || return 1
  printf '%s' "$backup_path"
}

recover_failed_rollback() {
  local current=$1 emergency=${2:-} recovered=true mode
  trap - INT TERM
  mode=$(cfg DATABASE_MODE)
  dc stop backend web >/dev/null 2>&1 || true
  release_runtime "$current"
  if [[ -n "$emergency" ]]; then native_restore "$mode" "$emergency" || recovered=false; fi
  if $recovered && [[ -n "$emergency" ]]; then dc run --rm --no-deps backend alembic upgrade head || recovered=false; fi
  if $recovered; then dc run --rm --no-deps backend alembic check || recovered=false; fi
  if $recovered; then dc up -d --wait backend web || recovered=false; fi
  if $recovered; then full_release_health || recovered=false; fi
  if $recovered; then
    printf 'Rollback failed.\nPrevious active release recovery: SUCCESS\nActive release: %s\n' "$current" >&2
    [[ -z "$emergency" ]] || printf 'Emergency backup retained: %s\n' "$emergency" >&2
    return 0
  fi
  printf 'Rollback failed.\nPrevious active release recovery: FAILED\nActive release: %s\n' "$current" >&2
  [[ -z "$emergency" ]] || printf 'Emergency backup retained: %s\n' "$emergency" >&2
  return 1
}

rollback_command() {
  local target='' restore_database=false current timestamp emergency='' mode
  while (($#)); do
    case "$1" in --restore-database) restore_database=true;; --non-interactive) NON_INTERACTIVE=true;; *) [[ -z "$target" ]] || die "Only one rollback release may be specified"; target=$1;; esac
    shift
  done
  current=$(current_release_sha); target=${target:-$(release_read previous_release 2>/dev/null || true)}
  valid_release_sha "$target" || die "No previous successful release is recorded."
  if ! successful_release_valid "$target"; then die "Target release is missing, invalid, or was not marked successful."; fi
  [[ "$(cfg DATABASE_MODE)" != *-external || $restore_database == false ]] || die "Database restore for external databases must be performed by the provider/operator."
  info "Who could — Rollback"
  printf '\nCurrent release     %s\nTarget release      %s\n' "$current" "$target"
  if $restore_database; then
    confirm_rollback_snapshot "$target"
  elif database_heads_compatible "$target"; then
    dc run --rm --no-deps backend alembic check >/dev/null 2>&1 || die "Target release Alembic check failed."
  else
    release_runtime "$current"
    die "Database schema is newer than or incompatible with the target release."
  fi
  ROLLBACK_CURRENT=$current; ROLLBACK_TARGET=$target; ROLLBACK_EMERGENCY=''; ROLLBACK_DATABASE_MUTATED=false; ROLLBACK_STAGE='stopping current release'
  trap rollback_interrupted INT TERM
  if dc stop backend web; then :; else recover_failed_rollback "$current" || true; return 1; fi
  if $restore_database; then
    mode=$(cfg DATABASE_MODE)
    ROLLBACK_STAGE='creating emergency backup'
    if emergency=$(create_rollback_emergency_backup); then :; else recover_failed_rollback "$current" || true; return 1; fi
    ROLLBACK_EMERGENCY=$emergency
    ROLLBACK_STAGE='restoring requested snapshot'; ROLLBACK_DATABASE_MUTATED=true
    if native_restore "$mode" "$ROLLBACK_SNAPSHOT"; then :; else recover_failed_rollback "$current" "$emergency" || true; return 1; fi
  fi
  release_runtime "$target"
  if $restore_database; then
    ROLLBACK_STAGE='checking restored target database'
    if dc run --rm --no-deps backend alembic upgrade head && dc run --rm --no-deps backend alembic check; then :; else recover_failed_rollback "$current" "$emergency" || true; return 1; fi
  fi
  ROLLBACK_STAGE='starting target release'
  if dc up -d --wait backend web && full_release_health; then :; else recover_failed_rollback "$current" "$emergency" || true; return 1; fi
  ROLLBACK_STAGE='preparing rollback commit'
  timestamp=$(date -u +%FT%TZ)
  if mark_release_success "$target" "$timestamp"; then :; else recover_failed_rollback "$current" "$emergency" || true; return 1; fi
  if prepare_release_transition "$current" "$target" rollback; then :; else recover_failed_rollback "$current" "$emergency" || true; return 1; fi
  # Canonical commit point: target is already marked successful and healthy.
  if atomic_current_switch "$target"; then :; else recover_failed_rollback "$current" "$emergency" || true; return 1; fi
  ROLLBACK_DATABASE_MUTATED=false
  trap - INT TERM
  release_write previous_release "$current"; release_write active_release "$target"; release_write installed_git_sha "$target"; release_write last_successful_deployment "$timestamp"
  printf 'Database schema     compatible\nBackend             healthy\nWeb                 healthy\n\nRollback successful.\n'
}

releases_command() {
  local active='' previous='' recorded_active recorded_previous canonical expected_previous dir sha timestamp label status state=CONSISTENT transition_rc=1
  recorded_active=$(release_read active_release 2>/dev/null || true)
  recorded_previous=$(release_read previous_release 2>/dev/null || true)
  if canonical=$(canonical_current_release 2>/dev/null); then
    active=$canonical
    if expected_previous=$(committed_transition_previous "$canonical"); then
      transition_rc=0; previous=$expected_previous
    else
      transition_rc=$?
      if ((transition_rc == 1)) && [[ "$recorded_active" == "$canonical" ]]; then previous=$recorded_previous; else state=INCONSISTENT; fi
    fi
  else
    state=INCONSISTENT
  fi
  printf 'RELEASE STATE %s\n\n' "$state"
  for label in ACTIVE PREVIOUS OLDER; do
    printf '%s\n' "$label"
    if [[ "$state" == INCONSISTENT && ( "$label" == ACTIVE || "$label" == PREVIOUS ) ]]; then printf 'UNKNOWN\n\n'; continue; fi
    for dir in "$STATE_DIR"/state/releases/*; do
      [[ -d "$dir" && -f "$dir/successful" ]] || continue
      sha=${dir##*/}
      case "$label:$sha" in ACTIVE:"$active"|PREVIOUS:"$previous") :;; OLDER:"$active"|OLDER:"$previous") continue;; OLDER:*) :;; *) continue;; esac
      timestamp=$(sed -n 's/^deployed_at=//p' "$dir/successful")
      if [[ "$sha" == "$active" ]]; then status=healthy; else status='rollback available'; fi
      printf '%.12s  %s  %s\n' "$sha" "$timestamp" "$status"
    done
    printf '\n'
  done
}

release_diagnostics() {
  local active previous installed last current_target=missing canonical='' state=INCONSISTENT backend web rollback=no expected_previous='not committed' expected_deployment=unavailable transition_rc=1
  active=$(release_read active_release 2>/dev/null || echo unavailable)
  previous=$(release_read previous_release 2>/dev/null || echo unavailable)
  installed=$(release_read installed_git_sha 2>/dev/null || echo unavailable)
  last=$(release_read last_successful_deployment 2>/dev/null || echo unavailable)
  if [[ -L "$STATE_DIR/current" ]]; then current_target=$(readlink "$STATE_DIR/current"); fi
  if canonical=$(canonical_current_release 2>/dev/null); then
    current_target=$canonical
    expected_deployment=$(successful_release_deployed_at "$canonical" 2>/dev/null || echo invalid)
    if expected_previous=$(committed_transition_previous "$canonical"); then transition_rc=0; else transition_rc=$?; expected_previous='not committed'; fi
    if [[ "$active" == "$canonical" && "$installed" == "$canonical" && "$last" == "$expected_deployment" ]] && ((transition_rc != 2)); then
      if ((transition_rc != 0)) || [[ "$previous" == "$expected_previous" ]]; then state=CONSISTENT; fi
    fi
  fi
  backend=$(dc images -q backend 2>/dev/null | head -1 || true); web=$(dc images -q web 2>/dev/null | head -1 || true)
  if [[ "$previous" != unavailable ]]; then rollback=yes; fi
  printf 'Current symlink        %s\nRecorded active        %s\nInstalled Git SHA      %s\nRecorded previous      %s\nExpected previous      %s\nRecorded deployment    %s\nExpected deployment    %s\nRelease state          %s\nRollback available     %s\nActive backend image   %s\nActive web image       %s\n' "$current_target" "$active" "$installed" "$previous" "$expected_previous" "$last" "$expected_deployment" "$state" "$rollback" "${backend:-unavailable}" "${web:-unavailable}"
  if [[ "$state" == INCONSISTENT ]]; then
    if [[ -n "$canonical" ]] && ((transition_rc == 0)); then
      printf 'Recovery guidance      Run a locked state-changing command to reconcile mirrors to %s.\n' "$canonical"
    elif [[ -n "$canonical" ]]; then
      printf 'Recovery guidance      Current is valid but transition/mirrors are ambiguous; inspect state/prepared_transition and repair mirrors manually.\n'
    else
      printf 'Recovery guidance      Repair current to an exact marked-successful release; automatic reconciliation is refused.\n'
    fi
  fi
}
