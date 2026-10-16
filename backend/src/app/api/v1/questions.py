"""Questions API router v1 with Multi-Stage audit inspection."""

import json
import logging

from fastapi import APIRouter, HTTPException, Query

from app.core.database import get_session
from app.models.db_models import ChatSession, Chunk, Document, Question, ValidationLog
from app.schemas.api_schemas import (
    QuestionDetailResponse,
    QuestionResponse,
    UsedChunkResponse,
    ValidationLogResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/{question_id}", response_model=QuestionDetailResponse)
def get_question(question_id: str):
    """Get question detail with multi-stage prompt traces, rubric, and validation logs."""
    with get_session() as db:
        q = db.query(Question).filter(Question.id == question_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Question not found")

        logs = db.query(ValidationLog).filter(
            ValidationLog.question_id == question_id
        ).order_by(ValidationLog.created_at.asc()).all()

        log_responses = [
            ValidationLogResponse(
                id=log.id,
                attempt_number=log.attempt_number,
                layer=log.layer,
                score_or_verdict=log.score_or_verdict,
                feedback=log.feedback,
                aspect_evaluations=log.aspect_evaluations,
                created_at=log.created_at,
            )
            for log in logs
        ]

        used_chunks = []
        if q.chunk_ids:
            try:
                c_ids = json.loads(q.chunk_ids) if isinstance(q.chunk_ids, str) else q.chunk_ids
                if isinstance(c_ids, list) and c_ids:
                    db_chunks = db.query(Chunk).filter(Chunk.id.in_(c_ids)).all()
                    chunk_map = {c.id: c for c in db_chunks}
                    for cid in c_ids:
                        if cid in chunk_map:
                            chk = chunk_map[cid]
                            used_chunks.append(
                                UsedChunkResponse(
                                    id=chk.id,
                                    document_id=chk.document_id,
                                    text=chk.text,
                                    category=chk.category,
                                    section_heading=chk.section_heading,
                                    chapter=chk.chapter,
                                    page_number=getattr(chk, "page_number", 1) or 1,
                                    chunk_index=getattr(chk, "chunk_index", 0) or 0,
                                    section_type=getattr(chk, "section_type", "materi_pokok") or "materi_pokok",
                                )
                            )
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Failed to parse chunk_ids for question_id='%s': %s", question_id, exc)

        options = None
        if q.options:
            try:
                options = json.loads(q.options) if isinstance(q.options, str) else q.options
            except (json.JSONDecodeError, TypeError):
                options = None

        return QuestionDetailResponse(
            id=q.id,
            session_id=q.session_id,
            question_type=getattr(q, "question_type", "esai") or "esai",
            question_text=q.question_text,
            options=options,
            answer_key=q.answer_key,
            explanation=getattr(q, "explanation", None),
            source_reference=getattr(q, "source_reference", None),
            bloom_level=q.bloom_level,
            status=q.status,
            refinement_count=q.refinement_count,
            knowledge_point=getattr(q, "knowledge_point", None),
            grounding_evidence=getattr(q, "grounding_evidence", None),
            rubric=getattr(q, "rubric", None),
            answer_elements=getattr(q, "answer_elements", None),
            prompt_traces=getattr(q, "prompt_traces", None),
            validation_logs=log_responses,
            used_chunks=used_chunks,
            quality_warnings=getattr(q, "quality_warnings", None),
        )


@router.get("/", response_model=list[QuestionResponse])
def list_questions(session_id: str | None = Query(None), document_id: str | None = Query(None)):
    """List questions, filterable by session_id and/or document_id (the book the session was opened on)."""
    with get_session() as db:
        query = (
            db.query(Question, ChatSession.document_id, Document.filename)
            .join(ChatSession, Question.session_id == ChatSession.id)
            .outerjoin(Document, ChatSession.document_id == Document.id)
        )
        if session_id:
            query = query.filter(Question.session_id == session_id)
        if document_id:
            query = query.filter(ChatSession.document_id == document_id)
        rows = query.order_by(Question.created_at.desc()).all()

        result = []
        for q, doc_id, doc_filename in rows:
            opts = None
            if q.options:
                try:
                    opts = json.loads(q.options) if isinstance(q.options, str) else q.options
                except Exception:
                    opts = None

            result.append(
                QuestionResponse(
                    id=q.id,
                    session_id=q.session_id,
                    document_id=doc_id,
                    document_filename=doc_filename,
                    question_type=getattr(q, "question_type", "esai") or "esai",
                    question_text=q.question_text,
                    options=opts,
                    answer_key=q.answer_key,
                    explanation=getattr(q, "explanation", None),
                    source_reference=getattr(q, "source_reference", None),
                    bloom_level=q.bloom_level,
                    status=q.status,
                    refinement_count=q.refinement_count,
                    knowledge_point=getattr(q, "knowledge_point", None),
                    grounding_evidence=getattr(q, "grounding_evidence", None),
                    rubric=getattr(q, "rubric", None),
                    answer_elements=getattr(q, "answer_elements", None),
                    chunk_ids=q.chunk_ids or "[]",
                    quality_warnings=getattr(q, "quality_warnings", None),
                )
            )
        return result
