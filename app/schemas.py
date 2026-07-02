"""
Pydantic schemas for request/response validation.
"""

from typing import List, Optional
from enum import Enum

from pydantic import BaseModel, Field, field_validator


# ── Enums ──

class FileType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"


class JobType(str, Enum):
    INDEX = "INDEX"
    SUMMARY = "SUMMARY"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


class AIStatus(str, Enum):
    INDEXING = "INDEXING"
    CHAT_READY = "CHAT_READY"
    READY = "READY"
    FAILED = "FAILED"


# ── Health ──

class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "microservice-social-learn-ai"


# ── Document Indexing ──

class DocumentIndexRequest(BaseModel):
    post_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    file_url: str = Field(..., min_length=1)
    file_type: FileType
    file_name: str = Field(..., min_length=1)


class DocumentIndexResponse(BaseModel):
    job_id: str
    post_id: str
    status: str = "PENDING"
    message: str = "Document index job created"


# ── Summary ──

class SummaryRequest(BaseModel):
    post_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)


class SummaryJobResponse(BaseModel):
    job_id: str
    post_id: str
    status: str = "PENDING"
    message: str = "Summary job created"


# ── Chat ──

class Citation(BaseModel):
    page_number: Optional[int] = None
    chunk_index: int
    content_preview: str


class ChatRequest(BaseModel):
    post_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=3, ge=1, le=5)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Question must not be blank")
        return v.strip()


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = []