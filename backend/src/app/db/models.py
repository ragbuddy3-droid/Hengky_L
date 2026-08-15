"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.engine import Base

def generate_uuid() -> str:
    """Generate a UUID4 string."""
    return str(uuid.uuid4())

def utcnow() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=generate_uuid)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=True)
    subject = Column(String, nullable=False)  # PJOK/IPAS/PKN
    status = Column(String, nullable=False, default="pending")  # pending/processing/ready/failed
    chunking_strategy = Column(String, nullable=True, default="structured")  # structured/pac
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status})>"

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    text = Column(Text, nullable=False)
    category = Column(String, nullable=False)  # Konsep/Narasi/Instruksi/Evaluasi
    section_heading = Column(String, nullable=True)
    chapter = Column(String, nullable=True)
    embedding_ref = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        return f"<Chunk(id={self.id}, document_id={self.document_id})>"

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    questions = relationship("Question", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, document_id={self.document_id})>"

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String, nullable=False)  # user/assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role={self.role})>"

class Question(Base):
    __tablename__ = "questions"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
    chunk_ids = Column(Text, nullable=False)  # JSON-serialized list of chunk IDs
    question_type = Column(String, nullable=False, default="esai")  # esai/isian_singkat
    question_text = Column(Text, nullable=False)
    options = Column(Text, nullable=True)  # JSON-serialized options (optional for essay/short answer)
    answer_key = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    source_reference = Column(Text, nullable=True)
    bloom_level = Column(String, nullable=False)
    status = Column(String, nullable=False, default="final")  # final/needs_review
    refinement_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    session = relationship("ChatSession", back_populates="questions")
    validation_logs = relationship("ValidationLog", back_populates="question", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Question(id={self.id}, bloom_level={self.bloom_level}, status={self.status})>"

class ValidationLog(Base):
    __tablename__ = "validation_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    question_id = Column(String, ForeignKey("questions.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    layer = Column(String, nullable=False)  # grounding/judge
    score_or_verdict = Column(String, nullable=False)
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    question = relationship("Question", back_populates="validation_logs")

    def __repr__(self) -> str:
        return f"<ValidationLog(id={self.id}, layer={self.layer}, attempt={self.attempt_number})>"
