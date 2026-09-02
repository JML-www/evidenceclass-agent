"""Pydantic request/response contracts for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictSchema):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=512)


class LoginResponse(StrictSchema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user_id: UUID
    workspace_id: UUID | None = None


class CreateJobRequest(StrictSchema):
    mode: Literal["image", "video", "structured"]
    goal: str = Field(default="analyze classroom evidence", min_length=1, max_length=2_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobResponse(StrictSchema):
    job_id: UUID
    workspace_id: UUID
    mode: str
    status: str
    progress: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class StartResponse(StrictSchema):
    job_id: UUID
    run_id: UUID
    job_status: str
    run_status: str
    task_id: str | None = None


class UploadInitRequest(StrictSchema):
    expected_mime: str
    max_size_bytes: int = Field(gt=0, le=500 * 1024 * 1024)
    role: str = Field(default="source", min_length=1, max_length=48)


class UploadInitResponse(StrictSchema):
    upload_id: UUID
    object_key: str
    upload_url: str
    expected_mime: str
    max_size_bytes: int
    expires_at: datetime


class UploadCompleteRequest(StrictSchema):
    expected_size_bytes: int = Field(ge=0)
    expected_sha256: str = Field(min_length=64, max_length=64)


class AssetResponse(StrictSchema):
    asset_id: UUID
    role: str
    mime: str
    size_bytes: int
    sha256: str
    download_url: str | None = None


class EventResponse(StrictSchema):
    event_id: int
    type: str
    job_id: UUID
    run_id: UUID | None = None
    stage: str | None = None
    progress: int
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class ReviewDecisionRequest(StrictSchema):
    decision: Literal["APPROVED", "REJECTED", "MODIFIED", "MATERIALS_REQUESTED"]
    note: str = ""
    revised_observation: dict[str, Any] | None = None


class KnowledgeDocumentRequest(StrictSchema):
    source_id: str
    source: str
    title: str
    author_or_organization: str
    license: str
    authorization_status: str
    sha256: str
    visibility_scope: str = "workspace"
    version: str = "1.0"
    status: str = "REGISTERED"


class ConversationRequest(StrictSchema):
    title: str = Field(min_length=1, max_length=255)
    job_id: UUID | None = None


class MessageRequest(StrictSchema):
    content: str = Field(min_length=1, max_length=10_000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message content cannot be blank")
        return value


class CitationResponse(StrictSchema):
    """A citation attached to an assistant answer.

    Evidence citations use ``evidence_id``; knowledge citations additionally
    carry the source document/chunk metadata.  Keeping both forms in one
    contract lets the UI render a single, clickable citation chip.
    """

    evidence_id: str | None = None
    citation_id: str | None = None
    source_ref: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    page: int | None = None
    version: str | None = None
    fact: str | None = None
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def citation_must_have_reference(self) -> CitationResponse:
        if not self.evidence_id and not self.citation_id:
            raise ValueError("citation must include evidence_id or citation_id")
        return self


class BoundaryResponse(StrictSchema):
    workspace_id: UUID
    job_id: UUID | None = None
    conversation_id: UUID
    allowed_sources: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class MessageResponse(StrictSchema):
    message_id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    citations: list[CitationResponse] = Field(default_factory=list)
    evidence_available: bool = False
    source: str | None = None
    limitations: list[str] = Field(default_factory=list)
    boundary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AnswerResponse(StrictSchema):
    conversation_id: UUID
    user_message: MessageResponse
    assistant_message: MessageResponse
    answer: str
    citations: list[CitationResponse] = Field(default_factory=list)
    evidence_available: bool
    source: str
    limitations: list[str] = Field(default_factory=list)
    boundary: BoundaryResponse
    summary_version: int = 0


class ConversationResponse(StrictSchema):
    conversation_id: UUID
    workspace_id: UUID
    job_id: UUID | None = None
    title: str
    summary_version: int = 0
    summary: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConversationSummaryResponse(StrictSchema):
    conversation_id: UUID
    version: int
    summary: str
    summary_hash: str
    updated_at: datetime
    source_message_start: UUID | None = None
    source_message_end: UUID | None = None
    boundary: BoundaryResponse


class FeedbackRequest(StrictSchema):
    decision: Literal["APPROVED", "REJECTED", "MODIFIED", "MATERIALS_REQUESTED"]
    reason: str = Field(min_length=1, max_length=10_000)
    original_observation: dict[str, Any] = Field(default_factory=dict)
    revised_observation: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ReviewItemResponse(StrictSchema):
    review_id: UUID
    job_id: UUID
    status: str
    decision: str | None = None
    reason: str
    reviewer_id: str | None = None
    revision: int
    original_observation: dict[str, Any] = Field(default_factory=dict)
    revised_observation: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    decided_at: datetime | None = None


class ReviewStatsResponse(StrictSchema):
    total: int
    pending: int
    decided: int
    by_decision: dict[str, int] = Field(default_factory=dict)
