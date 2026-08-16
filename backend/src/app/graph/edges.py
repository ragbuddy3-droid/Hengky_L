"""Routing and conditional edges for the AQG LangGraph StateGraph."""

import logging

from langgraph.graph import END

from app.graph.state import AQGState

logger = logging.getLogger(__name__)


def route_after_generation(state: AQGState) -> str:
    """Route after generation: proceed to grounding_validation if questions exist, else END."""
    raw_qs = state.get("raw_questions", [])
    current_q = state.get("current_question", {})
    if not raw_qs or not current_q or not current_q.get("question"):
        logger.warning("[Edge] No raw candidate questions generated -> END")
        return END
    logger.info("[Edge] Questions generated successfully (%d candidates) -> grounding_validation", len(raw_qs))
    return "grounding_validation"


def route_after_grounding(state: AQGState) -> str:
    """Route question based on Layer 1 Grounding Validation result."""
    logs = state.get("validation_logs", [])
    if not logs:
        return "self_refinement"

    last_log = logs[-1]
    verdict = last_log.get("verdict", "fail")
    attempt = state.get("current_attempt", 1)
    max_attempts = state.get("max_attempts", 3)

    if verdict == "auto_pass":
        logger.info("[Edge] Grounding auto-pass -> persist_questions")
        return "persist_questions"
    elif verdict == "pass":
        logger.info("[Edge] Grounding pass -> llm_judge_evaluation")
        return "llm_judge_evaluation"
    else:
        if attempt >= max_attempts:
            logger.info("[Edge] Grounding fail and attempts exhausted (%d/%d) -> persist_questions", attempt, max_attempts)
            return "persist_questions"
        logger.info("[Edge] Grounding fail -> self_refinement")
        return "self_refinement"


def route_after_judge(state: AQGState) -> str:
    """Route question based on Layer 2 LLM Judge evaluation result."""
    logs = state.get("validation_logs", [])
    if not logs:
        return "self_refinement"

    last_log = logs[-1]
    verdict = last_log.get("verdict", "fail")
    attempt = state.get("current_attempt", 1)
    max_attempts = state.get("max_attempts", 3)

    if verdict == "pass":
        logger.info("[Edge] Judge pass -> persist_questions")
        return "persist_questions"
    else:
        if attempt >= max_attempts:
            logger.info("[Edge] Judge fail and attempts exhausted (%d/%d) -> persist_questions", attempt, max_attempts)
            return "persist_questions"
        logger.info("[Edge] Judge fail -> self_refinement")
        return "self_refinement"


def route_after_persist(state: AQGState) -> str:
    """Check whether there are remaining candidate questions to validate."""
    current_idx = state.get("current_q_index", 0)
    raw_qs = state.get("raw_questions", [])

    if current_idx < len(raw_qs):
        logger.info("[Edge] Next question (%d/%d) -> grounding_validation", current_idx + 1, len(raw_qs))
        return "grounding_validation"

    logger.info("[Edge] All %d questions processed -> END", len(raw_qs))
    return END
