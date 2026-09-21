"""SQLAlchemy engine and explicit development/test database helpers."""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base
from .database_engine import create_database_engine

engine = create_database_engine()

SessionLocal = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _test_models():
    if settings.environment not in {"development", "test"}:
        raise RuntimeError("Destructive database helpers are disabled in production")
    from . import repair_models, service_models  # register every table


def reset_db() -> None:
    """Explicit destructive helper for isolated development/test databases."""
    _test_models()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def clear_db() -> None:
    """Delete data only in an explicitly configured development/test database."""
    _test_models()
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Explicitly reset the configured development database"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        required=True,
        help="destroy all data and recreate the schema",
    )
    parser.parse_args()
    if settings.environment != "development":
        raise SystemExit("Refusing reset unless WHO_COULD_ENV=development")
    reset_db()
    print("Development database reset (connection credentials hidden).")
