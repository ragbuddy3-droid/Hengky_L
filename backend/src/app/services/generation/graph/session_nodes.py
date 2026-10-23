"""Session-level LangGraph nodes (AQGState).

retrieve_context -> generate_questions -> review_results -> (top_up_questions -> review_results ->) persist_questions.
The nodes only orchestrate; retrieval, planning, prompting, and persistence live in app.services.
"""

import functools
import inspect
import logging
import time
from typing import Any

from app.core.config import get_settings
from app.services.generation import progress
from app.services.generation.graph.state import AQGState, count_final
from app.services.generation.pipeline import cached_analyses, ensure_analyses, ensure_plans, generate_and_validate
from app.services.generation.planner import (
    allocate_items,
    assign_bloom_levels,
    bloom_order,
    candidate_count,
    chunk_point_lists,
    interleave,
    real_capacity,
)
from app.services.questions.repository import save_questions
from app.services.retrieval.capacity import select_by_capacity
from app.services.retrieval.retriever import load_document_chunks, retrieve_chunks

logger = logging.getLogger(__name__)

_EXPANSION_ROUNDS = 2  # times Node 2 may pull reserve chunks when Stage 1 finds too few points


def _timed(node_name: str):
    """Log wall-clock duration of a graph node (sync or async)."""
    def decorator(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    return await fn(*args, **kwargs)
                finally:
                    logger.info("[Timing] node=%s %d ms", node_name, int((time.perf_counter() - t0) * 1000))
            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                logger.info("[Timing] node=%s %d ms", node_name, int((time.perf_counter() - t0) * 1000))
        return sync_wrapper
    return decorator


@_timed("retrieve_context")
def retrieve_context(state: AQGState) -> dict[str, Any]:
    """Node 1: rank chunks (hybrid RAG) and keep the fewest whose estimated capacity covers the candidates."""
    logger.info("[LangGraph Node 1] retrieve_context started for session_id='%s'", state["session_id"])
    progress.phase(state.get("session_id"), "retrieval", "Mencari materi yang relevan…")
    document_id = state["document_id"]

    chunks = load_document_chunks(document_id)
    if not chunks:
        logger.error("No chunks found in DB for document_id='%s'", document_id)
        return {
            "retrieved_chunks": [],
            "reserve_chunks": [],
            "source_chunk_ids": [],
            "error": f"Dokumen '{document_id}' belum diproses atau tidak memiliki chunk materi.",
        }

    result = retrieve_chunks(
        document_id=document_id,
        chunks=chunks,
        user_prompt=state.get("user_prompt", ""),
        chapter=state.get("chapter"),
        needed=candidate_count(state.get("num_questions", 5)),
    )
    return {
        "retrieved_chunks": result.chunks,
        "reserve_chunks": result.reserve,
        "source_chunk_ids": [c["id"] for c in result.chunks],
    }


@_timed("generate_questions")
async def generate_questions(state: AQGState) -> dict[str, Any]:
    """Node 2: Multi-Stage generation over capacity-checked chunks, each question validated as soon as it is written.

    Stage 1 measures each chunk's real capacity (valid testable points). If the selected chunks fall
    short, the next reserve chunks are analysed (at most `_EXPANSION_ROUNDS` times) before any point is
    reused. Each chunk then gets up to `max_questions_per_chunk` questions.
    """
    logger.info("[LangGraph Node 2] Multi-Stage generate_questions started")
    session_id = state.get("session_id")
    retrieved = list(state.get("retrieved_chunks", []))
    if not retrieved:
        return {"validated_questions": [], "error": state.get("error") or "Tidak ada konteks materi untuk pembuatan soal."}

    max_per_chunk = get_settings().retrieval.max_questions_per_chunk
    reserve = list(state.get("reserve_chunks", []))
    levels = assign_bloom_levels(candidate_count(state.get("num_questions", 5)), state.get("bloom_level"))

    stage_cache = await ensure_analyses(retrieved, {}, session_id)
    point_lists = chunk_point_lists(retrieved, cached_analyses(stage_cache))
    for _ in range(_EXPANSION_ROUNDS):
        short = len(levels) - real_capacity(point_lists, max_per_chunk)
        if short <= 0 or not reserve:
            break
        new_chunks, reserve = select_by_capacity(reserve, short, len(reserve))
        if not new_chunks:
            break
        logger.info("[Node 2] Capacity short by %d; analysing %d reserve chunk(s).", short, len(new_chunks))
        retrieved += new_chunks
        stage_cache = await ensure_analyses(new_chunks, stage_cache, session_id)
        point_lists = chunk_point_lists(retrieved, cached_analyses(stage_cache))

    items, spare_items = allocate_items(point_lists, levels, max_per_chunk)
    if not items:
        return {"validated_questions": [], "error": "Materi yang ditemukan tidak memuat poin yang dapat dijadikan soal."}
    stage_cache = await ensure_plans(state["document_id"], [it["bloom_level"] for it in items], stage_cache, session_id)
    logger.info(
        "[Node 2] %d candidates from %d chunks (real capacity %d).",
        len(items), len({it["chunk_id"] for it in items}), real_capacity(point_lists, max_per_chunk),
    )

    progress.phase(session_id, "generation", f"Membuat dan memvalidasi {len(items)} kandidat soal…")
    validated = await generate_and_validate(state, retrieved, items, stage_cache, "r1", existing=[])
    logger.info("[Node 2] %d of %d candidates validated (%d final).", len(validated), len(items), count_final(validated))

    return {
        "validated_questions": validated,
        "retrieved_chunks": retrieved,
        "reserve_chunks": reserve,
        "source_chunk_ids": [c["id"] for c in retrieved],
        "spare_items": spare_items,
        "stage_cache": stage_cache,
    }


def review_results(state: AQGState) -> dict[str, Any]:
    """Summarize the validated questions so far (after generation or top-up)."""
    validated = state.get("validated_questions", [])
    logger.info("[Node Review] %d/%d candidates passed (target %d).",
                count_final(validated), len(validated), state.get("num_questions", 5))
    return {}


@_timed("top_up_questions")
async def top_up_questions(state: AQGState) -> dict[str, Any]:
    """Generate and validate replacement candidates for questions that did not pass validation (one round only).

    Knowledge points come from, in order: valid points not used yet, reserve chunks (analysed now and
    checked for capacity), and finally the points whose question failed.
    """
    session_id = state.get("session_id")
    validated = state.get("validated_questions", [])
    count = max(0, state.get("num_questions", 5) - count_final(validated)) + 1

    # Keep the requested level mix: replace failed questions with the same levels
    failed = [q for q in validated if q.get("status") != "final"]
    levels = ([q["bloom_level"] for q in failed] + assign_bloom_levels(count, state.get("bloom_level")))[:count]

    retrieved = list(state.get("retrieved_chunks", []))
    reserve = list(state.get("reserve_chunks", []))
    spare = list(state.get("spare_items", []))
    stage_cache = state.get("stage_cache", {})

    if len(spare) < count and reserve:
        new_chunks, reserve = select_by_capacity(reserve, count - len(spare), len(reserve))
        if new_chunks:
            retrieved += new_chunks
            stage_cache = await ensure_analyses(new_chunks, stage_cache, session_id)
            used_points = [q.get("knowledge_point", "") for q in validated] + [s["point"] for s in spare]
            spare += interleave(chunk_point_lists(new_chunks, cached_analyses(stage_cache), exclude_points=used_points))
    if len(spare) < count:
        spare += [
            {"point": q.get("knowledge_point", ""), "quote": q.get("grounding_evidence", ""), "chunk_id": q["chunk_id"]}
            for q in failed if q.get("chunk_id")
        ]
    if not spare:
        return {"top_up_done": True}

    items, rest = allocate_items([spare], levels, max_per_chunk=len(levels))
    stage_cache = await ensure_plans(state["document_id"], levels, stage_cache, session_id)
    logger.info("[Node TopUp] Generating %d replacement candidates.", len(items))

    progress.phase(session_id, "top_up", f"Membuat {len(items)} soal pengganti…")
    replacements = await generate_and_validate(state, retrieved, items, stage_cache, "r2", existing=validated)
    return {
        "validated_questions": replacements,
        "retrieved_chunks": retrieved,
        "reserve_chunks": reserve,
        "source_chunk_ids": [c["id"] for c in retrieved],
        "spare_items": rest,
        "stage_cache": stage_cache,
        "top_up_done": True,
    }


@_timed("persist_questions")
def persist_questions(state: AQGState) -> dict[str, Any]:
    """Node 6: choose the best `num_questions` (passed first, then needs_review) and save them with their own logs/traces."""
    progress.phase(state.get("session_id"), "saving", "Menyimpan soal…")
    num_questions = state.get("num_questions", 5)
    validated = state.get("validated_questions", [])

    finals = [q for q in validated if q.get("status") == "final"]
    reviews = [q for q in validated if q.get("status") != "final"]
    selected = sorted((finals + reviews)[:num_questions], key=bloom_order)

    saved = save_questions(state["session_id"], selected, state.get("source_chunk_ids", []))
    logger.info(
        "[Node 6] Persisted %d questions (%d final, %d needs_review) out of %d validated candidates.",
        len(saved), count_final(saved), len(saved) - count_final(saved), len(validated),
    )
    return {"finalized_questions": saved}
