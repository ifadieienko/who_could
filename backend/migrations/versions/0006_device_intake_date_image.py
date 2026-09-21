"""Allow date and image fields in device intake templates.

Revision ID: 0006_device_intake_date_image
Revises: 0005_warehouse
"""
from alembic import op


revision = "0006_device_intake_date_image"
down_revision = "0005_warehouse"
branch_labels = None
depends_on = None


def _replace_constraint(allowed: str):
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("device_intake_fields", recreate="always") as batch:
            batch.drop_constraint("ck_device_intake_field_type", type_="check")
            batch.create_check_constraint("ck_device_intake_field_type", allowed)
    else:
        op.drop_constraint("ck_device_intake_field_type", "device_intake_fields", type_="check")
        op.create_check_constraint("ck_device_intake_field_type", "device_intake_fields", allowed)


def upgrade():
    _replace_constraint("field_type IN ('string','number','date','image')")


def downgrade():
    _replace_constraint("field_type IN ('string','number')")
