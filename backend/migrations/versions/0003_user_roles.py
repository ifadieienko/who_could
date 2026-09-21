"""Add users/roles administration tables.

Revision ID: 0003_user_roles
Revises: 0002_postgres_least_privilege
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_user_roles"
down_revision = "0002_postgres_least_privilege"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )

    roles = sa.table(
        "roles",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("is_system", sa.Boolean()),
    )
    op.bulk_insert(
        roles,
        [
            {"id": 1, "name": "admin", "description": "Administrator: manage users and roles", "is_system": True},
            {"id": 2, "name": "user", "description": "Base application user", "is_system": True},
        ],
    )

    bind = op.get_bind()
    existing_user_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM users ORDER BY id")).fetchall()]
    if existing_user_ids:
        user_role_table = sa.table(
            "user_roles",
            sa.column("user_id", sa.Integer()),
            sa.column("role_id", sa.Integer()),
        )
        bind.execute(user_role_table.insert(), [{"user_id": user_id, "role_id": 2} for user_id in existing_user_ids])
        bind.execute(user_role_table.insert(), {"user_id": existing_user_ids[0], "role_id": 1})


def downgrade():
    op.drop_table("user_roles")
    op.drop_table("roles")
