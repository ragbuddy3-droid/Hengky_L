"""Chat state management."""
import uuid
import re
import logging
from datetime import datetime, timezone
from app.db.models import ChatMessage, Question

logger = logging.getLogger(__name__)

class ChatStateManager:
    def __init__(self, session_id: str, db_session):
        self.session_id = session_id
        self.db = db_session
        logger.debug("ChatStateManager initialized for session_id='%s'", session_id)
        
    def get_history(self, limit: int = 20) -> list[dict]:
        """Get recent messages from DB."""
        messages = self.db.query(ChatMessage).filter(
            ChatMessage.session_id == self.session_id
        ).order_by(ChatMessage.created_at.desc()).limit(limit).all()
        
        result = [{"role": m.role, "content": m.content} for m in reversed(messages)]
        logger.debug("History retrieved: session_id='%s', messages=%d (limit=%d)",
                    self.session_id, len(result), limit)
        return result
        
    def add_message(self, role: str, content: str) -> ChatMessage:
        """Save message to DB."""
        msg = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=self.session_id,
            role=role,
            content=content,
            created_at=datetime.now(timezone.utc)
        )
        self.db.add(msg)
        logger.debug("Message added: session_id='%s', role='%s', content_length=%d",
                    self.session_id, role, len(content))
        return msg
        
    def get_context_summary(self) -> str:
        """Format recent history as context for LLM prompt."""
        history = self.get_history(limit=5)
        if not history:
            logger.debug("No history for context summary (session_id='%s')", self.session_id)
            return ""
        
        context = "Recent conversation:\n"
        for msg in history:
            context += f"{msg['role'].capitalize()}: {msg['content']}\n"
        
        logger.debug("Context summary generated: session_id='%s', messages=%d, length=%d",
                    self.session_id, len(history), len(context))
        return context
        
    def resolve_reference(self, text: str) -> str | None:
        """Resolve references like 'soal nomor 3' or 'soal 2' to question content."""
        match = re.search(r'soal\s*(?:nomor|no\.?)?\s*(\d+)', text, re.IGNORECASE)
        if match:
            try:
                num = int(match.group(1))
                logger.debug("Reference detected: question #%d for session_id='%s'", num, self.session_id)
                questions = self.db.query(Question).filter(
                    Question.session_id == self.session_id
                ).order_by(Question.created_at).all()
                
                if 1 <= num <= len(questions):
                    target_q = questions[num - 1]
                    return f"Soal #{num}: {target_q.question_text}"
                else:
                    logger.debug("Question index %d out of range (total=%d)", num, len(questions))
                    return f"Soal #{num} (tidak ditemukan dalam sesi ini)"
            except Exception as e:
                logger.warning("Error resolving question reference: %s", e)
        return None
