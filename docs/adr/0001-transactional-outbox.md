# ADR 0001 - Transactional Outbox for the API-to-Worker hand-off

- Status: Accepted
- Date: 2026-09-12
- Phase: 8 (asynchronous Worker and public API)
- Supersedes: none

## Context

`POST /api/v1/jobs/{job_id}/start` has to do two things that live in different failure domains:

1. Persist the business state change - flip the job to `QUEUED` and create the active `AgentRun` row.
2. Hand the run to an execution boundary - enqueue a Celery task (or the deterministic in-process
   task used by the offline acceptance).

The database is transactional. The broker is not part of that transaction. A naive implementation
therefore has exactly one of two bugs, and there is no way to pick a "safe" one:

- **Write first, enqueue second.** If the process dies between the two, the job is `QUEUED` with a
  run that nothing will ever execute. The user sees an analysis that never starts and never fails.
- **Enqueue first, write second.** If the write rolls back after a successful enqueue, a worker
  picks up a task for a run that does not exist. The worker either crashes on a missing row or, if
  it is written defensively, silently drops real work.

Both variants also lose the ordering guarantee: two rapid `start` calls could enqueue in the
opposite order to their commits, so a retry could be delivered before the run it retries.

There is a second, subtler requirement. The system must stay **idempotent** under duplicate
delivery: Celery's at-least-once delivery means the same task can arrive twice, and phase 7 already
requires the graph to survive a replayed run.

## Decision

Use a **transactional outbox** in the primary database.

### Write path

`start_job` writes the `AgentRun` row *and* the corresponding `outbox_events` row inside **one**
transaction. Either both rows exist or neither does. The HTTP handler returns as soon as that
transaction commits; it does **not** wait for the worker, which is what makes the `queued`
response a bounded-latency operation (asserted at < 500 ms by
`tests/unit/api/test_stage8_queue_latency.py`).

The outbox row is the durable record of intent. Delivery is a separate, retryable concern.

### Table

`outbox_events` (`packages/persistence/models.py`):

| column | type | meaning |
| --- | --- | --- |
| `id` | `Uuid` PK | event identity, stable across retries |
| `topic` | `String(128)` | routing key consumed by the publisher |
| `aggregate_id` | `Uuid` | the `AgentRun` this event is about |
| `payload_json` | `JSON` | publisher input; never contains secrets |
| `status` | `String(32)` | `PENDING` → `PUBLISHING` → `PUBLISHED` |
| `attempts` | `Integer` | incremented on every claim, for backoff and alerting |
| `created_at` | `DateTime(tz)` | ordering key; the publisher drains oldest-first |
| `published_at` | `DateTime(tz)` | set once the broker accepted the message |
| `last_error` | `Text` | truncated publisher failure, for operators |

Index `ix_outbox_events_status_created (status, created_at)` exists specifically to make the
"oldest pending batch" query cheap as the table grows.

### Delivery path

`OutboxPublisher.publish_pending(send, limit=50)` (`packages/persistence/outbox.py`):

1. Read a batch of `PENDING` rows ordered by `created_at`, oldest first.
2. For each row, open its **own** short transaction and claim it by moving
   `PENDING` → `PUBLISHING` and incrementing `attempts`. Claiming in a separate transaction is what
   keeps the claim visible to other publishers even if this process dies mid-send.
3. Call `send(topic, aggregate_id, payload)` outside any transaction.
4. On success, mark `PUBLISHED` and stamp `published_at`.
5. On any exception, return the row to `PENDING` and store `str(exc)[:1000]` in `last_error`. The
   next drain retries it.

Re-claiming requires the row to still be `PENDING`, so two publishers racing on the same batch
cannot both deliver it.

### Idempotency and ordering

- The outbox guarantees **at-least-once** delivery, never exactly-once. Exactly-once is not
  achievable across a database and a broker without distributed transactions, and we deliberately
  do not pretend otherwise.
- Duplicate delivery is absorbed downstream, not in the outbox: the worker claims only
  `QUEUED`/`INITIALIZING` work, ignores a replayed message, and skips a late completion after a
  cancellation. `tests/unit/persistence/test_stage8_outbox.py` and the live Celery integration test
  (`scripts/accept-stage-8.ps1 -RunCelery`) cover the duplicate-delivery path.
- Ordering within one aggregate is preserved because the batch is drained oldest-first and the
  worker's claim is state-gated.

### Failure modes we accept

- A row can be stuck in `PUBLISHING` if the process dies between claim and send. It is not
  auto-recovered today; it is visible as a non-terminal row and is an operator action. A lease
  column plus a timeout sweeper is the natural next step if this becomes a real operational cost.
- `send` is synchronous inside the drain loop, so a slow broker slows the whole batch. `limit`
  bounds the blast radius per call.

## Alternatives considered

### Direct dual write (write, then enqueue, no outbox)

Rejected. It is precisely the failure described in *Context*, and the failure is silent - the job
simply never runs.

### Publish-then-commit

Rejected for the same reason from the other side: a rolled-back commit leaves a live broker message
pointing at a run that does not exist.

### Change Data Capture (Debezium, logical replication)

Rejected for this project. It is operationally heavier (a connector runtime, a replication slot, its
own HA story) and it removes the explicit `attempts` / `last_error` / `published_at` observability
that the phase-12 reliability work relies on. It also makes the offline acceptance story much
harder, because SQLite cannot participate.

### Event sourcing as the primary model

Rejected as over-scoped. The aggregate here is a job lifecycle, not a domain where replaying the
full event history is the source of truth. Phase 7 already checkpoints graph state in SQL; adding a
second, competing history would create two answers to "what happened".

### Enqueue from a background scheduler that polls the `jobs` table

Rejected. It collapses the hand-off into "state changed, guess what work to do", which is exactly
the coupling the outbox removes. The outbox row is an explicit, versioned intent; a table-polling
scheduler would have to re-derive it.

## Consequences

**Positive**

- The API can return `queued` quickly and truthfully, because durability no longer depends on the
  broker being reachable.
- Broker outages degrade into a growing `PENDING` backlog rather than lost work. The backlog size
  and `attempts` distribution are promotable to metrics.
- Retry, ordering, and audit all read from one table, which makes failure injection
  (`packages/observability/faults.py`) able to reproduce broker-unavailable and mid-flight-worker
  exit deterministically.

**Negative**

- At-least-once delivery means every consumer must be idempotent. This is a real constraint on
  future consumers, not a theoretical one.
- The outbox table grows monotonically. Published rows need a retention policy; today they are kept
  as an audit trail.
- One more moving part in the start path, and one more place where a stuck row can hide.

## Verification

- `tests/unit/persistence/test_stage8_outbox.py` - claim, retry-after-failure, and status
  transitions.
- `tests/unit/api/test_stage8_queue_latency.py` - the start path returns `queued` in under 500 ms
  even when the execution boundary is deliberately slow.
- `tests/integration/test_stage8_celery.py` - live Redis + PostgreSQL: deliver, complete, redeliver,
  expect `SKIPPED`.
- `scripts/accept-stage-8.ps1 -RunCelery` runs the live variant.
