"""Background execution of the AQG LangGraph for a chat session, reporting back as a chat message."""

import json
import logging
from typing import Any

from app.core.database import get_session
from app.graph.state import AQGState
from app.graph.workflow import get_aqg_graph
from app.models.db_models import ChatSession, Chunk, Question
from app.schemas.api_schemas import GenerateParams
from app.services.auth.guest_quota import refund
from app.services.chat.state_manager import ChatStateManager, session_questions
from app.services.generation import progress
from app.services.generation.revision import RevisionAction, revise_question
from app.services.questions.repository import replace_question
from app.services.retrieval.retriever import chunk_dict, load_document_chunks
from app.services.validation.quality_checks import tokens

logger = logging.getLogger(__name__)


def _set_generation_status(session_id: str, status: str, refund_quota: bool = True) -> None:
    with get_session() as db:
        db.query(ChatSession).filter(ChatSession.id == session_id).update({ChatSession.generation_status: status})
        if status == "failed" and refund_quota:
            session = db.get(ChatSession, session_id)
            refund(db, session.guest_id if session and session.user_id is None else None, "generate")  # type: ignore[arg-type]
        db.commit()


def _post_assistant_message(session_id: str, content: str) -> None:
    with get_session() as db:
        ChatStateManager(session_id, db).add_message("assistant", content)
        db.commit()


def _format_question(number: int, q: dict[str, Any]) -> str:
    parts = [
        f"### Soal #{number} ({q.get('question_type', 'esai').upper()} - {q.get('bloom_level', '')})\n",
        f"**Pertanyaan:** {q.get('question', '')}\n\n",
        f"**Jawaban Ideal:** {q.get('answer', '')}\n\n",
    ]
    if q.get("explanation"):
        parts.append(f"**Penjelasan & Konteks:** {q['explanation']}\n\n")
    if q.get("source_reference"):
        parts.append(f"**Referensi Materi:** `{q['source_reference']}`\n\n")
    parts.append("---\n\n")
    return "".join(parts)


def format_generation_summary(questions: list[dict[str, Any]], start_number: int = 1) -> str:
    """Markdown chat message listing the generated questions, numbered as in the whole session."""
    num_final = sum(1 for q in questions if q.get("status") == "final")
    num_review = sum(1 for q in questions if q.get("status") == "needs_review")

    parts = [
        f"Berhasil membuat {len(questions)} soal!\n\n",
        f"• **Lolos Validasi:** {num_final} | **Perlu Tinjauan:** {num_review}\n\n",
    ]
    parts += [_format_question(number, q) for number, q in enumerate(questions, start_number)]
    return "".join(parts)


def format_revision_summary(number: int, action: str, q: dict[str, Any]) -> str:
    """Markdown chat message showing the new version of Soal #number."""
    verb = "dibuat ulang" if action == "regenerate" else "direvisi"
    status = "lolos validasi" if q.get("status") == "final" else "perlu tinjauan"
    return f"Soal #{number} berhasil {verb} ({status}).\n\n" + _format_question(number, q)


def _session_question_count(session_id: str) -> int:
    with get_session() as db:
        return db.query(Question).filter(Question.session_id == session_id).count()


def _initial_state(session_id: str, document_id: str, content: str, params: GenerateParams) -> AQGState:
    return {
        "session_id": session_id,
        "document_id": document_id,
        "user_prompt": content,
        "chapter": params.chapter,
        "bloom_level": params.bloom_level,
        "num_questions": params.num_questions,
        "retrieved_chunks": [],
        "reserve_chunks": [],
        "source_chunk_ids": [],
        "spare_items": [],
        "stage_cache": {},
        "top_up_done": False,
        "validated_questions": [],
        "finalized_questions": [],
        "error": None,
    }


