from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from apps.api.auth import hash_password
from apps.api.config import AppSettings
from apps.api.main import create_app
from apps.worker.queue import InProcessTaskQueue
from apps.worker.runtime import RuntimeWorker
from packages.object_storage.store import InMemoryObjectStore
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import User, Workspace, WorkspaceMember


def _client(tmp_path, *, queue_limit: int = 1):
    database = tmp_path / "stage12-api.db"
    engine = create_db_engine(f"sqlite:///{database.as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(
            User(
                id=user_id,
                email="stage12@example.test",
                password_hash=hash_password("correct horse"),
            )
        )
        session.flush()
        session.add(Workspace(id=workspace_id, name="Stage12", owner_id=user_id))
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="OWNER"))
    worker = RuntimeWorker(sessions)
    queue = InProcessTaskQueue(worker, auto_run=False)
    app = create_app(
        AppSettings(
            database_url=f"sqlite:///{database.as_posix()}",
            auth_secret="test-secret",
            worker_mode="manual",
            create_schema=False,
            queue_max_queued_per_workspace=queue_limit,
            queue_max_total_weight=10_000,
        ),
        session_factory=sessions,
        object_store=InMemoryObjectStore(),
        task_queue=queue,
    )
    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "stage12@example.test", "password": "correct horse"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, app, sessions, headers, engine


def test_request_id_is_generated_echoed_and_available_as_trace_id(tmp_path):
    client, _app, _sessions, _headers, engine = _client(tmp_path)
    response = client.get("/health/live")
    assert response.status_code == 200
    generated = response.headers["X-Request-ID"]
    assert generated and response.headers["X-Trace-ID"] == generated

    supplied = client.get("/health/live", headers={"X-Request-ID": "trace-abc-123"})
    assert supplied.headers["X-Request-ID"] == "trace-abc-123"
    assert supplied.headers["X-Trace-ID"] == "trace-abc-123"
    engine.dispose()


def test_metrics_endpoint_exposes_http_and_queue_metrics(tmp_path):
    client, _app, _sessions, _headers, engine = _client(tmp_path)
    client.get("/health/live")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "evidenceclass_http_requests_total" in body
    assert "evidenceclass_http_request_milliseconds" in body
    assert "# TYPE evidenceclass_http_requests_total counter" in body
    engine.dispose()


def test_queue_status_endpoint_reports_limits_and_estimate(tmp_path):
    client, _app, _sessions, headers, engine = _client(tmp_path)
    created = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"mode": "video", "goal": "queue status", "metadata": {"duration_seconds": 600}},
    )
    assert created.status_code == 201
    status = client.get("/api/v1/queue/status", headers=headers)
    assert status.status_code == 200
    payload = status.json()
    assert payload["in_flight"] == 0
    assert payload["limits"]["max_queued_per_workspace"] == 1
    assert payload["workspace_estimate"]["weight"] > 0
    engine.dispose()


def test_start_returns_backpressure_once_the_workspace_cap_is_reached(tmp_path):
    client, _app, _sessions, headers, engine = _client(tmp_path, queue_limit=1)
    job_ids = []
    for index in range(2):
        created = client.post(
            "/api/v1/jobs",
            headers={**headers, "Idempotency-Key": f"create-{index}"},
            json={"mode": "video", "goal": f"job {index}", "metadata": {"duration_seconds": 300}},
        )
        assert created.status_code == 201
        job_ids.append(created.json()["job_id"])

    first = client.post(
        f"/api/v1/jobs/{job_ids[0]}/start",
        headers={**headers, "Idempotency-Key": "start-0"},
    )
    assert first.status_code == 200

    rejected = client.post(
        f"/api/v1/jobs/{job_ids[1]}/start",
        headers={**headers, "Idempotency-Key": "start-1"},
    )
    assert rejected.status_code == 429
    body = rejected.json()
    assert body["code"] == "QUEUE_BACKPRESSURE"
    assert body["retryable"] is True
    assert body["request_id"]
    assert body["details"]["retry_after_seconds"] > 0

    # The API stays available and the queue never exceeds its ceiling.
    assert client.get("/health/live").status_code == 200
    snapshot = client.get("/api/v1/queue/status", headers=headers).json()
    assert snapshot["in_flight"] <= snapshot["limits"]["max_queued_per_workspace"]
    engine.dispose()


def test_too_long_media_is_rejected_with_a_distinct_code(tmp_path):
    client, _app, _sessions, headers, engine = _client(tmp_path, queue_limit=99)
    created = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "mode": "video",
            "goal": "huge recording",
            "metadata": {"duration_seconds": 99_999},
        },
    )
    job_id = created.json()["job_id"]
    rejected = client.post(f"/api/v1/jobs/{job_id}/start", headers=headers)
    assert rejected.status_code == 429
    assert rejected.json()["code"] == "QUEUE_TASK_TOO_LONG"
    engine.dispose()
