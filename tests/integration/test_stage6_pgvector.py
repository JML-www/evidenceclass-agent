import hashlib
import os
from datetime import date
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from packages.persistence import make_session_factory
from packages.persistence.models import User, Workspace
from packages.retrieval.contracts import (
    AuthorizationStatus,
    RetrievalFilters,
    SourceRegistration,
)
from packages.retrieval.embeddings import DeterministicHashEmbeddingAdapter
from packages.retrieval.ingestion import KnowledgeIngestionService
from packages.retrieval.sql_repository import SqlKnowledgeRepository
from packages.retrieval.stores import PgVectorStore

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_STAGE6_PGVECTOR_TESTS") != "1",
    reason="requires a PostgreSQL server with the pgvector extension",
)


def test_pgvector_extension_migration_and_cosine_operator(tmp_path):
    database_url = os.environ["DATABASE_URL"]
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
        assert connection.scalar(
            text("SELECT '[1,0,0]'::vector <=> '[1,0,0]'::vector")
        ) == 0
        index_definition = connection.scalar(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND indexname = 'ix_knowledge_chunks_embedding_hnsw'"
            )
        )
        assert index_definition is not None
        assert "USING hnsw" in index_definition
        assert "vector_cosine_ops" in index_definition
    sessions = make_session_factory(engine)
    workspace_id = UUID("33333333-3333-4333-8333-333333333333")
    with sessions.begin() as session:
        user = User(email="stage6-pgvector@example.test", password_hash="test-only")
        session.add(user)
        session.flush()
        session.add(Workspace(id=workspace_id, owner_id=user.id, name="Stage 6 pgvector"))
    source = tmp_path / "pgvector.md"
    source.write_text(
        "# Vector Smoke\npgvector cosine workspace filter smoke evidence",
        encoding="utf-8",
    )
    registration = SourceRegistration(
        document_id="44444444-4444-4444-8444-444444444444",
        workspace_id=str(workspace_id),
        source_id="pgvector-smoke",
        source_uri="fixture://pgvector.md",
        title="Pgvector smoke",
        author_or_organization="EvidenceClass tests",
        version="1.0.0",
        published_on=date(2026, 8, 15),
        license_name="Original test fixture",
        authorization_status=AuthorizationStatus.AUTHORIZED,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    embedding = DeterministicHashEmbeddingAdapter()
    repository = SqlKnowledgeRepository(sessions)
    KnowledgeIngestionService(repository, embedding).ingest(registration, source)
    repository.publish(registration.document_id)
    query_vector = embedding._vector("pgvector cosine workspace filter")
    results = PgVectorStore(sessions).search(
        query_vector,
        RetrievalFilters(workspace_id=str(workspace_id), source_ids=["pgvector-smoke"]),
        top_k=20,
    )
    assert results and results[0].chunk.heading == "Vector Smoke"
    command.downgrade(config, "7182e15ca38a")
    command.upgrade(config, "head")
    engine.dispose()
