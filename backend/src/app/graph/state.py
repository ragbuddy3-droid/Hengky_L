"""State schema definition for Multi-Stage LangGraph AQG pipeline."""

import operator
from typing import Annotated, Any, TypedDict


class AQGState(TypedDict):
    """Complete state representation for Multi-Stage question generation and validation graph."""

    # ── Request / Input Parameters ──
    session_id: str
    document_id: str
    user_prompt: str
    chapter: str | None
    bloom_level: str | None
    num_questions: int

    # ── Context / Retrieved Chunks ──
    retrieved_chunks: list[dict[str, Any]]
    source_chunk_ids: list[str]
    chat_history: str

    # ── Multi-Stage Generation Artifacts ──
    content_analysis: dict[str, Any]
    cognitive_plan: dict[str, Any]
    question_blueprint: dict[str, Any]
    raw_questions: list[dict[str, Any]]

    # ── Question Validation Tracking ──
    current_q_index: int
    current_question: dict[str, Any]
    current_attempt: int
    max_attempts: int
    failed_stage: str | None  # "generation" / "planning" / "none"
    judge_evaluation: dict[str, Any] | None

    # ── Stage Execution Traces & Logs ──
    stage_traces: list[dict[str, Any]]
    validation_logs: Annotated[list[dict[str, Any]], operator.add]
    finalized_questions: Annotated[list[dict[str, Any]], operator.add]

    # ── Errors / Diagnostics ──
    error: str | None
