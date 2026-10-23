"""Multi-stage generation pipeline shared by the session graph and chat revisions.

Stage 1 (per chunk, cached) and Stage 2 (per Bloom level) fill a shared stage cache; generate_and_validate then
runs Stage 3 per chunk and Stage 4 per question, sending each candidate into the validation subgraph as soon as
it is written.
"""

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any, TypeVar

from app.services.generation import progress
from app.services.generation.analysis_cache import load_cached_analyses, store_analyses
from app.services.generation.graph.state import AQGState, count_final
from app.services.generation.graph.validation import validate_candidate, validation_input
from app.services.generation.planner import (
    NO_FEW_SHOT,
    focus_context,
    load_few_shots,
    planning_summary,
    source_reference,
)
from app.services.generation.schemas import CognitivePlan, ContentAnalysis, QuestionBlueprint
from app.services.generation.stage_runners import (
    run_stage1_context_understanding,
    run_stage2_cognitive_planning,
    run_stage3_blueprint_batch,
    run_stage4_question_generation,
)
from app.services.llm import get_chat_model
from app.services.validation.quality_checks import (
    deduplicate_questions,
)

logger = logging.getLogger(__name__)

_DEDUP_THRESHOLD = 0.70

R = TypeVar("R")


async def _gather(coros: list[Awaitable[R]]) -> list[R]:
    """asyncio.gather as a list; LLM concurrency is capped inside the stage runners."""
    return list(await asyncio.gather(*coros))


# ── Shared Stage 1/2 cache ──

def cached_analyses(stage_cache: dict[str, Any]) -> dict[str, ContentAnalysis]:
    return {cid: ContentAnalysis.model_validate(v["analysis"]) for cid, v in stage_cache.get("analyses", {}).items()}


def _copy_cache(stage_cache: dict[str, Any]) -> dict[str, Any]:
    return {
        "analyses": dict(stage_cache.get("analyses", {})),
        "plans": dict(stage_cache.get("plans", {})),
        "few_shots": dict(stage_cache.get("few_shots", {})),
    }


async def ensure_analyses(
    chunks: list[dict[str, Any]], stage_cache: dict[str, Any], session_id: str | None = None,
) -> dict[str, Any]:
    """Stage 1 for chunks not in the cache yet: reuse the persistent per-chunk cache, call the LLM for the rest.

    Stage 1 runs once per chunk so every knowledge point keeps its source chunk. Returns a new cache.
    """
    cache = _copy_cache(stage_cache)
    missing = [c for c in chunks if c["id"] not in cache["analyses"]]
    if not missing:
        return cache

    stored = await asyncio.to_thread(load_cached_analyses, [c["id"] for c in missing])
    cache["analyses"].update(stored)
    to_run = [c for c in missing if c["id"] not in stored]
    if to_run:
        progress.phase(session_id, "analysis", f"Menganalisis {len(to_run)} bagian materi…")
        analysis_model = get_chat_model(is_judge=False, temperature=0.1)
        stage1 = await _gather([
            run_stage1_context_understanding(analysis_model, c.get("text", ""), 1) for c in to_run
        ])
        fresh = {
            chk["id"]: {"analysis": ca.model_dump(), "trace": trace.model_dump()}
            for chk, (ca, trace) in zip(to_run, stage1, strict=True)
        }
        cache["analyses"].update(fresh)
        await asyncio.to_thread(store_analyses, fresh)
    logger.info("[Stage 1] %d chunks: %d from cache, %d analysed.", len(missing), len(stored), len(to_run))
    return cache


async def ensure_plans(
    document_id: str, levels: list[str], stage_cache: dict[str, Any], session_id: str | None = None,
) -> dict[str, Any]:
    """Stage 2 (+ few-shot examples) for Bloom levels not planned yet, from a topic/concept summary only."""
    cache = _copy_cache(stage_cache)
    new_levels = [lvl for lvl in dict.fromkeys(levels) if lvl not in cache["plans"]]
    if not new_levels:
        return cache

    progress.phase(session_id, "planning", "Merencanakan level kognitif soal…")
    planning_model = get_chat_model(is_judge=False, temperature=0.2)
    summary = planning_summary(list(cached_analyses(cache).values()))
    stage2 = await _gather([
        run_stage2_cognitive_planning(planning_model, summary, lvl, 1) for lvl in new_levels
    ])
    for lvl, (plan, trace) in zip(new_levels, stage2, strict=True):
        cache["plans"][lvl] = {"plan": plan.model_dump(), "trace": trace.model_dump()}
    cache["few_shots"].update(await asyncio.to_thread(load_few_shots, document_id, new_levels))
    return cache


