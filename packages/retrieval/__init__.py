"""Citable, workspace-scoped retrieval boundary."""

from .citations import CitationValidator
from .contracts import (
    AuthorizationStatus,
    Citation,
    ClaimKind,
    DocumentStatus,
    KnowledgeChunk,
    ReportClaim,
    RetrievalFilters,
    SourceRegistration,
)
from .embeddings import DeterministicHashEmbeddingAdapter, LexicalOverlapReranker
from .ingestion import KnowledgeIngestionService
from .parsing import DocumentParser, HierarchicalChunker
from .registry import InMemoryKnowledgeRepository
from .security import GroundedPromptBuilder, ToolAuthorizationPolicy
from .service import RetrievalService
from .sql_repository import SqlKnowledgeRepository
from .stores import InMemoryVectorStore, PgVectorStore

__all__ = [
    "AuthorizationStatus",
    "Citation",
    "CitationValidator",
    "ClaimKind",
    "DeterministicHashEmbeddingAdapter",
    "DocumentParser",
    "DocumentStatus",
    "GroundedPromptBuilder",
    "HierarchicalChunker",
    "InMemoryKnowledgeRepository",
    "InMemoryVectorStore",
    "KnowledgeChunk",
    "KnowledgeIngestionService",
    "LexicalOverlapReranker",
    "PgVectorStore",
    "ReportClaim",
    "RetrievalFilters",
    "RetrievalService",
    "SourceRegistration",
    "SqlKnowledgeRepository",
    "ToolAuthorizationPolicy",
]
