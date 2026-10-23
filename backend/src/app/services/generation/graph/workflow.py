"""Session-level StateGraph: retrieve -> generate (each question validated as soon as it is written) -> (top-up once) -> persist."""

import functools
import logging

from langgraph.graph import END, StateGraph

from app.services.generation.graph.session_nodes import (
    generate_questions,
    persist_questions,
    retrieve_context,
    review_results,
    top_up_questions,
)
from app.services.generation.graph.state import AQGState, count_final

logger = logging.getLogger(__name__)


def route_after_generation(state: AQGState) -> str:
    """Review the validated candidates, or stop when generation produced none (the error explains why)."""
    if state.get("validated_questions"):
        return "review_results"
    logger.warning("[Edge] No candidate questions generated -> END")
    return END


def route_after_review(state: AQGState) -> str:
    """Top up once if fewer questions passed than requested, otherwise persist."""
    n_final = count_final(state.get("validated_questions", []))
    if n_final < state.get("num_questions", 5) and not state.get("top_up_done"):
        logger.info("[Edge] %d/%d passed -> top_up_questions", n_final, state.get("num_questions", 5))
        return "top_up_questions"
    return "persist_questions"


def build_aqg_graph():
    logger.debug("Building LangGraph AQG StateGraph workflow...")
    graph = StateGraph(AQGState)

    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_questions", generate_questions)
    graph.add_node("review_results", review_results)
    graph.add_node("top_up_questions", top_up_questions)
    graph.add_node("persist_questions", persist_questions)

    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "generate_questions")
    graph.add_conditional_edges("generate_questions", route_after_generation, ["review_results", END])
    graph.add_edge("top_up_questions", "review_results")
    graph.add_edge("persist_questions", END)
    graph.add_conditional_edges("review_results", route_after_review, ["top_up_questions", "persist_questions"])

    compiled = graph.compile()
    logger.info("LangGraph AQG StateGraph compiled successfully.")
    return compiled


@functools.cache
def get_aqg_graph():
    """Compiled session graph, built once."""
    return build_aqg_graph()
