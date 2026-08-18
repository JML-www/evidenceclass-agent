# Development log

Detailed personal learning logs are kept outside the public repository. This index records the
public milestones that can be verified from commits, tests, and CI:

- 2026-08-05: initialized the clean-room repository and migration boundary.
- 2026-08-06: completed tutorial step 2.1 with a 14-test characterization baseline.
- 2026-08-07: completed tutorial step 2.2 contracts v0.1 and cross-field validation locally;
  remote CI and merge status remain visible in GitHub history.
- 2026-08-07: completed tutorial steps 2.3 through 2.5 locally: modular deterministic engine,
  reusable service and installable CLI, five consistent artifacts, and 1000-example property
  testing. The personal detailed log is stored on the Desktop rather than in this repository.
- 2026-08-09: completed the phase-3 persistence boundary: pinned Compose infrastructure,
  reversible Alembic schema, three explicit lifecycle machines, 50-way idempotency tests,
  tenant-scoped object storage, manifest-last publication, retention cleanup, and live-infrastructure
  CI gate. Local Docker-dependent acceptance remains separately visible from offline tests.
- 2026-08-10: implemented the phase-4 offline model gateway: six provider-neutral capability
  Protocols, all-capability Fake and fault scenarios, a no-network five-artifact harness, one
  OpenAI-compatible Chat/Vision adapter, an optional temporary local-Qwen adapter, durable model
  attempt accounting, and bounded reliability policies. The available remote endpoint rejected
  generation with HTTP 403, while the optional GPU runtime download was too slow to finish in this
  session; both real-model attempts remain explicit pending evidence rather than claimed success.
- 2026-08-11: completed the phase-5 real-media pipeline: bounded FFprobe/FFmpeg validation,
  reproducible globally timestamped sampling, ASR/OCR/limited-VLM evidence contracts, and
  idempotent segment merging. The synthetic-media gate and local faster-whisper/RapidOCR evaluation
  passed; real-VLM accuracy remains unclaimed until a working authorized adapter is available.
- 2026-08-15: completed the phase-6 citable-RAG boundary: source authorization and publication
  lifecycle, Markdown/TXT/text-PDF parsing, stable heading/page chunks, pgvector schema and scoped
  Top-K retrieval, deterministic reranking and context budgets, prompt-injection boundaries, and
  citation publication validation. The 30-chunk audit, 40-question synthetic retrieval set, and
  10 injection trials pass offline; local live pgvector remains opt-in where Docker is unavailable.
- 2026-08-15: GitHub workflow run 9 exposed an Alembic drift between the PostgreSQL-only HNSW
  migration and ORM metadata. Declared the index in the model, excluded it only from SQLite
  autogenerate checks, added dialect SQL assertions, and split infrastructure from pgvector CI
  steps. The corrected local gate passes 142 tests; the live result remains pending the next push.
- 2026-08-18: completed the phase-7 Agent Runtime: a policy-aware Tool Registry, constrained
  structured planner, real LangGraph conditional graph, bounded repair/model/tool budgets,
  checkpoint/restart semantics, durable plan and prompt metadata, authorized single-decision
  human review, and an evidence-first claim publication gate. Three graph trajectories, restart
  reuse, SQLite migration cycles, and twenty polluted report drafts pass locally. The complete
  deterministic suite passes 180 tests; four explicit external-runtime tests remain skipped.
