"""Background execution of the AQG LangGraph for a chat session, reporting back as a chat message."""

import logging
from typing import Any

from app.core.config import get_settings
from app.core.database import get_session
from app.graph.state import AQGState
from app.graph.workflow import get_aqg_graph
from app.models.db_models import ChatSession
from app.schemas.api_schemas import GenerateParams
from app.services.chat.state_manager import ChatStateManager

logger = logging.getLogger(__name__)


def _set_generation_status(session_id: str, status: str) -> None:
    with get_session() as db:
        db.query(ChatSession).filter(ChatSession.id == session_id).update({ChatSession.generation_status: status})
        db.commit()


def _post_assistant_message(session_id: str, content: str) -> None:
    with get_session() as db:
        ChatStateManager(session_id, db).add_message("assistant", content)
        db.commit()


def format_generation_summary(questions: list[dict[str, Any]]) -> str:
    """Markdown chat message listing the generated questions."""
    num_final = sum(1 for q in questions if q.get("status") == "final")
    num_review = sum(1 for q in questions if q.get("status") == "needs_review")

    parts = [
        f"Berhasil membuat {len(questions)} soal Multi-Stage RAG-AQG!\n\n",
        f"• **Lolos Validasi:** {num_final} | **Perlu Tinjauan:** {num_review}\n\n",
    ]
    for idx, q in enumerate(questions, 1):
        parts.append(f"### Soal #{idx} ({q.get('question_type', 'esai').upper()} - {q.get('bloom_level', '')})\n")
        parts.append(f"**Pertanyaan:** {q.get('question', '')}\n\n")
        parts.append(f"**Jawaban Ideal:** {q.get('answer', '')}\n\n")
        if q.get("explanation"):
            parts.append(f"**Penjelasan & Konteks:** {q['explanation']}\n\n")
        if q.get("source_reference"):
            parts.append(f"**Referensi Materi:** `{q['source_reference']}`\n\n")
        parts.append("---\n\n")
    return "".join(parts)


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
        "raw_questions": [],
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

    try:
        final_state = await get_aqg_graph().ainvoke(
            _initial_state(session_id, document_id, content, params),
            config={"max_concurrency": get_settings().GENERATION_CONCURRENCY},
        )
        questions = final_state.get("finalized_questions", [])
        if not questions:
            reason = final_state.get("error") or "Tidak ada soal yang berhasil dibuat dari materi ini."
            _post_assistant_message(session_id, f"Maaf, soal belum dapat dibuat: {reason}")
            _set_generation_status(session_id, "failed")
            return

        _post_assistant_message(session_id, format_generation_summary(questions))
        logger.info("[Background] Saved LangGraph completion message for session_id='%s'", session_id)
        _set_generation_status(session_id, "done")

    except Exception as e:
        logger.error("[Background] Question generation failed for session_id='%s': %s", session_id, e, exc_info=True)
        _post_assistant_message(session_id, f"Maaf, terjadi kesalahan saat membuat soal: {e!s}")
        _set_generation_status(session_id, "failed")
