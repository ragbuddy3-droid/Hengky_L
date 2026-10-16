"""Pydantic schemas for API interactions with Multi-Stage AQG support."""

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

GenerationStatus = Literal["idle", "running", "done", "failed"]


def as_utc(v: datetime | None) -> datetime | None:
    """SQLite menyimpan DateTime tanpa zona waktu; nilai di DB selalu UTC (lihat `utcnow`)."""
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=UTC)
    return v


class DocumentUploadResponse(BaseModel):
    id: str
    status: str
    message: str = "Dokumen berhasil diunggah dan pemrosesan dimulai."

    model_config = ConfigDict(from_attributes=True)


class DocumentStatusResponse(BaseModel):
    id: str
    subject: str
    status: str
    filename: str
    chunking_strategy: str | None = "fixed"
    created_at: str | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatSessionCreate(BaseModel):
    document_id: str


class ChatSessionResponse(BaseModel):
    id: str
    document_id: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatSessionListItem(BaseModel):
    id: str
    document_id: str
    document_filename: str | None = None
    message_count: int = 0
    last_message_snippet: str | None = None
    created_at: str | None = None
    generation_status: GenerationStatus = "idle"
    generation_count: int | None = None
    generation_message_id: str | None = None


class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", mode="after")
    def ensure_utc(cls, v: datetime | None) -> datetime | None:
        return as_utc(v)


class GenerateParams(BaseModel):
    num_questions: int = 5
    chapter: str | None = None
    bloom_level: str | None = None


class QuestionOption(BaseModel):
    label: str
    text: str


class UsedChunkResponse(BaseModel):
    id: str
    document_id: str
    text: str
    category: str
    section_heading: str | None = None
    chapter: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    section_type: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RubricCriterionResponse(BaseModel):
    score: int
    criteria: str


class AnswerElementResponse(BaseModel):
    element: str
    weight: int | float = 1


class PromptTraceItemResponse(BaseModel):
    stage_name: str
    step_number: int = 1
    attempt_number: int = 1
    prompt_sent: str
    raw_response: str
    parsed_output: dict[str, Any] | None = None
    latency_ms: int = 0
    status: str = "success"
    error_message: str | None = None


class ValidationLogResponse(BaseModel):
    id: str
    attempt_number: int
    layer: str
    score_or_verdict: str
    feedback: str | None = None
    aspect_evaluations: dict[str, Any] | str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("aspect_evaluations", mode="before")
    def parse_aspect_evaluations(cls, v):
        if not v:
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {"raw": v}
        return v


class QuestionResponse(BaseModel):
    id: str
    session_id: str | None = None
    document_id: str | None = None
    document_filename: str | None = None
    question_type: str = "esai"
    question_text: str
    options: list[QuestionOption] | None = []
    answer_key: str
    explanation: str | None = None
    source_reference: str | None = None
    bloom_level: str
    status: str
    refinement_count: int
    knowledge_point: str | None = None
    grounding_evidence: str | None = None
    rubric: list[RubricCriterionResponse] | None = []
    answer_elements: list[AnswerElementResponse] | None = []
    source_chunks: list[str] = Field(default=[], validation_alias="chunk_ids")
    used_chunks: list[UsedChunkResponse] = []
    quality_warnings: list[str] | None = []

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("quality_warnings", mode="before")
    def parse_quality_warnings(cls, v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return [str(x) for x in parsed] if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return v if isinstance(v, list) else []

    @field_validator("options", mode="before")
    def parse_options(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return [{"label": k, "text": str(val)} for k, val in parsed.items()]
                if isinstance(parsed, list):
                    return parsed
                return []
            except json.JSONDecodeError:
                return []
        return v

    @field_validator("rubric", mode="before")
    def parse_rubric(cls, v: Any) -> list[Any]:
        if not v:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return v if isinstance(v, list) else []

    @field_validator("answer_elements", mode="before")
    def parse_answer_elements(cls, v: Any) -> list[Any]:
        if not v:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return v if isinstance(v, list) else []

    @field_validator("source_chunks", mode="before")
    def parse_source_chunks(cls, v: Any) -> list[Any]:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return v if isinstance(v, list) else []


class QuestionListResponse(BaseModel):
    questions: list[QuestionResponse]
    total: int


class QuestionDetailResponse(BaseModel):
    id: str
    session_id: str
    question_type: str = "esai"
    question_text: str
    options: dict[str, Any] | list[Any] | None = None
    answer_key: str
    explanation: str | None = None
    source_reference: str | None = None
    bloom_level: str
    status: str
    refinement_count: int
    knowledge_point: str | None = None
    grounding_evidence: str | None = None
    rubric: list[RubricCriterionResponse] | None = []
    answer_elements: list[AnswerElementResponse] | None = []
    prompt_traces: list[PromptTraceItemResponse] | None = []
    validation_logs: list[ValidationLogResponse] = []
    used_chunks: list[UsedChunkResponse] = []
    quality_warnings: list[str] | None = []

    model_config = ConfigDict(from_attributes=True)

    @field_validator("quality_warnings", mode="before")
    def parse_quality_warnings_detail(cls, v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return [str(x) for x in parsed] if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return v if isinstance(v, list) else []

    @field_validator("rubric", mode="before")
    def parse_rubric_detail(cls, v: Any) -> list[Any]:
        if not v:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return v if isinstance(v, list) else []

    @field_validator("answer_elements", mode="before")
    def parse_answer_elements_detail(cls, v: Any) -> list[Any]:
        if not v:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return v if isinstance(v, list) else []

    @field_validator("prompt_traces", mode="before")
    def parse_prompt_traces_detail(cls, v: Any) -> list[Any]:
        if not v:
            return []
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError, ValueError):
                return []
        return v if isinstance(v, list) else []



class GenerateRequest(BaseModel):
    num_questions: int = 5
    chapter: str | None = None
    bloom_level: str | None = None


class ErrorResponse(BaseModel):
    detail: str
