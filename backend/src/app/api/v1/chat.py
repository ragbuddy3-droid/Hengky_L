"""Chat API router v1."""
import uuid
import re
import asyncio
import logging
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.db.engine import get_session
from app.db.models import ChatSession, ChatMessage, Document
from app.chat.session_store import create_session
from app.chat.state_manager import ChatStateManager
from app.pipeline.orchestrator import run_aqg_pipeline

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

from app.schemas.api import (
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionListItem,
    ChatMessageCreate,
    ChatMessageResponse,
    GenerateParams,
)



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
    """Background task to generate questions via the RAG-AQG orchestrator."""
    logger.info("[Background] Starting AQG execution for session_id='%s'", session_id)
    
    document_id = None
    with get_session() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            logger.error("[Background] Chat session not found: session_id='%s'", session_id)
            return
        document_id = session.document_id

    try:
        questions = asyncio.run(
            run_aqg_pipeline(
                session_id=session_id,
                document_id=document_id,
                user_prompt=content,
                num_questions=params.num_questions,
                chapter=params.chapter,
                bloom_level=params.bloom_level
            )
        )
        
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
            logger.info("[Background] Saved completion summary message for session_id='%s'", session_id)

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
    logger.debug("GET list chat sessions (document_id=%s)", document_id or '(all)')
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
    logger.info("Creating new chat session for document_id='%s'", data.document_id)
    with get_session() as db:
        session = create_session(db, data.document_id)
        db.commit()
        logger.info("Chat session created: session_id='%s', document_id='%s'",
                    session.id, session.document_id)
        return ChatSessionResponse(id=session.id, document_id=session.document_id)

@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """Delete a chat session."""
    logger.info("DELETE chat session: session_id='%s'", session_id)
    with get_session() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            logger.warning("Delete chat session failed - session not found: session_id='%s'", session_id)
            raise HTTPException(status_code=404, detail="Sesi chat tidak ditemukan")
        db.delete(session)
        db.commit()
        logger.info("Chat session deleted: session_id='%s'", session_id)
        return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
def get_messages(session_id: str):
    """Get all messages in session."""
    logger.debug("GET messages for session_id='%s'", session_id)
    with get_session() as db:
        messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
        logger.debug("Returning %d messages for session_id='%s'", len(messages), session_id)
        return [ChatMessageResponse(id=m.id, role=m.role, content=m.content) for m in messages]


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
def send_message(session_id: str, data: ChatMessageCreate, background_tasks: BackgroundTasks):
    """Send a message to the chat session."""
    logger.info("Message received: session_id='%s', content_length=%d", session_id, len(data.content))
    
    with get_session() as db:
        manager = ChatStateManager(session_id, db)
        user_msg = manager.add_message("user", data.content)
        db.commit()
        
        keywords = ['buat soal', 'generate', 'buatkan soal', 'bikin soal', 'buatkan 5 soal', 'buat 5 soal', 'soal c']
        is_generation = any(kw in data.content.lower() for kw in keywords)
        
        logger.info("Message analysis: session_id='%s', is_generation_request=%s",
                    session_id, is_generation)
        
        if is_generation:
            params = _parse_generation_params(data.content)
            logger.info("Generation request detected, queueing background task (params=%s)", params)
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
                reply = f"Halo! Anda dapat meminta saya untuk membuat soal dari dokumen yang diunggah (contoh: 'Buatkan 5 soal C4 bab 2')."
                
            bot_msg = manager.add_message("assistant", reply)
            db.commit()
            return ChatMessageResponse(id=bot_msg.id, role=bot_msg.role, content=bot_msg.content)
