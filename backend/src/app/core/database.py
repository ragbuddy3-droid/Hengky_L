"""Database engine and session management."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

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
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    } if settings.DATABASE_URL.startswith("sqlite") else {},
    echo=False,
    pool_pre_ping=True,
)

# Enable WAL mode for better SQLite concurrent access
if settings.DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

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
    from app.models.db_models import (  # noqa: F401
        ChatMessage,
        ChatSession,
        Chunk,
        Document,
        Question,
        ValidationLog,
    )

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified and initialized.")

    # Lightweight migration and index creation for SQLite
    if settings.DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                # Ensure foreign key indexes exist
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chunks_document_id ON chunks(document_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_questions_session_id ON questions(session_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id ON chat_messages(session_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_validation_logs_question_id ON validation_logs(question_id);"))
                conn.commit()

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

                    if "rubric" not in existing_cols:
                        logger.info("Migrating database: adding rubric column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN rubric TEXT;"))
                        conn.commit()

                    if "answer_elements" not in existing_cols:
                        logger.info("Migrating database: adding answer_elements column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN answer_elements TEXT;"))
                        conn.commit()

                    if "grounding_evidence" not in existing_cols:
                        logger.info("Migrating database: adding grounding_evidence column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN grounding_evidence TEXT;"))
                        conn.commit()

                    if "knowledge_point" not in existing_cols:
                        logger.info("Migrating database: adding knowledge_point column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN knowledge_point TEXT;"))
                        conn.commit()

                    if "prompt_traces" not in existing_cols:
                        logger.info("Migrating database: adding prompt_traces column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN prompt_traces TEXT;"))
                        conn.commit()

                    if "quality_warnings" not in existing_cols:
                        logger.info("Migrating database: adding quality_warnings column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN quality_warnings TEXT;"))
                        conn.commit()

                # Migration for chunks table
                res_chunks = conn.execute(text("PRAGMA table_info(chunks);")).fetchall()
                existing_chunk_cols = {row[1] for row in res_chunks}
                if existing_chunk_cols:
                    if "page_number" not in existing_chunk_cols:
                        logger.info("Migrating database: adding page_number column to chunks table")
                        conn.execute(text("ALTER TABLE chunks ADD COLUMN page_number INTEGER;"))
                        conn.commit()

                    if "chunk_index" not in existing_chunk_cols:
                        logger.info("Migrating database: adding chunk_index column to chunks table")
                        conn.execute(text("ALTER TABLE chunks ADD COLUMN chunk_index INTEGER;"))
                        conn.commit()

                    if "category" not in existing_chunk_cols:
                        logger.info("Migrating database: adding category column to chunks table")
                        conn.execute(text("ALTER TABLE chunks ADD COLUMN category VARCHAR DEFAULT 'materi_pokok';"))
                        conn.commit()

                    if "section_type" not in existing_chunk_cols:
                        logger.info("Migrating database: adding section_type column to chunks table")
                        conn.execute(text("ALTER TABLE chunks ADD COLUMN section_type VARCHAR DEFAULT 'materi_pokok';"))
                        conn.commit()

                    if "section_heading" not in existing_chunk_cols:
                        logger.info("Migrating database: adding section_heading column to chunks table")
                        conn.execute(text("ALTER TABLE chunks ADD COLUMN section_heading VARCHAR;"))
                        conn.commit()

                    if "chapter" not in existing_chunk_cols:
                        logger.info("Migrating database: adding chapter column to chunks table")
                        conn.execute(text("ALTER TABLE chunks ADD COLUMN chapter VARCHAR;"))
                        conn.commit()

                    if "embedding_ref" not in existing_chunk_cols:
                        logger.info("Migrating database: adding embedding_ref column to chunks table")
                        conn.execute(text("ALTER TABLE chunks ADD COLUMN embedding_ref VARCHAR;"))
                        conn.commit()

                # Migration for documents table
                res_docs = conn.execute(text("PRAGMA table_info(documents);")).fetchall()
                existing_doc_cols = {row[1] for row in res_docs}
                if existing_doc_cols:
                    if "chunking_strategy" not in existing_doc_cols:
                        logger.info("Migrating database: adding chunking_strategy column to documents table")
                        conn.execute(text("ALTER TABLE documents ADD COLUMN chunking_strategy VARCHAR DEFAULT 'fixed';"))
                        conn.commit()

                    if "filepath" not in existing_doc_cols:
                        logger.info("Migrating database: adding filepath column to documents table")
                        conn.execute(text("ALTER TABLE documents ADD COLUMN filepath VARCHAR;"))
                        conn.commit()

                    if "error_message" not in existing_doc_cols:
                        logger.info("Migrating database: adding error_message column to documents table")
                        conn.execute(text("ALTER TABLE documents ADD COLUMN error_message TEXT;"))
                        conn.commit()

                # Migration for validation_logs table
                res_val = conn.execute(text("PRAGMA table_info(validation_logs);")).fetchall()
                existing_val_cols = {row[1] for row in res_val}
                if existing_val_cols and "aspect_evaluations" not in existing_val_cols:
                    logger.info("Migrating database: adding aspect_evaluations column to validation_logs table")
                    conn.execute(text("ALTER TABLE validation_logs ADD COLUMN aspect_evaluations TEXT;"))
                    conn.commit()

        except Exception as e:
            logger.warning("Lightweight migration check encountered error (non-fatal): %s", e)


# Automatically initialize database schema and apply migrations on load
try:
    init_db()
except Exception as _e:
    logger.warning("Failed to auto-init DB on load: %s", _e)


