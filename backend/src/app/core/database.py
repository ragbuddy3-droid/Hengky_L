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


def _add_owner_columns(conn, table: str, existing_cols: set[str]) -> None:
    """Kolom kepemilikan (akun/tamu) untuk tabel yang dibuat sebelum fitur login."""
    if "user_id" not in existing_cols:
        logger.info("Migrating database: adding user_id column to %s table", table)
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR REFERENCES users(id) ON DELETE CASCADE;"))
    if "guest_id" not in existing_cols:
        logger.info("Migrating database: adding guest_id column to %s table", table)
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN guest_id VARCHAR;"))
    if "last_active_at" not in existing_cols:
        logger.info("Migrating database: adding last_active_at column to %s table", table)
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN last_active_at DATETIME;"))
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON {table}(user_id);"))
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_guest_id ON {table}(guest_id);"))
    conn.commit()


def init_db() -> None:
    """Initialize database tables and run lightweight schema migrations."""
    from app.models.db_models import (  # noqa: F401
        ChatMessage,
        ChatSession,
        Chunk,
        ChunkAnalysis,
        Document,
        Question,
        User,
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

                    if "revision_count" not in existing_cols:
                        logger.info("Migrating database: adding revision_count column to questions table")
                        conn.execute(text("ALTER TABLE questions ADD COLUMN revision_count INTEGER NOT NULL DEFAULT 0;"))
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

                    if "warning_message" not in existing_doc_cols:
                        logger.info("Migrating database: adding warning_message column to documents table")
                        conn.execute(text("ALTER TABLE documents ADD COLUMN warning_message TEXT;"))
                        conn.commit()

                    _add_owner_columns(conn, "documents", existing_doc_cols)

                # Migration for validation_logs table
                res_val = conn.execute(text("PRAGMA table_info(validation_logs);")).fetchall()
                existing_val_cols = {row[1] for row in res_val}
                if existing_val_cols and "aspect_evaluations" not in existing_val_cols:
                    logger.info("Migrating database: adding aspect_evaluations column to validation_logs table")
                    conn.execute(text("ALTER TABLE validation_logs ADD COLUMN aspect_evaluations TEXT;"))
                    conn.commit()

                # Migration for chat_sessions table
                res_sess = conn.execute(text("PRAGMA table_info(chat_sessions);")).fetchall()
                existing_sess_cols = {row[1] for row in res_sess}
                if existing_sess_cols:
                    if "generation_status" not in existing_sess_cols:
                        logger.info("Migrating database: adding generation_status column to chat_sessions table")
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN generation_status VARCHAR NOT NULL DEFAULT 'idle';"))
                        conn.commit()

                    if "generation_count" not in existing_sess_cols:
                        logger.info("Migrating database: adding generation_count column to chat_sessions table")
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN generation_count INTEGER;"))
                        conn.commit()

                    if "generation_message_id" not in existing_sess_cols:
                        logger.info("Migrating database: adding generation_message_id column to chat_sessions table")
                        conn.execute(text("ALTER TABLE chat_sessions ADD COLUMN generation_message_id VARCHAR;"))
                        conn.commit()

                    _add_owner_columns(conn, "chat_sessions", existing_sess_cols)

        except Exception as e:
            logger.warning("Lightweight migration check encountered error (non-fatal): %s", e)


# Automatically initialize database schema and apply migrations on load
try:
    init_db()
except Exception as _e:
    logger.warning("Failed to auto-init DB on load: %s", _e)


