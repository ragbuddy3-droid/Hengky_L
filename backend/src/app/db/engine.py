"""Database engine and session management."""

from typing import Generator
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db() -> Generator:
    """Dependency generator for FastAPI Depends()."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for background tasks and non-FastAPI code."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db() -> None:
    """Create all tables in the database and perform lightweight schema migrations."""
    Base.metadata.create_all(bind=engine)
    
    with engine.connect() as conn:
        try:
            from sqlalchemy import text
            result = conn.execute(text("PRAGMA table_info(questions)"))
            columns = [row[1] for row in result.fetchall()]
            if columns:
                if "question_type" not in columns:
                    conn.execute(text("ALTER TABLE questions ADD COLUMN question_type TEXT DEFAULT 'esai'"))
                if "explanation" not in columns:
                    conn.execute(text("ALTER TABLE questions ADD COLUMN explanation TEXT"))
                if "source_reference" not in columns:
                    conn.execute(text("ALTER TABLE questions ADD COLUMN source_reference TEXT"))
                conn.commit()
        except Exception:
            pass
