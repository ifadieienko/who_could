# Server deployment

## Requirements and installation

The supported automatic host path is Ubuntu 22.04, 24.04, or 26.04 with at
least 2 GiB free disk. Run the installer from a real Git checkout with an
identifiable `HEAD` and an `origin` remote; extracted source archives are
rejected because they cannot establish the immutable release identity required
by safe update/rollback.

On supported Ubuntu, a root installation checks the host tools used by the
manager (`curl`, Python, Git, `flock`, `tar`, core/find/text utilities, and
related CA support) and installs missing packages through APT. Docker Engine and
Compose are then checked. If Docker is absent, the installer offers Docker's
official APT repository and installs Docker CE, containerd, Buildx, and the
Compose plugin; it never pipes a remote script to a shell or silently grants
membership in the root-equivalent `docker` group.

```bash
git clone <repository-url>
cd <repository>
sudo ./server.sh install
```

The wizard stores runtime state under `/opt/who-could`, builds the images,
starts only the selected database, checks `SELECT 1`, runs `alembic upgrade
head` and `alembic check`, then starts backend and Nginx. Success is printed and
`last_successful_deployment` is written only after application health and the
immutable release/update state have both been established. For automation use
the same validation path with `install --non-interactive --config
 deploy/.env.example` (copy and edit the example first).

A failed first installation is resumable. Configuration is written atomically;
if a later stage fails (for example a busy host port, image build, migration, or
health check), rerunning `server.sh install` detects that no successful-deploy
marker/release exists and resumes with the existing validated configuration and
secrets. A completed installation is idempotent: another `install` does not
rotate secrets or rewrite configuration.

## Architecture

```text
Internet -> Nginx (web; host 80 and, only with TLS, 443 -> 8080/8443)
                  |-- /       React static SPA
                  `-- /api/*  FastAPI backend:8000
                                      `-- SQLite | PostgreSQL | MariaDB
```

`frontend_network` contains web and backend. The internal
`database_network` contains backend and the one selected local database. Web
cannot reach that network. Backend and database ports use only `expose`; only
Nginx publishes host ports. Docker JSON logs rotate at 10 MiB, retaining five.

All long-running application/database containers use `restart: unless-stopped`.
SQLite lives in the protected host state directory; local PostgreSQL/MariaDB use
named volumes. Container recreation and a normal host reboot therefore preserve
application data.

## Commands

Run `./server.sh --help`. The manager supports `install`, `configure`, `start`,
`stop`, `restart`, `status`, `logs [backend|web|database]`, `health`, `doctor`,
`backup`, `restore FILE`, `cert-renew`, and `uninstall`. Ordinary uninstall
removes containers but preserves configuration, secrets, volumes, certificates,
data, and backups. It never runs `down -v`.

Safe operator-driven releases add `update --check`, `update [--ref REF]`,
`releases`, and `rollback [RELEASE] [--restore-database]`. They use immutable
full-SHA releases, SHA-tagged images, validated pre-migration backups, and an
atomic `current` link. See [UPDATE_ROLLBACK.md](UPDATE_ROLLBACK.md).

## HTTPS

* `acme`: starts HTTP first, uses the pinned Certbot container and webroot,
  installs the certificate, switches Nginx to HTTPS, and installs a twice-daily
  systemd renewal timer. `certbot renew` itself decides whether renewal is due.
* `custom`: validates input paths, copies the certificate and private key into
  `/opt/who-could/certs/custom`, mounts them read-only, and validates Nginx as it
  starts. An interrupted install reuses an already copied certificate/key rather
  than requiring the operator to provide the source files again.
* `disabled`: HTTP only, with no HSTS header.

Certificate directories and keys are normalized to a dedicated numeric TLS
reader group. The unprivileged web process receives only that supplemental
group; private keys remain `0640`, never world-readable. ACME rejects localhost,
raw IP addresses and non-standard HTTP ports because HTTP-01 requires a public
DNS hostname reaching host port 80.

Ensure DNS points to the host and inbound 80/443 are available before ACME.
The installer does not configure a firewall and never terminates a process that
already owns a chosen port.

## Deployment acceptance

CI now exercises the actual `server.sh install` path against an empty state
directory. The test intentionally occupies the configured HTTP port so the
first install fails after configuration/secrets have been created, then releases
the port and verifies that a second install resumes successfully. It also checks
immutable release state, idempotent re-install, stop/start persistence, user
login persistence, and the normal deployment smoke matrix for SQLite,
PostgreSQL, MariaDB, backup/restore, transactional update/rollback, and custom
HTTPS.

A hosted CI runner cannot prove package installation on a machine that starts
without Docker or prove persistence across a real kernel reboot. Use the
explicit disposable-VM acceptance for that final host boundary:

```bash
sudo bash deploy/test_fresh_host_acceptance.sh
# dry-run output explains the opt-in commands
```

With the explicit opt-in flag, the prepare phase runs the real installer with
local PostgreSQL, writes test data and a reboot marker. The post-reboot phase
waits for Docker/container restart, verifies health and login persistence, and
runs `doctor`. Optional `WHO_COULD_ACCEPTANCE_DOMAIN` and
`WHO_COULD_ACCEPTANCE_EMAIL` exercise real ACME issuance and the renewal command
on a disposable public DNS name; that intentionally uses the real CA, so observe
certificate-authority rate limits.

## Troubleshooting

Use `sudo ./server.sh doctor`, `status`, and `logs`. External database failures
stop before migrations; verify routing, provider allowlists, credentials, TLS,
CA, and schema-migration permissions. State uses `CONFIG_VERSION=2`; older v1
state is migrated atomically and idempotently. The state directory records the
installed Git SHA and last successful deployment time.

If an initial install fails, fix the reported cause and run the same `install`
command again. Do not delete `/opt/who-could` merely to retry: its incomplete
state is designed to be resumed safely. If configuration itself must change,
use `configure` after resolving the failed deployment or remove only disposable
test state when performing acceptance on a throwaway VM.

This is a production deployment **foundation**, not a claim of complete public
application security. Browser authentication still uses bearer tokens in
localStorage. HttpOnly Secure sessions, CSRF, recovery, verification, audit and
application-level abuse controls remain future work. Edge rate limiting is not
complete anti-DDoS protection.

## Pinned runtime images

The deployment currently pins Python `3.12.14-slim-bookworm` (PSF), Node
`22.22.0-bookworm-slim` for the build stage (MIT), nginx-unprivileged
`1.30.4-alpine3.24` (BSD-2-Clause), PostgreSQL `16.15-bookworm` (PostgreSQL
License), MariaDB `11.4.13-noble` (GPLv2), and Certbot `v5.1.0` (Apache-2.0).
They are open-source components suitable for commercial deployment. Tags are
explicit rather than `latest`; availability must remain covered by image-build
CI when they are updated.
