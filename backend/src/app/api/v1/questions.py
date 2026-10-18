"""Questions API router v1 with Multi-Stage audit inspection."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_owner
from app.core.database import get_session
from app.models.db_models import ChatSession, Chunk, Document, Question, ValidationLog
from app.schemas.api_schemas import (
    QuestionDetailResponse,
    QuestionResponse,
    UsedChunkResponse,
    ValidationLogResponse,
)
from app.services.auth.owner import Owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])


def _load_json(value: Any) -> Any:
    """Decode a JSON text column; non-strings pass through, unreadable text becomes None."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _common_fields(q: Question) -> dict[str, Any]:
    """Fields shared by the list and detail responses (JSON columns are parsed by the response validators)."""
    return {
        "id": q.id,
        "session_id": q.session_id,
        "question_type": q.question_type or "esai",
        "question_text": q.question_text,
        "answer_key": q.answer_key,
        "explanation": q.explanation,
        "source_reference": q.source_reference,
        "bloom_level": q.bloom_level,
        "status": q.status,
        "refinement_count": q.refinement_count,
        "knowledge_point": q.knowledge_point,
        "grounding_evidence": q.grounding_evidence,
        "quality_warnings": q.quality_warnings,
    }


def _used_chunks(db: Any, chunk_ids_json: Any) -> list[UsedChunkResponse]:
    """Chunks referenced by a question, in the stored order (own chunk first)."""
    c_ids = _load_json(chunk_ids_json)
    if not isinstance(c_ids, list) or not c_ids:
        return []
    chunk_map = {c.id: c for c in db.query(Chunk).filter(Chunk.id.in_(c_ids)).all()}
    return [
        UsedChunkResponse.model_validate({
            "id": chk.id,
            "document_id": chk.document_id,
            "text": chk.text,
            "category": chk.category,
            "section_heading": chk.section_heading,
            "chapter": chk.chapter,
            "page_number": chk.page_number or 1,
            "chunk_index": chk.chunk_index or 0,
            "section_type": chk.section_type or "materi_pokok",
        })
        for cid in c_ids
        if (chk := chunk_map.get(cid)) is not None
    ]


@router.get("/{question_id}", response_model=QuestionDetailResponse)
def get_question(question_id: str, owner: Owner = Depends(get_owner)):
    """Get question detail with multi-stage prompt traces, source chunks, and validation logs."""
    with get_session() as db:
        q = (
            db.query(Question)
            .join(ChatSession, Question.session_id == ChatSession.id)
            .filter(Question.id == question_id, owner.clause(ChatSession))
            .first()
        )
        if not q:
            raise HTTPException(status_code=404, detail="Question not found")

        logs = (
            db.query(ValidationLog)
            .filter(ValidationLog.question_id == question_id)
            .order_by(ValidationLog.created_at.asc())
            .all()
        )

        return QuestionDetailResponse.model_validate({
            **_common_fields(q),
            "prompt_traces": q.prompt_traces,
            "validation_logs": [ValidationLogResponse.model_validate(log) for log in logs],
            "used_chunks": _used_chunks(db, q.chunk_ids),
        })


@router.get("/", response_model=list[QuestionResponse])
def list_questions(
    session_id: str | None = Query(None),
    document_id: str | None = Query(None),
    owner: Owner = Depends(get_owner),
):
    """List questions, filterable by session_id and/or document_id (the book the session was opened on)."""
    with get_session() as db:
        query = (
            db.query(Question, ChatSession.document_id, Document.filename)
            .join(ChatSession, Question.session_id == ChatSession.id)
            .outerjoin(Document, ChatSession.document_id == Document.id)
            .filter(owner.clause(ChatSession))
        )
        if session_id:
            query = query.filter(Question.session_id == session_id)
        if document_id:
            query = query.filter(ChatSession.document_id == document_id)
        rows = query.order_by(Question.created_at.desc()).all()

        return [
            QuestionResponse.model_validate({
                **_common_fields(q),
                "document_id": doc_id,
                "document_filename": doc_filename,
                "chunk_ids": q.chunk_ids or "[]",
            })
            for q, doc_id, doc_filename in rows
        ]
