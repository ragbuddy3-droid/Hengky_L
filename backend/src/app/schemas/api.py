"""Pydantic schemas for API interactions."""

import json
from datetime import datetime
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    chunking_strategy: Optional[str] = "structured"
    created_at: Optional[str] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ChatSessionCreate(BaseModel):
    document_id: str


class ChatSessionResponse(BaseModel):
    id: str
    document_id: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ChatSessionListItem(BaseModel):
    id: str
    document_id: str
    document_filename: Optional[str] = None
    message_count: int = 0
    last_message_snippet: Optional[str] = None
    created_at: Optional[str] = None


class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GenerateParams(BaseModel):
    num_questions: int = 5
    chapter: Optional[str] = None
    bloom_level: Optional[str] = None


class QuestionOption(BaseModel):
    label: str
    text: str


class UsedChunkResponse(BaseModel):
    id: str
    document_id: str
    text: str
    category: str
    section_heading: Optional[str] = None
    chapter: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class QuestionResponse(BaseModel):
    id: str
    question_type: str = "esai"
    question_text: str
    options: Optional[List[QuestionOption]] = []
    answer_key: str
    explanation: Optional[str] = None
    source_reference: Optional[str] = None
    bloom_level: str
    status: str
    refinement_count: int
    source_chunks: List[str] = Field(default=[], validation_alias="chunk_ids")
    used_chunks: List[UsedChunkResponse] = []

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

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

    @field_validator("source_chunks", mode="before")
    def parse_source_chunks(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v


class QuestionListResponse(BaseModel):
    questions: List[QuestionResponse]
    total: int


class ValidationLogResponse(BaseModel):
    id: str
    attempt_number: int
    layer: str
    score_or_verdict: str
    feedback: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class QuestionDetailResponse(BaseModel):
    id: str
    session_id: str
    question_type: str = "esai"
    question_text: str
    options: Optional[Union[Dict[str, Any], List[Any]]] = None
    answer_key: str
    explanation: Optional[str] = None
    source_reference: Optional[str] = None
    bloom_level: str
    status: str
    refinement_count: int
    validation_logs: List[ValidationLogResponse] = []
    used_chunks: List[UsedChunkResponse] = []



class GenerateRequest(BaseModel):
    num_questions: int = 5
    chapter: Optional[str] = None
    bloom_level: Optional[str] = None


class ErrorResponse(BaseModel):
    detail: str

