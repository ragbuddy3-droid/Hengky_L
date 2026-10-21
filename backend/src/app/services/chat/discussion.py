"""Answer questions about one generated question, grounded in the question package and its source chunk."""

import json
import logging
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.models.db_models import ChatMessage, Chunk, Question, ValidationLog
from app.services.chat.intent import format_history
from app.services.chat.prompts import DISCUSSION_PROMPT, SYSTEM_DISCUSSION_PERSONA
from app.services.generation.stage_runners import JUDGE_CONTEXT_CHARS, invoke_json

logger = logging.getLogger(__name__)

_STATUS_LABELS = {"final": "Lolos validasi", "needs_review": "Perlu tinjauan guru"}


def question_chunk_text(db: Session, question: Question) -> str:
    """Text of the chunk the question was generated from (its first stored chunk id)."""
    try:
        chunk_ids = json.loads(str(question.chunk_ids or "[]"))
    except json.JSONDecodeError:
        chunk_ids = []
    if not chunk_ids:
        return ""
    chunk = db.get(Chunk, chunk_ids[0])
    return str(chunk.text) if chunk else ""


def _validation_note(db: Session, question: Question) -> str:
    last = (
        db.query(ValidationLog)
        .filter(ValidationLog.question_id == question.id)
        .order_by(ValidationLog.attempt_number.desc(), ValidationLog.created_at.desc())
        .first()
    )
    if not last:
        return "-"
    return f"{last.layer}: {last.score_or_verdict}. {last.feedback or ''}".strip()


def answer_about_question(
    db: Session, number: int, question: Question, history: Sequence[ChatMessage], message: str,
) -> str:
    """One LLM call answering the user's message about Soal #number."""
    prompt = DISCUSSION_PROMPT.format(
        number=number,
        question=question.question_text,
        question_type=question.question_type or "esai",
        bloom_level=question.bloom_level,
        answer=question.answer_key,
        explanation=question.explanation or "-",
        knowledge_point=question.knowledge_point or "-",
        grounding_evidence=question.grounding_evidence or "-",
        source_reference=question.source_reference or "-",
        status=_STATUS_LABELS.get(str(question.status), str(question.status)),
        validation_note=_validation_note(db, question),
        context=question_chunk_text(db, question)[:JUDGE_CONTEXT_CHARS] or "(materi sumber tidak tersedia)",
        history=format_history(history),
        message=message,
    )
    try:
        reply = str(invoke_json(SYSTEM_DISCUSSION_PERSONA, prompt, temperature=0.2).get("reply") or "").strip()
    except Exception as e:
        logger.error("[Chat Discussion] LLM call failed: %s", e)
        reply = ""
    return reply or "Maaf, saya belum bisa menjawab pertanyaan tentang soal ini sekarang. Silakan coba lagi."
