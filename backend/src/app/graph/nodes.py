"""LangGraph node implementations for Multi-Stage RAG-AQG generation, 2-layer validation, and persistence.

Session-level nodes (AQGState): retrieve_context -> generate_questions -> review_results
-> (top_up_questions -> review_results ->) persist_questions.

Generation is pipelined per question: as soon as a candidate leaves Stage 4 it enters its own run of the
validation subgraph (QuestionState): grounding_validation -> llm_judge_evaluation <-> self_refinement
-> finalize_question. Once enough candidates are final, the remaining ones are cancelled.

The nodes only orchestrate; retrieval, planning, prompting, and persistence live in app.services.
"""

import asyncio
import functools
import inspect
import json
import logging
import time
from collections.abc import Awaitable
from typing import Any, TypeVar

from app.core.config import get_settings
from app.graph.state import AQGState, QuestionState
from app.services.generation import progress
from app.services.generation.analysis_cache import load_cached_analyses, store_analyses
from app.services.generation.planner import (
    NO_FEW_SHOT,
    allocate_items,
    assign_bloom_levels,
    bloom_order,
    candidate_count,
    chunk_point_lists,
    focus_context,
    interleave,
    load_few_shots,
    planning_summary,
    real_capacity,
    source_reference,
)
from app.services.generation.schemas import (
    CognitivePlan,
    ContentAnalysis,
    QuestionBlueprint,
)
from app.services.generation.stage_runners import (
    run_llm_judge,
    run_refinement_a,
    run_refinement_b,
    run_stage1_context_understanding,
    run_stage2_cognitive_planning,
    run_stage3_blueprint_batch,
    run_stage3_question_blueprint,
    run_stage4_question_generation,
)
from app.services.llm import get_chat_model
from app.services.questions.repository import save_questions
from app.services.retrieval.capacity import select_by_capacity
from app.services.retrieval.retriever import (
    get_shared_dense_index,
    load_document_chunks,
    retrieve_chunks,
)
from app.services.validation.grounding_checker import compute_grounding_evidence_score
from app.services.validation.quality_checks import (
    deduplicate_questions,
    find_clarity_issue,
    find_unanswerable_answer,
    is_reflective_question,
)

logger = logging.getLogger(__name__)

_DEDUP_THRESHOLD = 0.70
_EXPANSION_ROUNDS = 2  # times Node 2 may pull reserve chunks when Stage 1 finds too few points
_JUDGE_ASPECTS = ["grounding", "bloom_adherence", "bahasa", "answerability", "answer_alignment"]

R = TypeVar("R")


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


async def _gather(coros: list[Awaitable[R]]) -> list[R]:
    """asyncio.gather as a list; LLM concurrency is capped inside the stage runners."""
    return list(await asyncio.gather(*coros))


def _count_final(questions: list[dict[str, Any]]) -> int:
    return sum(1 for q in questions if q.get("status") == "final")


# ── Shared Stage 1/2 cache ──

def _analyses(stage_cache: dict[str, Any]) -> dict[str, ContentAnalysis]:
    return {cid: ContentAnalysis.model_validate(v["analysis"]) for cid, v in stage_cache.get("analyses", {}).items()}


def _copy_cache(stage_cache: dict[str, Any]) -> dict[str, Any]:
    return {
        "analyses": dict(stage_cache.get("analyses", {})),
        "plans": dict(stage_cache.get("plans", {})),
        "few_shots": dict(stage_cache.get("few_shots", {})),
    }


