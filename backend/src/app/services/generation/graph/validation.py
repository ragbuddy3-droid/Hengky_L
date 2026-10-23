"""Per-question validation subgraph (QuestionState).

grounding_validation -> llm_judge_evaluation <-> self_refinement -> finalize_question. Each candidate runs its
own isolated copy, so validation logs and prompt traces never leak across questions.
"""

import functools
import json
import logging
from typing import Any

from langgraph.graph import END, StateGraph

from app.core.config import get_settings
from app.services.generation import progress
from app.services.generation.graph.state import QuestionState
from app.services.generation.planner import (
    NO_FEW_SHOT,
)
from app.services.generation.schemas import CognitivePlan, ContentAnalysis, QuestionBlueprint
from app.services.generation.stage_runners import (
    run_llm_judge,
    run_refinement_a,
    run_refinement_b,
    run_stage3_question_blueprint,
    run_stage4_question_generation,
)
from app.services.llm import get_chat_model
from app.services.retrieval.retriever import get_shared_dense_index
from app.services.validation.grounding_checker import compute_grounding_evidence_score
from app.services.validation.quality_checks import (
    find_book_navigation_issue,
    find_clarity_issue,
    find_unanswerable_answer,
    is_reflective_question,
)

logger = logging.getLogger(__name__)

_JUDGE_ASPECTS = ["grounding", "bloom_adherence", "bahasa", "answerability", "answer_alignment"]


# ── Entry points ──

def validation_input(
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
        "max_attempts": get_settings().validation.max_refinement_attempts,
        "failed_stage": "none",
        "judge_evaluation": None,
        "validation_logs": [],
        "stage_traces": list(q.get("stage_traces", [])),
    }


async def validate_candidate(state: QuestionState) -> dict[str, Any]:
    """Run the per-question validation subgraph; the result carries its own logs and traces."""
    result = await get_validation_graph().ainvoke(state)
    q = dict(result["question"])
    q["validation_logs"] = result.get("validation_logs", [])
    q["stage_traces"] = result.get("stage_traces", [])
    return q


# ── Nodes ──

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
    navigation_issue = find_book_navigation_issue(q_text, q.get("answer", ""))
    if navigation_issue:
        return fail("pre_check", "fail (book_navigation)", navigation_issue)

    grounding_res = compute_grounding_evidence_score(
        question_text=q_text,
        answer_text=q.get("answer", ""),
        grounding_evidence=q.get("grounding_evidence", ""),
        fallback_chunks=[state["context"]] if state.get("context") else [],
        dense_idx=get_shared_dense_index(),
    )
    g_score = grounding_res["score"]
    threshold = get_settings().validation.fast_reject_threshold
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


# ── Routing ──

def route_after_grounding(state: QuestionState) -> str:
    """Route based on the Layer 1 (pre-check / Fast-Reject grounding) result."""
    logs = state.get("validation_logs", [])
    if logs and logs[-1].get("verdict") == "pass":
        return "llm_judge_evaluation"
    if state["attempt"] >= state["max_attempts"]:
        logger.info("[Edge] Layer 1 fail, attempts exhausted (%d/%d) -> finalize", state["attempt"], state["max_attempts"])
        return "finalize_question"
    return "self_refinement"


def route_after_judge(state: QuestionState) -> str:
    """Route based on the Layer 2 LLM Judge result."""
    logs = state.get("validation_logs", [])
    if logs and logs[-1].get("verdict") == "pass":
        return "finalize_question"
    if state["attempt"] >= state["max_attempts"]:
        logger.info("[Edge] Judge fail, attempts exhausted (%d/%d) -> finalize", state["attempt"], state["max_attempts"])
        return "finalize_question"
    return "self_refinement"


@functools.cache
def get_validation_graph():
    """Compiled per-question loop: Layer 1 grounding -> Layer 2 judge <-> self-refinement -> finalize."""
    graph = StateGraph(QuestionState)

    graph.add_node("grounding_validation", grounding_validation)
    graph.add_node("llm_judge_evaluation", llm_judge_evaluation)
    graph.add_node("self_refinement", self_refinement)
    graph.add_node("finalize_question", finalize_question)

    graph.set_entry_point("grounding_validation")
    graph.add_edge("self_refinement", "grounding_validation")
    graph.add_edge("finalize_question", END)

    graph.add_conditional_edges(
        "grounding_validation",
        route_after_grounding,
        ["llm_judge_evaluation", "self_refinement", "finalize_question"],
    )
    graph.add_conditional_edges(
        "llm_judge_evaluation",
        route_after_judge,
        ["self_refinement", "finalize_question"],
    )
    return graph.compile()
