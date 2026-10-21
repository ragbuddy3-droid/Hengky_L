"""Regenerate or revise one stored question on request from chat, through the same stages and validation loop.

Both paths work on the question's own chunk only, reuse the persistent Stage 1 cache, and send the result
through the per-question validation subgraph (grounding -> judge <-> self-refinement), so a revision that
drifts away from the material is repaired or ends up as "needs_review" like any generated question.
"""

import logging
from typing import Any, Literal, cast

from app.graph.nodes import (
    cached_analyses,
    ensure_analyses,
    ensure_plans,
    generate_and_validate,
    validate_candidate,
    validation_input,
)
from app.graph.state import AQGState
from app.services.generation import progress
from app.services.generation.planner import source_reference, valid_points
from app.services.generation.schemas import CognitivePlan, QuestionBlueprint
from app.services.generation.stage_runners import run_refinement_a
from app.services.llm import get_chat_model
from app.services.validation.quality_checks import jaccard, tokens

logger = logging.getLogger(__name__)

RevisionAction = Literal["regenerate", "revise"]

_CANDIDATE_ID = "rv-1"


def _pick_point(chunk: dict[str, Any], points: list[dict[str, Any]], old: dict[str, Any], others: list[dict[str, Any]]) -> dict[str, Any]:
    """The chunk's knowledge point least similar to the old question's and to the session's other questions."""
    if not points:
        return {"point": old.get("knowledge_point") or "", "quote": old.get("grounding_evidence") or "", "chunk_id": chunk["id"]}
    avoid = [tokens(old.get("knowledge_point") or "")] + [tokens(o.get("knowledge_point") or "") for o in others]
    return min(points, key=lambda p: max((jaccard(tokens(p["point"]), a) for a in avoid if a), default=0.0))


async def _regenerate(
    session_id: str, document_id: str, chunk: dict[str, Any], old: dict[str, Any], level: str,
    others: list[dict[str, Any]], stage_cache: dict[str, Any],
) -> dict[str, Any] | None:
    analysis = cached_analyses(stage_cache)[chunk["id"]]
    item = {**_pick_point(chunk, valid_points(chunk, analysis), old, others), "bloom_level": level}
    state: dict[str, Any] = {"session_id": session_id, "document_id": document_id, "num_questions": 1, "bloom_level": level}
    results = await generate_and_validate(cast(AQGState, state), [chunk], [item], stage_cache, "rv", existing=others)
    return results[0] if results else None


async def _revise(
    session_id: str, chunk: dict[str, Any], old: dict[str, Any], level: str, instruction: str, stage_cache: dict[str, Any],
) -> dict[str, Any]:
    analysis = cached_analyses(stage_cache)[chunk["id"]]
    plan = CognitivePlan.model_validate(stage_cache["plans"][level]["plan"])
    q_type = old.get("question_type") or "esai"
    blueprint = QuestionBlueprint(
        knowledge_point=old.get("knowledge_point") or "",
        question_type=q_type,
        question_intent=plan.student_task,
        grounding_evidence=old.get("grounding_evidence") or "",
        expected_answer_summary=old.get("answer") or "",
    )

    progress.candidate(session_id, _CANDIDATE_ID, "writing")
    pkg, trace = await run_refinement_a(
        chat_model=get_chat_model(is_judge=False, temperature=0.3),
        question=old.get("question", ""),
        expected_answer=old.get("answer", ""),
        explanation=old.get("explanation", ""),
        blueprint=blueprint,
        retrieved_context=chunk.get("text", ""),
        validation_feedback=f"Permintaan revisi dari guru: {instruction}",
        target_bloom_level=level,
        question_type=q_type,
        attempt=1,
    )
    q = {
        "question": pkg.question,
        "question_type": pkg.question_type or q_type,
        "answer": pkg.expected_answer,
        "explanation": pkg.explanation or old.get("explanation", ""),
        "source_reference": source_reference(chunk),
        "bloom_level": level,
        "knowledge_point": pkg.knowledge_point or blueprint.knowledge_point,
        "grounding_evidence": pkg.grounding_evidence or blueprint.grounding_evidence,
        "content_analysis": analysis.model_dump(),
        "cognitive_plan": plan.model_dump(),
        "question_blueprint": blueprint.model_dump(),
        "context": chunk.get("text", ""),
        "stage_traces": [
            stage_cache["analyses"][chunk["id"]]["trace"], stage_cache["plans"][level]["trace"], trace.model_dump(),
        ],
        "chunk_id": chunk["id"],
        "has_fallback": trace.has_fallback,
    }
    result = await validate_candidate(validation_input(q, session_id, level, _CANDIDATE_ID))
    progress.candidate(session_id, _CANDIDATE_ID, result.get("status", "needs_review"), result)
    return result


async def revise_question(
    session_id: str,
    document_id: str,
    chunk: dict[str, Any],
    old: dict[str, Any],
    action: RevisionAction,
    level: str | None,
    instruction: str | None,
    others: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """New validated version of `old` (keys as in generation: question, answer, ...), or None if none was produced.

    `others` are the session's other questions, which a regenerated question must not duplicate.
    """
    target = level or old.get("bloom_level") or "C2-Memahami"
    stage_cache = await ensure_analyses([chunk], {}, session_id)
    stage_cache = await ensure_plans(document_id, [target], stage_cache, session_id)
    logger.info("[Revision] %s question (level %s) from chunk '%s'.", action, target, source_reference(chunk)[:60])

    if action == "regenerate":
        progress.phase(session_id, "generation", "Membuat ulang soal…")
        return await _regenerate(session_id, document_id, chunk, old, target, others, stage_cache)
    progress.phase(session_id, "generation", "Merevisi soal…")
    return await _revise(session_id, chunk, old, target, instruction or "Perbaiki soal agar lebih baik.", stage_cache)