async def _ensure_analyses(
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


async def _ensure_plans(
    document_id: str, levels: list[str], stage_cache: dict[str, Any], session_id: str | None = None,
) -> dict[str, Any]:
    """Stage 2 (+ few-shot examples) for Bloom levels not planned yet, from a topic/concept summary only."""
    cache = _copy_cache(stage_cache)
    new_levels = [lvl for lvl in dict.fromkeys(levels) if lvl not in cache["plans"]]
    if not new_levels:
        return cache

    progress.phase(session_id, "planning", "Merencanakan level kognitif soal…")
    planning_model = get_chat_model(is_judge=False, temperature=0.2)
    summary = planning_summary(list(_analyses(cache).values()))
    stage2 = await _gather([
        run_stage2_cognitive_planning(planning_model, summary, lvl, 1) for lvl in new_levels
    ])
    for lvl, (plan, trace) in zip(new_levels, stage2, strict=True):
        cache["plans"][lvl] = {"plan": plan.model_dump(), "trace": trace.model_dump()}
    cache["few_shots"].update(await asyncio.to_thread(load_few_shots, document_id, new_levels))
    return cache


def _validation_input(
    q: dict[str, Any], session_id: str | None, session_bloom_level: str | None, candidate_id: str,
) -> QuestionState:
    """Isolated QuestionState for one candidate: its own context, traces, and an empty log."""
    return {
        "question": {k: v for k, v in q.items() if k not in ("stage_traces", "context")},
        "context": q.get("context", ""),
        "session_bloom_level": session_bloom_level,
        "session_id": session_id or "",
        "candidate_id": candidate_id,
        "attempt": 1,
        "max_attempts": get_settings().MAX_REFINEMENT_ATTEMPTS,
        "failed_stage": "none",
        "judge_evaluation": None,
        "validation_logs": [],
        "stage_traces": list(q.get("stage_traces", [])),
    }


async def validate_candidate(state: QuestionState) -> dict[str, Any]:
    """Run the per-question validation subgraph; the result carries its own logs and traces."""
    from app.graph.workflow import get_validation_graph

    result = await get_validation_graph().ainvoke(state)
    q = dict(result["question"])
    q["validation_logs"] = result.get("validation_logs", [])
    q["stage_traces"] = result.get("stage_traces", [])
    return q


async def _generate_and_validate(
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
    analyses = _analyses(stage_cache)
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
    finals_before = _count_final(existing)
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

        result = await validate_candidate(_validation_input(q, session_id, state.get("bloom_level"), cid))
        validated.append(result)
        _close(cid, result.get("status", "needs_review"), result)
        if finals_before + _count_final(validated) >= target:
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


# ── Session-level Nodes (AQGState) ──

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

    max_per_chunk = get_settings().MAX_QUESTIONS_PER_CHUNK
    reserve = list(state.get("reserve_chunks", []))
    levels = assign_bloom_levels(candidate_count(state.get("num_questions", 5)), state.get("bloom_level"))

    stage_cache = await _ensure_analyses(retrieved, {}, session_id)
    point_lists = chunk_point_lists(retrieved, _analyses(stage_cache))
    for _ in range(_EXPANSION_ROUNDS):
        short = len(levels) - real_capacity(point_lists, max_per_chunk)
        if short <= 0 or not reserve:
            break
        new_chunks, reserve = select_by_capacity(reserve, short, len(reserve))
        if not new_chunks:
            break
        logger.info("[Node 2] Capacity short by %d; analysing %d reserve chunk(s).", short, len(new_chunks))
        retrieved += new_chunks
        stage_cache = await _ensure_analyses(new_chunks, stage_cache, session_id)
        point_lists = chunk_point_lists(retrieved, _analyses(stage_cache))

    items, spare_items = allocate_items(point_lists, levels, max_per_chunk)
    if not items:
        return {"validated_questions": [], "error": "Materi yang ditemukan tidak memuat poin yang dapat dijadikan soal."}
    stage_cache = await _ensure_plans(state["document_id"], [it["bloom_level"] for it in items], stage_cache, session_id)
    logger.info(
        "[Node 2] %d candidates from %d chunks (real capacity %d).",
        len(items), len({it["chunk_id"] for it in items}), real_capacity(point_lists, max_per_chunk),
    )

    progress.phase(session_id, "generation", f"Membuat dan memvalidasi {len(items)} kandidat soal…")
    validated = await _generate_and_validate(state, retrieved, items, stage_cache, "r1", existing=[])
    logger.info("[Node 2] %d of %d candidates validated (%d final).", len(validated), len(items), _count_final(validated))

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
                _count_final(validated), len(validated), state.get("num_questions", 5))
    return {}


@_timed("top_up_questions")
async def top_up_questions(state: AQGState) -> dict[str, Any]:
    """Generate and validate replacement candidates for questions that did not pass validation (one round only).

    Knowledge points come from, in order: valid points not used yet, reserve chunks (analysed now and
    checked for capacity), and finally the points whose question failed.
    """
    session_id = state.get("session_id")
    validated = state.get("validated_questions", [])
    count = max(0, state.get("num_questions", 5) - _count_final(validated)) + 1

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
            stage_cache = await _ensure_analyses(new_chunks, stage_cache, session_id)
            used_points = [q.get("knowledge_point", "") for q in validated] + [s["point"] for s in spare]
            spare += interleave(chunk_point_lists(new_chunks, _analyses(stage_cache), exclude_points=used_points))
    if len(spare) < count:
        spare += [
            {"point": q.get("knowledge_point", ""), "quote": q.get("grounding_evidence", ""), "chunk_id": q["chunk_id"]}
            for q in failed if q.get("chunk_id")
        ]
    if not spare:
        return {"top_up_done": True}

    items, rest = allocate_items([spare], levels, max_per_chunk=len(levels))
    stage_cache = await _ensure_plans(state["document_id"], levels, stage_cache, session_id)
    logger.info("[Node TopUp] Generating %d replacement candidates.", len(items))

    progress.phase(session_id, "top_up", f"Membuat {len(items)} soal pengganti…")
    replacements = await _generate_and_validate(state, retrieved, items, stage_cache, "r2", existing=validated)
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
        len(saved), _count_final(saved), len(saved) - _count_final(saved), len(validated),
    )
    return {"finalized_questions": saved}


