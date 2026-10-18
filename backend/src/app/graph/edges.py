"""Routing and conditional edges for the AQG LangGraph StateGraphs."""

import logging

from app.graph.state import AQGState, QuestionState

logger = logging.getLogger(__name__)


# ── Per-question validation subgraph ──

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


# ── Session graph ──

def route_after_generation(state: AQGState) -> str:
    """Review the validated candidates, or stop when generation produced none (the error explains why)."""
    from langgraph.graph import END

    if state.get("validated_questions"):
        return "review_results"
    logger.warning("[Edge] No candidate questions generated -> END")
    return END


def route_after_review(state: AQGState) -> str:
    """Top up once if fewer questions passed than requested, otherwise persist."""
    validated = state.get("validated_questions", [])
    n_final = sum(1 for q in validated if q.get("status") == "final")
    if n_final < state.get("num_questions", 5) and not state.get("top_up_done"):
        logger.info("[Edge] %d/%d passed -> top_up_questions", n_final, state.get("num_questions", 5))
        return "top_up_questions"
    return "persist_questions"
