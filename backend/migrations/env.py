from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from app.config import settings
from app.database_engine import create_database_engine
from app.models import Base
from app import service_models  # noqa: F401 - registers service tables in Base.metadata

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def offline():
    url = settings.database_url.render_as_string(hide_password=False) if hasattr(settings.database_url, "render_as_string") else settings.database_url
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def online():
    # NullPool is appropriate for a one-shot migration; URL, driver and TLS
    # connect_args are shared with the application runtime.
    connectable = create_database_engine(poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


offline() if context.is_offline_mode() else online()
