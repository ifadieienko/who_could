"""Organization metadata and immutable per-job currency; preserve tenant identities."""
from alembic import op
import sqlalchemy as sa

revision = "0011_organizations"
down_revision = "0010_stage_forms_plans"
branch_labels = depends_on = None


def upgrade():
    for name, length, default in [
        ("vertical_key", 30, "repair"), ("locale", 10, "ru"),
        ("timezone", 80, "Europe/Warsaw"), ("currency", 3, "PLN"), ("country", 2, "PL")]:
        op.add_column("workshops", sa.Column(name, sa.String(length), nullable=False, server_default=default))
    op.add_column("workshops", sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("workshops", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("repair_orders", sa.Column("currency", sa.String(3), nullable=False, server_default="PLN"))
    roles = sa.table("workshop_roles", sa.column("id", sa.Integer()), sa.column("permissions", sa.JSON()), sa.column("is_owner", sa.Boolean()))
    conn = op.get_bind()
    for row in conn.execute(sa.select(roles)).mappings().all():
        p = set(row["permissions"])
        p.update("jobs." + x[7:] for x in list(p) if x.startswith("orders."))
        if "contacts.read" in p:
            p.update({"customers.read", "assets.read"})
        if "orders.create" in p:
            p.add("assets.write")
        if "templates.manage" in p:
            p.update({"forms.manage", "workflows.manage"})
        if row["is_owner"]:
            p.update({"organization.manage", "documents.manage"})
        conn.execute(roles.update().where(roles.c.id == row["id"]).values(permissions=sorted(p)))


def downgrade():
    raise RuntimeError("Restore a verified backup; dropping organization data is unsafe.")
