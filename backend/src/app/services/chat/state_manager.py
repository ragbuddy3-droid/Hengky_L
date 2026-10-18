"""State and history manager for chat interactions."""

import logging
import re

from sqlalchemy.orm import Session

from app.models.db_models import ChatMessage, Question

logger = logging.getLogger(__name__)


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

    def resolve_reference(self, text: str) -> str | None:
        """Resolve references like 'soal nomor 3' to past questions in session."""
        match = re.search(r'soal\s+(?:nomor\s+|no\.?\s*)?(\d+)', text, re.IGNORECASE)
        if not match:
            return None

        idx = int(match.group(1)) - 1
        if idx < 0:
            return None

        questions = (
            self.db.query(Question)
            .filter(Question.session_id == self.session_id)
            .order_by(Question.created_at.asc())
            .all()
        )
        if 0 <= idx < len(questions):
            q = questions[idx]
            return f"Soal #{idx + 1}: '{q.question_text}' (Jawaban: {q.answer_key})"

        return None
