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


def list_chat_sessions(db: Session, document_id: str | None = None) -> list[ChatSession]:
    """List chat sessions with optional document filter."""
    query = db.query(ChatSession)
    if document_id:
        query = query.filter(ChatSession.document_id == document_id)
    return query.order_by(ChatSession.created_at.desc()).all()


def delete_chat_session(db: Session, session_id: str) -> bool:
    """Delete chat session by ID."""
    session = get_chat_session(db, session_id)
    if session:
        db.delete(session)
        db.commit()
        logger.info("Deleted ChatSession id='%s'", session_id)
        return True
    return False
