# EvidenceClass Agent

EvidenceClass Agent is an in-progress system for turning authorized, anonymized classroom
media into traceable observations, deterministic metrics, review tasks, and reports.

The repository currently contains the migrated characterization suite, strict Pydantic
contracts, the standalone deterministic Evidence Engine, the phase-3 persistence boundary, and
the phase-4 provider-neutral model gateway.
PostgreSQL stores business and trace metadata, Redis is reserved for later queue work, and MinIO
stores bytes behind tenant-scoped services. Explicit Job, Agent Run, and Tool Call state machines
and database-backed idempotency make duplicate and out-of-order requests testable. Fake model
calls now produce a durable trace and five artifacts without network access. It does not yet
contain an executable production Agent graph, an API, or a Web application.

## Current boundary

- Product layer: persistence services now own jobs, upload metadata, idempotency, and retention;
  HTTP endpoints and the Web product remain future work.
- Agent layer: versioned checkpoint state and lifecycle transitions are implemented; planning,
  tool selection, branching, and graph execution remain future work.
- AI capability layer: phase 4 implements replaceable Chat, VLM, ASR, OCR, Embedding, and Reranker
  Protocols; all-capability Fake adapters; one OpenAI-compatible Chat/Vision path; and an optional
  temporary local Qwen3.5 path. Real ASR, OCR, Embedding, and Reranker providers remain later work.
- Deterministic layer: phase 2 is implemented. Pure validation, metrics, sourced scoring,
  evidence IDs, result construction, presentation-only renderers, a reusable service, and the
  CLI own validation, metrics, evidence, hashes, and artifact consistency.

## Phase-3 infrastructure

Copy `.env.example` to the ignored `.env`, replace every placeholder, then run the complete
health, persistence, migration, and integration acceptance:

```powershell
.\scripts\accept-stage-3.ps1
```

The script starts PostgreSQL, password-protected Redis, and MinIO, verifies all health checks,
runs an Alembic upgrade/downgrade/upgrade cycle, restarts all three containers, checks that each
named volume retained a unique sentinel, and runs the live integration test. It deliberately
leaves containers and volumes running for inspection.

## Phase-4 model gateway

Run the complete offline acceptance, including all Fake failure scenarios, no-network Job trace,
five artifacts, retries, one Schema repair, rate limit, circuit breaker, hard call/token/cost/time
budgets, model-call persistence, and reversible migration:

```powershell
.\scripts\accept-stage-4.ps1
```

The optional local Qwen3.5 checkpoint is a temporary functional model, not the final model choice
and not evidence of accuracy. Set `LOCAL_QWEN_MODEL_PATH` to a checkpoint outside this repository;
its isolated multi-gigabyte runtime is deliberately excluded from normal setup and Git:

```powershell
$env:LOCAL_QWEN_MODEL_PATH = "C:\path\to\Qwen3.5-0.8B"
.\scripts\setup-local-qwen.ps1
.\scripts\accept-stage-4.ps1 -RunLocalQwen
```

The first command may take a long time because it installs GPU PyTorch. Failure or absence of this
optional runtime does not block Fake CI, phase-5 media work, or later Agent orchestration.

## Development setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

## Standalone engine CLI

The installed command calls `EvidenceEngineService`, the same in-process boundary that a future
Worker or Agent tool will use:

```powershell
evidenceclass engine analyze `
  ".\fixtures\structured\image-demo.json" `
  --output ".\runs\image-demo"
```

On success, the command prints the analysis mode, elapsed time, five artifact paths, byte sizes,
and SHA-256 hashes. Invalid input exits nonzero. The output writer replaces only the five managed
artifact names and preserves unrelated files in the destination directory.

See `docs/stage-2-acceptance.md`, `docs/stage-3-acceptance.md`, and
`docs/stage-4-acceptance.md` for the executable acceptance matrices and honest external blockers.

Only synthetic or explicitly authorized fixtures may enter this repository. See
`PROVENANCE.md` for the migration ledger and `SECURITY.md` for reporting instructions.
