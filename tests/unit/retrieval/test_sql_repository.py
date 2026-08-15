import hashlib
from datetime import date
from uuid import UUID

from sqlalchemy import func, select

from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    User,
    Workspace,
)
from packages.retrieval.contracts import AuthorizationStatus, SourceRegistration
from packages.retrieval.embeddings import DeterministicHashEmbeddingAdapter
from packages.retrieval.ingestion import KnowledgeIngestionService
from packages.retrieval.sql_repository import SqlKnowledgeRepository


def test_sql_repository_persists_governed_document_and_384d_chunks(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'knowledge.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    workspace_id = UUID("55555555-5555-4555-8555-555555555555")
    with sessions.begin() as session:
        user = User(email="retrieval-sql@example.test", password_hash="test-only")
        session.add(user)
        session.flush()
        session.add(Workspace(id=workspace_id, owner_id=user.id, name="Retrieval SQL"))

    source = tmp_path / "sql-source.md"
    source.write_text(
        "# SQL Source\nworkspace-scoped SQL ingestion evidence",
        encoding="utf-8",
    )
    registration = SourceRegistration(
        document_id="66666666-6666-4666-8666-666666666666",
        workspace_id=str(workspace_id),
        source_id="sql-source",
        source_uri="fixture://sql-source.md",
        title="SQL source",
        author_or_organization="EvidenceClass tests",
        version="1.0.0",
        published_on=date(2026, 8, 15),
        license_name="Original test fixture",
        authorization_status=AuthorizationStatus.AUTHORIZED,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    repository = SqlKnowledgeRepository(sessions)
    chunks = KnowledgeIngestionService(
        repository, DeterministicHashEmbeddingAdapter()
    ).ingest(registration, source)
    published = repository.publish(registration.document_id)

    assert published.status.value == "PUBLISHED"
    assert len(chunks) == 1 and len(chunks[0].embedding or []) == 384
    with sessions() as session:
        document = session.get(KnowledgeDocument, UUID(registration.document_id))
        assert document is not None
        assert document.status == "PUBLISHED"
        assert document.source_id == "sql-source"
        assert document.parser_version == "document-parser.v0.1"
        assert session.scalar(select(func.count(KnowledgeChunk.id))) == 1
    engine.dispose()
