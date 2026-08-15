"""Session store."""
import uuid
import logging
from datetime import datetime, timezone
from app.db.models import ChatSession

logger = logging.getLogger(__name__)

def create_session(db, document_id: str) -> ChatSession:
    session = ChatSession(
        id=str(uuid.uuid4()),
        document_id=document_id,
        created_at=datetime.now(timezone.utc)
    )
    db.add(session)
    logger.info("Session created: session_id='%s', document_id='%s'", session.id, document_id)
    return session

def get_session(db, session_id: str) -> ChatSession | None:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session:
        logger.debug("Session found: session_id='%s'", session_id)
    else:
        logger.warning("Session not found: session_id='%s'", session_id)
    return session

def list_sessions(db, document_id: str = None) -> list[ChatSession]:
    query = db.query(ChatSession)
    if document_id:
        query = query.filter(ChatSession.document_id == document_id)
    sessions = query.all()
    logger.debug("Sessions listed: count=%d, document_id=%s", len(sessions), document_id or '(all)')
    return sessions
