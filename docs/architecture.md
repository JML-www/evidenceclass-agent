# Architecture boundary

EvidenceClass Agent uses a modular monolith plus an asynchronous worker. The four logical
layers remain separate even while they live in one repository.

| Layer | Owns | Must not own |
|---|---|---|
| Product | Upload, jobs, progress, review, reports, and scoped Q&A | Metric calculation |
| Agent | Planning, tool selection, branches, recovery, and human interruption | Deterministic scoring formulas |
| AI capability | ASR, OCR, VLM, LLM, embedding, and reranking adapters | Business authorization |
| Deterministic | Schema, validation, metrics, evidence, hashes, and artifact consistency | Guesses about missing facts |

Planned request flow:

```text
Web -> API/control plane -> asynchronous worker -> Agent runtime
                                         |-> model gateway
                                         |-> retrieval
                                         `-> deterministic evidence engine
```

The current milestone implements the offline code boundary for tutorial phase 4. The deterministic
engine remains independent, while SQLAlchemy models and Alembic own durable metadata. PostgreSQL,
password-protected Redis, and MinIO have pinned Compose services, health checks, and named volumes.

Three lifecycle levels are deliberately independent:

```text
Job       : CREATED -> UPLOADING -> QUEUED -> RUNNING -> NEEDS_REVIEW -> SUCCEEDED
Agent Run : INITIALIZING -> INSPECTING -> PLANNING -> EXECUTING -> VERIFYING -> COMPLETED
Tool Call : PENDING -> STARTED -> RETRYING -> SUCCEEDED
```

Failure, cancellation, timeout, and human-review branches are explicit in
`packages/agent_runtime/state_machines.py`. Application code changes Job and Agent Run status only
through `JobLifecycleService`; a cancelled Job ignores late Worker completion. The tutorial's
phrase “WAITING_HUMAN -> RUNNING” maps to `WAITING_HUMAN -> EXECUTING`, because `EXECUTING` is the
documented Agent Run execution state and `RUNNING` belongs to the separate Job lifecycle.

Idempotency reservations use the unique tuple `(workspace_id, endpoint, idempotency_key)` and a
canonical request SHA-256. Same key and same request replays the stored response; same key and a
different request raises a stable 409 conflict. A second database constraint prevents more than
one active Agent Run per Job even when callers use different idempotency keys.

Object keys contain workspace, Job, category, and random IDs, never client absolute paths or
original filenames. Upload completion verifies size, declared MIME, byte signature, and SHA-256
before a `media_assets` row exists. Artifact publication copies all versioned objects first and
writes the manifest last, so consumers never discover a partial set. SQL authorization is checked
before presigned download URLs are issued, and soft deletion plus `purge_after` governs cleanup.

The model gateway exposes six structural Protocols instead of supplier SDKs: Chat, Vision, ASR,
OCR, Embedding, and Reranker. Every successful result carries provider, model revision, prompt and
config versions, latency, tokens, characters, audio seconds, cost-or-unknown, a raw object
reference, and a validated parsed result. The OpenAI SDK is confined to one adapter module; Fake
and local-Qwen adapters implement the same contracts.

`ResilientModelExecutor` owns bounded exponential backoff with jitter, at most one Schema repair,
local rate limiting, a provider/model circuit breaker, and hard preflight reservations for call,
token, cost, and wall-time budgets. Authentication, permission, content-policy, and deterministic
semantic failures are not retried. Every attempt writes sanitized accounting to `model_calls`;
prompts, image bytes, complete transcripts, raw response bodies, and keys are absent from SQL logs.

The temporary `LocalQwen35Adapter` proves that the gateway is not tied to OpenAI. It targets the
user-owned multimodal Qwen3.5-0.8B checkpoint only when an isolated optional GPU runtime is
installed. The word “temporary” is part of its provider and evaluation identifiers. It is not the
final model selection, and its local execution cost records external API cost as zero while
excluding electricity and hardware cost.

The current `AgentState` is still a checkpoint contract, not an executable production Agent.
`FakeStage4AcceptanceHarness` proves Job -> trace -> model call -> deterministic engine -> five
artifacts only for integration acceptance. Agent graph execution, API routes, Workers, and the Web
product remain later phases.
