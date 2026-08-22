from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.auth import hash_password
from apps.api.config import AppSettings
from apps.api.main import create_app
from apps.worker.queue import InProcessTaskQueue
from apps.worker.runtime import RuntimeWorker
from packages.object_storage.store import InMemoryObjectStore
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import User, Workspace, WorkspaceMember


def _client(tmp_path):
    database = tmp_path / "stage8-api.db"
    engine = create_db_engine(f"sqlite:///{database.as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(
            User(
                id=user_id,
                email="api@example.test",
                password_hash=hash_password("correct horse"),
            )
        )
        session.flush()
        session.add(Workspace(id=workspace_id, name="API test", owner_id=user_id))
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="OWNER"))
    store = InMemoryObjectStore()
    worker = RuntimeWorker(sessions)
    queue = InProcessTaskQueue(worker, auto_run=False)
    app = create_app(
        AppSettings(
            database_url=f"sqlite:///{database.as_posix()}",
            auth_secret="test-secret",
            worker_mode="manual",
            create_schema=False,
        ),
        session_factory=sessions,
        object_store=store,
        task_queue=queue,
    )
    return TestClient(app), app, sessions, store, user_id, workspace_id, engine


def _token(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "api@example.test", "password": "correct horse"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_stage8_auth_jobs_worker_events_and_idempotency(tmp_path):
    client, app, sessions, _store, _user_id, workspace_id, engine = _client(tmp_path)
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/api/v1/jobs").status_code == 401
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "create-1"}

    first = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"mode": "image", "goal": "summarize visible evidence"},
    )
    assert first.status_code == 201
    replay = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={"mode": "image", "goal": "summarize visible evidence"},
    )
    assert replay.status_code == 201
    assert replay.json()["job_id"] == first.json()["job_id"]
    conflict = client.post(
        "/api/v1/jobs", headers=headers, json={"mode": "video", "goal": "different request"}
    )
    assert conflict.status_code == 409
    job_id = first.json()["job_id"]
    started = client.post(
        f"/api/v1/jobs/{job_id}/start",
        headers={**headers, "Idempotency-Key": "start-1"},
    )
    assert started.status_code == 200
    assert started.json()["job_status"] == "QUEUED"
    run_id = UUID(started.json()["run_id"])
    result = app.state.queue.run_now(run_id)
    assert result["status"] == "COMPLETED"
    job = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert job.json()["status"] == "SUCCEEDED"
    events = client.get(f"/api/v1/jobs/{job_id}/events", headers=headers)
    assert events.status_code == 200
    assert "job.succeeded" in events.text
    assert "agent.step.completed" in events.text
    event_ids = [
        int(line.split(":", 1)[1].strip())
        for line in events.text.splitlines()
        if line.startswith("id:")
    ]
    resumed = client.get(
        f"/api/v1/jobs/{job_id}/events",
        headers={**headers, "Last-Event-ID": str(event_ids[0])},
    )
    assert f"id: {event_ids[0]}\n" not in resumed.text
    assert f"id: {event_ids[-1]}\n" in resumed.text
    assert client.get(f"/api/v1/jobs/{job_id}/agent-runs", headers=headers).json()[0][
        "run_id"
    ] == str(run_id)
    assert client.get(f"/api/v1/agent-runs/{run_id}/steps", headers=headers).status_code == 200
    assert app.state.queue.run_now(run_id)["status"] == "SKIPPED"
    assert str(workspace_id) == first.json()["workspace_id"]
    engine.dispose()


