"""StateGraph assembly and compilation for RAG-AQG workflow."""

import logging
from langgraph.graph import StateGraph, END
from app.graph.state import AQGState
from app.graph.nodes import (
    retrieve_context,
    generate_questions,
    grounding_validation,
    llm_judge_evaluation,
    self_refinement,
    persist_questions,
)
from app.graph.edges import (
    route_after_generation,
    route_after_grounding,
    route_after_judge,
    route_after_persist,
)

logger = logging.getLogger(__name__)

_aqg_graph = None


def build_aqg_graph():
    """Construct and compile the AQG StateGraph."""
    logger.info("Building LangGraph AQG StateGraph workflow...")

    graph = StateGraph(AQGState)

    # 1. Add Nodes
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_questions", generate_questions)
    graph.add_node("grounding_validation", grounding_validation)
    graph.add_node("llm_judge_evaluation", llm_judge_evaluation)
    graph.add_node("self_refinement", self_refinement)
    graph.add_node("persist_questions", persist_questions)

    # 2. Add Fixed Edges
    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "generate_questions")
    graph.add_edge("self_refinement", "grounding_validation")

    # 3. Add Conditional Edges
    graph.add_conditional_edges(
        "generate_questions",
        route_after_generation,
        {
            "grounding_validation": "grounding_validation",
            END: END,
        }
    )

    graph.add_conditional_edges(
        "grounding_validation",
        route_after_grounding,
        {
            "persist_questions": "persist_questions",
            "llm_judge_evaluation": "llm_judge_evaluation",
            "self_refinement": "self_refinement",
        }
    )

    graph.add_conditional_edges(
        "llm_judge_evaluation",
        route_after_judge,
        {
            "persist_questions": "persist_questions",
            "self_refinement": "self_refinement",
        }
    )

    graph.add_conditional_edges(
        "persist_questions",
        route_after_persist,
        {
            "grounding_validation": "grounding_validation",
            END: END,
        }
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
