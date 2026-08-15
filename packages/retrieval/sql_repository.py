"""Transactional SQL knowledge ingestion for the production pgvector path."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from packages.persistence.models import KnowledgeChunk as SqlKnowledgeChunk
from packages.persistence.models import KnowledgeDocument as SqlKnowledgeDocument

from .contracts import (
    AuthorizationStatus,
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeDocumentRecord,
    SourceRegistration,
    VisibilityScope,
)
from .errors import PublicationGateError, SourceRegistrationError
from .registry import UNKNOWN_LICENSE_VALUES


class SqlKnowledgeRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def register(self, registration: SourceRegistration) -> KnowledgeDocumentRecord:
        try:
            document_uuid = UUID(registration.document_id)
            workspace_uuid = UUID(registration.workspace_id)
        except ValueError as exc:
            raise SourceRegistrationError(
                "SQL document_id and workspace_id must be UUID strings"
            ) from exc
        with self._sessions.begin() as session:
            existing = session.scalar(
                select(SqlKnowledgeDocument.id).where(
                    SqlKnowledgeDocument.workspace_id == workspace_uuid,
                    SqlKnowledgeDocument.source_id == registration.source_id,
                    SqlKnowledgeDocument.version == registration.version,
                )
            )
            if existing is not None:
                raise SourceRegistrationError("workspace/source/version is already registered")
            session.add(
                SqlKnowledgeDocument(
                    id=document_uuid,
                    workspace_id=workspace_uuid,
                    source_id=registration.source_id,
                    source=registration.source_uri,
                    title=registration.title,
                    author_or_organization=registration.author_or_organization,
                    published_on=registration.published_on,
                    license=registration.license_name,
                    authorization_status=registration.authorization_status.value,
                    sha256=registration.sha256,
                    visibility_scope=registration.visibility_scope.value,
                    version=registration.version,
                    status=DocumentStatus.REGISTERED.value,
                )
            )
        return KnowledgeDocumentRecord(registration=registration)

    def mark_parsed(
        self, document_id: str, chunks: Iterable[KnowledgeChunk], *, parser_version: str
    ) -> KnowledgeDocumentRecord:
        document_uuid = UUID(document_id)
        parsed = list(chunks)
        if not parsed:
            raise SourceRegistrationError("a parsed document must contain at least one chunk")
        with self._sessions.begin() as session:
            document = session.get(SqlKnowledgeDocument, document_uuid)
            if document is None:
                raise SourceRegistrationError(f"unknown document_id: {document_id}")
            session.execute(
                delete(SqlKnowledgeChunk).where(
                    SqlKnowledgeChunk.document_id == document_uuid
                )
            )
            for chunk in parsed:
                session.add(
                    SqlKnowledgeChunk(
                        document_id=document_uuid,
                        chunk_id=chunk.chunk_id,
                        page=chunk.page,
                        heading=chunk.heading,
                        ordinal=chunk.ordinal,
                        content=chunk.content,
                        content_sha256=chunk.content_sha256,
                        token_count=chunk.token_count,
                        metadata_json={
                            "workspace_id": chunk.workspace_id,
                            "source_id": chunk.source_id,
                            "version": chunk.version,
                        },
                        embedding=chunk.embedding,
                    )
                )
            document.status = DocumentStatus.PARSED.value
            document.parser_version = parser_version
            document.parse_error = None
            registration = self._registration(document)
        return KnowledgeDocumentRecord(
            registration=registration,
            status=DocumentStatus.PARSED,
            parser_version=parser_version,
        )

    def mark_parse_failed(self, document_id: str, error: str) -> KnowledgeDocumentRecord:
        with self._sessions.begin() as session:
            document = session.get(SqlKnowledgeDocument, UUID(document_id))
            if document is None:
                raise SourceRegistrationError(f"unknown document_id: {document_id}")
            document.parse_error = error[:4000]
            registration = self._registration(document)
        return KnowledgeDocumentRecord(registration=registration, parse_error=error[:4000])

    def publish(self, document_id: str) -> KnowledgeDocumentRecord:
        document_uuid = UUID(document_id)
        with self._sessions.begin() as session:
            document = session.get(SqlKnowledgeDocument, document_uuid)
            if document is None:
                raise SourceRegistrationError(f"unknown document_id: {document_id}")
            chunk_count = session.scalar(
                select(func.count(SqlKnowledgeChunk.id)).where(
                    SqlKnowledgeChunk.document_id == document_uuid
                )
            )
            errors: list[str] = []
            if document.status != DocumentStatus.PARSED.value:
                errors.append("document must be parsed before publication")
            if document.authorization_status != AuthorizationStatus.AUTHORIZED.value:
                errors.append("authorization status must be AUTHORIZED")
            if document.license.casefold() in UNKNOWN_LICENSE_VALUES:
                errors.append("license or authorization basis is unknown")
            if not chunk_count:
                errors.append("document has no indexed chunks")
            if errors:
                raise PublicationGateError("; ".join(errors))
            previous = session.scalars(
                select(SqlKnowledgeDocument).where(
                    SqlKnowledgeDocument.id != document_uuid,
                    SqlKnowledgeDocument.workspace_id == document.workspace_id,
                    SqlKnowledgeDocument.source_id == document.source_id,
                    SqlKnowledgeDocument.status == DocumentStatus.PUBLISHED.value,
                )
            )
            for item in previous:
                item.status = DocumentStatus.SUPERSEDED.value
            document.status = DocumentStatus.PUBLISHED.value
            registration = self._registration(document)
            parser_version = document.parser_version
        return KnowledgeDocumentRecord(
            registration=registration,
            status=DocumentStatus.PUBLISHED,
            parser_version=parser_version,
        )

    @staticmethod
    def _registration(document: SqlKnowledgeDocument) -> SourceRegistration:
        return SourceRegistration(
            document_id=str(document.id),
            workspace_id=str(document.workspace_id),
            source_id=document.source_id,
            source_uri=document.source,
            title=document.title,
            author_or_organization=document.author_or_organization,
            version=document.version,
            published_on=document.published_on,
            license_name=document.license,
            authorization_status=AuthorizationStatus(document.authorization_status),
            sha256=document.sha256,
            visibility_scope=VisibilityScope(document.visibility_scope),
        )
