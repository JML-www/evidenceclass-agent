# Phase 3 acceptance record

This record maps tutorial steps 3.1 through 3.5 to executable evidence. It does not claim that
HTTP routes, a queue Worker, model calls, or an executable Agent graph exist yet.

## Step 3.1: PostgreSQL, Redis, and MinIO

`deploy/docker-compose.yml` pins all three images, declares health checks, and uses named volumes.
Credentials are required through the ignored `.env`; `.env.example` contains placeholders only.
`scripts/accept-stage-3.ps1` writes a unique sentinel to every service, restarts all containers,
and verifies that PostgreSQL, Redis, and MinIO retained it.

The live test is `tests/integration/test_stage3_infrastructure.py`. It is skipped during offline
unit runs and enabled only with `RUN_STAGE3_INFRA_TESTS=1`. GitHub Actions starts real service
containers and enables it, so a missing local Docker installation cannot be confused with a
passing live-infrastructure check.

## Step 3.2: schema and reversible migration

The first Alembic revision creates the tutorial's complete minimum business schema plus the
idempotency ledger: users, workspaces and membership; Jobs and media; Agent Runs, Steps, Tool Calls
and Model Calls; observations, evidence, review items and artifacts; knowledge documents and
chunks; conversations and messages; evaluation runs; and idempotency records.

`tests/unit/persistence/test_migrations.py` starts with an empty database, upgrades to `head`,
checks every required table, verifies metadata has no pending migration, downgrades to `base`, and
upgrades again. The live integration test repeats downgrade and upgrade against PostgreSQL.

## Step 3.3: explicit state machines

The transition tables in `packages/agent_runtime/state_machines.py` are the only lifecycle rule
source. Parameterized tests execute every table row, followed by focused invariant tests:

- `SUCCEEDED -> RUNNING` is illegal.
- a late Worker success or failure leaves a cancelled Job cancelled.
- a human-waiting Agent Run cannot resume without an approved or rejected review decision.
- a completed or errored Agent Run releases its database `active_slot`.
- a repeated start returns the existing run; the unique active slot is a second database guard.

Job `RUNNING` and Agent Run `EXECUTING` remain separate on purpose. Versioned `AgentState` stores
only small structured state and object IDs; an unknown `raw_video` field fails validation.

## Step 3.4: idempotency

`IdempotencyService` reserves `(workspace_id, endpoint, key)` under a database unique constraint,
saves a canonical request hash and response reference, and returns the stored response for an
identical replay. Reusing the key with another request raises `IdempotencyConflict` with status
code 409.

Two thread-pool tests each submit 50 concurrent identical requests. One produces exactly one Job;
the other produces exactly one active Agent Run and one run ID. A later start with a different key
still returns that active run.

## Step 3.5: tenant-scoped object storage

`ObjectStorageService` issues presigned uploads to temporary random keys. Completion rechecks byte
count, maximum size, MIME header, byte signature, and SHA-256 before creating a formal asset. A
workspace-scoped SQL query runs before every presigned download, so an unauthorized workspace
receives the same not-found boundary as a missing asset.

The current duplicate policy is explicit retention: identical hashes may create separate asset
rows and random object keys. Artifact objects are fully copied before the JSON manifest is written;
the manifest is the publication pointer. Deletion is soft until `purge_after`, then both temporary
and formal prefixes plus SQL object records are removed.

## Acceptance commands

Offline and deterministic checks:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests\unit\persistence\test_idempotency.py -q
.\.venv\Scripts\python.exe -m pytest tests\unit\persistence\test_migrations.py -q
git diff --check
```

Live infrastructure, restart persistence, and PostgreSQL migration cycle:

```powershell
Copy-Item .env.example .env
# Replace every placeholder in .env first.
.\scripts\accept-stage-3.ps1
```

The live command must not be reported as passed when Docker is unavailable. The remote
`phase-3-infrastructure` Actions job is the post-push confirmation for that environment.
