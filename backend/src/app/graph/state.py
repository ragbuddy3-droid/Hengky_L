"""State schema definition for LangGraph AQG pipeline."""

from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator


class AQGState(TypedDict):
    """Complete state representation for the question generation and validation graph."""

    # ── Request / Input Parameters ──
    session_id: str
    document_id: str
    user_prompt: str
    chapter: Optional[str]
    bloom_level: Optional[str]
    num_questions: int

    # ── Context / Retrieved Chunks ──
    retrieved_chunks: List[Dict[str, Any]]
    source_chunk_ids: List[str]
    chat_history: str

    # ── Generation Candidates ──
    raw_questions: List[Dict[str, Any]]

    # ── Question Validation Tracking ──
    current_q_index: int
    current_question: Dict[str, Any]
    current_attempt: int
    max_attempts: int

    # ── Accumulated Artifacts ──
    validation_logs: Annotated[List[Dict[str, Any]], operator.add]
    finalized_questions: Annotated[List[Dict[str, Any]], operator.add]

    # ── Errors / Diagnostics ──
    error: Optional[str]
