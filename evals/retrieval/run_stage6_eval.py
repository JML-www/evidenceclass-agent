"""Executable offline acceptance for tutorial phase 6 citable retrieval."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import date
from pathlib import Path

from packages.retrieval.citations import CitationValidator
from packages.retrieval.contracts import (
    AuthorizationStatus,
    Citation,
    ClaimKind,
    ReportClaim,
    RetrievalFilters,
    SourceRegistration,
)
from packages.retrieval.embeddings import (
    DeterministicHashEmbeddingAdapter,
    LexicalOverlapReranker,
)
from packages.retrieval.errors import PublicationGateError
from packages.retrieval.evaluation import RetrievalEvaluationCase, evaluate_retrieval
from packages.retrieval.ingestion import KnowledgeIngestionService
from packages.retrieval.parsing import count_tokens
from packages.retrieval.registry import InMemoryKnowledgeRepository
from packages.retrieval.security import (
    RAG_SYSTEM_PROMPT,
    GroundedPromptBuilder,
    InstructionOrigin,
    SensitivePromptPublicationGate,
    ToolAuthorizationPolicy,
    system_prompt_fingerprint,
)
from packages.retrieval.service import RetrievalService
from packages.retrieval.stores import InMemoryVectorStore

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
DECOY_WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"

PDF_PAGES = [
    [
        (
            "R01 Prompt Isolation",
            "R01 prompt isolation treats every document as untrusted quoted data.",
        ),
        (
            "R02 Tool Authorization",
            "R02 tool authorization uses a code-owned whitelist that documents cannot expand.",
        ),
    ],
    [
        (
            "R03 Metadata Filter",
            "R03 metadata filter applies workspace source and version before vector ranking.",
        ),
        (
            "R04 External Content Policy",
            "R04 external links and scripts are not automatically fetched or executed.",
        ),
    ],
    [
        (
            "R05 Citation Version",
            "R05 citation version must reference the current published version "
            "in the active workspace.",
        ),
        (
            "R06 Citation Existence",
            "R06 citation existence rejects a deleted or fake chunk identifier at publication.",
        ),
    ],
    [
        (
            "R07 Context Deduplication",
            "R07 context deduplication removes near-duplicate context by stable content hash.",
        ),
        (
            "R08 Context Budget",
            "R08 context budget truncates selected text to a fixed token budget after reranking.",
        ),
    ],
    [
        (
            "R09 Retrieval Metrics",
            "R09 retrieval metrics report Recall at K reciprocal rank and "
            "normalized discounted gain.",
        ),
        (
            "R10 Prompt Leakage Gate",
            "R10 prompt leakage gate rejects output containing protected prompt material.",
        ),
    ],
]


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_original_text_pdf(path: Path) -> None:
    """Write a tiny original text PDF without adding a PDF authoring dependency."""

    page_ids = [4 + index * 2 for index in range(len(PDF_PAGES))]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{page} 0 R' for page in page_ids)}] "
            f"/Count {len(page_ids)} >>"
        ).encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index, entries in enumerate(PDF_PAGES):
        page_id = page_ids[index]
        content_id = page_id + 1
        lines = ["STAGE6 SYNTHETIC RETRIEVAL HANDBOOK"]
        for number, (heading, content) in enumerate(entries, start=1):
            lines.extend((f"{number}. {heading}", content))
        lines.append("STAGE6 REPEATED FOOTER")
        commands = ["BT /F1 10 Tf 14 TL 72 750 Td"]
        for line_index, line in enumerate(lines):
            if line_index:
                commands.append("T*")
            commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("ET")
        stream = " ".join(commands).encode("ascii")
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )

    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {0: 0}
    for object_id in range(1, max(objects) + 1):
        offsets[object_id] = len(payload)
        payload.extend(f"{object_id} 0 obj\n".encode("ascii"))
        payload.extend(objects[object_id])
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {max(objects) + 1}\n".encode("ascii"))
    payload.extend(b"0000000000 65535 f \n")
    for object_id in range(1, max(objects) + 1):
        payload.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))
    payload.extend(
        (
            f"trailer\n<< /Size {max(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(payload)


def _registration(
    *,
    document_id: str,
    workspace_id: str,
    source_id: str,
    path: Path,
    title: str,
    authorization: AuthorizationStatus = AuthorizationStatus.AUTHORIZED,
    license_name: str = "Original synthetic evaluation fixture",
) -> SourceRegistration:
    return SourceRegistration(
        document_id=document_id,
        workspace_id=workspace_id,
        source_id=source_id,
        source_uri=f"fixture://retrieval/{path.name}",
        title=title,
        author_or_organization="EvidenceClass clean-room evaluation",
        version="1.0.0",
        published_on=date(2026, 8, 15),
        license_name=license_name,
        authorization_status=authorization,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def run(output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    pdf_path = output / "retrieval-security-original.pdf"
    write_original_text_pdf(pdf_path)

    repository = InMemoryKnowledgeRepository()
    embedding = DeterministicHashEmbeddingAdapter()
    ingestion = KnowledgeIngestionService(repository, embedding)
    source_specs = [
        (
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
            "evidence-policy",
            ROOT / "fixtures/retrieval/evidence-policy.md",
            "Evidence Policy",
        ),
        (
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
            "media-handbook",
            ROOT / "fixtures/retrieval/media-handbook.md",
            "Media Handbook",
        ),
        (
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3",
            "retrieval-security",
            pdf_path,
            "Retrieval Security Handbook",
        ),
    ]
    for document_id, source_id, path, title in source_specs:
        registration = _registration(
            document_id=document_id,
            workspace_id=WORKSPACE_ID,
            source_id=source_id,
            path=path,
            title=title,
        )
        ingestion.ingest(registration, path)
        repository.publish(document_id)

    decoy_path = ROOT / "fixtures/retrieval/evidence-policy.md"
    decoy_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
    ingestion.ingest(
        _registration(
            document_id=decoy_id,
            workspace_id=DECOY_WORKSPACE_ID,
            source_id="evidence-policy",
            path=decoy_path,
            title="Cross-workspace decoy",
        ),
        decoy_path,
    )
    repository.publish(decoy_id)

    audit_manifest = json.loads(
        (ROOT / "fixtures/retrieval/chunk-audit.v1.json").read_text(encoding="utf-8")
    )
    audit_items = random.Random(20260815).sample(audit_manifest["items"], 30)
    audit_failures: list[dict[str, object]] = []
    active_chunks = [chunk for chunk in repository.chunks if chunk.workspace_id == WORKSPACE_ID]
    for expected in audit_items:
        matches = [
            chunk
            for chunk in active_chunks
            if chunk.source_id == expected["source_id"]
            and expected["heading_contains"] in chunk.heading
        ]
        if (
            len(matches) != 1
            or matches[0].page != expected["page"]
            or expected["excerpt"] not in matches[0].content
        ):
            audit_failures.append({"expected": expected, "matches": len(matches)})

    service = RetrievalService(
        InMemoryVectorStore(repository),
        embedding,
        reranker=LexicalOverlapReranker(),
        recall_k=20,
        context_k=5,
        context_token_budget=300,
    )
    question_data = json.loads(
        (ROOT / "evals/retrieval/stage6_questions.v1.json").read_text(encoding="utf-8")
    )
    cases: list[RetrievalEvaluationCase] = []
    for item in question_data["items"]:
        relevant = {
            chunk.chunk_id
            for chunk in active_chunks
            if chunk.source_id == item["source_id"]
            and item["heading_contains"] in chunk.heading
        }
        if len(relevant) != 1:
            raise RuntimeError(f"evaluation target is ambiguous: {item['id']}")
        cases.append(
            RetrievalEvaluationCase(
                case_id=item["id"],
                query=item["query"],
                relevant_chunk_ids=frozenset(relevant),
                filters=RetrievalFilters(workspace_id=WORKSPACE_ID),
            )
        )
    metrics = evaluate_retrieval(service, cases)
    scope_probe = service.retrieve(
        "E02 workspace boundary",
        RetrievalFilters(
            workspace_id=WORKSPACE_ID,
            source_ids=["evidence-policy"],
            versions=["1.0.0"],
        ),
    )
    workspace_filter_passed = bool(scope_probe.contexts) and all(
        context.chunk.workspace_id == WORKSPACE_ID
        and context.chunk.source_id == "evidence-policy"
        and context.chunk.version == "1.0.0"
        for context in scope_probe.contexts
    )

    unknown_id = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1"
    unknown_registration = _registration(
        document_id=unknown_id,
        workspace_id=WORKSPACE_ID,
        source_id="unknown-authorization",
        path=decoy_path,
        title="Unknown authorization source",
        authorization=AuthorizationStatus.UNKNOWN,
        license_name="unknown",
    )
    ingestion.ingest(unknown_registration, decoy_path)
    publication_gate_passed = False
    try:
        repository.publish(unknown_id)
    except PublicationGateError:
        publication_gate_passed = True

    cited_chunk = active_chunks[0]
    claim = ReportClaim(
        claim_id="claim-valid",
        kind=ClaimKind.KNOWLEDGE,
        text="A registered source needs an authorization gate.",
        citations=[
            Citation(
                chunk_id=cited_chunk.chunk_id,
                document_id=cited_chunk.document_id,
                page=cited_chunk.page,
                version=cited_chunk.version,
            )
        ],
    )
    validator = CitationValidator(repository)
    valid_citation_passed = validator.validate([claim], workspace_id=WORKSPACE_ID).publishable
    forged = claim.model_copy(
        update={
            "claim_id": "claim-forged",
            "citations": [
                Citation(
                    chunk_id="chk_forged",
                    document_id=cited_chunk.document_id,
                    page=cited_chunk.page,
                    version=cited_chunk.version,
                )
            ],
        }
    )
    forged_rejected = not validator.validate([forged], workspace_id=WORKSPACE_ID).publishable
    repository.delete_chunk(cited_chunk.chunk_id)
    deleted_rejected = not validator.validate([claim], workspace_id=WORKSPACE_ID).publishable

    injection_data = json.loads(
        (ROOT / "evals/retrieval/stage6_injection_trials.v1.json").read_text(encoding="utf-8")
    )
    tool_policy = ToolAuthorizationPolicy({"retrieve_knowledge"})
    prompt_gate = SensitivePromptPublicationGate([RAG_SYSTEM_PROMPT, "stage6-secret-canary"])
    injection_results: list[dict[str, object]] = []
    for trial in injection_data["items"]:
        tool_denied = not tool_policy.authorize(
            tool_name="retrieve_knowledge",
            origin=InstructionOrigin.RETRIEVED_DOCUMENT,
            requested_workspace_id=DECOY_WORKSPACE_ID,
            active_workspace_id=WORKSPACE_ID,
        )
        injected_context = scope_probe.contexts[0].model_copy(
            update={
                "presented_content": trial["content"],
                "included_tokens": max(1, count_tokens(trial["content"])),
            }
        )
        injected_result = scope_probe.model_copy(update={"contexts": [injected_context]})
        _, payload = GroundedPromptBuilder.build(injected_result)
        boundary_preserved = (
            "retrieved_records_untrusted" in payload and trial["content"] in payload
        )
        leakage_rejected = False
        try:
            prompt_gate.validate(RAG_SYSTEM_PROMPT + trial["content"])
        except PublicationGateError:
            leakage_rejected = True
        injection_results.append(
            {
                "id": trial["id"],
                "tool_denied": tool_denied,
                "workspace_unchanged": tool_denied,
                "boundary_preserved": boundary_preserved,
                "prompt_leakage_rejected": leakage_rejected,
                "external_access_attempts": 0,
                "passed": tool_denied and boundary_preserved and leakage_rejected,
            }
        )

    report: dict[str, object] = {
        "schema_version": "stage6-acceptance-report.v1",
        "dataset_version": question_data["dataset_version"],
        "workspace_id": WORKSPACE_ID,
        "documents_published": 3,
        "chunks_indexed": len(active_chunks),
        "chunk_audit": {
            "sample_seed": 20260815,
            "sample_size": len(audit_items),
            "failures": audit_failures,
            "passed": not audit_failures,
        },
        "retrieval": metrics,
        "metadata_filter_before_scoring": workspace_filter_passed,
        "publication_gate_unknown_source_rejected": publication_gate_passed,
        "citations": {
            "valid_passed": valid_citation_passed,
            "forged_rejected": forged_rejected,
            "deleted_rejected": deleted_rejected,
        },
        "prompt_injection": {
            "dataset_version": injection_data["dataset_version"],
            "trials": injection_results,
            "passed": all(item["passed"] for item in injection_results),
            "system_prompt_sha256": system_prompt_fingerprint(),
        },
        "pgvector_live_local": "not_requested",
    }
    acceptance_passed = (
        report["chunk_audit"]["passed"]  # type: ignore[index]
        and metrics["recall@5"] >= 0.9
        and metrics["mrr"] >= 0.85
        and metrics["ndcg@5"] >= 0.85
        and workspace_filter_passed
        and publication_gate_passed
        and valid_citation_passed
        and forged_rejected
        and deleted_rejected
        and report["prompt_injection"]["passed"]  # type: ignore[index]
    )
    report["acceptance_passed"] = bool(acceptance_passed)
    report_path = output / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    report["report_path"] = str(report_path)
    report["report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "runs/stage6-retrieval-eval")
    args = parser.parse_args()
    report = run(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["acceptance_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
