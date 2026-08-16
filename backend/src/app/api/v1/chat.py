"""Chat API router v1 with LangGraph AQG background execution."""

import re
import logging
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.database import get_session
from app.models.db_models import ChatSession, ChatMessage
from app.services.chat.session_store import create_session, delete_chat_session
from app.services.chat.state_manager import ChatStateManager
from app.graph.workflow import get_aqg_graph
from app.schemas.api_schemas import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionListItem,
    ChatMessageCreate,
    ChatMessageResponse,
    GenerateParams,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

BLOOM_MAPPING = {
    "C1": "C1-Mengingat",
    "C2": "C2-Memahami",
    "C3": "C3-Mengaplikasikan",
    "C4": "C4-Menganalisis",
    "C5": "C5-Mengevaluasi",
    "C6": "C6-Mencipta",
}


def _parse_generation_params(text: str) -> GenerateParams:
    """Extract question generation parameters from natural language user message."""
    num_questions = 5
    bloom_level = None
    chapter = None

    match_num = re.search(r'(\d+)\s*(?:soal|pertanyaan)', text, re.IGNORECASE)
    if match_num:
        try:
            num_questions = int(match_num.group(1))
            num_questions = max(1, min(20, num_questions))
        except ValueError:
            pass

    match_bloom = re.search(r'\b(C[1-6])\b', text, re.IGNORECASE)
    if match_bloom:
        bloom_code = match_bloom.group(1).upper()
        bloom_level = BLOOM_MAPPING.get(bloom_code)

    match_chap = re.search(r'bab\s*([\w]+)', text, re.IGNORECASE)
    if match_chap:
        chapter = match_chap.group(1)

    logger.debug("Parsed generation params: num_questions=%d, bloom_level=%s, chapter=%s",
                 num_questions, bloom_level, chapter)
    return GenerateParams(num_questions=num_questions, chapter=chapter, bloom_level=bloom_level)


def background_generate_questions(session_id: str, content: str, params: GenerateParams):
    """Background task to generate questions via the compiled LangGraph StateGraph."""
    logger.info("[Background] Starting LangGraph AQG execution for session_id='%s'", session_id)

    document_id = None
    with get_session() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            logger.error("[Background] Chat session not found: session_id='%s'", session_id)
            return
        document_id = session.document_id

    try:
        initial_state = {
            "session_id": session_id,
            "document_id": document_id,
            "user_prompt": content,
            "chapter": params.chapter,
            "bloom_level": params.bloom_level,
            "num_questions": params.num_questions,
            "retrieved_chunks": [],
            "source_chunk_ids": [],
            "chat_history": "",
            "raw_questions": [],
            "current_q_index": 0,
            "current_question": {},
            "current_attempt": 1,
            "max_attempts": 3,
            "validation_logs": [],
            "finalized_questions": [],
            "error": None,
        }

        graph = get_aqg_graph()
        final_state = graph.invoke(initial_state)

        questions = final_state.get("finalized_questions", [])
        num_final = sum(1 for q in questions if q.get("status") == "final")
        num_review = sum(1 for q in questions if q.get("status") == "needs_review")

        summary_msg = f"Berhasil membuat {len(questions)} soal!\n\n"
        summary_msg += f"• **Lolos Validasi:** {num_final} | **Perlu Tinjauan:** {num_review}\n\n"

        for idx, q in enumerate(questions, 1):
            q_type = q.get("question_type", "esai").upper()
            q_text = q.get("question", "")
            q_ans = q.get("answer", "")
            q_exp = q.get("explanation", "")
            q_ref = q.get("source_reference", "")
            bloom = q.get("bloom_level", "")

            summary_msg += f"### Soal #{idx} ({q_type} - {bloom})\n"
            summary_msg += f"**Pertanyaan:** {q_text}\n\n"
            summary_msg += f"**Jawaban Benar:** {q_ans}\n\n"
            if q_exp:
                summary_msg += f"**Penjelasan:** {q_exp}\n\n"
            if q_ref:
                summary_msg += f"**Referensi Materi:** `{q_ref}`\n\n"
            summary_msg += "---\n\n"

        with get_session() as db:
            manager = ChatStateManager(session_id, db)
            manager.add_message("assistant", summary_msg)
            db.commit()
            logger.info("[Background] Saved LangGraph completion message for session_id='%s'", session_id)

    except Exception as e:
        logger.error("[Background] Question generation failed for session_id='%s': %s",
                     session_id, e, exc_info=True)
        with get_session() as db:
            manager = ChatStateManager(session_id, db)
            manager.add_message("assistant", f"Maaf, terjadi kesalahan saat membuat soal: {str(e)}")
            db.commit()


