import hashlib
from datetime import date

import pytest

from packages.retrieval.contracts import AuthorizationStatus, SourceRegistration
from packages.retrieval.embeddings import (
    DeterministicHashEmbeddingAdapter,
    LexicalOverlapReranker,
)
from packages.retrieval.ingestion import KnowledgeIngestionService
from packages.retrieval.registry import InMemoryKnowledgeRepository
from packages.retrieval.service import RetrievalService
from packages.retrieval.stores import InMemoryVectorStore


@pytest.fixture
def stage6_repository_and_service(tmp_path):
    source = tmp_path / "source.md"
    source.write_text(
        "# E01 Authorization Gate\nE01 authorization gate requires known permission.\n"
        "# E02 Workspace Filter\nE02 workspace filter runs before similarity scoring.",
        encoding="utf-8",
    )
    repository = InMemoryKnowledgeRepository()
    embedding = DeterministicHashEmbeddingAdapter()
    ingestion = KnowledgeIngestionService(repository, embedding)
    registration = SourceRegistration(
        document_id="document-1",
        workspace_id="workspace-1",
        source_id="source-1",
        source_uri="fixture://source.md",
        title="Source",
        author_or_organization="Tests",
        version="1.0",
        published_on=date(2026, 8, 15),
        license_name="Original test fixture",
        authorization_status=AuthorizationStatus.AUTHORIZED,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    ingestion.ingest(registration, source)
    repository.publish("document-1")
    service = RetrievalService(
        InMemoryVectorStore(repository),
        embedding,
        reranker=LexicalOverlapReranker(),
    )
    return repository, service
