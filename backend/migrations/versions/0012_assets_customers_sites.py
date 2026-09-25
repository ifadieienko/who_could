"""Promote devices to generic assets without replacing rows or order links."""

from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = "0012_assets_customers_sites"
down_revision = "0011_organizations"
branch_labels = depends_on = None


def upgrade():
    for name, length, default in [
        ("kind", 20, "person"),
        ("company_name", 160, ""),
        ("tax_id", 80, ""),
        ("contact_person", 160, ""),
    ]:
        op.add_column(
            "repair_customers",
            sa.Column(name, sa.String(length), nullable=False, server_default=default),
        )
    op.add_column(
        "repair_customers",
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "repair_customers",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "customer_sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False
        ),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("repair_customers.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_customer_sites_workshop_id", "customer_sites", ["workshop_id"])
    op.create_index("ix_customer_sites_customer_id", "customer_sites", ["customer_id"])
    for name, length, default in [
        ("asset_type", 80, "device"),
        ("name", 160, ""),
        ("manufacturer", 160, ""),
        ("status", 30, "active"),
    ]:
        op.add_column(
            "repair_devices",
            sa.Column(name, sa.String(length), nullable=False, server_default=default),
        )
    op.add_column(
        "repair_devices",
        sa.Column(
            "custom_values", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    for name in ("created_at", "updated_at"):
        op.add_column(
            "repair_devices",
            sa.Column(
                name,
                sa.DateTime(),
                nullable=False,
                server_default=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    op.add_column(
        "repair_devices",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE repair_devices ADD COLUMN site_id INTEGER REFERENCES customer_sites(id)"
        )
    else:
        op.add_column(
            "repair_devices", sa.Column("site_id", sa.Integer(), nullable=True)
        )
        op.create_foreign_key(
            "fk_asset_site", "repair_devices", "customer_sites", ["site_id"], ["id"]
        )
    op.add_column(
        "repair_devices", sa.Column("external_id", sa.String(160), nullable=True)
    )
    op.create_index(
        "uq_asset_external_id",
        "repair_devices",
        ["workshop_id", "external_id"],
        unique=True,
    )
    op.execute("UPDATE repair_devices SET name = model")
    # Keep both names for existing code while granting customer creation to roles
    # already allowed to create repair orders with embedded customer data.
    roles = sa.table(
        "workshop_roles",
        sa.column("id", sa.Integer()),
        sa.column("permissions", sa.JSON()),
    )
    conn = op.get_bind()
    for row in conn.execute(sa.select(roles)).mappings().all():
        p = set(row["permissions"])
        if {"orders.create", "jobs.create"} & p:
            p.add("customers.write")
            conn.execute(
                roles.update()
                .where(roles.c.id == row["id"])
                .values(permissions=sorted(p))
            )


def downgrade():
    raise RuntimeError(
        "Restore a verified backup; asset and site history must be preserved."
    )
