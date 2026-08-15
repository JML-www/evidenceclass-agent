"""Strict contracts for source registration, retrieval, and citation publication."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, field_validator

RETRIEVAL_SCHEMA_VERSION = "retrieval.v0.1"
EMBEDDING_DIMENSIONS = 384


class RetrievalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class AuthorizationStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    UNKNOWN = "UNKNOWN"
    DENIED = "DENIED"


class DocumentStatus(str, Enum):
    REGISTERED = "REGISTERED"
    PARSED = "PARSED"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"


class VisibilityScope(str, Enum):
    WORKSPACE = "WORKSPACE"


class SourceRegistration(RetrievalModel):
    document_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    source_uri: str = Field(min_length=1, max_length=1024)
    title: str = Field(min_length=1, max_length=255)
    author_or_organization: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=64)
    published_on: date | None = None
    license_name: str = Field(min_length=1, max_length=255)
    authorization_status: AuthorizationStatus
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visibility_scope: VisibilityScope = VisibilityScope.WORKSPACE

    @field_validator(
        "document_id",
        "workspace_id",
        "source_id",
        "source_uri",
        "title",
        "author_or_organization",
        "version",
        "license_name",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source registration text cannot be blank")
        return stripped


class KnowledgeDocumentRecord(RetrievalModel):
    registration: SourceRegistration
    status: DocumentStatus = DocumentStatus.REGISTERED
    parser_version: str | None = None
    parse_error: str | None = None


class ParsedSection(RetrievalModel):
    page: PositiveInt | None = None
    heading: str = Field(min_length=1)
    content: str = Field(min_length=1)


class KnowledgeChunk(RetrievalModel):
    chunk_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=128)
    source_uri: str = Field(min_length=1, max_length=1024)
    title: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=64)
    page: PositiveInt | None = None
    heading: str = Field(min_length=1)
    ordinal: NonNegativeInt
    content: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    token_count: PositiveInt
    embedding: list[float] | None = None

    @field_validator("embedding")
    @classmethod
    def validate_embedding(cls, value: list[float] | None) -> list[float] | None:
        if value is not None and len(value) != EMBEDDING_DIMENSIONS:
            raise ValueError(f"embedding must have {EMBEDDING_DIMENSIONS} dimensions")
        return value


class RetrievalFilters(RetrievalModel):
    workspace_id: str = Field(min_length=1, max_length=128)
    source_ids: list[str] = Field(default_factory=list)
    versions: list[str] = Field(default_factory=list)


class StructuredQuery(RetrievalModel):
    rewrite_version: str = Field(min_length=1, max_length=64)
    original: str = Field(min_length=1)
    normalized: str = Field(min_length=1)
    terms: list[str] = Field(min_length=1)
    filters: RetrievalFilters


class ScoredChunk(RetrievalModel):
    chunk: KnowledgeChunk
    vector_score: float = Field(ge=-1.0, le=1.0)
    rerank_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @property
    def effective_score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.vector_score


class RetrievedContext(RetrievalModel):
    chunk: KnowledgeChunk
    score: float
    presented_content: str = Field(min_length=1)
    included_tokens: PositiveInt
    truncated: bool = False


class RetrievalResult(RetrievalModel):
    schema_version: str = RETRIEVAL_SCHEMA_VERSION
    query: StructuredQuery
    candidate_chunk_ids: list[str]
    contexts: list[RetrievedContext]
    context_tokens: NonNegativeInt
    duplicates_dropped: NonNegativeInt = 0
    budget_dropped: NonNegativeInt = 0


class Citation(RetrievalModel):
    chunk_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    page: PositiveInt | None = None
    version: str = Field(min_length=1, max_length=64)


class ClaimKind(str, Enum):
    KNOWLEDGE = "KNOWLEDGE"
    OBSERVATION = "OBSERVATION"
    METRIC = "METRIC"


class ReportClaim(RetrievalModel):
    claim_id: str = Field(min_length=1, max_length=128)
    kind: ClaimKind
    text: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)


class CitationValidationResult(RetrievalModel):
    publishable: bool
    checked_claims: NonNegativeInt
    errors: list[str] = Field(default_factory=list)
