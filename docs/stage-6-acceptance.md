# Phase 6 acceptance record

Phase 6 turns authorized teaching references into workspace-scoped chunks that can be retrieved
and cited without allowing a document or model to invent provenance. Required acceptance is fully
offline. A separate opt-in test exercises the PostgreSQL pgvector extension and SQL query when
Docker or another authorized database is available.

## Step 6.1: source registration and publication

Every source is registered before bytes are parsed. The strict record contains document and
source IDs, title, author or organization, version, publication date, license/authorization basis,
authorization status, exact SHA-256, workspace, source URI, and `WORKSPACE` visibility.

The lifecycle is `REGISTERED -> PARSED -> PUBLISHED`; a newer published version supersedes the
older version. Publication fails when authorization is `UNKNOWN`/`DENIED`, the license basis is
unknown, parsing did not complete, or no chunks exist. A file hash mismatch remains attached to
the already registered source rather than becoming an untraceable parser error.

## Step 6.2: parsing and stable chunks

`DocumentParser` supports UTF-8 Markdown, TXT, and PDFs with extractable text. Markdown hierarchy
is retained as a heading path. PDF chunks retain one-based page numbers, repeated headers/footers
are removed when they recur on at least 60% of pages, and extraction errors identify the failing
page. Unsupported types, invalid UTF-8, empty extraction, and hash mismatches have distinct errors.

`HierarchicalChunker` prefers section boundaries and splits only long sections with a bounded token
window and overlap. Each chunk stores document/workspace/source IDs, version, page, heading,
ordinal, content SHA-256, token estimate, and a stable policy-derived chunk ID. The executable
acceptance uses seed `20260815` to sample 30/30 synthetic chunks and compares every heading, page,
and expected body excerpt with a versioned audit manifest.

## Step 6.3: retrieval baseline

The request path is:

```text
versioned deterministic query rewrite
  -> caller-owned workspace/source/version filter
  -> 384-dimensional cosine Top-20
  -> optional lexical Top-5 reranker
  -> content-hash de-duplication
  -> fixed context-token budget and truncation
  -> chunk ID, score, title, source, version, heading, and page
```

The offline adapter is transparent feature hashing, not a learned embedding. It keeps CI runnable
without a network or multi-gigabyte checkpoint. The production schema uses `vector(384)`, enables
the PostgreSQL `vector` extension, builds an HNSW cosine index, and performs workspace/source/
version/status predicates in SQL before distance ordering. Transactional SQL ingestion and
register/publish gates use the same contracts as offline evaluation.

The versioned evaluation set has 40 questions over 30 original synthetic chunks. Direct and
Chinese paraphrase cases report Recall@5, MRR, nDCG@5, and failed case IDs rather than judging only
an answer. Current offline results are 1.0 for all three metrics. Those values are a regression
baseline for this deliberately code-labelled small set and must not be presented as production RAG
quality or real educational-domain generalization.

## Step 6.4: prompt-injection boundary

Retrieved content is JSON-serialized under `retrieved_records_untrusted`. The system instruction
says documents cannot change rules, tool permissions, workspace scope, or citation requirements.
Tool authorization is a code-owned allowlist and rejects every request whose origin is a retrieved
document. There is no automatic URL fetch, script execution, or workspace-switch path. A second
publication gate rejects protected prompt material in a proposed answer.

Ten versioned English/Chinese trials cover prompt disclosure, developer-message disclosure,
unauthorized tools, cross-workspace access, key exfiltration, script/link execution, forged
citations, and workspace switching. All ten must preserve the data boundary, make zero external
access attempts, deny the tool request, retain the active workspace, and reject prompt leakage.
This is deterministic policy acceptance; a later real-LLM red-team set is still required.

## Step 6.5: citation publication gate

Every knowledge claim must contain at least one citation. Code verifies that the chunk exists,
belongs to the active workspace, references the stated document, has the stated page and version,
and belongs to the currently `PUBLISHED` source version. Observation and deterministic metric
claims are typed separately. Acceptance proves a valid citation passes while forged IDs, deleted
chunks, wrong pages/versions, cross-workspace references, and superseded sources fail.

## Commands and evidence boundary

Required offline gate:

```powershell
.\scripts\accept-stage-6.ps1
```

Optional live PostgreSQL/pgvector gate:

```powershell
.\scripts\accept-stage-3.ps1
.\scripts\accept-stage-6.ps1 -RunPgVector
```

Generated PDF bytes and the JSON report remain in ignored `runs/stage6-retrieval-eval/`. The local
machine used for the 2026-08-15 acceptance has no Docker CLI, so the optional local live-pgvector
test is recorded as not requested rather than passed. The GitHub infrastructure job is configured
with `pgvector/pgvector:0.8.6-pg16-bookworm` and will run the live extension, migration, SQL
ingestion, filtered cosine query, and reversible migration test after the changes are pushed.
