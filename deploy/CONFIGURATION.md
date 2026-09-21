# Deployment configuration

Runtime configuration is `/opt/who-could/config/deployment.env`. It contains no
secret values and is parsed as data rather than sourced as shell code. During
reconfiguration stored values become defaults. Do not edit invalid/newline
values into it.

| Name | Default | Meaning / when to change | Security impact |
|---|---|---|---|
| `CONFIG_VERSION` | `2` | State schema version; v1 is migrated atomically and idempotently | Never downgrade manually |
| `HOST_SECURITY_ENABLED` | `false` | CrowdSec host layer was configured explicitly | Never enables a firewall in unattended setup by itself |
| `CROWDSEC_ENABLED` | `false` | CrowdSec engine integration state | CrowdSec remains a host systemd service |
| `HOST_FIREWALL_ENABLED` | `false` | Who could observed/enabled UFW rules | UFW is never enabled silently |
| `SSH_PORT` | `22` | Effective SSH port protected before optional UFW enable | Validated as 1–65535 |
| `DATABASE_MODE` | `postgresql-local` | One of five modes below | Selects data location and trust boundary |
| `PUBLIC_HOSTNAME` | `localhost` | DNS name used by Nginx/certificates | Validated to prevent config injection |
| `HTTP_PORT` / `HTTPS_PORT` | `80` / `443` | Public host ports | Opening them is the operator's responsibility |
| `HTTPS_MODE` | `disabled` | `acme`, `custom`, or `disabled` | Public sites should use verified TLS |
| `ACME_EMAIL` | none | Renewal notices in ACME mode | Required and validated for ACME |
| `DATABASE_NAME` / `DATABASE_USER` | `who_could` | Existing DB identity | Grant only schema/app permissions needed by Alembic |
| `DATABASE_HOST` / `DATABASE_PORT` | service default | External endpoint or local service | External networking/allowlists are operator-managed |
| `DATABASE_SSLMODE` | `verify-full` external PostgreSQL | pg8000 TLS verification | Do not weaken on public networks |
| `DATABASE_SSL_CA` | system trust / required for external MariaDB | CA bundle mounted/read by backend | Trust only the database provider CA |
| `BACKEND_MEMORY_LIMIT` | `512m` | Compose runtime memory limit | Raising affects VPS capacity |
| `WEB_MEMORY_LIMIT` | `256m` | Nginx memory limit | Raising affects VPS capacity |
| `DATABASE_MEMORY_LIMIT` | `1g` | Local DB memory limit | Ensure host has headroom |
| `SECRETS_GID` | `10001` | Supplemental container group | Must match protected host file group |
| `TLS_READER_GID` | `10002` | Supplemental web group for certificates | Grants read/traverse only to protected TLS material |

## Database modes

| Mode | Storage and connection |
|---|---|
| SQLite local | `/opt/who-could/data/sqlite/who_could.db`, bind-mounted at `/data`; survives recreate/rebuild |
| PostgreSQL local | Pinned PostgreSQL 16 image and named volume; private Docker network |
| PostgreSQL external | Existing host, port (5432), DB, user, hidden password; SSL defaults to `verify-full` and optional custom CA |
| MariaDB local | Pinned MariaDB 11.4 LTS image and named volume; private Docker network |
| MariaDB external | Existing host, port (3306), DB, user, hidden password and required verified-TLS CA |

External databases and users are never created. The endpoint must be reachable
from Docker, accept the supplied identity, and permit `SELECT 1` and Alembic's
schema changes. Cross-engine SQLite-to-server migration is intentionally not
performed; any existing SQLite file is retained.

Local database passwords are generated at first initialization. Reconfigure
keeps them unchanged because changing the `_FILE` after an official database
image has initialized its volume would not change the database-side account.
Rotation is deliberately refused by this foundation rather than creating a
silent mismatch. External database passwords are never randomly generated:
interactive setup reads them hidden, while non-interactive setup requires a
root-only `DATABASE_PASSWORD_FILE` input. Existing external passwords can be
kept or explicitly changed during interactive reconfiguration.

## Secrets

Compose file-backed secrets are **not HashiCorp Vault**. The values remain as
protected Linux host files in `/opt/who-could/secrets`, owned by root and the
dedicated numeric group with mode `0440` (never `0444`). Containers receive
only `/run/secrets/app_secret` and the selected mode-specific password file; the
non-root backend reads them through `WHO_COULD_SECRET_FILE` and
`DATABASE_PASSWORD_FILE`. Local PostgreSQL, local MariaDB, and external
databases have separate persistent secret files, so switching modes never
overwrites a local volume's original credential. MariaDB root credentials use its documented `_FILE`
variable. Values are absent from the env file, Compose YAML, image, and normal
logs. Anyone with root/Docker access can still read them.

Nginx rate zones are `auth` (10 requests/minute, burst 10) and `api` (10/second,
burst 40), keyed on the direct `$binary_remote_addr`. Do not trust proxy headers
until a future explicit Cloudflare/trusted-proxy configuration is added.
