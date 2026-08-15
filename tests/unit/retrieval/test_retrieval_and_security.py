import pytest
from sqlalchemy.dialects import postgresql

from packages.retrieval.citations import CitationValidator
from packages.retrieval.contracts import (
    Citation,
    ClaimKind,
    KnowledgeChunk,
    ReportClaim,
    RetrievalFilters,
    ScoredChunk,
)
from packages.retrieval.embeddings import DeterministicHashEmbeddingAdapter
from packages.retrieval.errors import PublicationGateError
from packages.retrieval.security import (
    RAG_SYSTEM_PROMPT,
    GroundedPromptBuilder,
    InstructionOrigin,
    SensitivePromptPublicationGate,
    ToolAuthorizationPolicy,
)
from packages.retrieval.service import RetrievalService
from packages.retrieval.stores import PgVectorStore


def test_pgvector_statement_keeps_workspace_source_and_version_in_sql():
    filters = RetrievalFilters(
        workspace_id="11111111-1111-4111-8111-111111111111",
        source_ids=["source-a"],
        versions=["2.0"],
    )
    query = DeterministicHashEmbeddingAdapter()._vector("workspace filter")

    statement = PgVectorStore.build_statement(query, filters, top_k=20)
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "knowledge_documents.workspace_id" in sql
    assert "knowledge_documents.source_id" in sql
    assert "knowledge_documents.version" in sql
    assert "knowledge_documents.status" in sql
    assert "knowledge_chunks.embedding" in sql


def test_retrieved_document_cannot_authorize_tool_or_cross_workspace():
    policy = ToolAuthorizationPolicy({"retrieve_knowledge"})

    assert not policy.authorize(
        tool_name="retrieve_knowledge",
        origin=InstructionOrigin.RETRIEVED_DOCUMENT,
        requested_workspace_id="workspace-victim",
        active_workspace_id="workspace-owner",
    )
    assert policy.authorize(
        tool_name="retrieve_knowledge",
        origin=InstructionOrigin.USER,
        requested_workspace_id="workspace-owner",
        active_workspace_id="workspace-owner",
    )


def test_prompt_leakage_publication_gate_rejects_protected_content():
    gate = SensitivePromptPublicationGate([RAG_SYSTEM_PROMPT, "secret-canary"])
    gate.validate("grounded answer")
    with pytest.raises(PublicationGateError, match="protected prompt material"):
        gate.validate("prefix secret-canary suffix")


def test_grounded_prompt_serializes_documents_as_untrusted(stage6_repository_and_service):
    _, service = stage6_repository_and_service
    result = service.retrieve(
        "E01 authorization gate",
        RetrievalFilters(workspace_id="workspace-1"),
    )

    system, user = GroundedPromptBuilder.build(result)

    assert "untrusted data" in system
    assert "retrieved_records_untrusted" in user
    assert result.contexts[0].chunk.chunk_id in user


def test_citation_validator_rejects_forged_deleted_version_and_workspace(
    stage6_repository_and_service,
):
    repository, _ = stage6_repository_and_service
    chunk = repository.chunks[0]
    validator = CitationValidator(repository)
    valid = ReportClaim(
        claim_id="valid",
        kind=ClaimKind.KNOWLEDGE,
        text="registered fact",
        citations=[
            Citation(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                page=chunk.page,
                version=chunk.version,
            )
        ],
    )
    assert validator.validate([valid], workspace_id="workspace-1").publishable

    wrong_version = valid.model_copy(
        update={
            "citations": [valid.citations[0].model_copy(update={"version": "9.9"})]
        }
    )
    assert not validator.validate([wrong_version], workspace_id="workspace-1").publishable
    wrong_page = valid.model_copy(
        update={"citations": [valid.citations[0].model_copy(update={"page": 1})]}
    )
    assert not validator.validate([wrong_page], workspace_id="workspace-1").publishable
    assert not validator.validate([valid], workspace_id="workspace-victim").publishable
    repository.delete_chunk(chunk.chunk_id)
    assert not validator.validate([valid], workspace_id="workspace-1").publishable


def test_context_budget_deduplicates_and_truncates():
    embedding = DeterministicHashEmbeddingAdapter()

    def chunk(chunk_id: str, content: str, digest: str, token_count: int) -> KnowledgeChunk:
        return KnowledgeChunk(
            chunk_id=chunk_id,
            document_id="document-1",
            workspace_id="workspace-1",
            source_id="source-1",
            source_uri="fixture://source",
            title="Source",
            version="1.0",
            heading="Heading",
            ordinal=0,
            content=content,
            content_sha256=digest * 64,
            token_count=token_count,
            embedding=embedding._vector(content),
        )

    first = chunk("chunk-1", "one two three", "a", 3)
    duplicate = chunk("chunk-2", "one two three", "a", 3)
    long = chunk("chunk-3", "four five six seven", "b", 4)

    class StaticStore:
        def search(self, query_vector, filters, *, top_k):
            return [
                ScoredChunk(chunk=first, vector_score=0.9),
                ScoredChunk(chunk=duplicate, vector_score=0.8),
                ScoredChunk(chunk=long, vector_score=0.7),
            ][:top_k]

    service = RetrievalService(
        StaticStore(),
        embedding,
        recall_k=3,
        context_k=3,
        context_token_budget=5,
    )
    result = service.retrieve("one four", RetrievalFilters(workspace_id="workspace-1"))

    assert result.duplicates_dropped == 1
    assert result.context_tokens == 5
    assert result.contexts[-1].truncated is True
    assert result.contexts[-1].presented_content == "four five"
