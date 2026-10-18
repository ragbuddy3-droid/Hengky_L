"""Chat API router v1: sessions, messages, and starting background question generation."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.database import get_session
from app.models.db_models import ChatMessage, ChatSession
from app.schemas.api_schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionListItem,
    ChatSessionResponse,
)
from app.services.chat.intent import is_generation_intent, parse_generation_params
from app.services.chat.session_store import create_session, delete_chat_session
from app.services.chat.state_manager import ChatStateManager
from app.services.generation.runner import background_generate_questions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _session_item(s: ChatSession) -> ChatSessionListItem:
    last_msg = s.messages[-1].content if s.messages else None
    if last_msg and len(last_msg) > 60:
        last_msg = last_msg[:60] + "..."
    return ChatSessionListItem.model_validate({
        "id": s.id,
        "document_id": s.document_id,
        "document_filename": s.document.filename if s.document else None,
        "message_count": len(s.messages) if s.messages else 0,
        "last_message_snippet": last_msg,
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at is not None else None,
        "generation_status": s.generation_status or "idle",
        "generation_count": s.generation_count,
        "generation_message_id": s.generation_message_id,
    })


@router.get("/sessions", response_model=list[ChatSessionListItem])
def list_sessions(document_id: str | None = None):
    """List all chat sessions, optionally filtered by document_id."""
    with get_session() as db:
        query = db.query(ChatSession)
        if document_id:
            query = query.filter(ChatSession.document_id == document_id)
        return [_session_item(s) for s in query.order_by(ChatSession.created_at.desc()).all()]


@router.get("/sessions/{session_id}", response_model=ChatSessionListItem)
def get_session_detail(session_id: str):
    """Get one chat session, including its question generation status (for polling)."""
    with get_session() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Sesi chat tidak ditemukan")
        return _session_item(session)


@router.post("/sessions", response_model=ChatSessionResponse)
def create_new_session(data: ChatSessionCreate):
    """Create new chat session for a document."""
    with get_session() as db:
        session = create_session(db, data.document_id)
        db.commit()
        return ChatSessionResponse.model_validate({"id": session.id, "document_id": session.document_id})


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """Delete a chat session."""
    with get_session() as db:
        success = delete_chat_session(db, session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Sesi chat tidak ditemukan")
        db.commit()
        return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
def get_messages(session_id: str):
    """Get all messages in session."""
    with get_session() as db:
        messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
        return [ChatMessageResponse.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
def send_message(session_id: str, data: ChatMessageCreate, background_tasks: BackgroundTasks):
    """Send a message to the chat session."""
    with get_session() as db:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Sesi chat tidak ditemukan")

        manager = ChatStateManager(session_id, db)
        manager.add_message("user", data.content)
        db.commit()

        if is_generation_intent(data.content):
            if str(session.generation_status) == "running":
                reply = "Soal sebelumnya masih dibuat. Mohon tunggu hingga selesai sebelum meminta soal baru."
            else:
                params = parse_generation_params(data.content)
                bot_msg = manager.add_message(
                    "assistant",
                    f"Sedang membuat {params.num_questions} soal ({params.bloom_level or 'Beragam Level'}). Mohon tunggu sebentar..."
                )
                db.query(ChatSession).filter(ChatSession.id == session_id).update({
                    ChatSession.generation_status: "running",
                    ChatSession.generation_count: params.num_questions,
                    ChatSession.generation_message_id: bot_msg.id,
                })
                db.commit()
                # Status sudah 'running' di DB sebelum task berjalan, jadi polling tidak melihat celah 'idle'
                background_tasks.add_task(background_generate_questions, session_id, data.content, params)
                return ChatMessageResponse.model_validate(bot_msg)
        else:
            ref_content = manager.resolve_reference(data.content)
            if ref_content:
                reply = f"Mengenai soal tersebut ({ref_content}): Silakan sampaikan pertanyaan Anda lebih lanjut."
            else:
                reply = "Halo! Anda dapat meminta saya untuk membuat soal dari dokumen yang diunggah (contoh: 'Buatkan 5 soal C4 bab 2')."

        bot_msg = manager.add_message("assistant", reply)
        db.commit()
        return ChatMessageResponse.model_validate(bot_msg)