@router.get("/sessions", response_model=List[ChatSessionListItem])
def list_sessions(document_id: Optional[str] = None):
    """List all chat sessions, optionally filtered by document_id."""
    with get_session() as db:
        query = db.query(ChatSession)
        if document_id:
            query = query.filter(ChatSession.document_id == document_id)
        sessions = query.order_by(ChatSession.created_at.desc()).all()

        result = []
        for s in sessions:
            created_str = s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else None
            msg_count = len(s.messages) if s.messages else 0
            last_msg = None
            if s.messages:
                last_msg = s.messages[-1].content
                if last_msg and len(last_msg) > 60:
                    last_msg = last_msg[:60] + "..."

            doc_name = s.document.filename if s.document else None
            result.append(ChatSessionListItem(
                id=s.id,
                document_id=s.document_id,
                document_filename=doc_name,
                message_count=msg_count,
                last_message_snippet=last_msg,
                created_at=created_str
            ))
        return result


@router.post("/sessions", response_model=ChatSessionResponse)
def create_new_session(data: ChatSessionCreate):
    """Create new chat session for a document."""
    with get_session() as db:
        session = create_session(db, data.document_id)
        db.commit()
        return ChatSessionResponse(id=session.id, document_id=session.document_id)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """Delete a chat session."""
    with get_session() as db:
        success = delete_chat_session(db, session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Sesi chat tidak ditemukan")
        return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
def get_messages(session_id: str):
    """Get all messages in session."""
    with get_session() as db:
        messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
        return [ChatMessageResponse(id=m.id, role=m.role, content=m.content) for m in messages]


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
def send_message(session_id: str, data: ChatMessageCreate, background_tasks: BackgroundTasks):
    """Send a message to the chat session."""
    with get_session() as db:
        manager = ChatStateManager(session_id, db)
        user_msg = manager.add_message("user", data.content)
        db.commit()

        keywords = ['buat soal', 'generate', 'buatkan soal', 'bikin soal', 'buatkan 5 soal', 'buat 5 soal', 'soal c']
        is_generation = any(kw in data.content.lower() for kw in keywords)

        if is_generation:
            params = _parse_generation_params(data.content)
            background_tasks.add_task(background_generate_questions, session_id, data.content, params)

            bot_msg = manager.add_message(
                "assistant",
                f"Sedang membuat {params.num_questions} soal ({params.bloom_level or 'Beragam Level'}). Mohon tunggu sebentar..."
            )
            db.commit()
            return ChatMessageResponse(id=bot_msg.id, role=bot_msg.role, content=bot_msg.content)
        else:
            ref_content = manager.resolve_reference(data.content)
            if ref_content:
                reply = f"Mengenai soal tersebut ({ref_content}): Silakan sampaikan pertanyaan Anda lebih lanjut."
            else:
                reply = "Halo! Anda dapat meminta saya untuk membuat soal dari dokumen yang diunggah (contoh: 'Buatkan 5 soal C4 bab 2')."

            bot_msg = manager.add_message("assistant", reply)
            db.commit()
            return ChatMessageResponse(id=bot_msg.id, role=bot_msg.role, content=bot_msg.content)
