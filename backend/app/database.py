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
            session.rollback(); raise


def reset_db() -> None:
    """Explicit destructive helper for isolated development/test databases."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def clear_db() -> None:
    """Delete test data without replacing the Alembic-created schema."""
    from .models import Application, DeviceIntakeField, DeviceIntakeForm, DeviceIntakeOrder, Job, Role, User, WarehouseColumn, WarehouseRow, WarehouseTable, user_roles
    from .service_models import CustomerPickup, MasterBoardColumn, MasterWorkItem
    with engine.begin() as connection:
        connection.execute(user_roles.delete())
        connection.execute(CustomerPickup.__table__.delete())
        connection.execute(MasterWorkItem.__table__.delete())
        connection.execute(MasterBoardColumn.__table__.delete())
        connection.execute(WarehouseRow.__table__.delete())
        connection.execute(WarehouseColumn.__table__.delete())
        connection.execute(WarehouseTable.__table__.delete())
        connection.execute(DeviceIntakeOrder.__table__.delete())
        connection.execute(DeviceIntakeField.__table__.delete())
        connection.execute(DeviceIntakeForm.__table__.delete())
        connection.execute(Application.__table__.delete())
        connection.execute(Job.__table__.delete())
        connection.execute(User.__table__.delete())
        connection.execute(Role.__table__.delete().where(Role.is_system.is_(False)))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Explicitly reset the configured development database")
    parser.add_argument("--reset", action="store_true", required=True, help="destroy all data and recreate the schema")
    parser.parse_args()
    if settings.environment != "development":
        raise SystemExit("Refusing reset unless WHO_COULD_ENV=development")
    reset_db()
    print("Development database reset (connection credentials hidden).")