def test_stage8_upload_validation_and_tenant_boundary(tmp_path):
    client, app, sessions, store, _user_id, workspace_id, engine = _client(tmp_path)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    job = client.post(
        "/api/v1/jobs", headers={**headers, "Idempotency-Key": "upload-job"}, json={"mode": "image"}
    ).json()
    job_id = job["job_id"]
    init = client.post(
        f"/api/v1/jobs/{job_id}/assets/uploads",
        headers=headers,
        json={"expected_mime": "image/png", "max_size_bytes": 1_000},
    )
    assert init.status_code == 201
    upload = init.json()
    png = b"\x89PNG\r\n\x1a\n" + b"fixture"
    store.put(upload["object_key"], png, "image/png")
    complete = client.post(
        f"/api/v1/jobs/{job_id}/assets/uploads/{upload['upload_id']}/complete",
        headers=headers,
        json={"expected_size_bytes": len(png), "expected_sha256": hashlib.sha256(png).hexdigest()},
    )
    assert complete.status_code == 200
    assert complete.json()["mime"] == "image/png"
    bad_init = client.post(
        f"/api/v1/jobs/{job_id}/assets/uploads",
        headers=headers,
        json={"expected_mime": "application/x-executable", "max_size_bytes": 100},
    )
    assert bad_init.status_code == 422
    fake = client.post(
        f"/api/v1/jobs/{job_id}/assets/uploads",
        headers=headers,
        json={"expected_mime": "image/png", "max_size_bytes": 100},
    ).json()
    fake_bytes = b"this is not a png"
    store.put(fake["object_key"], fake_bytes, "image/png")
    fake_complete = client.post(
        f"/api/v1/jobs/{job_id}/assets/uploads/{fake['upload_id']}/complete",
        headers=headers,
        json={
            "expected_size_bytes": len(fake_bytes),
            "expected_sha256": hashlib.sha256(fake_bytes).hexdigest(),
        },
    )
    assert fake_complete.status_code == 422
    over = client.post(
        f"/api/v1/jobs/{job_id}/assets/uploads",
        headers=headers,
        json={"expected_mime": "image/png", "max_size_bytes": 8},
    ).json()
    store.put(over["object_key"], png, "image/png")
    over_complete = client.post(
        f"/api/v1/jobs/{job_id}/assets/uploads/{over['upload_id']}/complete",
        headers=headers,
        json={
            "expected_size_bytes": len(png),
            "expected_sha256": hashlib.sha256(png).hexdigest(),
        },
    )
    assert over_complete.status_code == 422
    cross_complete = client.post(
        f"/api/v1/jobs/{job_id}/assets/uploads/{over['upload_id']}/complete",
        headers={**headers, "X-Workspace-ID": str(uuid4())},
        json={
            "expected_size_bytes": len(png),
            "expected_sha256": hashlib.sha256(png).hexdigest(),
        },
    )
    assert cross_complete.status_code == 403
    cross = client.get(
        f"/api/v1/jobs/{job_id}",
        headers={**headers, "X-Workspace-ID": str(uuid4())},
    )
    assert cross.status_code == 403
    assert len(app.state.events.list_all(job_id=UUID(job_id))) == 0
    engine.dispose()


def test_stage8_stable_errors_cancel_rerun_and_openapi(tmp_path):
    client, app, _sessions, _store, _user_id, _workspace_id, engine = _client(tmp_path)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    invalid = client.post("/api/v1/jobs", headers=headers, json={"mode": "unknown"})
    assert invalid.status_code == 422
    assert set(invalid.json()) == {"code", "message", "retryable", "request_id", "details"}
    assert invalid.json()["code"] == "INVALID_SCHEMA"
    missing = client.get(f"/api/v1/jobs/{uuid4()}", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "RESOURCE_NOT_FOUND"

    job = client.post(
        "/api/v1/jobs",
        headers={**headers, "Idempotency-Key": "cancel-job"},
        json={"mode": "structured"},
    ).json()
    started = client.post(
        f"/api/v1/jobs/{job['job_id']}/start",
        headers={**headers, "Idempotency-Key": "cancel-start"},
    ).json()
    cancelled = client.post(f"/api/v1/jobs/{job['job_id']}/cancel", headers=headers)
    assert cancelled.json()["status"] == "CANCELLED"
    assert app.state.queue.run_now(UUID(started["run_id"]))["status"] == "SKIPPED"
    rerun = client.post(
        f"/api/v1/jobs/{job['job_id']}/rerun",
        headers={**headers, "Idempotency-Key": "rerun-1"},
    )
    assert rerun.status_code == 200
    assert rerun.json()["run_id"] != started["run_id"]

    paths = set(app.openapi()["paths"])
    required = {
        "/api/v1/jobs",
        "/api/v1/jobs/{job_id}",
        "/api/v1/jobs/{job_id}/start",
        "/api/v1/jobs/{job_id}/events",
        "/api/v1/jobs/{job_id}/agent-runs",
        "/api/v1/jobs/{job_id}/evidence",
        "/api/v1/jobs/{job_id}/artifacts",
        "/api/v1/agent-runs/{run_id}/steps",
        "/api/v1/review-items/{review_id}/decision",
        "/api/v1/knowledge/documents",
        "/api/v1/conversations",
        "/api/v1/conversations/{conversation_id}/messages",
    }
    assert required <= paths
    engine.dispose()
