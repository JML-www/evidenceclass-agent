"""In-memory and pgvector Top-K stores with metadata filtering before scoring."""

from __future__ import annotations

import math
from typing import Protocol
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, sessionmaker

from packages.persistence.models import KnowledgeChunk as SqlKnowledgeChunk
from packages.persistence.models import KnowledgeDocument as SqlKnowledgeDocument

from .contracts import KnowledgeChunk, RetrievalFilters, ScoredChunk
from .registry import InMemoryKnowledgeRepository


class VectorStore(Protocol):
    def search(
        self, query_vector: list[float], filters: RetrievalFilters, *, top_k: int
    ) -> list[ScoredChunk]: ...


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vector dimensions do not match")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


class InMemoryVectorStore:
    def __init__(self, repository: InMemoryKnowledgeRepository) -> None:
        self._repository = repository

    def search(
        self, query_vector: list[float], filters: RetrievalFilters, *, top_k: int
    ) -> list[ScoredChunk]:
        # list_searchable_chunks performs the security boundary before similarity is evaluated.
        chunks = self._repository.list_searchable_chunks(filters)
        scored = [
            ScoredChunk(
                chunk=chunk,
                vector_score=cosine_similarity(query_vector, chunk.embedding or []),
            )
            for chunk in chunks
        ]
        return sorted(scored, key=lambda item: (-item.vector_score, item.chunk.chunk_id))[:top_k]


class PgVectorStore:
    """Production-shaped pgvector store; all tenant filters are inside the SQL query."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def build_statement(
        query_vector: list[float], filters: RetrievalFilters, *, top_k: int
    ) -> Select:
        distance = SqlKnowledgeChunk.embedding.cosine_distance(query_vector)
        statement = (
            select(SqlKnowledgeChunk, SqlKnowledgeDocument, distance.label("distance"))
            .join(
                SqlKnowledgeDocument,
                SqlKnowledgeDocument.id == SqlKnowledgeChunk.document_id,
            )
            .where(
                SqlKnowledgeDocument.workspace_id == UUID(filters.workspace_id),
                SqlKnowledgeDocument.status == "PUBLISHED",
                SqlKnowledgeChunk.embedding.is_not(None),
            )
        )
        if filters.source_ids:
            statement = statement.where(SqlKnowledgeDocument.source_id.in_(filters.source_ids))
        if filters.versions:
            statement = statement.where(SqlKnowledgeDocument.version.in_(filters.versions))
        return statement.order_by(distance).limit(top_k)

    def search(
        self, query_vector: list[float], filters: RetrievalFilters, *, top_k: int
    ) -> list[ScoredChunk]:
        statement = self.build_statement(query_vector, filters, top_k=top_k)
        with self._sessions() as session:
            rows = session.execute(statement).all()
        return [self._to_scored(chunk, document, distance) for chunk, document, distance in rows]

    @staticmethod
    def _to_scored(
        chunk: SqlKnowledgeChunk,
        document: SqlKnowledgeDocument,
        distance: float,
    ) -> ScoredChunk:
        return ScoredChunk(
            chunk=KnowledgeChunk(
                chunk_id=chunk.chunk_id,
                document_id=str(document.id),
                workspace_id=str(document.workspace_id),
                source_id=document.source_id,
                source_uri=document.source,
                title=document.title,
                version=document.version,
                page=chunk.page,
                heading=chunk.heading,
                ordinal=chunk.ordinal,
                content=chunk.content,
                content_sha256=chunk.content_sha256,
                token_count=chunk.token_count,
                embedding=list(chunk.embedding) if chunk.embedding is not None else None,
            ),
            vector_score=max(-1.0, min(1.0, 1.0 - float(distance))),
        )
