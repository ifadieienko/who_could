"""Add configurable warehouse tables and rows.

Revision ID: 0005_warehouse
Revises: 0004_device_intake_forms
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_warehouse"
down_revision = "0004_device_intake_forms"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "warehouse_tables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_warehouse_tables_owner_id", "warehouse_tables", ["owner_id"])

    op.create_table(
        "warehouse_columns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("warehouse_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("field_type", sa.String(length=12), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "field_type IN ('string','number','date','image','barcode','qrcode')",
            name="ck_warehouse_column_type",
        ),
        sa.UniqueConstraint("table_id", "position", name="uq_warehouse_column_position"),
    )
    op.create_index("ix_warehouse_columns_table_id", "warehouse_columns", ["table_id"])

    op.create_table(
        "warehouse_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("warehouse_tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_warehouse_rows_table_id", "warehouse_rows", ["table_id"])


def downgrade():
    op.drop_index("ix_warehouse_rows_table_id", table_name="warehouse_rows")
    op.drop_table("warehouse_rows")
    op.drop_index("ix_warehouse_columns_table_id", table_name="warehouse_columns")
    op.drop_table("warehouse_columns")
    op.drop_index("ix_warehouse_tables_owner_id", table_name="warehouse_tables")
    op.drop_table("warehouse_tables")
