"""Database engine and session management."""

import logging
from contextlib import contextmanager
from typing import Generator
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Ensure SQLite data directory exists
if settings.DATABASE_URL.startswith("sqlite"):
    db_path_str = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    db_path = Path(db_path_str)
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI route handlers."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for background tasks and services."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables and run lightweight schema migrations."""
    from app.models.db_models import Document, Chunk, ChatSession, ChatMessage, Question, ValidationLog  # noqa: F401
    
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified and initialized.")

    # Lightweight migration for SQLite to ensure all columns exist
    if settings.DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                res = conn.execute(text("PRAGMA table_info(questions);")).fetchall()
                existing_cols = {row[1] for row in res}
                
                if existing_cols:
                    if "question_type" not in existing_cols:
                        logger.info("Migrating database: adding question_type column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN question_type VARCHAR DEFAULT 'esai';"))
                        conn.commit()

                    if "explanation" not in existing_cols:
                        logger.info("Migrating database: adding explanation column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN explanation TEXT;"))
                        conn.commit()

                    if "source_reference" not in existing_cols:
                        logger.info("Migrating database: adding source_reference column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN source_reference TEXT;"))
                        conn.commit()
        except Exception as e:
            logger.warning("Lightweight migration check encountered error (non-fatal): %s", e)
