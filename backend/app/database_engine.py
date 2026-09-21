"""Shared MariaDB SQLAlchemy engine construction for the API and Alembic."""
from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

from .config import Settings, settings


def database_connect_args(configuration: Settings, backend_name: str) -> dict[str, Any]:
    """Build MariaDB driver connect arguments without rendering credentials."""
    if backend_name != "mariadb":
        raise RuntimeError("Only MariaDB is supported")
    if configuration.database_ssl_ca:
        return {"ssl": {"ca": configuration.database_ssl_ca}}
    return {}


def create_database_engine(*, configuration: Settings = settings, poolclass=None) -> Engine:
    """Create the MariaDB engine with identical URL/TLS semantics for every caller."""
    url = make_url(configuration.database_url)
    backend_name = url.get_backend_name()
    if backend_name != "mariadb":
        raise RuntimeError("Only MariaDB is supported")
    options: dict[str, Any] = {
        "pool_pre_ping": configuration.pool_pre_ping,
        "connect_args": database_connect_args(configuration, backend_name),
    }
    if poolclass is not None:
        options["poolclass"] = poolclass
    else:
        options.update(
            pool_size=configuration.pool_size,
            max_overflow=configuration.max_overflow,
            pool_recycle=configuration.pool_recycle,
        )
    return create_engine(configuration.database_url, **options)
