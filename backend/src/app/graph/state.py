"""State schema definitions for Multi-Stage LangGraph AQG pipeline."""

import operator
from typing import Annotated, Any, TypedDict


class AQGState(TypedDict):
    """Session-level state: retrieval, candidate generation, fan-out validation, persistence."""

    # ── Request / Input Parameters ──
    session_id: str
    document_id: str
    user_prompt: str
    chapter: str | None
    bloom_level: str | None
    num_questions: int

    # ── Context / Retrieved Chunks ──
    retrieved_chunks: list[dict[str, Any]]  # chunk budget follows num_questions; one chunk may yield several questions
    reserve_chunks: list[dict[str, Any]]  # next-ranked chunks, analysed only if the top-up round needs new points
    source_chunk_ids: list[str]

    # ── Multi-Stage Generation Artifacts ──
    raw_questions: list[dict[str, Any]]  # candidates of the current validation round
    spare_items: list[dict[str, Any]]  # unused (knowledge point, chunk) specs for top-up
    stage_cache: dict[str, Any]  # shared Stage 1/2 outputs + traces reused by the top-up round
    top_up_done: bool

    # ── Fan-in of per-question validation results (each item carries its own logs & traces) ──
    validated_questions: Annotated[list[dict[str, Any]], operator.add]
    finalized_questions: list[dict[str, Any]]

    # ── Errors / Diagnostics ──
    error: str | None


class QuestionState(TypedDict):
    """Per-question validation state. Isolated per candidate, so logs/traces never leak across questions."""

    question: dict[str, Any]
    context: str  # material the generator used; judge & refinement see the same text
    session_bloom_level: str | None
    attempt: int
    max_attempts: int
    failed_stage: str  # "generation" / "planning" / "none"
    judge_evaluation: dict[str, Any] | None
    validation_logs: list[dict[str, Any]]
    stage_traces: list[dict[str, Any]]
