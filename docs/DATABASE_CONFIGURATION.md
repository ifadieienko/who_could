# Database and secret configuration

The schema is managed by Alembic. Run `cd backend && alembic upgrade head` before starting the API; startup never creates or deletes tables. `alembic downgrade -1` removes the initial schema and is destructive.

## Precedence and settings

1. `DATABASE_URL` is used unchanged when present.
2. Otherwise `DATABASE_ENGINE` enables structured settings and SQLAlchemy `URL.create()` safely escapes credentials.
3. Otherwise the local default is `backend/data/who_could.db` (SQLite).

| Setting | Default | Purpose, when to change, and security |
|---|---|---|
| `WHO_COULD_ENV` | `production` | Use `development` only locally; it permits a random, restart-volatile signing secret. |
| `WHO_COULD_SECRET` | none | Token signing secret, at least 32 characters. Never commit it. |
| `WHO_COULD_SECRET_FILE` | none | Preferred secret-file path; overrides the value above. File errors fail startup without revealing content. |
| `DATABASE_URL` | none | Complete SQLAlchemy URL. It has highest DB precedence; protect it if it contains credentials. |
| `DATABASE_ENGINE` | none | `postgresql` or `mariadb`; activates structured configuration. |
| `DATABASE_HOST` | `localhost` | Database DNS name/address. |
| `DATABASE_PORT` | 5432/3306 | Server port selected by engine. |
| `DATABASE_NAME` | `who_could` | Database/schema name. |
| `DATABASE_USER` | none | Least-privileged application account. |
| `DATABASE_PASSWORD` | none | Password value; prefer its file counterpart. |
| `DATABASE_PASSWORD_FILE` | none | Password file; overrides the value and supports `/run/secrets/*`. |
| `DATABASE_SSLMODE` | driver default | PostgreSQL `disable`, `prefer`, `require`, `verify-ca`, or `verify-full`. Prefer verification externally. |
| `DATABASE_SSL_CA` | none | CA file used by PostgreSQL pg8000 and MariaDB for verified TLS. No verification is disabled implicitly. |
| `DATABASE_POOL_SIZE` | `5` | Persistent server connections; tune to server capacity. Not applied to SQLite. |
| `DATABASE_MAX_OVERFLOW` | `5` | Temporary server connections above pool size. |
| `DATABASE_POOL_RECYCLE` | `1800` | Seconds before recycling server connections. |
| `DATABASE_POOL_PRE_PING` | `true` | Detect stale connections before checkout. |

A `_FILE` setting takes precedence over its matching plain value. Trailing newline characters are removed. Secrets and rendered connection URLs are not logged by application code.

## Deployment modes and examples

### A. Local SQLite

```dotenv
WHO_COULD_ENV=development
DATABASE_URL=sqlite:////data/who_could.db
```

Omit `DATABASE_URL` to use `backend/data/who_could.db`. SQLite is convenient for development, not the recommended multi-worker production database.

### B. PostgreSQL local/future Docker

Direct URL (special characters must be percent-encoded when writing a URL yourself):

```dotenv
DATABASE_URL=postgresql+pg8000://who_could:example-only@localhost:5432/who_could
```

Structured configuration safely escapes the password:

```dotenv
DATABASE_ENGINE=postgresql
DATABASE_HOST=db
DATABASE_PORT=5432
DATABASE_NAME=who_could
DATABASE_USER=who_could
DATABASE_PASSWORD_FILE=/run/secrets/database_password
```

### C. External PostgreSQL with TLS

```dotenv
DATABASE_ENGINE=postgresql
DATABASE_HOST=postgres.example.invalid
DATABASE_PORT=5432
DATABASE_NAME=who_could
DATABASE_USER=who_could
DATABASE_PASSWORD_FILE=/run/secrets/database_password
DATABASE_SSLMODE=verify-full
DATABASE_SSL_CA=/etc/ssl/certs/provider-postgresql-ca.pem
```

Use the provider's trusted system/root certificates and keep verification enabled.

### D. MariaDB local/future Docker

```dotenv
DATABASE_URL=mariadb+pymysql://who_could:example-only@localhost:3306/who_could
```

or:

```dotenv
DATABASE_ENGINE=mariadb
DATABASE_HOST=db
DATABASE_PORT=3306
DATABASE_NAME=who_could
DATABASE_USER=who_could
DATABASE_PASSWORD_FILE=/run/secrets/database_password
```

### E. External MariaDB with TLS

```dotenv
DATABASE_ENGINE=mariadb
DATABASE_HOST=mariadb.example.invalid
DATABASE_PORT=3306
DATABASE_NAME=who_could
DATABASE_USER=who_could
DATABASE_PASSWORD_FILE=/run/secrets/database_password
DATABASE_SSL_CA=/etc/ssl/certs/provider-ca.pem
```

Restrict secret/CA file permissions and use the provider CA. Docker Compose, proxies, firewall, CrowdSec, ACME, backups, Redis, and monitoring are intentionally deferred to the deployment stage.


## Existing SQLite databases from versions before Alembic

`alembic upgrade head` recognizes only the exact legacy `users`, `jobs`, and `applications` schema, including its primary keys, uniqueness, foreign-key cascades, status checks, and indexes. When it matches, Alembic renames the legacy tables, creates the canonical target schema, copies every row with its original ID and relationships, and removes the temporary legacy tables only after the copy succeeds. The resulting indexes, constraints, and column definitions match `Base.metadata`, so `alembic check` is clean while all data remains intact. A partial schema, extra application tables, changed columns, or missing constraints fails closed and must be reviewed manually; the application never blindly stamps an unknown database. Re-running the upgrade is safe. Make a normal filesystem backup before every schema operation.

The PostgreSQL driver is `pg8000` (BSD-3-Clause), selected instead of LGPL-licensed psycopg. `DATABASE_SSLMODE=verify-ca` builds a verified SSL context from `DATABASE_SSL_CA` without hostname matching; `verify-full` additionally verifies the hostname. `require` explicitly requests encrypted transport without certificate verification, while `disable` explicitly disables it. Because pg8000 has no libpq-style plaintext fallback, `prefer` chooses TLS with the platform trust store rather than silently falling back to plaintext. Use `verify-full` for external production databases.
