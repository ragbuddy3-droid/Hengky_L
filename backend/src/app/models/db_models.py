"""SQLAlchemy ORM models for the backend."""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def generate_uuid() -> str:
    """Generate a UUID4 string."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(unique=True, index=True)  # disimpan lowercase
    name: Mapped[str]
    password_hash: Mapped[str]
    created_at: Mapped[datetime | None] = mapped_column(default=utcnow)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"


class GuestUsage(Base):
    """Kuota sekali pakai mode tamu. Tidak ikut dihapus bersama data tamu agar kuota tidak kembali."""

    __tablename__ = "guest_usage"

    guest_id: Mapped[str] = mapped_column(primary_key=True)
    uploaded_at: Mapped[datetime | None]
    session_created_at: Mapped[datetime | None]
    generated_at: Mapped[datetime | None]


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_uuid)
    # Pemilik: akun (user_id) atau tamu (guest_id dari cookie browser); keduanya kosong = data lama tanpa pemilik
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    guest_id: Mapped[str | None] = mapped_column(index=True)
    last_active_at: Mapped[datetime | None] = mapped_column(default=utcnow)
    filename: Mapped[str]
    filepath: Mapped[str | None]
    subject: Mapped[str]  # PJOK / IPAS / PKN / etc.
    status: Mapped[str] = mapped_column(default="pending")  # pending / processing / ready / failed
    chunking_strategy: Mapped[str | None] = mapped_column(default="fixed")  # legacy; only "fixed" exists
    error_message: Mapped[str | None] = mapped_column(Text)
    warning_message: Mapped[str | None] = mapped_column(Text)  # e.g. content does not match the chosen subject
    uploaded_at: Mapped[datetime | None] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(default=utcnow, onupdate=utcnow)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status})>"


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(default="materi_pokok")  # materi_pokok / uraian_materi / studi_kasus / ...
    section_heading: Mapped[str | None]
    chapter: Mapped[str | None]
    page_number: Mapped[int | None]
    chunk_index: Mapped[int | None]
    section_type: Mapped[str | None] = mapped_column(default="materi_pokok")
    created_at: Mapped[datetime | None] = mapped_column(default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="chunks")
    analysis: Mapped["ChunkAnalysis | None"] = relationship(back_populates="chunk", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Chunk(id={self.id}, document_id={self.document_id})>"


class ChunkAnalysis(Base):
    """Cached Stage 1 (Context Understanding) result of a chunk, reused across generation requests."""

    __tablename__ = "chunk_analyses"

    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True)
    prompt_key: Mapped[str]  # hash of the Stage 1 prompt + model; a change invalidates the cache
    analysis: Mapped[str] = mapped_column(Text)  # JSON ContentAnalysis
    trace: Mapped[str] = mapped_column(Text)  # JSON PromptStageTrace of the call that produced it
    created_at: Mapped[datetime | None] = mapped_column(default=utcnow)

    chunk: Mapped["Chunk"] = relationship(back_populates="analysis")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    guest_id: Mapped[str | None] = mapped_column(index=True)
    last_active_at: Mapped[datetime | None] = mapped_column(default=utcnow)
    # Status generasi soal di latar belakang: idle / running / done / failed
    generation_status: Mapped[str] = mapped_column(default="idle")
    generation_count: Mapped[int | None]  # Jumlah soal yang diminta pada generasi terakhir
    generation_message_id: Mapped[str | None]  # Pesan asisten "Sedang membuat..." milik generasi terakhir
    created_at: Mapped[datetime | None] = mapped_column(default=utcnow)

    document: Mapped["Document"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    questions: Mapped[list["Question"]] = relationship(back_populates="session", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, document_id={self.document_id})>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str]  # user / assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(default=utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role={self.role})>"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    chunk_ids: Mapped[str] = mapped_column(Text)  # JSON-serialized list of chunk IDs
    question_type: Mapped[str] = mapped_column(default="esai")  # esai / isian_singkat
    question_text: Mapped[str] = mapped_column(Text)
    answer_key: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text)
    bloom_level: Mapped[str]
    status: Mapped[str] = mapped_column(default="final")  # final / needs_review
    refinement_count: Mapped[int] = mapped_column(default=0)
    revision_count: Mapped[int] = mapped_column(default=0)  # Revisi / buat ulang atas permintaan pengguna lewat chat

    # Multi-Stage AQG Extensions
    grounding_evidence: Mapped[str | None] = mapped_column(Text)  # Exact quote from context
    knowledge_point: Mapped[str | None] = mapped_column(Text)  # Specific topic/concept point
    prompt_traces: Mapped[str | None] = mapped_column(Text)  # JSON-serialized execution trace for each stage
    quality_warnings: Mapped[str | None] = mapped_column(Text)  # JSON list of quality issue strings

    created_at: Mapped[datetime | None] = mapped_column(default=utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="questions")
    validation_logs: Mapped[list["ValidationLog"]] = relationship(back_populates="question", cascade="all, delete-orphan")

    @property
    def chunk_id_list(self) -> list[str]:
        """`chunk_ids` decoded; unreadable values become [] (the question's own chunk comes first)."""
        try:
            ids = json.loads(self.chunk_ids or "[]")
        except json.JSONDecodeError:
            return []
        return ids if isinstance(ids, list) else []

    def __repr__(self) -> str:
        return f"<Question(id={self.id}, bloom_level={self.bloom_level}, status={self.status})>"


class ValidationLog(Base):
    __tablename__ = "validation_logs"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_uuid)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    attempt_number: Mapped[int]
    layer: Mapped[str]  # grounding / judge / pre_check
    score_or_verdict: Mapped[str]
    feedback: Mapped[str | None] = mapped_column(Text)
    aspect_evaluations: Mapped[str | None] = mapped_column(Text)  # JSON-serialized breakdown of the judge aspects
    created_at: Mapped[datetime | None] = mapped_column(default=utcnow)

    question: Mapped["Question"] = relationship(back_populates="validation_logs")

    def __repr__(self) -> str:
        return f"<ValidationLog(id={self.id}, layer={self.layer}, attempt={self.attempt_number})>"
