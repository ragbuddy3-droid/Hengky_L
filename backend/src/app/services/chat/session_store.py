"""Chat session persistence store operations."""

import logging

from sqlalchemy.orm import Session

from app.models.db_models import ChatSession

logger = logging.getLogger(__name__)


def create_session(db: Session, document_id: str) -> ChatSession:
    """Create a new chat session linked to a document."""
    session = ChatSession(document_id=document_id)
    db.add(session)
    db.flush()
    logger.info("Created ChatSession id='%s' for document_id='%s'", session.id, document_id)
    return session


def get_chat_session(db: Session, session_id: str) -> ChatSession | None:
    """Retrieve chat session by ID."""
    return db.query(ChatSession).filter(ChatSession.id == session_id).first()


def fail_interrupted_generations(db: Session) -> int:
    """Generasi berjalan sebagai background task di proses ini; status 'running' saat startup berarti terputus."""
    count = (
        db.query(ChatSession)
        .filter(ChatSession.generation_status == "running")
        .update({ChatSession.generation_status: "failed"})
    )
    if count:
        logger.warning("Marked %d interrupted generation(s) as failed", count)
    return count


def delete_chat_session(db: Session, session_id: str) -> bool:
    """Delete chat session by ID."""
    session = get_chat_session(db, session_id)
    if session:
        db.delete(session)
        db.flush()
        logger.info("Deleted ChatSession id='%s'", session_id)
        return True
    return False
