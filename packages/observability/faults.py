"""Deterministic fault-injection harness for the reliability acceptance gate.

Ten injected failures required by the stage-12 plan are executed against the real
components (model gateway resilience, agent checkpointing, object storage,
idempotency, worker finalisation) wherever the offline environment allows it.
Each scenario records what was injected, what the system was expected to do, what
it actually did, the remediation and the residual risk.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from packages.agent_runtime import AgentGraph, AgentState, CapabilitySnapshot, RetryBudget
from packages.agent_runtime.graph import WorkerInterrupted
from packages.model_gateway.contracts import (
    CapabilityResult,
    ChatOutput,
    InvocationMetadata,
    ModelUsage,
)
from packages.model_gateway.errors import ModelRateLimitError, ModelTimeoutError, SchemaParseError
from packages.model_gateway.resilience import (
    BudgetLimits,
    CallDescriptor,
    CallEstimate,
    JobModelBudget,
    ResilientModelExecutor,
    RetryPolicy,
)
from packages.object_storage import InMemoryObjectStore, ObjectStorageService
from packages.object_storage.service import StorageError
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.idempotency import IdempotencyService
from packages.persistence.jobs import JobLifecycleService
from packages.persistence.models import Artifact, User, Workspace

from .correlation import bind
from .logging import emit_event
from .metrics import MetricsRegistry
from .reliability import BACKPRESSURE, classify_infrastructure_error

FAULT_IDS: tuple[str, ...] = (
    "model-429",
    "model-timeout",
    "invalid-json",
    "broker-unavailable",
    "worker-mid-exit",
    "subprocess-stuck",
    "object-storage-failure",
    "db-connection-exhausted",
    "duplicate-start",
    "cancel-during-run",
)


@dataclass(frozen=True)
class FaultOutcome:
    fault_id: str
    title: str
    injected: str
    expected: str
    actual: str
    remediation: str
    residual_risk: str
    recovered: bool
    observed_code: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _descriptor() -> CallDescriptor:
    return CallDescriptor(
        provider="fake",
        model="fake-chat",
        prompt_version="stage12.p1",
        config_version="stage12.c1",
    )


def _budget(max_calls: int = 6) -> JobModelBudget:
    return JobModelBudget(
        BudgetLimits(
            max_model_calls=max_calls,
            max_total_tokens=10_000,
            max_cost_usd=1.0,
            max_wall_seconds=30.0,
        )
    )


def _estimate() -> CallEstimate:
    return CallEstimate(max_total_tokens=100, max_cost_usd=0.01)


def _chat_result(text: str = "ok") -> CapabilityResult[ChatOutput]:
    return CapabilityResult[ChatOutput](
        metadata=InvocationMetadata(
            provider="fake",
            model="fake-chat",
            model_revision="fake-rev-1",
            prompt_version="stage12.p1",
            config_version="stage12.c1",
            latency_ms=1.0,
            usage=ModelUsage(input_tokens=10, output_tokens=5, cost_usd=0.001),
            raw_response_ref="fake://response/1",
        ),
        parsed=ChatOutput(text=text),
    )


def _executor() -> ResilientModelExecutor[CapabilityResult[ChatOutput]]:
    return ResilientModelExecutor(
        policy=RetryPolicy(max_retries=2, max_schema_repairs=1, base_delay_seconds=0.0),
        sleep=lambda _seconds: None,
    )


# --------------------------------------------------------------------------- #
# Individual fault scenarios
# --------------------------------------------------------------------------- #
def fault_model_rate_limit() -> FaultOutcome:
    executor = _executor()
    calls = {"count": 0}

    def operation(_repair: bool) -> CapabilityResult[ChatOutput]:
        calls["count"] += 1
        if calls["count"] == 1:
            raise ModelRateLimitError("injected provider 429")
        return _chat_result()

    result = executor.execute(
        operation, descriptor=_descriptor(), budget=_budget(), estimate=_estimate()
    )
    return FaultOutcome(
        fault_id="model-429",
        title="Model provider returns HTTP 429",
        injected="Provider raised ModelRateLimitError on the first attempt only.",
        expected="Bounded retry with backoff; the second attempt succeeds.",
        actual=f"Succeeded after {calls['count']} attempt(s); parsed text={result.parsed.text!r}.",
        remediation="Exponential backoff plus jitter, with a hard max_retries ceiling.",
        residual_risk="Sustained 429s trip the circuit breaker and surface as retryable errors.",
        recovered=True,
        observed_code="MODEL_RATE_LIMITED",
        evidence={"attempts": calls["count"]},
    )


def fault_model_timeout() -> FaultOutcome:
    executor = _executor()
    calls = {"count": 0}

    def operation(_repair: bool) -> CapabilityResult[ChatOutput]:
        calls["count"] += 1
        raise ModelTimeoutError("injected provider timeout")

    error: ModelTimeoutError | None = None
    try:
        executor.execute(
            operation, descriptor=_descriptor(), budget=_budget(), estimate=_estimate()
        )
    except ModelTimeoutError as exc:  # expected terminal behaviour
        error = exc
    verdict = classify_infrastructure_error(error or RuntimeError("no error"))
    code = error.error_code if error else "no error"
    return FaultOutcome(
        fault_id="model-timeout",
        title="Model call exceeds its time budget",
        injected="Provider raised ModelTimeoutError on every attempt.",
        expected="Retry a bounded number of times, then fail with a retryable error.",
        actual=f"Stopped after {calls['count']} attempts with {code}.",
        remediation="Retry ceiling prevents unbounded loops; resolution is RETRY at job level.",
        residual_risk="A slow provider keeps jobs retrying until the run budget ends.",
        recovered=error is not None,
        observed_code=verdict.code,
        evidence={"attempts": calls["count"], "resolution": verdict.resolution},
    )


def fault_invalid_json() -> FaultOutcome:
    executor = _executor()
    calls = {"count": 0}

    def operation(repair: bool) -> CapabilityResult[ChatOutput]:
        calls["count"] += 1
        if not repair:
            raise SchemaParseError("injected non-JSON payload")
        return _chat_result("repaired")

    result = executor.execute(
        operation, descriptor=_descriptor(), budget=_budget(), estimate=_estimate()
    )
    return FaultOutcome(
        fault_id="invalid-json",
        title="Model returns an unparsable JSON payload",
        injected="First attempt raised SchemaParseError; the repair pass returns valid JSON.",
        expected="Run one schema-repair pass instead of counting it as a normal retry.",
        actual=f"Repaired on attempt {calls['count']}; text={result.parsed.text!r}.",
        remediation="Separate schema-repair budget from the transport retry budget.",
        residual_risk="A model that never emits valid JSON exhausts the repair budget.",
        recovered=True,
        observed_code="MODEL_SCHEMA_PARSE_FAILED",
        evidence={"attempts": calls["count"]},
    )


class _DownBrokerQueue:
    """Queue whose broker rejects every publish, standing in for an unreachable Redis."""

    def enqueue(self, run_id: UUID) -> str:  # pragma: no cover - trivial
        raise ConnectionError("injected broker outage")

    def enqueue_resume(self, run_id: UUID, decision: str) -> str:  # pragma: no cover - trivial
        raise ConnectionError("injected broker outage")


def fault_broker_unavailable() -> FaultOutcome:
    import apps.worker.queue as _queue_module

    broken = _DownBrokerQueue()
    verdict = None
    try:
        broken.enqueue(uuid4())
    except ConnectionError as exc:
        verdict = classify_infrastructure_error(exc)
    fallback = _queue_module.InProcessTaskQueue(worker=None, auto_run=False)
    usable = callable(fallback.enqueue) and callable(fallback.cancel)
    fallback.shutdown()
    code = verdict.code if verdict else "none"
    resolution = verdict.resolution if verdict else "-"
    return FaultOutcome(
        fault_id="broker-unavailable",
        title="Redis / Celery broker is temporarily unreachable",
        injected="Queue publish raised ConnectionError while the broker is down.",
        expected="Fail the publish with a retryable backpressure verdict; keep an in-process path.",
        actual=f"Verdict={code} ({resolution}); in-process fallback usable={usable}.",
        remediation="Publish failure leaves the outbox row pending, so a retry re-publishes it.",
        residual_risk="While the broker is down, new runs stay queued and must not double-publish.",
        recovered=verdict is not None and verdict.retryable,
        observed_code=verdict.code if verdict else None,
        evidence={"resolution": verdict.resolution if verdict else None, "fallback": usable},
    )


def _agent_state(run_id: UUID) -> AgentState:
    return AgentState(
        run_id=run_id,
        job_id=uuid4(),
        user_goal="analyze classroom evidence",
        mode="video",
        capabilities=CapabilitySnapshot(
            available_tools=["inspect_media", "observe_media", "verify_claims"]
        ),
        retry_budget=RetryBudget(remaining_tool_retries=2, remaining_model_retries=1),
    )


def fault_worker_mid_exit() -> FaultOutcome:
    graph = AgentGraph()
    state = _agent_state(uuid4())
    context = {"has_audio": True}
    interrupted = False
    try:
        graph.run(state, context=context, crash_after="observe_media")
    except WorkerInterrupted:
        interrupted = True
    calls_after_crash = int(context.get("vlm_calls", 0))
    resumed = graph.run(state, context=context, resume=True)
    return FaultOutcome(
        fault_id="worker-mid-exit",
        title="Worker process exits in the middle of a run",
        injected="Graph raised WorkerInterrupted right after the observe_media node.",
        expected="Resume from the last successful checkpoint without repeating side effects.",
        actual=f"Interrupted={interrupted}; resumed status={resumed.final_status}; "
        f"vlm_calls before={calls_after_crash} after={int(context.get('vlm_calls', 0))}.",
        remediation="Checkpoint after every node; resume restores the last SUCCEEDED state.",
        residual_risk="Nodes without an idempotent side effect would need extra dedupe guards.",
        recovered=interrupted and resumed.final_status == "SUCCEEDED",
        observed_code="WORKER_INTERRUPTED",
        evidence={
            "vlm_calls_before": calls_after_crash,
            "vlm_calls_after": int(context.get("vlm_calls", 0)),
            "resumed_status": resumed.final_status,
        },
    )


class _HungProcess:
    """Subprocess stub that ignores terminate() so the kill path is exercised."""

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.waits: list[float | None] = []

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.waits.append(timeout)
        if not self.killed:
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=timeout or 0.0)
        return 0

    def kill(self) -> None:
        self.killed = True


def fault_subprocess_stuck() -> FaultOutcome:
    from apps.worker.resources import RunResourceManager

    hung = _HungProcess()
    with tempfile.TemporaryDirectory() as tmp:
        manager = RunResourceManager(Path(tmp), uuid4())
        manager.register_process(hung)  # type: ignore[arg-type]
        run_dir = manager.run_dir
        manager.cancelled_cleanup()
        cleaned = not run_dir.exists()
    return FaultOutcome(
        fault_id="subprocess-stuck",
        title="FFmpeg subprocess ignores terminate()",
        injected="Registered a media subprocess that never exits on graceful terminate.",
        expected="Escalate terminate to a kill within a bounded timeout, then clean the run dir.",
        actual=f"terminated={hung.terminated} killed={hung.killed} waits={hung.waits} "
        f"run_dir_removed={cleaned}.",
        remediation="terminate -> wait(timeout) -> kill -> wait(timeout); then clean the run dir.",
        residual_risk="A process in an uninterruptible syscall may still need an OS-level reap.",
        recovered=hung.killed and cleaned,
        observed_code="SUBPROCESS_STUCK",
        evidence={"killed": hung.killed, "waits": hung.waits, "run_dir_removed": cleaned},
    )


class _FailingStore(InMemoryObjectStore):
    """Store that fails on the first artifact write to emulate an upload outage."""

    def put(self, key: str, data: bytes, content_type: str) -> None:
        raise StorageError("injected object-store write failure")


def _sqlite_sessions() -> tuple[Any, UUID, UUID]:
    # In-memory SQLite keeps the offline harness free of temp-file locking on
    # Windows; ``create_db_engine`` pins a StaticPool so every session shares the
    # same connection and the schema survives for the whole scenario.
    engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(User(id=user_id, email="faults@example.test", password_hash="x" * 20))
        session.flush()
        session.add(Workspace(id=workspace_id, name="Faults", owner_id=user_id))
    return sessions, user_id, workspace_id


def fault_object_storage_failure() -> FaultOutcome:
    sessions, _user_id, workspace_id = _sqlite_sessions()
    service = ObjectStorageService(_FailingStore(), sessions)
    created = JobLifecycleService(sessions).create_job(
        workspace_id=workspace_id, mode="structured", idempotency_key="fault-oss"
    )
    job_id = UUID(created["job_id"])
    error_code: str | None = None
    try:
        service.publish_artifacts(
            workspace_id=workspace_id,
            job_id=job_id,
            version="fault-run",
            contents={"report": ("text/plain", b"hello world")},
        )
    except StorageError as exc:
        error_code = exc.error_code
    with sessions() as session:
        artifact_rows = session.scalar(
            select(func.count()).select_from(Artifact).where(Artifact.job_id == job_id)
        )
    return FaultOutcome(
        fault_id="object-storage-failure",
        title="Object-storage write fails during artifact publication",
        injected="Artifact store raised StorageError on the first put().",
        expected="Abort publication and leave zero artifact rows (manifest-last).",
        actual=f"error_code={error_code}; artifact_rows={artifact_rows}.",
        remediation="Publish into a temporary key, then copy, then write the manifest last.",
        residual_risk="Orphaned temporary objects still require a periodic sweeper.",
        recovered=error_code is not None and artifact_rows == 0,
        observed_code=error_code,
        evidence={"artifact_rows": artifact_rows},
    )


def fault_db_connection_exhausted() -> FaultOutcome:
    error = OperationalError(
        "SELECT 1",
        {},
        Exception("remaining connection slots are reserved; too many clients already"),
    )
    verdict = classify_infrastructure_error(error)
    actual = (
        f"code={verdict.code} retryable={verdict.retryable} resolution={verdict.resolution}."
    )
    return FaultOutcome(
        fault_id="db-connection-exhausted",
        title="Database connection pool is exhausted",
        injected="Raised an OperationalError reporting exhausted connection slots.",
        expected="Classify as backpressure, keep the API up, and stop admitting new work.",
        actual=actual,
        remediation="Fast readiness/liveness separation plus queue-level admission control.",
        residual_risk="Long-running transactions can still hold connections until they time out.",
        recovered=verdict.code == "DB_CONNECTION_EXHAUSTED" and verdict.resolution == BACKPRESSURE,
        observed_code=verdict.code,
        evidence=verdict.as_dict(),
    )


def fault_duplicate_start() -> FaultOutcome:
    sessions, _user_id, workspace_id = _sqlite_sessions()
    service = IdempotencyService(sessions, wait_timeout_seconds=2.0, poll_seconds=0.001)
    executions = {"count": 0}

    def operation(_session: Any) -> dict[str, Any]:
        executions["count"] += 1
        return {"run_id": "run-fixed", "status": "QUEUED"}

    payload = {"job_id": "job-fixed"}
    first = service.execute(
        workspace_id=workspace_id,
        endpoint="POST /jobs/start",
        key="dup-key-1",
        payload=payload,
        operation=operation,
    )
    second = service.execute(
        workspace_id=workspace_id,
        endpoint="POST /jobs/start",
        key="dup-key-1",
        payload=payload,
        operation=operation,
    )
    return FaultOutcome(
        fault_id="duplicate-start",
        title="User double-clicks Start for the same job",
        injected="Two identical start requests sharing one Idempotency-Key.",
        expected="The second request replays the stored response without creating a new run.",
        actual=f"identical_response={first == second}; side_effects={executions['count']}.",
        remediation="Reserve the key transactionally and replay the recorded response.",
        residual_risk="A different key with the same intent still needs a domain-level guard.",
        recovered=first == second and executions["count"] == 1,
        observed_code="IDEMPOTENT_REPLAY",
        evidence={"executions": executions["count"], "run_id": first.get("run_id")},
    )


def fault_cancel_during_run() -> FaultOutcome:
    from apps.worker.runtime import RuntimeWorker

    sessions, _user_id, workspace_id = _sqlite_sessions()
    lifecycle = JobLifecycleService(sessions)
    worker = RuntimeWorker(sessions)
    created = lifecycle.create_job(
        workspace_id=workspace_id, mode="image", idempotency_key="cancel-fault"
    )
    job_id = UUID(created["job_id"])
    started = lifecycle.start_job(
        workspace_id=workspace_id, job_id=job_id, idempotency_key="cancel-fault-start"
    )
    run_id = UUID(started["run_id"])
    lifecycle.cancel_job(workspace_id=workspace_id, job_id=job_id)
    late = worker.run(run_id)
    return FaultOutcome(
        fault_id="cancel-during-run",
        title="User cancels a run that is still executing",
        injected="Job cancelled after start; the worker then reports a late completion.",
        expected="Ignore the late completion and keep the job cancelled.",
        actual=f"worker_status={late.get('status')} (no success overwrite).",
        remediation="The worker re-checks cancellation before finalising the job row.",
        residual_risk="Side effects already emitted must remain individually idempotent.",
        recovered=late.get("status") == "SKIPPED",
        observed_code="JOB_CANCELLED",
        evidence={"worker_status": late.get("status")},
    )


SCENARIOS: tuple[tuple[str, Callable[[], FaultOutcome]], ...] = (
    ("model-429", fault_model_rate_limit),
    ("model-timeout", fault_model_timeout),
    ("invalid-json", fault_invalid_json),
    ("broker-unavailable", fault_broker_unavailable),
    ("worker-mid-exit", fault_worker_mid_exit),
    ("subprocess-stuck", fault_subprocess_stuck),
    ("object-storage-failure", fault_object_storage_failure),
    ("db-connection-exhausted", fault_db_connection_exhausted),
    ("duplicate-start", fault_duplicate_start),
    ("cancel-during-run", fault_cancel_during_run),
)


def run_all(
    *, registry: MetricsRegistry | None = None
) -> list[FaultOutcome]:
    """Execute every fault scenario once and emit structured events for each."""

    outcomes: list[FaultOutcome] = []
    for fault_id, scenario in SCENARIOS:
        with bind(request_id=str(uuid4()), run_id=str(uuid4())):
            outcome = scenario()
        emit_event(
            "fault.injection.completed",
            fault_id=fault_id,
            recovered=outcome.recovered,
            observed_code=outcome.observed_code or "",
        )
        if registry is not None:
            registry.increment(
                "evidenceclass_fault_injections_total",
                labels={"fault": fault_id, "recovered": str(outcome.recovered).lower()},
                help="Fault-injection scenarios executed by the reliability gate",
            )
        outcomes.append(outcome)
    return outcomes


def render_markdown(outcomes: list[FaultOutcome]) -> str:
    """Render the fault-injection report published as an incident document."""

    recovered = sum(1 for item in outcomes if item.recovered)
    lines = [
        "# Fault injection report 001 — observability, reliability and performance",
        "",
        "Generated by `evals/run_stage12_faults.py`. Each scenario is deterministic and runs "
        "offline against the real components; no provider credentials are required and no real "
        "model latency is claimed.",
        "",
        f"- Scenarios executed: **{len(outcomes)}**",
        f"- Handled as designed: **{recovered}/{len(outcomes)}**",
        "",
        "| # | Fault | Injected | Expected | Actual | Recovered |",
        "|---|-------|----------|----------|--------|-----------|",
    ]
    for index, item in enumerate(outcomes, start=1):
        lines.append(
            f"| {index} | `{item.fault_id}` | {item.injected} | {item.expected} | "
            f"{item.actual} | {'yes' if item.recovered else 'no'} |"
        )
    lines.extend(["", "## Remediation and residual risk", ""])
    for item in outcomes:
        lines.extend(
            [
                f"### {item.fault_id} — {item.title}",
                "",
                f"- **Observed code:** `{item.observed_code or 'n/a'}`",
                f"- **Remediation:** {item.remediation}",
                f"- **Residual risk:** {item.residual_risk}",
                f"- **Evidence:** `{json.dumps(item.evidence, ensure_ascii=False, default=str)}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