# ── Per-question Validation Nodes (QuestionState) ──

def _log(attempt: int, layer: str, verdict: str, score_or_verdict: str, feedback: str, aspects: str | None = None) -> dict[str, Any]:
    return {
        "attempt_number": attempt,
        "layer": layer,
        "score_or_verdict": score_or_verdict,
        "feedback": feedback,
        "aspect_evaluations": aspects,
        "verdict": verdict,
    }


def grounding_validation(state: QuestionState) -> dict[str, Any]:
    """Layer 1: deterministic pre-check, then Fast-Reject grounding similarity between QA and grounding evidence.

    Score < threshold triggers refinement; otherwise proceed to the LLM Judge (Layer 2).
    """
    q = state["question"]
    attempt = state["attempt"]
    logs = list(state.get("validation_logs", []))

    def fail(layer: str, verdict: str, feedback: str, aspects: str | None = None) -> dict[str, Any]:
        logs.append(_log(attempt, layer, "fail", verdict, feedback, aspects))
        return {"validation_logs": logs, "failed_stage": "generation"}

    q_text = q.get("question", "")
    if not q_text:
        return fail("grounding", "fail (empty_question)", "Soal kosong.")

    logger.info("[Validation] grounding (attempt %d) for: '%s'", attempt, q_text[:60])
    progress.candidate(state.get("session_id"), state.get("candidate_id"), "validating", q, attempt)

    # Pre-check: reflective, classroom/text-referencing, multi-question, or unanswerable items are rejected
    # before spending a judge call
    if is_reflective_question(q_text):
        return fail("pre_check", "fail (reflective_pattern)",
                    "Soal bersifat reflektif / meta-learning. Ganti dengan fakta/teori/konsep konkret dari buku.")
    clarity_issue = find_clarity_issue(q_text)
    if clarity_issue:
        return fail("pre_check", "fail (unclear_question)", clarity_issue)
    unanswerable = find_unanswerable_answer(q.get("answer", ""))
    if unanswerable:
        return fail("pre_check", "fail (unanswerable)", unanswerable)

    grounding_res = compute_grounding_evidence_score(
        question_text=q_text,
        answer_text=q.get("answer", ""),
        grounding_evidence=q.get("grounding_evidence", ""),
        fallback_chunks=[state["context"]] if state.get("context") else [],
        dense_idx=get_shared_dense_index(),
    )
    g_score = grounding_res["score"]
    threshold = get_settings().FAST_REJECT_THRESHOLD
    aspects = json.dumps({"grounding_similarity": g_score, "target": grounding_res["target"]}, ensure_ascii=False)

    if g_score < threshold:
        return fail(
            "grounding", f"fail (fast_reject score={g_score:.3f})",
            f"Grounding similarity sangat rendah ({g_score:.3f} < {threshold:.2f}). Jawaban tidak selaras dengan materi teks buku.",
            aspects,
        )

    logs.append(_log(
        attempt, "grounding", "pass", f"pass (score={g_score:.3f})",
        f"Lolos Fast-Reject (similarity={g_score:.3f}). Diteruskan ke LLM-as-Judge.",
        aspects,
    ))
    return {"validation_logs": logs, "failed_stage": "none"}


