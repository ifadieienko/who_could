# Safe updates and rollback

`server.sh update` is an operator-initiated, single-host deployment transaction,
not `git pull` in a running checkout. A release is the archive of one exact Git
commit; images are `who-could-backend:<sha>` and `who-could-web:<sha>`.

## On-host model

```text
/opt/who-could/
├── releases/<full-git-sha>/       immutable source archives
├── current -> releases/<active>   atomically replaced active link
├── state/
│   ├── active_release, previous_release, installed_git_sha
│   ├── last_successful_deployment
│   ├── repository.git/            objects/existing transport configuration
│   └── releases/<sha>/             success and backup metadata
├── backups/                        validated database backups
└── config/, secrets/, certs/, data/ persistent runtime state
```

Runtime data and credentials never enter a release. The first update uses the
recorded `installed_git_sha` and its Git object to create the initial immutable
release; it refuses `unknown`, a missing object, or arbitrary dirty files. The
`current` link changes by temporary symlink plus atomic rename. Successful
releases, previous images, and associated backups are not automatically pruned.

## Update commands

```bash
sudo ./server.sh update --check
sudo ./server.sh update
sudo ./server.sh update --ref refs/tags/v2.0.0
```

`--check` only fetches through the existing Git transport, resolves an exact
SHA, and reports current/available releases. It does not build, back up,
migrate, restart, or write deployment state. Normal source is `origin/main` and
must descend from the installed SHA. A safely validated explicit ref may be a
commit, tag, or remote branch, but its resolved SHA is the release identity.

The manager never asks for or stores a PAT. Configure SSH/deploy keys or a Git
credential helper outside Who could. Failed fetch authentication stops before
deployment mutation and leaves the application running.

Before database mutation, update validates required files, deployment shell
syntax, Compose in the current database/TLS mode, free space, and
`CONFIG_VERSION=2`; then it builds both SHA-tagged images. Operator-supplied
custom images cause a safe refusal instead of being overwritten.

For SQLite, local PostgreSQL, and local MariaDB, update first builds and runs a
read-only candidate connectivity check while the previous backend remains
available. It then stops the backend, creates a quiesced backup, and validates
it with `integrity_check`,
`pg_restore --list`, or dump size/header checks. Metadata associates previous
release, candidate, path, and timestamp. It then checks DB connectivity, runs
`alembic upgrade head` and `alembic check`, waits for backend/web, checks
`nginx -t`, frontend, API, and configured TLS, and only then commits `current`
and state. The snapshot therefore precedes migration with no accepted backend
writes between those boundaries. A failure before migration restarts/checks the
previous release without restoring an unchanged database.

Every release retains a generated `state/releases/<sha>/site.conf`, rendered
from that release's templates. Candidate, rollback, and recovery containers
mount the matching configuration, so a template update cannot silently run
against stale Nginx configuration. Each new `server.sh` process validates the
canonical `current` target, release directory, success marker, generated config,
and recorded mirrors, then restores the persisted SHA runtime before any Compose
operation. Consequently start, restore, certificate renewal, and configure do
not fall back to `:local` images or the legacy shared site config.

The atomic `current` symlink is the canonical deployment commit point. A release
is marked successful and immutable per-release transition metadata is prepared
before that switch. The transition records `from_release`, `to_release`, kind,
timestamp, and prepared status without changing the committed previous pointer;
`active_release` and `installed_git_sha` are mirrors written afterwards. If a
crash leaves those mirrors stale, a locked state-changing command reconciles
them—including `previous_release`—only when `current` has the exact
`releases/<full-sha>` form and matching trusted transition metadata. A prepared
transition whose destination is not `current` did not commit and cannot replace
the old previous pointer. The canonical release must also have a matching
healthy success marker and generated `site.conf`. Invalid or
unmarked targets fail closed. `status` and `doctor` remain read-only and report
the canonical target, recorded mirror, `INCONSISTENT` state, and recovery advice.
The trusted successful-release record also supplies the expected deployment
timestamp; locked reconciliation repairs a stale `last_successful_deployment`,
while diagnostics show recorded and expected values. `releases` derives ACTIVE
from canonical `current` and PREVIOUS from a matching committed transition, so
it does not confidently label stale mirrors after a crash. Ambiguous transition
state is displayed as `INCONSISTENT`/`UNKNOWN` without changing any files.

A post-mutation local-DB failure stops the candidate, restores the validated
backup, checks the previous release's migrations, restores its images and link,
starts it, and requires full health. Recovery failure diagnostics retain both
SHAs, stage, backup, and a manual command. No path executes `alembic downgrade`.

External PostgreSQL/MariaDB cannot be rolled back automatically. Interactive
update requires the exact phrase `EXTERNAL BACKUP CONFIRMED`; non-interactive
use requires `--external-db-backup-confirmed`. A post-migration failure reports
that the provider snapshot may require restore and performs no fake DB rollback.

## History and rollback

```bash
sudo ./server.sh releases
sudo ./server.sh rollback
sudo ./server.sh rollback <full-sha>
sudo ./server.sh rollback <full-sha> --restore-database
```

History comes from local immutable state. Code-only rollback runs the target
release's Alembic `ScriptDirectory` heads and compares them exactly with the
database `MigrationContext` heads before stopping the active service. It also
runs `alembic check` as an additional assertion and refuses a newer, unknown, or
otherwise incompatible schema. It never performs a schema downgrade.

For a local DB, `--restore-database` uses the update-associated snapshot. It
warns that subsequent writes will be lost and requires exactly `ROLLBACK WITH
DATA LOSS`. Destructive rollback is unavailable non-interactively and for
external databases.

Rollback itself is transactional. A failed code-only target start restores and
health-checks the previous active release without committing state. Destructive
rollback first creates and validates an emergency snapshot of the current
quiesced database. If snapshot restore, target migration checks, or target
health fail, that emergency snapshot and the previous active release are
restored; emergency backups are retained for diagnostics. SIGINT and SIGTERM
use the same recovery path: code-only rollback restarts the canonical current
release, while an interrupted destructive restore first restores its validated
emergency snapshot. Rollback-specific traps are cleared at the atomic commit
point so a later mirror-write interruption is handled by safe reconciliation.

## Operations, interruption, and limits

Update/rollback use the same exclusive lock as configure, restore, uninstall,
and host-security changes. Before DB mutation, interruption cleans staging.
After a handled mutation failure, local recovery runs. After an uncatchable
kill, inspect `state/releases/*/pre-update-backup`, run `doctor`, and use the
manual destructive rollback command; preserve prior releases/images/backups.

Disk checking estimates candidate source, two images, and backup needs, but
Docker storage drivers may require more. Monitor Docker storage and
`/opt/who-could`; the manager never runs broad Docker pruning.

Certificate renewal uses `/opt/who-could/current/server.sh` after bootstrap and
the installation source's `server.sh` as a safe fallback for non-Git source
archives. A later successful bootstrap rewrites the unit to the stable path.
Update does not
reissue ACME certificates, reinstall CrowdSec, reset UFW, alter bouncer
registration, or apply candidate host-security mutations. Diagnostics use the
existing read-only security checks.

This protects one transaction on one host. It is **not** HA, zero downtime, a
distributed deployment, database PITR, or an external snapshot manager. A short
service interruption occurs during migration and health checks.
