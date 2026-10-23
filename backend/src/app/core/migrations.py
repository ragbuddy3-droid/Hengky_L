"""Create missing tables and apply lightweight SQLite migrations for databases made by older versions."""

import logging

from sqlalchemy import Engine, text

from app.core.database import Base, engine

logger = logging.getLogger(__name__)

# Columns added after a table was first released: (table, column, SQL type and default)
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    ("questions", "question_type", "VARCHAR DEFAULT 'esai'"),
    ("questions", "explanation", "TEXT"),
    ("questions", "source_reference", "TEXT"),
    ("questions", "grounding_evidence", "TEXT"),
    ("questions", "knowledge_point", "TEXT"),
    ("questions", "prompt_traces", "TEXT"),
    ("questions", "quality_warnings", "TEXT"),
    ("questions", "revision_count", "INTEGER NOT NULL DEFAULT 0"),
    ("chunks", "page_number", "INTEGER"),
    ("chunks", "chunk_index", "INTEGER"),
    ("chunks", "category", "VARCHAR DEFAULT 'materi_pokok'"),
    ("chunks", "section_type", "VARCHAR DEFAULT 'materi_pokok'"),
    ("chunks", "section_heading", "VARCHAR"),
    ("chunks", "chapter", "VARCHAR"),
    ("documents", "chunking_strategy", "VARCHAR DEFAULT 'fixed'"),
    ("documents", "filepath", "VARCHAR"),
    ("documents", "error_message", "TEXT"),
    ("documents", "warning_message", "TEXT"),
    ("validation_logs", "aspect_evaluations", "TEXT"),
    ("chat_sessions", "generation_status", "VARCHAR NOT NULL DEFAULT 'idle'"),
    ("chat_sessions", "generation_count", "INTEGER"),
    ("chat_sessions", "generation_message_id", "VARCHAR"),
]
# Account/guest ownership, added when login was introduced
_OWNED_TABLES = ["documents", "chat_sessions"]
_OWNER_COLUMNS = [
    ("user_id", "VARCHAR REFERENCES users(id) ON DELETE CASCADE"),
    ("guest_id", "VARCHAR"),
    ("last_active_at", "DATETIME"),
]
_INDEXES = [
    ("ix_chunks_document_id", "chunks", "document_id"),
    ("ix_questions_session_id", "questions", "session_id"),
    ("ix_chat_messages_session_id", "chat_messages", "session_id"),
    ("ix_validation_logs_question_id", "validation_logs", "question_id"),
    *((f"ix_{table}_{column}", table, column) for table in _OWNED_TABLES for column in ("user_id", "guest_id")),
]


def _migrate_sqlite(bind: Engine) -> None:
    """Add missing columns to tables created by older versions, then ensure the indexes exist."""
    added = _ADDED_COLUMNS + [(table, col, ddl) for table in _OWNED_TABLES for col, ddl in _OWNER_COLUMNS]
    with bind.connect() as conn:
        existing: dict[str, set[str]] = {}
        for table, column, ddl in added:
            if table not in existing:
                existing[table] = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table});"))}
            if column not in existing[table]:
                logger.info("Migrating database: adding %s column to %s table", column, table)
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl};"))
        for name, table, column in _INDEXES:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({column});"))
        conn.commit()


def init_db(bind: Engine = engine) -> None:
    """Create missing tables and run lightweight SQLite schema migrations."""
    import app.models.db_models  # noqa: F401  (registers the models on Base)

    Base.metadata.create_all(bind=bind)
    logger.info("Database tables verified and initialized.")
    if bind.dialect.name == "sqlite":
        try:
            _migrate_sqlite(bind)
        except Exception as e:
            logger.warning("Lightweight migration check encountered error (non-fatal): %s", e)
