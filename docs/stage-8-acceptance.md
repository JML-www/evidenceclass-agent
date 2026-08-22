# Phase-8 acceptance: asynchronous Worker and public API

Phase 8 exposes the phase-7 runtime through a FastAPI control plane and a durable Worker boundary.
The default acceptance uses SQLite, an in-memory object store, and a manual in-process queue so CI
can prove contracts without paid models. The infrastructure GitHub Actions job separately starts a
real Celery worker against Redis and PostgreSQL.

## Implemented boundary

- `POST /api/v1/auth/login` issues an HMAC-signed bearer token after PBKDF2 password verification.
- Every tenant resource query checks workspace membership before returning a resource or upload URL.
- Requests and declared responses use strict Pydantic models. Stable failures contain `code`,
  `message`, `retryable`, `request_id`, and `details`; validation never exposes a Python traceback.
- Job creation and start remain database-idempotent. Start writes the Agent Run and Outbox event in
  one transaction; the publisher then enqueues a named Celery task or deterministic local task.
- The Worker claims only `QUEUED`/`INITIALIZING` work, executes the SQL-checkpointed Agent graph,
  appends step events, and ignores duplicate deliveries and late completion after cancellation.
- Upload initialization returns a presigned URL. Completion reconstructs a server-owned ticket and
  validates ownership, expiry, nonempty size, maximum size, MIME, byte signature, and SHA-256.
- SSE replays the append-only event log after `Last-Event-ID`, so reconnects do not depend on an
  API-process buffer. Clients de-duplicate by the monotonically increasing event ID.
- Cancel, retry, and rerun have distinct semantics. Cancel revokes the task where possible; retry
  reuses the failed run/checkpoint; rerun creates a new run and preserves old runs and artifacts.
- Run-scoped cleanup terminates registered child processes and removes only that run's temporary
  directory. The focused test proves a live child exits and an adjacent file remains untouched.

## Required offline command

```powershell
.\scripts\accept-stage-8.ps1 -RunFull
```

This runs Ruff; API/auth/tenant/upload/Worker/Outbox/SSE/cancel/OpenAPI tests; the complete Alembic
cycle; `pip check`; the full regression suite; and `compileall`.

## Live Celery command

With migrated PostgreSQL and a reachable Redis broker configured in `DATABASE_URL` and `REDIS_URL`:

```powershell
.\scripts\accept-stage-8.ps1 -RunCelery
```

The live test starts a Celery worker, delivers the stored Run, waits for `COMPLETED`, redelivers the
same message, expects `SKIPPED`, and verifies the persisted Job is `SUCCEEDED`. GitHub Actions runs
this test in the infrastructure job.

## Honest limits

- Local acceptance does not prove production throughput or a multi-host broker failure recovery.
- Celery revoke can stop a claimed task, while individual FFmpeg/model adapters must register any
  child process with the run resource manager to receive forced termination.
- SSE is implemented as replay plus heartbeat per request; production deployments should add a
  notification channel to reduce polling latency without changing the event-log contract.
- Authentication is a minimal project-owned bearer-token boundary, not SSO, OAuth, account
  recovery, rate limiting, or the complete phase-13 RBAC/privacy program.
