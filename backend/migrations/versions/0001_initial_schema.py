"""Create the canonical schema or safely transform the exact legacy SQLite schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

DOMAIN_TABLES = {"users", "jobs", "applications"}
LEGACY_COLUMNS = {
    "users": [("id", "INTEGER"), ("name", "TEXT"), ("email", "TEXT"), ("password_hash", "TEXT"), ("city", "TEXT"), ("bio", "TEXT"), ("skills", "TEXT"), ("created_at", "TEXT")],
    "jobs": [("id", "INTEGER"), ("owner_id", "INTEGER"), ("title", "TEXT"), ("description", "TEXT"), ("category", "TEXT"), ("work_mode", "TEXT"), ("duration", "TEXT"), ("location", "TEXT"), ("budget_type", "TEXT"), ("budget_min", "INTEGER"), ("budget_max", "INTEGER"), ("currency", "TEXT"), ("deadline", "TEXT"), ("skills", "TEXT"), ("status", "TEXT"), ("created_at", "TEXT")],
    "applications": [("id", "INTEGER"), ("job_id", "INTEGER"), ("applicant_id", "INTEGER"), ("message", "TEXT"), ("proposed_rate", "INTEGER"), ("estimated_time", "TEXT"), ("status", "TEXT"), ("created_at", "TEXT")],
}
LEGACY_NOT_NULL = {
    "users": {"name", "email", "password_hash", "created_at"},
    "jobs": {"owner_id", "title", "description", "category", "work_mode", "duration", "budget_type", "currency", "status", "created_at"},
    "applications": {"job_id", "applicant_id", "message", "status", "created_at"},
}
LEGACY_DEFAULTS = {
    "users": {"created_at": "current_timestamp"},
    "jobs": {"currency": "'usd'", "status": "'open'", "created_at": "current_timestamp"},
    "applications": {"status": "'sent'", "created_at": "current_timestamp"},
}
LEGACY_CHECKS = {
    "jobs": {"work_modein('online','offline','hybrid')", "durationin('one_day','short','long')", "budget_typein('fixed','hourly','negotiable')", "statusin('open','in_progress','closed')"},
    "applications": {"statusin('sent','accepted','declined')"},
}

def _normalize(value):
    if value is None:
        return None
    value = "".join(str(value).split()).lower()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    return value

def _is_exact_legacy_schema():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    present = set(inspector.get_table_names()) - {"alembic_version"}
    if not present:
        return False
    if bind.dialect.name != "sqlite" or present != DOMAIN_TABLES:
        raise RuntimeError("Refusing to adopt an unknown or partial existing database schema")
    for table, expected in LEGACY_COLUMNS.items():
        columns = inspector.get_columns(table)
        actual = [(column["name"], str(column["type"]).upper()) for column in columns]
        if actual != expected:
            raise RuntimeError(f"Refusing to adopt incompatible legacy columns or types: {table}")
        not_null = {column["name"] for column in columns if not column["nullable"]}
        defaults = {column["name"]: _normalize(column["default"]) for column in columns if column["default"] is not None}
        if not_null != LEGACY_NOT_NULL[table] or defaults != LEGACY_DEFAULTS[table]:
            raise RuntimeError(f"Refusing to adopt incompatible legacy nullability/defaults: {table}")
        if inspector.get_pk_constraint(table).get("constrained_columns") != ["id"]:
            raise RuntimeError(f"Refusing to adopt incompatible legacy primary key: {table}")
    uniques = {table: {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table)} for table in DOMAIN_TABLES}
    expected_uniques = {"users": {("email",)}, "jobs": set(), "applications": {("job_id", "applicant_id")}}
    if uniques != expected_uniques:
        raise RuntimeError("Refusing to adopt incompatible legacy uniqueness")
    expected_fks = {
        "jobs": {(("owner_id",), "users", ("id",), "CASCADE")},
        "applications": {(("job_id",), "jobs", ("id",), "CASCADE"), (("applicant_id",), "users", ("id",), "CASCADE")},
    }
    for table, expected in expected_fks.items():
        actual = {(tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]), (fk.get("options") or {}).get("ondelete")) for fk in inspector.get_foreign_keys(table)}
        if actual != expected:
            raise RuntimeError(f"Refusing to adopt incompatible legacy foreign keys: {table}")
    expected_indexes = {"users": set(), "jobs": {("idx_jobs_owner", ("owner_id",)), ("idx_jobs_status", ("status",))}, "applications": {("idx_applications_job", ("job_id",)), ("idx_applications_applicant", ("applicant_id",))}}
    for table, expected in expected_indexes.items():
        actual = {(item["name"], tuple(item["column_names"])) for item in inspector.get_indexes(table)}
        if actual != expected:
            raise RuntimeError(f"Refusing to adopt incompatible legacy indexes: {table}")
        checks = {_normalize(item["sqltext"]) for item in inspector.get_check_constraints(table)}
        if checks != LEGACY_CHECKS.get(table, set()):
            raise RuntimeError(f"Refusing to adopt incompatible legacy checks: {table}")
    return True

def _create_canonical_schema():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(80), nullable=False), sa.Column("email", sa.String(320), nullable=False, unique=True), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("city", sa.String(80)), sa.Column("bio", sa.Text()), sa.Column("skills", sa.String(400)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("jobs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("title", sa.String(120), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("category", sa.String(80), nullable=False), sa.Column("work_mode", sa.String(10), nullable=False), sa.Column("duration", sa.String(10), nullable=False), sa.Column("location", sa.String(120)), sa.Column("budget_type", sa.String(12), nullable=False), sa.Column("budget_min", sa.Integer()), sa.Column("budget_max", sa.Integer()), sa.Column("currency", sa.String(3), nullable=False), sa.Column("deadline", sa.Date()), sa.Column("skills", sa.String(400)), sa.Column("status", sa.String(12), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("work_mode IN ('online','offline','hybrid')", name="ck_jobs_work_mode"), sa.CheckConstraint("duration IN ('one_day','short','long')", name="ck_jobs_duration"), sa.CheckConstraint("budget_type IN ('fixed','hourly','negotiable')", name="ck_jobs_budget_type"), sa.CheckConstraint("status IN ('open','in_progress','closed')", name="ck_jobs_status"))
    op.create_index("ix_jobs_owner_id", "jobs", ["owner_id"]); op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_table("applications", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("job_id", sa.Integer(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False), sa.Column("applicant_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("proposed_rate", sa.Integer()), sa.Column("estimated_time", sa.String(120)), sa.Column("status", sa.String(10), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("job_id", "applicant_id", name="uq_application_job_applicant"), sa.CheckConstraint("status IN ('sent','accepted','declined')", name="ck_applications_status"))
    op.create_index("ix_applications_job_id", "applications", ["job_id"]); op.create_index("ix_applications_applicant_id", "applications", ["applicant_id"])


def _canonicalize_legacy_schema():
    # Renaming first leaves the original data untouched until all canonical
    # tables have been created and populated successfully in this migration.
    op.rename_table("applications", "_legacy_applications")
    op.rename_table("jobs", "_legacy_jobs")
    op.rename_table("users", "_legacy_users")
    _create_canonical_schema()
    op.execute(sa.text("INSERT INTO users (id,name,email,password_hash,city,bio,skills,created_at) SELECT id,name,email,password_hash,city,bio,skills,created_at FROM _legacy_users"))
    op.execute(sa.text("INSERT INTO jobs (id,owner_id,title,description,category,work_mode,duration,location,budget_type,budget_min,budget_max,currency,deadline,skills,status,created_at) SELECT id,owner_id,title,description,category,work_mode,duration,location,budget_type,budget_min,budget_max,currency,deadline,skills,status,created_at FROM _legacy_jobs"))
    op.execute(sa.text("INSERT INTO applications (id,job_id,applicant_id,message,proposed_rate,estimated_time,status,created_at) SELECT id,job_id,applicant_id,message,proposed_rate,estimated_time,status,created_at FROM _legacy_applications"))
    op.drop_table("_legacy_applications")
    op.drop_table("_legacy_jobs")
    op.drop_table("_legacy_users")

def upgrade():
    if _is_exact_legacy_schema():
        _canonicalize_legacy_schema()
    else:
        _create_canonical_schema()

def downgrade():
    op.drop_table("applications")
    op.drop_table("jobs")
    op.drop_table("users")
