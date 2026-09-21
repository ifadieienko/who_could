"""Separate versioned stage forms and subscription entitlements; preserve old orders."""

from alembic import op
import sqlalchemy as sa

revision = "0010_stage_forms_plans"
down_revision = "0009_workshop_platform"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workshops",
        sa.Column("plan", sa.String(30), nullable=False, server_default="starter"),
    )
    op.add_column(
        "repair_templates",
        sa.Column("purpose", sa.String(20), nullable=False, server_default="intake"),
    )
    op.add_column(
        "repair_orders",
        sa.Column(
            "stage_forms", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
    )


def downgrade():
    raise RuntimeError(
        "Restore a database backup; downgrading would discard completed stage forms."
    )
