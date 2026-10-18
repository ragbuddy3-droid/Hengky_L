"""Persistence of generated questions with their own validation logs and prompt traces."""

import json
import logging
import uuid
from typing import Any

from app.core.database import get_session
from app.models.db_models import Question, ValidationLog
from app.services.validation.quality_checks import validate_answer_quality

logger = logging.getLogger(__name__)

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


def save_questions(
    session_id: str,
    questions: list[dict[str, Any]],
    source_chunk_ids: list[str],
) -> list[dict[str, Any]]:
    """Insert questions (+ their validation logs); returns copies carrying the new ids and filled defaults."""
    saved: list[dict[str, Any]] = []
    with get_session() as db:
        for q in questions:
            q = dict(q)
            q["id"] = str(uuid.uuid4())
            q["source_reference"] = q.get("source_reference") or "Materi Buku"
            q["explanation"] = q.get("explanation") or f"Penjelasan berdasarkan materi {q.get('knowledge_point', '')}."

            quality_issues = validate_answer_quality(q)
            # Generation, judge, and refinement only saw the question's own chunk
            chunk_ids = [q["chunk_id"]] if q.get("chunk_id") else source_chunk_ids

            db.add(Question(
                id=q["id"],
                session_id=session_id,
                chunk_ids=_dumps(chunk_ids),
                question_type=q.get("question_type", "esai"),
                question_text=q.get("question", ""),
                answer_key=q.get("answer", ""),
                explanation=q["explanation"],
                source_reference=q["source_reference"],
                bloom_level=q.get("bloom_level") or "C2-Memahami",
                status=q.get("status", "needs_review"),
                refinement_count=q.get("refinement_count", 0),
                grounding_evidence=q.get("grounding_evidence", ""),
                knowledge_point=q.get("knowledge_point", ""),
                prompt_traces=_dumps(_prune_stage_traces(q.get("stage_traces", []))),
                quality_warnings=_dumps(quality_issues) if quality_issues else None,
            ))

            for log_item in q.get("validation_logs", []):
                db.add(ValidationLog(
                    question_id=q["id"],
                    attempt_number=log_item.get("attempt_number", 1),
                    layer=log_item.get("layer", "grounding"),
                    score_or_verdict=log_item.get("score_or_verdict", ""),
                    feedback=log_item.get("feedback", ""),
                    aspect_evaluations=log_item.get("aspect_evaluations"),
                ))
            saved.append(q)

        db.commit()
    return saved
