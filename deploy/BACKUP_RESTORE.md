# Backup and restore

Production uses MariaDB. `sudo ./server.sh backup` creates two companion objects:

- `/opt/who-could/backups/mariadb_<UTC>.sql`, mode `0600`: `mariadb-dump --single-transaction`.
- The directory `<same SQL filename>.assets/`, mode `0700`, containing `uploads.tar`, mode `0600`: full images and thumbnails from the persistent repair uploads volume.

Copy both together. If `BACKUP_EXPORT_DIR` is configured, both are copied to the mounted off-host destination. Older releases stored intake photos inside SQL; their attachment archive is empty. Archive filenames are UUIDs and contain no user-provided paths.

Photos are immutable and are not deleted by the application. The SQL snapshot is taken before the attachment copy, so concurrent new uploads may add extra files to the archive without invalidating the database snapshot. A pre-update backup stops backend writes first. Do not independently prune uploads while a backup is running.

`sudo ./server.sh restore BACKUP.sql` checks the dump, makes an emergency backup, requires `RESTORE`, stops the backend, replaces the database, restores the companion photos when present, runs Alembic upgrade/check, restarts and checks health. It does not execute Alembic downgrade. Legacy SQL-only backups remain readable; a modern backup without its companion cannot recover its photos. Restore tests should verify file downloads as well as SQL records. The file restore accepts only flat UUID JPEG entries, rejects links/path traversal and writes each object atomically; unrelated newer files are retained.

External MariaDB backups remain the provider/operator's responsibility. Coordinate its consistent database snapshot with a copy of the uploads volume; the built-in `backup` command deliberately refuses to claim an external database backup. To stream only attachments with the same Compose environment and overlays as your deployment:

```bash
docker compose ... exec -T backend python -m app.backup_uploads export > uploads.tar
```

The `...` above means your deployment's actual `--env-file` and `-f` arguments; do not paste it literally. Do not expose a provider database password on the command line. Keep the SQL snapshot, attachment archive and application release together.

A backup on the same VPS does not protect against loss of the VPS. Encrypt off-host storage, set retention, and regularly restore into a separate environment. Changes made after a restored snapshot are lost. See [the workshop migration notes](../docs/WORKSHOP_RELEASE.md) before upgrading existing data.