async def generate_and_validate(
    state: AQGState,
    chunks: list[dict[str, Any]],
    items: list[dict[str, Any]],
    stage_cache: dict[str, Any],
    round_tag: str,
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pipeline per question: Stage 3 once per chunk, then Stage 4 -> dedup -> validation for each question.

    Every call sees only the question's own chunk; that text is stored as the candidate's context so the
    judge and refinement evaluate against exactly the same material. A question is validated as soon as it
    is written instead of waiting for its siblings. Once `num_questions` questions are final (counting
    `existing`), candidates still in flight are cancelled. Returns this round's validated questions.
    """
    session_id = state.get("session_id")
    target = state.get("num_questions", 5)
    chunk_by_id = {c["id"]: c for c in chunks}
    generation_model = get_chat_model(is_judge=False, temperature=0.4)
    analyses = cached_analyses(stage_cache)
    plans = {lvl: CognitivePlan.model_validate(v["plan"]) for lvl, v in stage_cache["plans"].items()}

    groups: dict[str, list[int]] = {}
    for idx, item in enumerate(items):
        groups.setdefault(item["chunk_id"], []).append(idx)

    ids = [f"{round_tag}-{i + 1}" for i in range(len(items))]
    for cid in ids:
        progress.candidate(session_id, cid, "blueprint")

    validated: list[dict[str, Any]] = []
    seen = list(existing)  # questions a new candidate must not duplicate
    open_ids = set(ids)
    finals_before = count_final(existing)
    target_reached = asyncio.Event()

    def _close(cid: str, status: str, q: dict[str, Any] | None = None) -> None:
        open_ids.discard(cid)
        progress.candidate(session_id, cid, status, q)

    async def _question(idx: int, blueprint: QuestionBlueprint, bp_fallback: bool, t3: dict[str, Any]) -> None:
        item, cid = items[idx], ids[idx]
        chk = chunk_by_id[item["chunk_id"]]
        level = item["bloom_level"]
        c_analysis = analyses[item["chunk_id"]]
        context = focus_context(chk)
        # Each question's trace holds only the stages that produced it
        step_traces = [stage_cache["analyses"][chk["id"]]["trace"], stage_cache["plans"][level]["trace"], t3]

        progress.candidate(session_id, cid, "writing")
        q_type = blueprint.question_type or plans[level].recommended_question_format or "esai"
        q_pkg, t4 = await run_stage4_question_generation(
            generation_model, context, blueprint, level, q_type,
            stage_cache["few_shots"].get(level, NO_FEW_SHOT), 1,
        )
        step_traces.append(t4.model_dump())

        q = {
            "question": q_pkg.question,
            "question_type": q_pkg.question_type or q_type,
            "answer": q_pkg.expected_answer,
            "explanation": q_pkg.explanation or f"Berdasarkan analisis materi '{c_analysis.topic}'. Poin uji: {blueprint.knowledge_point}.",
            "source_reference": source_reference(chk),
            # The assigned level is authoritative; the model's echo of it is not
            "bloom_level": level,
            "knowledge_point": q_pkg.knowledge_point or blueprint.knowledge_point or item["point"],
            "grounding_evidence": q_pkg.grounding_evidence or blueprint.grounding_evidence,
            "content_analysis": c_analysis.model_dump(),
            "cognitive_plan": plans[level].model_dump(),
            "question_blueprint": blueprint.model_dump(),
            "context": context,
            "stage_traces": step_traces,
            "chunk_id": chk["id"],
            "has_fallback": bp_fallback or any(t.get("status") == "fallback" or t.get("has_fallback") for t in step_traces),
        }

        if not deduplicate_questions([q], threshold=_DEDUP_THRESHOLD, existing=seen):
            logger.info("[Pipeline] %s dropped as a near-duplicate: '%s'", cid, q["question"][:60])
            _close(cid, "dropped")
            return
        seen.append(q)

        result = await validate_candidate(validation_input(q, session_id, state.get("bloom_level"), cid))
        validated.append(result)
        _close(cid, result.get("status", "needs_review"), result)
        if finals_before + count_final(validated) >= target:
            target_reached.set()

    async def _chunk_group(chunk_id: str, indices: list[int]) -> None:
        group = [items[i] for i in indices]
        logger.info("[Multi-Stage Gen] %d question(s) from chunk '%s'.", len(group), source_reference(chunk_by_id[chunk_id])[:60])
        blueprints, fallbacks, t3 = await run_stage3_blueprint_batch(
            generation_model, focus_context(chunk_by_id[chunk_id]), group, plans, 1,
        )
        trace = t3.model_dump()
        await asyncio.gather(*[
            _question(i, bp, fb, trace) for i, bp, fb in zip(indices, blueprints, fallbacks, strict=True)
        ])

    all_done = asyncio.gather(*[_chunk_group(cid, idxs) for cid, idxs in groups.items()])
    stop = asyncio.ensure_future(target_reached.wait())
    await asyncio.wait([all_done, stop], return_when=asyncio.FIRST_COMPLETED)
    stop.cancel()
    if all_done.done():
        all_done.result()  # surface an unexpected error from a chunk group
    else:
        logger.info("[Pipeline] %d final questions reached; cancelling %d candidate(s).", target, len(open_ids))
        all_done.cancel()
        await asyncio.gather(all_done, return_exceptions=True)
    for cid in list(open_ids):
        _close(cid, "dropped")
    return validated
