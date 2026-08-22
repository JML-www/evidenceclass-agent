"""Pydantic request/response contracts for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
