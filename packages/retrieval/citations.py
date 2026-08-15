"""Deterministic citation checks used as a report publication gate."""

from __future__ import annotations

from collections.abc import Iterable

from .contracts import (
    CitationValidationResult,
    ClaimKind,
    DocumentStatus,
    ReportClaim,
)
from .registry import InMemoryKnowledgeRepository


class CitationValidator:
    def __init__(self, repository: InMemoryKnowledgeRepository) -> None:
        self._repository = repository

    def validate(
        self, claims: Iterable[ReportClaim], *, workspace_id: str
    ) -> CitationValidationResult:
        errors: list[str] = []
        checked = 0
        for claim in claims:
            checked += 1
            if claim.kind is ClaimKind.KNOWLEDGE and not claim.citations:
                errors.append(f"{claim.claim_id}: knowledge claim has no citation")
                continue
            for citation in claim.citations:
                chunk = self._repository.get_chunk(citation.chunk_id)
                if chunk is None:
                    errors.append(f"{claim.claim_id}: unknown chunk {citation.chunk_id}")
                    continue
                record = self._repository.document_for_chunk(citation.chunk_id)
                if record is None:
                    errors.append(f"{claim.claim_id}: citation document is missing")
                    continue
                if chunk.document_id != citation.document_id:
                    errors.append(f"{claim.claim_id}: citation document_id mismatch")
                if chunk.workspace_id != workspace_id:
                    errors.append(f"{claim.claim_id}: citation crosses workspace boundary")
                if chunk.version != citation.version:
                    errors.append(f"{claim.claim_id}: citation version mismatch")
                if chunk.page != citation.page:
                    errors.append(f"{claim.claim_id}: citation page mismatch")
                if record.status is not DocumentStatus.PUBLISHED:
                    errors.append(f"{claim.claim_id}: citation version is not currently published")
        return CitationValidationResult(
            publishable=not errors,
            checked_claims=checked,
            errors=errors,
        )
