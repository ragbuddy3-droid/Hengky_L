"""Questions API router v1."""
import json
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from app.db.engine import get_session
from app.db.models import Question, ValidationLog, Chunk
from app.schemas.api import ValidationLogResponse, QuestionDetailResponse, UsedChunkResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])



@router.get("/{question_id}", response_model=QuestionDetailResponse)
def get_question(question_id: str):
    """Get question detail with validation logs and used context chunks."""
    logger.debug("GET question detail: question_id='%s'", question_id)
    with get_session() as db:
        q = db.query(Question).filter(Question.id == question_id).first()
        if not q:
            logger.warning("Question not found: question_id='%s'", question_id)
            raise HTTPException(status_code=404, detail="Question not found")

        logs = db.query(ValidationLog).filter(
            ValidationLog.question_id == question_id
        ).all()
        
        logger.debug("Question found: question_id='%s', status='%s', validation_logs=%d",
                    question_id, q.status, len(logs))
        
        log_responses = [
            ValidationLogResponse(
                id=log.id,
                attempt_number=log.attempt_number,
                layer=log.layer,
                score_or_verdict=log.score_or_verdict,
                feedback=log.feedback,
            )
            for log in logs
        ]

        used_chunks = []
        if q.chunk_ids:
            try:
                c_ids = json.loads(q.chunk_ids) if isinstance(q.chunk_ids, str) else q.chunk_ids
                if isinstance(c_ids, list) and c_ids:
                    db_chunks = db.query(Chunk).filter(Chunk.id.in_(c_ids)).all()
                    # Preserve original order from c_ids if possible
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
            validation_logs=log_responses,
            used_chunks=used_chunks,
        )


@router.get("/")
def list_questions(session_id: Optional[str] = Query(None)):
    """List questions, filterable by session_id."""
    logger.debug("GET list questions (session_id=%s)", session_id or '(all)')
    with get_session() as db:
        query = db.query(Question)
        if session_id:
            query = query.filter(Question.session_id == session_id)
        questions = query.all()
        logger.debug("Returning %d questions", len(questions))
        result = []
        for q in questions:
            opts = None
            if q.options:
                try:
                    opts = json.loads(q.options) if isinstance(q.options, str) else q.options
                except Exception:
                    opts = None
            result.append({
                "id": q.id,
                "question_type": getattr(q, "question_type", "esai") or "esai",
                "question_text": q.question_text,
                "options": opts,
                "answer_key": q.answer_key,
                "explanation": getattr(q, "explanation", None),
                "source_reference": getattr(q, "source_reference", None),
                "bloom_level": q.bloom_level,
                "status": q.status,
                "refinement_count": q.refinement_count,
            })
        return result
