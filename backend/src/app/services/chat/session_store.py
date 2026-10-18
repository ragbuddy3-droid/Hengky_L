"""Chat session persistence store operations."""

import logging

from sqlalchemy.orm import Session

from app.models.db_models import ChatSession
from app.services.auth.owner import Owner

logger = logging.getLogger(__name__)


def create_session(db: Session, document_id: str, owner: Owner) -> ChatSession:
    """Create a new chat session linked to a document, owned by the requester."""
    session = ChatSession(document_id=document_id, **owner.fields())
    db.add(session)
    db.flush()
    logger.info("Created ChatSession id='%s' for document_id='%s'", session.id, document_id)
    return session


def get_chat_session(db: Session, session_id: str, owner: Owner) -> ChatSession | None:
    """Retrieve a chat session by ID if it belongs to the requester."""
    return db.query(ChatSession).filter(ChatSession.id == session_id, owner.clause(ChatSession)).first()


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


def delete_chat_session(db: Session, session_id: str, owner: Owner) -> bool:
    """Delete a chat session by ID if it belongs to the requester."""
    session = get_chat_session(db, session_id, owner)
    if session:
        db.delete(session)
        db.flush()
        logger.info("Deleted ChatSession id='%s'", session_id)
        return True
    return False
