"""Chat API router v1: sessions, messages, and starting background question generation."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_owner
from app.core.database import get_session
from app.models.db_models import ChatMessage, ChatSession, Document, utcnow
from app.schemas.api_schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionListItem,
    ChatSessionResponse,
)
from app.services.auth.guest_quota import GUEST_LIMIT_MESSAGES, can_use, consume
from app.services.auth.owner import Owner
from app.services.chat.handler import handle_message
from app.services.chat.session_store import create_session, delete_chat_session, get_chat_session
from app.services.generation import progress
from app.services.generation.runner import background_generate_questions, background_revise_question

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_STREAM_START_WAIT_TICKS = 40  # x 0.25 s
_NOT_FOUND = "Sesi chat tidak ditemukan"


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
def list_sessions(document_id: str | None = None, owner: Owner = Depends(get_owner)):
    """List the requester's chat sessions, optionally filtered by document_id."""
    with get_session() as db:
        query = db.query(ChatSession).filter(owner.clause(ChatSession))
        if document_id:
            query = query.filter(ChatSession.document_id == document_id)
        return [_session_item(s) for s in query.order_by(ChatSession.created_at.desc()).all()]


@router.get("/sessions/{session_id}", response_model=ChatSessionListItem)
def get_session_detail(session_id: str, owner: Owner = Depends(get_owner)):
    """Get one chat session, including its question generation status (for polling)."""
    with get_session() as db:
        session = get_chat_session(db, session_id, owner)
        if not session:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        return _session_item(session)


@router.get("/sessions/{session_id}/generation/stream")
async def stream_generation(session_id: str, owner: Owner = Depends(get_owner)):
    """Server-Sent Events of the running generation: history first, then live events until "done"."""
    with get_session() as db:
        session = get_chat_session(db, session_id, owner)
        if not session:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        status = str(session.generation_status or "idle")

    def sse(event: dict) -> str:
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    async def events() -> AsyncIterator[str]:
        # The background task registers its run right after the request that set 'running' returns
        for _ in range(_STREAM_START_WAIT_TICKS):
            if progress.is_active(session_id) or status != "running":
                break
            await asyncio.sleep(0.25)
        if not progress.is_active(session_id):
            # Nothing in memory (finished long ago, or the server restarted): report the stored status
            yield sse({"type": "done", "status": "failed" if status == "running" else status})
            return
        async for event in progress.subscribe(session_id):
            yield ": ping\n\n" if event is None else sse(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions", response_model=ChatSessionResponse)
def create_new_session(data: ChatSessionCreate, owner: Owner = Depends(get_owner)):
    """Create new chat session for one of the requester's documents."""
    with get_session() as db:
        if not db.query(Document.id).filter(Document.id == data.document_id, owner.clause(Document)).first():
            raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
        if not can_use(db, owner, "session"):
            raise HTTPException(status_code=403, detail=GUEST_LIMIT_MESSAGES["session"])
        session = create_session(db, data.document_id, owner)
        consume(db, owner, "session")
        db.commit()
        return ChatSessionResponse.model_validate({"id": session.id, "document_id": session.document_id})


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, owner: Owner = Depends(get_owner)):
    """Delete a chat session."""
    with get_session() as db:
        success = delete_chat_session(db, session_id, owner)
        if not success:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        db.commit()
        return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
def get_messages(session_id: str, owner: Owner = Depends(get_owner)):
    """Get all messages in session."""
    with get_session() as db:
        if not get_chat_session(db, session_id, owner):
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
        return [ChatMessageResponse.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
def send_message(
    session_id: str,
    data: ChatMessageCreate,
    background_tasks: BackgroundTasks,
    owner: Owner = Depends(get_owner),
):
    """Send a message to the chat session."""
    with get_session() as db:
        session = get_chat_session(db, session_id, owner)
        if not session:
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        session.last_active_at = utcnow()  # type: ignore[assignment]

        reply = handle_message(db, session, owner, data.content)
        db.commit()
        if reply.job:
            kind, args = reply.job
            progress.discard(session_id)
            if kind == "generate":
                background_tasks.add_task(background_generate_questions, *args)
            else:
                background_tasks.add_task(background_revise_question, *args)
        return ChatMessageResponse.model_validate(reply.message)
