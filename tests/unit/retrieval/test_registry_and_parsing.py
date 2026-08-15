import hashlib
from datetime import date
from pathlib import Path

import pytest

from packages.model_gateway.contracts import EmbeddingOutput, EmbeddingResult
from packages.retrieval.citations import CitationValidator
from packages.retrieval.contracts import (
    AuthorizationStatus,
    Citation,
    ClaimKind,
    ReportClaim,
    SourceRegistration,
)
from packages.retrieval.embeddings import DeterministicHashEmbeddingAdapter
from packages.retrieval.errors import DocumentParseError, PublicationGateError
from packages.retrieval.ingestion import KnowledgeIngestionService
from packages.retrieval.parsing import DocumentParser, HierarchicalChunker
from packages.retrieval.registry import InMemoryKnowledgeRepository


def registration(
    path: Path,
    *,
    document_id: str = "document-1",
    authorization: AuthorizationStatus = AuthorizationStatus.AUTHORIZED,
    license_name: str = "Original synthetic test fixture",
) -> SourceRegistration:
    return SourceRegistration(
        document_id=document_id,
        workspace_id="workspace-1",
        source_id="source-1",
        source_uri=f"fixture://{path.name}",
        title="Test source",
        author_or_organization="EvidenceClass tests",
        version="1.0.0",
        published_on=date(2026, 8, 15),
        license_name=license_name,
        authorization_status=authorization,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_register_first_ingestion_preserves_headings_and_stable_chunks(tmp_path):
    source = tmp_path / "knowledge.md"
    source.write_text("# Root\nintro text\n## Child\nstable content", encoding="utf-8")
    repository = InMemoryKnowledgeRepository()
    service = KnowledgeIngestionService(
        repository,
        DeterministicHashEmbeddingAdapter(),
        chunker=HierarchicalChunker(max_tokens=20, overlap_tokens=4),
    )

    first = service.ingest(registration(source), source)
    repository.publish("document-1")

    assert [chunk.heading for chunk in first] == ["Root", "Root > Child"]
    assert all(chunk.embedding and len(chunk.embedding) == 384 for chunk in first)
    assert repository.documents[0].status.value == "PUBLISHED"


def test_hash_failure_is_attached_to_registered_source(tmp_path):
    source = tmp_path / "knowledge.txt"
    source.write_text("authorized original", encoding="utf-8")
    invalid = registration(source).model_copy(update={"sha256": "0" * 64})
    repository = InMemoryKnowledgeRepository()
    service = KnowledgeIngestionService(repository, DeterministicHashEmbeddingAdapter())

    with pytest.raises(DocumentParseError, match="SHA-256 mismatch"):
        service.ingest(invalid, source)

    assert len(repository.documents) == 1
    assert "SHA-256 mismatch" in (repository.documents[0].parse_error or "")


@pytest.mark.parametrize(
    ("authorization", "license_name"),
    [
        (AuthorizationStatus.UNKNOWN, "Original fixture"),
        (AuthorizationStatus.DENIED, "Original fixture"),
        (AuthorizationStatus.AUTHORIZED, "unknown"),
    ],
)
def test_unknown_or_denied_source_cannot_be_published(
    tmp_path, authorization, license_name
):
    source = tmp_path / "knowledge.txt"
    source.write_text("registered text", encoding="utf-8")
    repository = InMemoryKnowledgeRepository()
    service = KnowledgeIngestionService(repository, DeterministicHashEmbeddingAdapter())
    service.ingest(
        registration(source, authorization=authorization, license_name=license_name), source
    )

    with pytest.raises(PublicationGateError):
        repository.publish("document-1")


def test_unsupported_and_invalid_utf8_errors_are_specific(tmp_path):
    binary = tmp_path / "broken.txt"
    binary.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(DocumentParseError, match="UTF-8 decode failed"):
        DocumentParser().parse(binary, title="Broken")

    unsupported = tmp_path / "knowledge.docx"
    unsupported.write_text("text", encoding="utf-8")
    with pytest.raises(DocumentParseError, match="unsupported document type"):
        DocumentParser().parse(unsupported, title="Unsupported")


def test_txt_parser_and_long_window_keep_text_and_heading(tmp_path):
    source = tmp_path / "knowledge.txt"
    source.write_text(
        "# Text Heading\n" + " ".join(f"token-{index}" for index in range(45)),
        encoding="utf-8",
    )
    parsed = DocumentParser().parse(source, title="Text fallback")
    chunks = HierarchicalChunker(max_tokens=20, overlap_tokens=5).chunk(
        registration(source), parsed
    )

    assert len(chunks) == 3
    assert all(chunk.heading == "Text Heading" for chunk in chunks)
    assert chunks[0].content.startswith("token-0")
    assert chunks[-1].content.endswith("token-44")


def test_publishing_new_version_supersedes_old_citations(tmp_path):
    source = tmp_path / "versioned.md"
    source.write_text("# Versioned\nversioned knowledge", encoding="utf-8")
    repository = InMemoryKnowledgeRepository()
    service = KnowledgeIngestionService(repository, DeterministicHashEmbeddingAdapter())
    first = registration(source)
    service.ingest(first, source)
    repository.publish(first.document_id)
    old_chunk = repository.chunks[0]
    old_claim = ReportClaim(
        claim_id="old-version",
        kind=ClaimKind.KNOWLEDGE,
        text="old knowledge",
        citations=[
            Citation(
                chunk_id=old_chunk.chunk_id,
                document_id=old_chunk.document_id,
                page=old_chunk.page,
                version=old_chunk.version,
            )
        ],
    )
    assert CitationValidator(repository).validate(
        [old_claim], workspace_id="workspace-1"
    ).publishable

    second = registration(source, document_id="document-2").model_copy(
        update={"version": "2.0.0"}
    )
    service.ingest(second, source)
    repository.publish(second.document_id)

    assert not CitationValidator(repository).validate(
        [old_claim], workspace_id="workspace-1"
    ).publishable


def test_pdf_extraction_failure_reports_exact_page(tmp_path, monkeypatch):
    source = tmp_path / "page-error.pdf"
    source.write_bytes(b"synthetic placeholder")

    class GoodPage:
        def extract_text(self):
            return "extractable first page"

    class BrokenPage:
        def extract_text(self):
            raise ValueError("damaged content stream")

    class FakeReader:
        pages = [GoodPage(), BrokenPage()]

    monkeypatch.setattr(
        "packages.retrieval.parsing.PdfReader", lambda _path, strict: FakeReader()
    )
    with pytest.raises(DocumentParseError, match="page 2") as captured:
        DocumentParser().parse(source, title="Page error")

    assert captured.value.page == 2


def test_ingestion_rejects_embedding_with_wrong_dimensions(tmp_path):
    source = tmp_path / "wrong-vector.md"
    source.write_text("# Vector\nwrong dimension", encoding="utf-8")
    baseline = DeterministicHashEmbeddingAdapter()

    class WrongDimensionEmbedding:
        def embed(self, request):
            result = baseline.embed(request)
            return EmbeddingResult(
                metadata=result.metadata,
                parsed=EmbeddingOutput(vectors=[[0.1, 0.2, 0.3]]),
            )

    repository = InMemoryKnowledgeRepository()
    service = KnowledgeIngestionService(repository, WrongDimensionEmbedding())

    with pytest.raises(ValueError, match="384 dimensions"):
        service.ingest(registration(source), source)
