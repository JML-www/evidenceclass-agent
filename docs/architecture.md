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

The current milestone completes the code boundary for tutorial phase 3. The deterministic engine
remains independent, while SQLAlchemy models and Alembic own durable metadata. PostgreSQL,
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

The current `AgentState` is a checkpoint contract, not an executable Agent. Model adapters, Agent
graph execution, API routes, Workers, and the Web product remain later phases.
