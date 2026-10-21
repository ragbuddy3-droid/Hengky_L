"""State and history manager for chat interactions."""

import logging

from sqlalchemy.orm import Session

from app.models.db_models import ChatMessage, Question

logger = logging.getLogger(__name__)


def session_questions(db: Session, session_id: str) -> list[Question]:
    """Questions of a session in their canonical order: 'soal nomor N' is the N-th item (1-based).

    Revisions update a question in place, so its number never changes.
    """
    return (
        db.query(Question)
        .filter(Question.session_id == session_id)
        .order_by(Question.created_at.asc(), Question.id.asc())
        .all()
    )


class ChatStateManager:
    """Manages chat messages, conversational context, and question cross-references."""

    def __init__(self, session_id: str, db: Session):
        self.session_id = session_id
        self.db = db

    def add_message(self, role: str, content: str) -> ChatMessage:
        """Append a new message to the conversation."""
        msg = ChatMessage(session_id=self.session_id, role=role, content=content)
        self.db.add(msg)
        self.db.flush()
        logger.info("Added chat message (session_id='%s', role='%s', length=%d)", self.session_id, role, len(content))
        return msg

    def recent_history(self, limit: int = 6) -> list[ChatMessage]:
        """Last `limit` messages, oldest first."""
        rows = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == self.session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(rows))

    def questions(self) -> list[Question]:
        return session_questions(self.db, self.session_id)