async def background_generate_questions(session_id: str, content: str, params: GenerateParams) -> None:
    """Run the AQG graph for a session, then post the result and set the session's generation status."""
    logger.info("[Background] Starting LangGraph AQG execution for session_id='%s'", session_id)

    with get_session() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            logger.error("[Background] Chat session not found: session_id='%s'", session_id)
            return
        document_id = str(session.document_id)

    progress.start(session_id, params.num_questions)
    try:
        final_state = await get_aqg_graph().ainvoke(_initial_state(session_id, document_id, content, params))
        questions = final_state.get("finalized_questions", [])
        if not questions:
            reason = final_state.get("error") or "Tidak ada soal yang berhasil dibuat dari materi ini."
            _post_assistant_message(session_id, f"Maaf, soal belum dapat dibuat: {reason}")
            _set_generation_status(session_id, "failed")
            progress.finish(session_id, "failed", reason)
            return

        start_number = max(1, _session_question_count(session_id) - len(questions) + 1)
        _post_assistant_message(session_id, format_generation_summary(questions, start_number))
        logger.info("[Background] Saved LangGraph completion message for session_id='%s'", session_id)
        _set_generation_status(session_id, "done")
        progress.finish(session_id, "done")

    except Exception as e:
        logger.error("[Background] Question generation failed for session_id='%s': %s", session_id, e, exc_info=True)
        _post_assistant_message(session_id, f"Maaf, terjadi kesalahan saat membuat soal: {e!s}")
        _set_generation_status(session_id, "failed")
        progress.finish(session_id, "failed", str(e))


def _question_dict(q: Question) -> dict[str, Any]:
    """A stored question in the key shape used by generation and validation."""
    return {
        "question": q.question_text,
        "question_type": q.question_type or "esai",
        "answer": q.answer_key,
        "explanation": q.explanation or "",
        "bloom_level": q.bloom_level,
        "knowledge_point": q.knowledge_point or "",
        "grounding_evidence": q.grounding_evidence or "",
    }


def _load_revision_input(
    session_id: str, question_id: str,
) -> tuple[str, int, dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]] | None:
    """(document_id, number, old question, its chunk, the session's other questions), or None if gone."""
    with get_session() as db:
        session = db.get(ChatSession, session_id)
        questions = session_questions(db, session_id)
        index = next((i for i, q in enumerate(questions) if str(q.id) == question_id), None)
        if session is None or index is None:
            return None
        old = _question_dict(questions[index])
        chunk_ids = json.loads(str(questions[index].chunk_ids or "[]"))
        others = [_question_dict(q) for q in questions if str(q.id) != question_id]
        document_id = str(session.document_id)
    return document_id, index + 1, old, _source_chunk(document_id, chunk_ids, old), others


def _source_chunk(document_id: str, chunk_ids: list[str], old: dict[str, Any]) -> dict[str, Any] | None:
    """The question's own chunk; if it is gone (document re-processed), the chunk that best contains its evidence."""
    if chunk_ids:
        with get_session() as db:
            own = db.get(Chunk, chunk_ids[0])
            if own is not None and str(own.document_id) == document_id:
                return chunk_dict(own)
    chunks = load_document_chunks(document_id)
    if not chunks:
        return None
    evidence = tokens(old.get("grounding_evidence") or f"{old.get('question', '')} {old.get('answer', '')}")
    best = max(chunks, key=lambda c: len(evidence & tokens(c.get("text", ""))))
    return best if evidence & tokens(best.get("text", "")) else None


async def background_revise_question(
    session_id: str, question_id: str, action: RevisionAction, bloom_level: str | None, instruction: str | None,
) -> None:
    """Regenerate or revise one question, replace it in place, then post the result to the chat."""
    loaded = _load_revision_input(session_id, question_id)
    if loaded is None:
        logger.error("[Background] Question '%s' of session '%s' not found for revision", question_id, session_id)
        _set_generation_status(session_id, "failed", refund_quota=False)
        return
    document_id, number, old, chunk, others = loaded

    progress.start(session_id, 1)
    try:
        if chunk is None:
            raise ValueError("materi sumber soal ini sudah tidak tersedia")
        new = await revise_question(session_id, document_id, chunk, old, action, bloom_level, instruction, others)
        saved = replace_question(question_id, new) if new else None
        if not saved:
            reason = "hasil baru terlalu mirip dengan soal lain atau tidak dapat dibuat. Soal lama tetap disimpan."
            _post_assistant_message(session_id, f"Maaf, Soal #{number} belum dapat diperbarui: {reason}")
            _set_generation_status(session_id, "failed", refund_quota=False)
            progress.finish(session_id, "failed", reason)
            return

        _post_assistant_message(session_id, format_revision_summary(number, action, saved))
        _set_generation_status(session_id, "done")
        progress.finish(session_id, "done")

    except Exception as e:
        logger.error("[Background] Question revision failed for session_id='%s': %s", session_id, e, exc_info=True)
        _post_assistant_message(session_id, f"Maaf, terjadi kesalahan saat memperbarui Soal #{number}: {e!s}")
        _set_generation_status(session_id, "failed", refund_quota=False)
        progress.finish(session_id, "failed", str(e))
