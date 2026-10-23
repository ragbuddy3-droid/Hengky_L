"""Database engine and session management. Importing this module creates no tables; see core.migrations.init_db."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _create_engine():
    db = get_settings().database
    if not db.is_sqlite:
        return create_engine(db.url, pool_pre_ping=True)

    if database := make_url(db.url).database:
        Path(database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(db.url, connect_args={"check_same_thread": False, "timeout": 30}, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        # WAL lets the background generation write while requests read
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Session for background tasks, services and scripts; rolled back on error, always closed."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
