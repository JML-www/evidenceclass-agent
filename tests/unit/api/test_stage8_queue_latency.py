"""Gate: the start/retry/rerun control plane returns "queued" within 500 ms.

The contract requires the API to acknowledge admission and enqueue the work
*without* blocking on the Worker. This is proven by injecting a pipeline that
sleeps far longer than the budget and asserting that the HTTP response still
lands well inside 500 ms and that the worker has not finished when it returns.
"""

from __future__ import annotations

import time
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from apps.api.auth import hash_password
from apps.api.config import AppSettings
from apps.api.main import create_app
from apps.worker.queue import InProcessTaskQueue
from packages.object_storage.store import InMemoryObjectStore
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import User, Workspace, WorkspaceMember


class _SlowPipeline:
    """Stand-in Worker whose ``run`` deliberately sleeps to simulate a slow job."""

    def __init__(self, delay_seconds: float) -> None:
        self.delay = delay_seconds
        self.started_at: float | None = None
        self.finished_at: float | None = None

    def run(self, run_id: UUID | str) -> dict[str, object]:
        self.started_at = time.perf_counter()
        time.sleep(self.delay)
        self.finished_at = time.perf_counter()
        return {"run_id": str(run_id), "status": "COMPLETED"}

    def resume(self, run_id: UUID | str, decision: str) -> dict[str, object]:
        return self.run(run_id)


def _build(tmp_path, *, task_queue=None, sse_heartbeat_seconds: int = 2):
    database = tmp_path / "latency.db"
    engine = create_db_engine(f"sqlite:///{database.as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(
            User(id=user_id, email="api@example.test", password_hash=hash_password("correct horse"))
        )
        session.flush()
        session.add(Workspace(id=workspace_id, name="API test", owner_id=user_id))
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="OWNER"))
    store = InMemoryObjectStore()
    app = create_app(
        AppSettings(
            database_url=f"sqlite:///{database.as_posix()}",
            auth_secret="test-secret",
            worker_mode="manual",
            create_schema=False,
            sse_heartbeat_seconds=sse_heartbeat_seconds,
        ),
        session_factory=sessions,
        object_store=store,
        task_queue=task_queue,
    )
    return TestClient(app), app, sessions, engine, workspace_id


def _token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "api@example.test", "password": "correct horse"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _create(client: TestClient, headers: dict[str, str], key: str) -> str:
    resp = client.post(
        "/api/v1/jobs", headers={**headers, "Idempotency-Key": key}, json={"mode": "image"}
    )
    assert resp.status_code == 201
    return resp.json()["job_id"]


@pytest.mark.parametrize("endpoint", ["start", "retry", "rerun"])
def test_stage8_queue_returns_within_500ms_with_slow_pipeline(tmp_path, endpoint):
    # A pipeline that takes 5 s per run must not make the control plane block.
    slow = _SlowPipeline(delay_seconds=5.0)
    queue = InProcessTaskQueue(slow, auto_run=True)
    client, app, sessions, engine, workspace_id = _build(tmp_path, task_queue=queue)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Warm up one run so library/import jitter is not charged against the budget.
    warm_id = _create(client, headers, "warm-create")
    warm_start = client.post(
        f"/api/v1/jobs/{warm_id}/start",
        headers={**headers, "Idempotency-Key": "warm-start"},
    )
    assert warm_start.status_code == 200

    # The measured run.
    job_id = _create(client, headers, "lat-create")
    start_headers = {**headers, "Idempotency-Key": "lat-start"}
    begun = time.perf_counter()
    if endpoint == "start":
        resp = client.post(f"/api/v1/jobs/{job_id}/start", headers=start_headers)
    elif endpoint == "retry":
        client.post(f"/api/v1/jobs/{job_id}/start", headers=start_headers)
        with sessions() as session:
            from packages.persistence.models import AnalysisJob

            session.execute(
                AnalysisJob.__table__.update()
                .where(AnalysisJob.id == UUID(job_id))
                .values(status="FAILED")
            )
            session.commit()
        resp = client.post(
            f"/api/v1/jobs/{job_id}/retry",
            headers={**headers, "Idempotency-Key": "lat-retry"},
        )
    else:
        # rerun requires a terminal job state and no active run, so drive the
        # job straight to FAILED without ever starting it (starting would leave
        # an active run behind and reject the rerun).
        with sessions() as session:
            from packages.persistence.models import AnalysisJob

            session.execute(
                AnalysisJob.__table__.update()
                .where(AnalysisJob.id == UUID(job_id))
                .values(status="FAILED")
            )
            session.commit()
        resp = client.post(
            f"/api/v1/jobs/{job_id}/rerun",
            headers={**headers, "Idempotency-Key": "lat-rerun"},
        )
    elapsed_ms = (time.perf_counter() - begun) * 1000.0

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_status"] == "QUEUED"
    assert body["task_id"], "no task id returned for the enqueued run"

    # The acceptance contract: the API returns "queued" without blocking on the worker.
    assert elapsed_ms < 500.0, f"{endpoint} took {elapsed_ms:.1f}ms, expected < 500ms"

    # Decoupling proof: the slow pipeline was triggered but has not finished, so
    # the API could not have waited for execution.
    assert slow.started_at is not None, "worker was never enqueued"
    assert slow.finished_at is None, "API blocked until the worker finished"
    time.sleep(0.05)
    assert slow.finished_at is None, "API returned only after the worker completed"

    queue.shutdown()
    engine.dispose()
