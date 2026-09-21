"""Add configurable device intake form templates.

Revision ID: 0004_device_intake_forms
Revises: 0003_user_roles
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_device_intake_forms"
down_revision = "0003_user_roles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "device_intake_forms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_device_intake_forms_owner_id", "device_intake_forms", ["owner_id"])
    op.create_table(
        "device_intake_fields",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("form_id", sa.Integer(), sa.ForeignKey("device_intake_forms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("field_type", sa.String(length=10), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("form_id", "position", name="uq_device_intake_field_position"),
        sa.CheckConstraint("field_type IN ('string','number')", name="ck_device_intake_field_type"),
    )
    op.create_index("ix_device_intake_fields_form_id", "device_intake_fields", ["form_id"])


def downgrade():
    op.drop_index("ix_device_intake_fields_form_id", table_name="device_intake_fields")
    op.drop_table("device_intake_fields")
    op.drop_index("ix_device_intake_forms_owner_id", table_name="device_intake_forms")
    op.drop_table("device_intake_forms")
