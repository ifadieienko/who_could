# Backup and restore

`sudo ./server.sh backup` writes a mode-and-UTC-timestamped file beneath
`/opt/who-could/backups` with mode `0600`:

* SQLite uses the SQLite online backup API rather than copying a live WAL file.
* PostgreSQL uses `pg_dump -Fc` (custom/compressed logical format).
* MariaDB uses `mariadb-dump --single-transaction`.

External database backups are not attempted: the command explicitly directs
the operator to provider/operator backup facilities and does not claim success.

`sudo ./server.sh restore BACKUP` checks the expected extension, identifies the
target, first makes an emergency backup, requires the exact word `RESTORE`,
stops the backend, restores with SQLite/PostgreSQL/MariaDB-native tooling, runs
Alembic upgrade/check, restarts, and health-checks. It never runs an Alembic
downgrade. Test restores regularly and define retention appropriate to policy.

**A backup on the same VPS does not protect against loss of the VPS.** Copy
encrypted backups off-server. Automated off-site scheduling is deferred to a
future operations PR.