def _target_bloom(state: QuestionState) -> str:
    return state["question"].get("bloom_level") or state.get("session_bloom_level") or "C2-Memahami"


async def llm_judge_evaluation(state: QuestionState) -> dict[str, Any]:
    """Layer 2: LLM-as-Judge across grounding, bloom_adherence, bahasa, answerability, answer_alignment."""
    q = state["question"]
    attempt = state["attempt"]

    judge_eval, judge_trace = await run_llm_judge(
        judge_model=get_chat_model(is_judge=True, temperature=0.05),
        retrieved_context=state.get("context", ""),
        grounding_evidence=q.get("grounding_evidence", ""),
        question=q.get("question", ""),
        expected_answer=q.get("answer", ""),
        explanation=q.get("explanation", ""),
        target_bloom_level=_target_bloom(state),
        attempt=attempt,
    )

    failed_aspects = [
        name for name in _JUDGE_ASPECTS
        if getattr(judge_eval, name).status.lower().strip() != "pass"
    ]
    # The judge sometimes says overall "pass" while an aspect failed; a single failed aspect fails the question
    verdict = "pass" if judge_eval.overall.lower().strip() == "pass" and not failed_aspects else "fail"
    failed_stage = judge_eval.failed_stage.lower().strip() if verdict != "pass" else "none"
    if verdict != "pass" and failed_stage not in ("generation", "planning"):
        failed_stage = "planning" if failed_aspects == ["bloom_adherence"] else "generation"
    logger.info("[Validation] judge overall='%s', failed_stage='%s', failed_aspects=%s (attempt %d)",
                verdict, failed_stage, failed_aspects, attempt)

    feedback_parts = [f"[{name.upper()}] {getattr(judge_eval, name).feedback}" for name in failed_aspects]
    full_feedback = " ; ".join(feedback_parts) if feedback_parts else "Semua aspek evaluasi juri lolos."

    logs = list(state.get("validation_logs", []))
    logs.append(_log(
        attempt, "judge", verdict, f"{verdict} (failed_stage={failed_stage})", full_feedback,
        json.dumps(judge_eval.model_dump(), ensure_ascii=False),
    ))

    return {
        "validation_logs": logs,
        "failed_stage": failed_stage,
        "judge_evaluation": judge_eval.model_dump(),
        "stage_traces": [*state.get("stage_traces", []), judge_trace.model_dump()],
    }


