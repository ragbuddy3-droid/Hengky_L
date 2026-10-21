"""Persistence of generated questions with their own validation logs and prompt traces."""

import json
import uuid
from datetime import timedelta
from typing import Any

from app.core.database import get_session
from app.models.db_models import Question, ValidationLog, utcnow
from app.services.validation.quality_checks import validate_answer_quality

_MAX_STORED_PROMPT_CHARS = 6000


def _prune_stage_traces(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cap very long prompts to keep SQLite small. Raw responses are kept whole so their JSON stays readable."""
    pruned = []
    for tr in traces:
        t_copy = dict(tr)
        prompt = t_copy.get("prompt_sent")
        if isinstance(prompt, str) and len(prompt) > _MAX_STORED_PROMPT_CHARS:
            t_copy["prompt_sent"] = prompt[:_MAX_STORED_PROMPT_CHARS] + "... [truncated for storage]"
        pruned.append(t_copy)
    return pruned


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _validation_log_rows(question_id: str, logs: list[dict[str, Any]]) -> list[ValidationLog]:
    return [
        ValidationLog(
            question_id=question_id,
            attempt_number=log_item.get("attempt_number", 1),
            layer=log_item.get("layer", "grounding"),
            score_or_verdict=log_item.get("score_or_verdict", ""),
            feedback=log_item.get("feedback", ""),
            aspect_evaluations=log_item.get("aspect_evaluations"),
        )
        for log_item in logs
    ]


def _with_defaults(q: dict[str, Any], question_id: str, fallback_reference: str | None = None) -> dict[str, Any]:
    q = dict(q)
    q["id"] = question_id
    q["source_reference"] = q.get("source_reference") or fallback_reference or "Materi Buku"
    q["explanation"] = q.get("explanation") or f"Penjelasan berdasarkan materi {q.get('knowledge_point', '')}."
    return q


def _content_columns(q: dict[str, Any]) -> dict[str, Any]:
    """Question columns written by both inserts and in-place revisions."""
    quality_issues = validate_answer_quality(q)
    return {
        "question_type": q.get("question_type", "esai"),
        "question_text": q.get("question", ""),
        "answer_key": q.get("answer", ""),
        "explanation": q["explanation"],
        "source_reference": q["source_reference"],
        "status": q.get("status", "needs_review"),
        "refinement_count": q.get("refinement_count", 0),
        "grounding_evidence": q.get("grounding_evidence", ""),
        "knowledge_point": q.get("knowledge_point", ""),
        "prompt_traces": _dumps(_prune_stage_traces(q.get("stage_traces", []))),
        "quality_warnings": _dumps(quality_issues) if quality_issues else None,
    }


def save_questions(
    session_id: str,
    questions: list[dict[str, Any]],
    source_chunk_ids: list[str],
) -> list[dict[str, Any]]:
    """Insert questions (+ their validation logs); returns copies carrying the new ids and filled defaults."""
    saved: list[dict[str, Any]] = []
    # Distinct timestamps keep the saved order as the session numbering ("soal nomor N")
    base_time = utcnow()
    with get_session() as db:
        for offset, q in enumerate(questions):
            q = _with_defaults(q, str(uuid.uuid4()))
            # Generation, judge, and refinement only saw the question's own chunk
            chunk_ids = [q["chunk_id"]] if q.get("chunk_id") else source_chunk_ids
            db.add(Question(
                id=q["id"],
                session_id=session_id,
                created_at=base_time + timedelta(microseconds=offset),
                chunk_ids=_dumps(chunk_ids),
                bloom_level=q.get("bloom_level") or "C2-Memahami",
                **_content_columns(q),
            ))
            db.add_all(_validation_log_rows(q["id"], q.get("validation_logs", [])))
            saved.append(q)

        db.commit()
    return saved


def replace_question(question_id: str, q: dict[str, Any]) -> dict[str, Any] | None:
    """Overwrite a stored question in place (same id and position) with a revised one and its new logs/traces."""
    with get_session() as db:
        row = db.get(Question, question_id)
        if row is None:
            return None
        q = _with_defaults(q, question_id, str(row.source_reference or ""))
        for column, value in _content_columns(q).items():
            setattr(row, column, value)
        if q.get("chunk_id"):
            row.chunk_ids = _dumps([q["chunk_id"]])  # type: ignore[assignment]
        row.bloom_level = q.get("bloom_level") or row.bloom_level  # type: ignore[assignment]
        row.revision_count = (row.revision_count or 0) + 1  # type: ignore[assignment]

        db.query(ValidationLog).filter(ValidationLog.question_id == question_id).delete()
        db.add_all(_validation_log_rows(question_id, q.get("validation_logs", [])))
        db.commit()
        q["revision_count"] = row.revision_count
    return q
