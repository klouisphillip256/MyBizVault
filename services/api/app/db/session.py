from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings, sqlalchemy_database_url


engine = create_engine(
    sqlalchemy_database_url(settings.database_url),
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db() -> Generator[DbSession, None, None]:
    with DbSession(engine) as db:
        yield db
