# EvidenceClass Agent

EvidenceClass Agent is an in-progress system for turning authorized, anonymized classroom
media into traceable observations, deterministic metrics, review tasks, and reports.

The repository currently contains the migrated characterization suite, strict Pydantic
contracts, the standalone deterministic Evidence Engine, the phase-3 persistence boundary, and
the phase-4 provider-neutral model gateway, the phase-5 real media pipeline, the phase-6
citable RAG boundary, the phase-7 Agent Runtime, and the phase-8 API/Worker control plane.
PostgreSQL stores business and trace metadata, Redis brokers Celery tasks, and MinIO
stores bytes behind tenant-scoped services. Explicit Job, Agent Run, and Tool Call state machines
and database-backed idempotency make duplicate and out-of-order requests testable. Fake model
calls produce a durable trace and five artifacts without network access. The repository now has an
executable Agent graph, public API, and the phase-9 original Web product foundation.

## Current boundary

- Product layer: FastAPI owns authenticated jobs, uploads, resources, progress events, reviews,
  conversations, idempotency, and retention; `apps/web` provides the original React workbench
  with an explicit Mock API boundary while local infrastructure is unavailable.
- Agent layer: versioned state, constrained planning, Tool Registry, LangGraph branching,
  checkpoints, review interruptions, claim verification, and Worker execution are implemented.
- AI capability layer: provider-neutral Protocols have Fake adapters and optional local
  faster-whisper/RapidOCR paths. OpenAI-compatible and temporary Qwen paths implement vision;
  real VLM trial execution still needs an authorized working endpoint or the optional Qwen runtime.
- Media layer: safe FFprobe inspection, decode validation, deterministic uniform/scene sampling,
  global timestamps, 16 kHz mono extraction, energy VAD, ASR merge, OCR provenance/thresholding,
  six-label visual observations, and idempotent segment merge are implemented.
- Retrieval layer: register-first source governance, Markdown/TXT/text-PDF parsing, hierarchical
  stable chunks, code-owned workspace/source/version filters, pgvector Top-20 retrieval, optional
  Top-5 reranking, context budgets, injection boundaries, and citation publication gates are
  implemented. The offline baseline is deterministic and is not a learned embedding quality claim.
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

## Phase-5 real media pipeline

Bootstrap ignored project-local FFmpeg/FFprobe binaries, then run the required offline gate:

```powershell
.\scripts\setup-media-tools.ps1
.\scripts\accept-stage-5.ps1
```

The gate generates only original synthetic media. It covers a normal ten-second video, no-audio,
corruption, text disguised as video, Unicode/space paths, oversize metadata, reproducible frame
hashes, shared dual-camera time, VAD/ASR/OCR/VLM Fake wiring, thirty visual trials, and shuffled,
duplicated, or missing long-video segments.

Optional real local ASR/OCR acceptance requires the heavy `media-models` extra and an explicit
faster-whisper model. No model is selected or downloaded by default:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,media-models]"
.\scripts\accept-stage-5.ps1 -RunRealMediaModels -WhisperModel tiny
```

The real evaluator uses an authorized five-minute synthetic speech fixture and synthetic
slide/board/no-text images. Its CER and OCR errors are functional evidence for those fixtures,
not a classroom accuracy claim. See `docs/stage-5-acceptance.md` for current results and the
remaining real-VLM blocker.

## Phase-6 citable RAG

Run the complete offline gate without a model download or Docker:

```powershell
.\scripts\accept-stage-6.ps1
```

The gate parses original Markdown and generated text-PDF sources, audits a seeded random sample
of 30 chunks, evaluates 40 retrieval questions with Recall@5/MRR/nDCG@5, checks tenant/source/
version filtering, executes 10 prompt-injection trials, and proves that unknown sources plus
forged or deleted citations cannot pass publication. The local feature-hashing embedding and
lexical reranker make CI deterministic; production SQL uses a 384-dimensional pgvector column and
an HNSW cosine index.

Live pgvector acceptance is opt-in and requires the Compose services plus `DATABASE_URL`:

```powershell
.\scripts\accept-stage-3.ps1
.\scripts\accept-stage-6.ps1 -RunPgVector
```

The GitHub infrastructure job uses a pinned pgvector PostgreSQL image and runs the live migration,
extension, SQL ingestion, metadata-filtered cosine query, and downgrade/upgrade test. See
`docs/stage-6-acceptance.md` for evidence boundaries and the synthetic-set limitation.

## Phase-7 Agent Runtime

Run the runtime, persistence, migration, dependency, and full-regression gate:

```powershell
.\scripts\accept-stage-7.ps1 -RunFull
```

The runtime uses typed `AgentState`, a policy-aware Tool Registry, a structured planner, and a real
LangGraph `StateGraph` with conditional audio/image/transcript paths. Explicit budgets stop loops;
checkpoint records preserve the last successful state; high-risk observations enter a durable
human-review state; and publication requires evidence, citation, number, scope, and cross-artifact
claim checks. The offline acceptance includes three distinct graph trajectories, worker-restart
recovery without a repeated observation call, authorized single-decision review, and twenty
deliberately polluted drafts.

The default path remains deterministic and uses no paid model call. See
`docs/stage-7-acceptance.md` for the exact runtime evidence and remaining external skips.

## Phase-8 asynchronous Worker and API

Run the API/Worker, upload, Outbox, SSE, cancellation, OpenAPI, migration, and regression gate:

```powershell
.\scripts\accept-stage-8.ps1 -RunFull
```

Start the local API with the project environment:

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

`POST /jobs/{id}/start` commits an Agent Run and transactional Outbox record before publishing a
Celery or local task. Workers claim persisted runs, write SQL checkpoints and append-only progress
events, and reject duplicate delivery. Upload completion verifies workspace ownership, expiry,
size, MIME signature, and SHA-256. SSE honors `Last-Event-ID`; cancel, retry, and rerun preserve
different audit semantics. GitHub Actions runs a live Celery/PostgreSQL/Redis integration test in
addition to the offline Windows suite. See `docs/stage-8-acceptance.md` for limits and evidence.

## Phase-9 original Web product

The new product surface is in `apps/web`; it does not reuse the old application's assets or CSS.
It includes the task centre, new analysis flow, Agent Run timeline, evidence browser, review
workbench, result and evidence-first Q&A pages, responsive tokens, and Playwright smoke tests.
It defaults to deterministic Mock API data so UI states can be exercised without Docker:

```powershell
Set-Location -LiteralPath ".\apps\web"
npm install
npm run dev
npm run build
npm run test:e2e
```

Set `VITE_USE_MOCK_API=false` and `VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1` when the
phase-8 API is running. The current machine has not installed the Node dependency graph because
the registry is unreachable with the user's ladder disabled; this is recorded in the development
log and is not reported as a build pass.

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

See `docs/stage-2-acceptance.md` through `docs/stage-8-acceptance.md` for executable acceptance
matrices and honest external blockers.

Only synthetic or explicitly authorized fixtures may enter this repository. See
`PROVENANCE.md` for the migration ledger and `SECURITY.md` for reporting instructions.
