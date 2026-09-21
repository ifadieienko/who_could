"""Add master service board and customer pickup workflow.

Revision ID: 0008_master_service_board
Revises: 0007_device_intake_orders
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_master_service_board"
down_revision = "0007_device_intake_orders"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "master_board_columns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_terminal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_id", "position", name="uq_master_board_column_position"),
    )
    op.create_index("ix_master_board_columns_owner_id", "master_board_columns", ["owner_id"])

    op.create_table(
        "master_work_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("device_intake_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("column_id", sa.Integer(), sa.ForeignKey("master_board_columns.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", name="uq_master_work_items_order_id"),
    )
    op.create_index("ix_master_work_items_order_id", "master_work_items", ["order_id"])
    op.create_index("ix_master_work_items_master_id", "master_work_items", ["master_id"])
    op.create_index("ix_master_work_items_column_id", "master_work_items", ["column_id"])

    op.create_table(
        "customer_pickups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("device_intake_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intake_owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("master_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="ready"),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('ready','issued')", name="ck_customer_pickup_status"),
        sa.UniqueConstraint("order_id", name="uq_customer_pickups_order_id"),
    )
    op.create_index("ix_customer_pickups_order_id", "customer_pickups", ["order_id"])
    op.create_index("ix_customer_pickups_intake_owner_id", "customer_pickups", ["intake_owner_id"])
    op.create_index("ix_customer_pickups_master_id", "customer_pickups", ["master_id"])
    op.create_index("ix_customer_pickups_status", "customer_pickups", ["status"])


def downgrade():
    op.drop_index("ix_customer_pickups_status", table_name="customer_pickups")
    op.drop_index("ix_customer_pickups_master_id", table_name="customer_pickups")
    op.drop_index("ix_customer_pickups_intake_owner_id", table_name="customer_pickups")
    op.drop_index("ix_customer_pickups_order_id", table_name="customer_pickups")
    op.drop_table("customer_pickups")

    op.drop_index("ix_master_work_items_column_id", table_name="master_work_items")
    op.drop_index("ix_master_work_items_master_id", table_name="master_work_items")
    op.drop_index("ix_master_work_items_order_id", table_name="master_work_items")
    op.drop_table("master_work_items")

    op.drop_index("ix_master_board_columns_owner_id", table_name="master_board_columns")
    op.drop_table("master_board_columns")
