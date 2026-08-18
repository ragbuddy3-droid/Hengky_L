"""SQLAlchemy ORM models for backend_new."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


def generate_uuid() -> str:
    """Generate a UUID4 string."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(UTC)


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=generate_uuid)
    filename = Column(String, nullable=False)
    filepath = Column(String, nullable=True)
    subject = Column(String, nullable=False)  # PJOK / IPAS / PKN / etc.
    status = Column(String, nullable=False, default="pending")  # pending / processing / ready / failed
    chunking_strategy = Column(String, nullable=True, default="fixed")  # fixed / semantic
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
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    category = Column(String, nullable=False)  # Konsep / Narasi / Instruksi / Evaluasi
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
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow)

    document = relationship("Document", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    questions = relationship("Question", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, document_id={self.document_id})>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    session = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role={self.role})>"


class Question(Base):
    __tablename__ = "questions"

    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    chunk_ids = Column(Text, nullable=False)  # JSON-serialized list of chunk IDs
    question_type = Column(String, nullable=False, default="esai")  # esai / isian_singkat
    question_text = Column(Text, nullable=False)
    options = Column(Text, nullable=True)  # JSON-serialized options (optional)
    answer_key = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    source_reference = Column(Text, nullable=True)
    bloom_level = Column(String, nullable=False)
    status = Column(String, nullable=False, default="final")  # final / needs_review
    refinement_count = Column(Integer, default=0, nullable=False)

    # Multi-Stage AQG Extensions
    rubric = Column(Text, nullable=True)  # JSON-serialized rubric criteria tiers
    answer_elements = Column(Text, nullable=True)  # JSON-serialized answer elements with weights
    grounding_evidence = Column(Text, nullable=True)  # Exact quote from context
    knowledge_point = Column(Text, nullable=True)  # Specific topic/concept point
    prompt_traces = Column(Text, nullable=True)  # JSON-serialized execution trace for each stage
    quality_warnings = Column(Text, nullable=True)  # JSON list of quality issue strings

    created_at = Column(DateTime, default=utcnow)

    session = relationship("ChatSession", back_populates="questions")
    validation_logs = relationship("ValidationLog", back_populates="question", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Question(id={self.id}, bloom_level={self.bloom_level}, status={self.status})>"


class ValidationLog(Base):
    __tablename__ = "validation_logs"

    id = Column(String, primary_key=True, default=generate_uuid)
    question_id = Column(String, ForeignKey("questions.id"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)
    layer = Column(String, nullable=False)  # grounding / judge / pre_check
    score_or_verdict = Column(String, nullable=False)
    feedback = Column(Text, nullable=True)
    aspect_evaluations = Column(Text, nullable=True)  # JSON-serialized breakdown of 6 judge aspects
    created_at = Column(DateTime, default=utcnow)

    question = relationship("Question", back_populates="validation_logs")

    def __repr__(self) -> str:
        return f"<ValidationLog(id={self.id}, layer={self.layer}, attempt={self.attempt_number})>"

