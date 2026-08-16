"""State and history manager for chat interactions."""

import re
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.db_models import ChatMessage, Question

logger = logging.getLogger(__name__)


class ChatStateManager:
    """Manages chat messages, conversational context, and question cross-references."""

    def __init__(self, session_id: str, db: Session):
        self.session_id = session_id
        self.db = db

    def get_history(self, limit: int = 20) -> List[ChatMessage]:
        """Fetch chronological message history for the session."""
        return (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == self.session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
            .all()
        )

    def add_message(self, role: str, content: str) -> ChatMessage:
        """Append a new message to the conversation."""
        msg = ChatMessage(session_id=self.session_id, role=role, content=content)
        self.db.add(msg)
        self.db.flush()
        logger.info("Added chat message (session_id='%s', role='%s', length=%d)", self.session_id, role, len(content))
        return msg

    def get_context_summary(self, max_messages: int = 6) -> str:
        """Format recent chat history into a prompt-friendly context string."""
        history = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == self.session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(max_messages)
            .all()
        )
        if not history:
            return ""

        # Chronological order
        history.reverse()
        summary_lines = []
        for msg in history:
            role_label = "Pengguna" if msg.role == "user" else "Asisten"
            summary_lines.append(f"{role_label}: {msg.content}")

        return "\n".join(summary_lines)

    def resolve_reference(self, text: str) -> Optional[str]:
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