async def self_refinement(state: QuestionState) -> dict[str, Any]:
    """Smart Self-Refinement Router.

    - failed_stage == "planning" -> Refinement Prompt B (re-plans Bloom), then Stage 3 + Stage 4 again.
    - otherwise -> Refinement Prompt A (repairs wording/grounding/explanation).
    """
    attempt = state["attempt"] + 1
    q = dict(state["question"])
    logs = state.get("validation_logs", [])
    last_feedback = logs[-1].get("feedback", "Perbaiki soal agar lebih konkret.") if logs else "Perbaiki soal."
    failed_stage = state.get("failed_stage") or "generation"
    context_str = state.get("context", "")

    logger.info("[Validation] self_refinement attempt %d/%d (failed_stage='%s')", attempt, state["max_attempts"], failed_stage)
    progress.candidate(state.get("session_id"), state.get("candidate_id"), "refining", q, attempt)

    chat_model = get_chat_model(is_judge=False, temperature=0.2)
    curr_traces = list(state.get("stage_traces", []))
    target_bloom = _target_bloom(state)

    c_analysis = ContentAnalysis.model_validate(q.get("content_analysis") or {})
    cog_plan = CognitivePlan.model_validate(q.get("cognitive_plan") or {})
    q_blueprint = QuestionBlueprint.model_validate(q.get("question_blueprint") or {})

    if failed_stage == "planning":
        detected_level = ((state.get("judge_evaluation") or {}).get("bloom_adherence") or {}).get("detected_level") or "Mismatch"
        new_plan, t_ref_b = await run_refinement_b(
            chat_model=chat_model,
            prev_plan=cog_plan,
            question_text=q.get("question", ""),
            validation_feedback=last_feedback,
            detected_level=detected_level,
            target_bloom_level=target_bloom,
            content_analysis=c_analysis,
            attempt=attempt,
        )
        curr_traces.append(t_ref_b.model_dump())

        # Re-run Stage 3 with the new cognitive plan, keeping the same knowledge point
        new_blueprint, t_bp = await run_stage3_question_blueprint(
            chat_model, c_analysis, new_plan, q.get("knowledge_point"), attempt,
        )
        curr_traces.append(t_bp.model_dump())

        new_pkg, t_gen = await run_stage4_question_generation(
            chat_model=chat_model,
            retrieved_context=context_str,
            blueprint=new_blueprint,
            target_bloom_level=target_bloom,
            question_type=new_blueprint.question_type or "esai",
            few_shot_examples=NO_FEW_SHOT,
            attempt=attempt,
        )
        curr_traces.append(t_gen.model_dump())

        q["question_type"] = new_pkg.question_type or new_blueprint.question_type or q.get("question_type", "esai")
        q["grounding_evidence"] = new_pkg.grounding_evidence or new_blueprint.grounding_evidence
        q["cognitive_plan"] = new_plan.model_dump()
        q["question_blueprint"] = new_blueprint.model_dump()
        q["has_fallback"] = q.get("has_fallback") or t_gen.has_fallback
    else:
        new_pkg, t_ref_a = await run_refinement_a(
            chat_model=chat_model,
            question=q.get("question", ""),
            expected_answer=q.get("answer", ""),
            explanation=q.get("explanation", ""),
            blueprint=q_blueprint,
            retrieved_context=context_str,
            validation_feedback=last_feedback,
            target_bloom_level=target_bloom,
            question_type=q.get("question_type", "esai"),
            attempt=attempt,
        )
        curr_traces.append(t_ref_a.model_dump())
        q["grounding_evidence"] = new_pkg.grounding_evidence or q_blueprint.grounding_evidence

    q["question"] = new_pkg.question
    q["answer"] = new_pkg.expected_answer
    q["explanation"] = new_pkg.explanation or q.get("explanation", "")

    return {"question": q, "attempt": attempt, "stage_traces": curr_traces}


def finalize_question(state: QuestionState) -> dict[str, Any]:
    """Set the final status: 'final' only if the last judge verdict passed without fallback stages."""
    q = dict(state["question"])
    logs = state.get("validation_logs", [])
    last = logs[-1] if logs else {}
    passed = last.get("layer") == "judge" and last.get("verdict") == "pass"

    q["status"] = "final" if passed and not q.get("has_fallback") else "needs_review"
    q["refinement_count"] = state["attempt"] - 1
    logger.info("[Validation] finalize '%s' -> %s after %d attempt(s)", q.get("question", "")[:50], q["status"], state["attempt"])
    return {"question": q}
