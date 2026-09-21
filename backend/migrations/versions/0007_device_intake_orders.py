"""Add persistent device intake orders.

Revision ID: 0007_device_intake_orders
Revises: 0006_device_intake_date_image
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_device_intake_orders"
down_revision = "0006_device_intake_date_image"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_intake_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("form_id", sa.Integer(), sa.ForeignKey("device_intake_forms.id", ondelete="SET NULL"), nullable=True),
        sa.Column("form_name", sa.String(length=120), nullable=False),
        sa.Column("fields_snapshot", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('deferred','accepted')", name="ck_device_intake_order_status"),
    )
    op.create_index("ix_device_intake_orders_owner_id", "device_intake_orders", ["owner_id"])
    op.create_index("ix_device_intake_orders_form_id", "device_intake_orders", ["form_id"])
    op.create_index("ix_device_intake_orders_status", "device_intake_orders", ["status"])


def downgrade():
    op.drop_index("ix_device_intake_orders_status", table_name="device_intake_orders")
    op.drop_index("ix_device_intake_orders_form_id", table_name="device_intake_orders")
    op.drop_index("ix_device_intake_orders_owner_id", table_name="device_intake_orders")
    op.drop_table("device_intake_orders")
