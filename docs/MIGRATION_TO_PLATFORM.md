# Incremental platform migration

Migrations 0001–0010 are immutable. Back up the database and files before upgrading
an existing installation, using the existing procedures in WORKSHOP_RELEASE.md.

0011 adds organization metadata/version and a job currency column. Existing
workshop and job IDs, URLs, form snapshots, workflows, files, estimates, payments,
and memberships remain intact. Legacy organizations default to repair/Russian,
Europe/Warsaw, Poland and PLN; change timezone if this differs from your business.
New organization records default to English. UI translation beyond organization
settings is still in progress.

Existing role permissions gain generic aliases without removing legacy values.
The new generic form/workflow permissions are independent for newly edited roles.

Apply using the deployment's existing Alembic upgrade-to-head step. Do not run a
database reset. Downgrade is intentionally refused: restore a verified database
and matching files backup if rollback is required.

Automated migration gates cover an empty database, the populated pre-workshop
0008 fixture, and a populated 0010 fixture. The latter compares every original
column across the upgrade, allowing only additive permission aliases.

0012 extends `repair_devices` into the generic Asset model in place. Existing
primary keys and order foreign keys do not change. `name` starts from `model`;
new asset timestamps on historic records indicate migration time, not a known
original purchase/intake date. Customers gain person/company details. Optional
sites are stored separately. Both devices and sites stay within their tenant;
asset external IDs are unique per tenant when supplied. Asset/customer removal
is not exposed; asset retirement preserves history.

0013 adds `vertical_key`, `job_type`, `priority`, and nullable `site_id` to
`repair_orders`. Existing jobs receive `repair`, `repair`, `normal`, and NULL.
No identity, customer/device link, currency, snapshot, history or version changes.
The migration deliberately does not copy a current asset site into historic jobs.
Back up the database and uploads and stop application writes before upgrading.
Run Alembic upgrade to head with the new backend, then restart it; the new model
requires the new columns. Downgrade is refused; rollback requires the matching
pre-upgrade code and verified backup.


0014 creates `job_form_instances` and copies every stage form, including custom
slots, from the frozen job JSON. Original rows, snapshots, receipts and job
versions are unchanged. Instance versions start at 1; timestamps inherit the
job timestamps (not an inferred history of individual form edits). Family is
resolved only from a same-organization template; missing metadata remains NULL.
The schema and revision always come from the frozen snapshot, never today's
published template. Intake is not migrated in this step.

Stop all application writers and take a database/files backup before upgrading.
Deploy 0014 and its matching backend together; do not run an older backend against
the new schema because it cannot maintain the instance mirror. SQL backups
include the new table; portable organization exports include its rows as well.
Rollback requires restoring the backup and matching code, not deleting the table.
