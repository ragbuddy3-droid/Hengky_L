"""Chat API router v1: sessions, messages, and starting background question generation."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.sse import EventSourceResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.api.deps import DbDep, OwnerDep
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

router = APIRouter(prefix="/chat", tags=["chat"])

_STREAM_START_WAIT_TICKS = 40  # x 0.25 s
_NOT_FOUND = "Sesi chat tidak ditemukan"


def _owned_session(db: Session, session_id: str, owner: Owner) -> ChatSession:
    session = get_chat_session(db, session_id, owner)
    if not session:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return session


def _last_messages(db: Session, session_ids: list[str]) -> dict[str, str]:
    """Latest message content per session, in one query."""
    latest = (
        db.query(ChatMessage.session_id, func.max(ChatMessage.created_at).label("at"))
        .filter(ChatMessage.session_id.in_(session_ids))
        .group_by(ChatMessage.session_id)
        .subquery()
    )
    rows = (
        db.query(ChatMessage.session_id, ChatMessage.content)
        .join(latest, (ChatMessage.session_id == latest.c.session_id) & (ChatMessage.created_at == latest.c.at))
        .all()
    )
    return {session_id: content for session_id, content in rows}


def _session_item(s: ChatSession, last_msg: str | None) -> ChatSessionListItem:
    if last_msg and len(last_msg) > 60:
        last_msg = last_msg[:60] + "..."
    return ChatSessionListItem.model_validate({
        "id": s.id,
        "document_id": s.document_id,
        "document_filename": s.document.filename if s.document else None,
        "last_message_snippet": last_msg,
        "created_at": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at is not None else None,
        "generation_status": s.generation_status or "idle",
        "generation_count": s.generation_count,
        "generation_message_id": s.generation_message_id,
    })


@router.get("/sessions", response_model=list[ChatSessionListItem])
def list_sessions(owner: OwnerDep, db: DbDep, document_id: str | None = None):
    """List the requester's chat sessions, optionally filtered by document_id."""
    query = db.query(ChatSession).options(selectinload(ChatSession.document)).filter(owner.clause(ChatSession))
    if document_id:
        query = query.filter(ChatSession.document_id == document_id)
    sessions = query.order_by(ChatSession.created_at.desc()).all()
    last = _last_messages(db, [s.id for s in sessions])
    return [_session_item(s, last.get(s.id)) for s in sessions]


@router.get("/sessions/{session_id}", response_model=ChatSessionListItem)
def get_session_detail(session_id: str, owner: OwnerDep, db: DbDep):
    """Get one chat session, including its question generation status (for polling)."""
    session = _owned_session(db, session_id, owner)
    return _session_item(session, _last_messages(db, [session_id]).get(session_id))


def _generation_status(session_id: str, owner: OwnerDep, db: DbDep) -> str:
    """Checked as a dependency so a 404 is sent before the event stream starts."""
    return _owned_session(db, session_id, owner).generation_status or "idle"


@router.get("/sessions/{session_id}/generation/stream", response_class=EventSourceResponse)
async def stream_generation(
    session_id: str, status: Annotated[str, Depends(_generation_status)],
) -> AsyncIterator[dict[str, Any]]:
    """Server-Sent Events of the running generation: history first, then live events until "done".

    FastAPI adds the keep-alive pings and the no-cache / no-buffering headers.
    """
    # The background task registers its run right after the request that set 'running' returns
    for _ in range(_STREAM_START_WAIT_TICKS):
        if progress.is_active(session_id) or status != "running":
            break
        await asyncio.sleep(0.25)
    if not progress.is_active(session_id):
        # Nothing in memory (finished long ago, or the server restarted): report the stored status
        yield {"type": "done", "status": "failed" if status == "running" else status}
        return
    async for event in progress.subscribe(session_id):
        yield event


@router.post("/sessions", response_model=ChatSessionResponse)
def create_new_session(data: ChatSessionCreate, owner: OwnerDep, db: DbDep):
    """Create new chat session for one of the requester's documents."""
    if not db.query(Document.id).filter(Document.id == data.document_id, owner.clause(Document)).first():
        raise HTTPException(status_code=404, detail="Dokumen tidak ditemukan")
    if not can_use(db, owner, "session"):
        raise HTTPException(status_code=403, detail=GUEST_LIMIT_MESSAGES["session"])
    session = create_session(db, data.document_id, owner)
    consume(db, owner, "session")
    db.commit()
    return ChatSessionResponse.model_validate({"id": session.id, "document_id": session.document_id})


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, owner: OwnerDep, db: DbDep):
    """Delete a chat session."""
    if not delete_chat_session(db, session_id, owner):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    db.commit()
    return {"status": "deleted", "session_id": session_id}


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
def get_messages(session_id: str, owner: OwnerDep, db: DbDep):
    """Get all messages in session."""
    _owned_session(db, session_id, owner)
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
def send_message(session_id: str, data: ChatMessageCreate, background_tasks: BackgroundTasks, owner: OwnerDep, db: DbDep):
    """Send a message to the chat session."""
    session = _owned_session(db, session_id, owner)
    session.last_active_at = utcnow()

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
