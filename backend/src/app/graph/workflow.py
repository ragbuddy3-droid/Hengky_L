"""StateGraph assembly and compilation for RAG-AQG workflow."""

import logging

from langgraph.graph import END, StateGraph

from app.graph.edges import (
    route_after_generation,
    route_after_grounding,
    route_after_judge,
    route_after_review,
)
from app.graph.nodes import (
    finalize_question,
    generate_questions,
    grounding_validation,
    llm_judge_evaluation,
    persist_questions,
    retrieve_context,
    review_results,
    self_refinement,
    top_up_questions,
)
from app.graph.state import AQGState, QuestionState

logger = logging.getLogger(__name__)

_aqg_graph = None
_validation_graph = None


def build_validation_graph():
    """Per-question loop: Layer 1 grounding -> Layer 2 judge <-> self-refinement -> finalize."""
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


def build_aqg_graph():
    """Session graph: retrieve -> generate (each question validated as soon as it is written) -> (top-up once) -> persist."""
    logger.info("Building LangGraph AQG StateGraph workflow...")

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

    graph.add_conditional_edges(
        "review_results",
        route_after_review,
        ["top_up_questions", "persist_questions"],
    )

    compiled = graph.compile()
    logger.info("LangGraph AQG StateGraph compiled successfully.")
    return compiled


def get_aqg_graph():
    """Retrieve singleton compiled LangGraph instance."""
    global _aqg_graph
    if _aqg_graph is None:
        _aqg_graph = build_aqg_graph()
    return _aqg_graph


def get_validation_graph():
    """Retrieve singleton compiled per-question validation graph."""
    global _validation_graph
    if _validation_graph is None:
        _validation_graph = build_validation_graph()
    return _validation_graph
