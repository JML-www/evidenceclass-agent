"""Workspace-scoped knowledge source registry and publication lifecycle."""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import (
    AuthorizationStatus,
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeDocumentRecord,
    RetrievalFilters,
    SourceRegistration,
)
from .errors import PublicationGateError, SourceRegistrationError

UNKNOWN_LICENSE_VALUES = {"unknown", "unverified", "n/a", "none", "未知"}


class InMemoryKnowledgeRepository:
    """Deterministic repository used by offline evaluation and unit tests.

    The production vector store applies the same filters in SQL. Keeping this repository small
    makes security and retrieval evaluation runnable without Docker or network access.
    """

    def __init__(self) -> None:
        self._documents: dict[str, KnowledgeDocumentRecord] = {}
        self._chunks: dict[str, KnowledgeChunk] = {}

    def register(self, registration: SourceRegistration) -> KnowledgeDocumentRecord:
        if registration.document_id in self._documents:
            raise SourceRegistrationError(
                f"document_id already registered: {registration.document_id}"
            )
        if any(
            record.registration.workspace_id == registration.workspace_id
            and record.registration.source_id == registration.source_id
            and record.registration.version == registration.version
            for record in self._documents.values()
        ):
            raise SourceRegistrationError("workspace/source/version is already registered")
        record = KnowledgeDocumentRecord(registration=registration)
        self._documents[registration.document_id] = record
        return record

    def mark_parsed(
        self, document_id: str, chunks: Iterable[KnowledgeChunk], *, parser_version: str
    ) -> KnowledgeDocumentRecord:
        record = self.require_document(document_id)
        parsed = list(chunks)
        if not parsed:
            raise SourceRegistrationError("a parsed document must contain at least one chunk")
        if any(chunk.document_id != document_id for chunk in parsed):
            raise SourceRegistrationError("chunk document_id does not match registration")
        if len({chunk.chunk_id for chunk in parsed}) != len(parsed):
            raise SourceRegistrationError("chunk IDs must be unique")
        for chunk_id, chunk in list(self._chunks.items()):
            if chunk.document_id == document_id:
                del self._chunks[chunk_id]
        self._chunks.update({chunk.chunk_id: chunk for chunk in parsed})
        updated = record.model_copy(
            update={
                "status": DocumentStatus.PARSED,
                "parser_version": parser_version,
                "parse_error": None,
            }
        )
        self._documents[document_id] = updated
        return updated

    def mark_parse_failed(self, document_id: str, error: str) -> KnowledgeDocumentRecord:
        record = self.require_document(document_id)
        updated = record.model_copy(update={"parse_error": error})
        self._documents[document_id] = updated
        return updated

    def publish(self, document_id: str) -> KnowledgeDocumentRecord:
        record = self.require_document(document_id)
        registration = record.registration
        errors: list[str] = []
        if record.status is not DocumentStatus.PARSED:
            errors.append("document must be parsed before publication")
        if registration.authorization_status is not AuthorizationStatus.AUTHORIZED:
            errors.append("authorization status must be AUTHORIZED")
        if registration.license_name.casefold() in UNKNOWN_LICENSE_VALUES:
            errors.append("license or authorization basis is unknown")
        if not any(chunk.document_id == document_id for chunk in self._chunks.values()):
            errors.append("document has no indexed chunks")
        if errors:
            raise PublicationGateError("; ".join(errors))

        for other_id, other in list(self._documents.items()):
            if (
                other_id != document_id
                and other.status is DocumentStatus.PUBLISHED
                and other.registration.workspace_id == registration.workspace_id
                and other.registration.source_id == registration.source_id
            ):
                self._documents[other_id] = other.model_copy(
                    update={"status": DocumentStatus.SUPERSEDED}
                )
        published = record.model_copy(update={"status": DocumentStatus.PUBLISHED})
        self._documents[document_id] = published
        return published

    def require_document(self, document_id: str) -> KnowledgeDocumentRecord:
        try:
            return self._documents[document_id]
        except KeyError as exc:
            raise SourceRegistrationError(f"unknown document_id: {document_id}") from exc

    def get_chunk(self, chunk_id: str) -> KnowledgeChunk | None:
        return self._chunks.get(chunk_id)

    def delete_chunk(self, chunk_id: str) -> None:
        self._chunks.pop(chunk_id, None)

    def list_searchable_chunks(self, filters: RetrievalFilters) -> list[KnowledgeChunk]:
        """Apply tenant/source/version metadata filters before vector scoring."""

        allowed_documents = {
            document_id
            for document_id, record in self._documents.items()
            if record.status is DocumentStatus.PUBLISHED
            and record.registration.workspace_id == filters.workspace_id
            and (not filters.source_ids or record.registration.source_id in filters.source_ids)
            and (not filters.versions or record.registration.version in filters.versions)
        }
        return [
            chunk
            for chunk in self._chunks.values()
            if chunk.document_id in allowed_documents and chunk.embedding is not None
        ]

    def document_for_chunk(self, chunk_id: str) -> KnowledgeDocumentRecord | None:
        chunk = self._chunks.get(chunk_id)
        return self._documents.get(chunk.document_id) if chunk else None

    @property
    def documents(self) -> tuple[KnowledgeDocumentRecord, ...]:
        return tuple(self._documents.values())

    @property
    def chunks(self) -> tuple[KnowledgeChunk, ...]:
        return tuple(self._chunks.values())
