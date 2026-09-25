"""Generic job metadata while preserving repair orders and their snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "0013_generic_jobs"
down_revision = "0012_assets_customers_sites"
branch_labels = depends_on = None


def upgrade():
    for name, length, value in [
        ("vertical_key", 30, "repair"),
        ("job_type", 80, "repair"),
        ("priority", 20, "normal"),
    ]:
        op.add_column(
            "repair_orders",
            sa.Column(name, sa.String(length), nullable=False, server_default=value),
        )
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE repair_orders ADD COLUMN site_id INTEGER REFERENCES customer_sites(id)"
        )
    else:
        op.add_column(
            "repair_orders", sa.Column("site_id", sa.Integer(), nullable=True)
        )
        op.create_foreign_key(
            "fk_job_site", "repair_orders", "customer_sites", ["site_id"], ["id"]
        )


def downgrade():
    raise RuntimeError(
        "Restore a verified backup; generic job context cannot be discarded safely."
    )
