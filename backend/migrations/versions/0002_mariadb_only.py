"""Compatibility marker for the MariaDB-only deployment line.

The revision identifier is intentionally preserved because existing MariaDB
installations may already have it recorded in alembic_version from earlier
releases. PostgreSQL-specific migration logic has been removed.
"""

revision = "0002_postgres_least_privilege"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
