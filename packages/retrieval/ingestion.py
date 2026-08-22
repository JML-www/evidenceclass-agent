"""Register-first document ingestion with hash verification and replaceable embeddings."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from packages.model_gateway.contracts import EmbeddingRequest, InvocationContext
from packages.model_gateway.interfaces import EmbeddingModel

from .contracts import KnowledgeChunk, KnowledgeDocumentRecord, SourceRegistration
from .errors import DocumentParseError
from .parsing import DocumentParser, HierarchicalChunker


class KnowledgeWriteRepository(Protocol):
    def register(self, registration: SourceRegistration) -> KnowledgeDocumentRecord: ...

    def mark_parsed(
        self, document_id: str, chunks: Iterable[KnowledgeChunk], *, parser_version: str
    ) -> KnowledgeDocumentRecord: ...

    def mark_parse_failed(self, document_id: str, error: str) -> KnowledgeDocumentRecord: ...


class KnowledgeIngestionService:
    def __init__(
        self,
        repository: KnowledgeWriteRepository,
        embedding_model: EmbeddingModel,
        *,
        parser: DocumentParser | None = None,
        chunker: HierarchicalChunker | None = None,
        embedding_batch_size: int = 128,
    ) -> None:
        self._repository = repository
        self._embedding_model = embedding_model
        self._parser = parser or DocumentParser()
        self._chunker = chunker or HierarchicalChunker()
        self._embedding_batch_size = embedding_batch_size

    def ingest(self, registration: SourceRegistration, path: str | Path) -> list[KnowledgeChunk]:
        """Register the source before parsing so every failure has source provenance."""

        self._repository.register(registration)
        source = Path(path)
        try:
            actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            if actual_hash != registration.sha256:
                raise DocumentParseError(
                    f"file SHA-256 mismatch: expected {registration.sha256}, got {actual_hash}"
                )
            parsed = self._parser.parse(source, title=registration.title)
            chunks = self._chunker.chunk(registration, parsed)
            embedded = self._embed_chunks(chunks)
            self._repository.mark_parsed(
                registration.document_id,
                embedded,
                parser_version=parsed.parser_version,
            )
            return embedded
        except Exception as exc:
            self._repository.mark_parse_failed(registration.document_id, str(exc))
            raise

    def _embed_chunks(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        embedded: list[KnowledgeChunk] = []
        for start in range(0, len(chunks), self._embedding_batch_size):
            batch = chunks[start : start + self._embedding_batch_size]
            result = self._embedding_model.embed(
                EmbeddingRequest(
                    texts=[chunk.content for chunk in batch],
                    context=InvocationContext(
                        prompt_version="retrieval-ingestion.v0.1",
                        config_version="hash-embedding-384.v0.1",
                        timeout_seconds=30.0,
                        max_output_tokens=1,
                    ),
                )
            )
            if len(result.parsed.vectors) != len(batch):
                raise DocumentParseError("embedding count does not match chunk count")
            embedded.extend(
                KnowledgeChunk.model_validate(
                    {**chunk.model_dump(mode="python"), "embedding": vector}
                )
                for chunk, vector in zip(batch, result.parsed.vectors, strict=True)
            )
        return embedded
