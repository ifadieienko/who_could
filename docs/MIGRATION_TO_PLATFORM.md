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

0013 adds job vertical/type/priority and optional site references. No order is
recreated and no workflow or form snapshot is changed. Existing order URLs and
API clients remain compatible with the generic job endpoints.
