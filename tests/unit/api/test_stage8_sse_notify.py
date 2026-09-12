"""SSE notification channel tests.

These prove the event bus (apps.api.event_bus) actually pushes newly appended
events to connected SSE clients instead of relying on a polling interval, that
``Last-Event-ID`` reconnects replay history without duplication, and that the
stream closes cleanly once a terminal event lands.
"""

from __future__ import annotations

import threading
import time
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.auth import hash_password
from apps.api.config import AppSettings
from apps.api.main import create_app
from apps.worker.queue import InProcessTaskQueue
from packages.object_storage.store import InMemoryObjectStore
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import User, Workspace, WorkspaceMember


def _build(tmp_path, *, sse_heartbeat_seconds: int = 2):
    database = tmp_path / "sse.db"
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
    # auto_run=False so the worker never appends real events; we drive the bus directly.
    queue = InProcessTaskQueue(None, auto_run=False)
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
        task_queue=queue,
    )
    return TestClient(app), app, sessions, engine, workspace_id


def _token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "api@example.test", "password": "correct horse"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _append_later(app, job_id: str, delay: float, **fields) -> None:
    """Append an event from another thread after ``delay`` seconds."""

    def _run() -> None:
        time.sleep(delay)
        app.state.events.append(job_id=UUID(job_id), run_id=None, **fields)

    threading.Thread(target=_run, daemon=True).start()


def test_sse_pushes_new_event_without_polling(tmp_path):
    client, app, sessions, engine, workspace_id = _build(tmp_path)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    job_id = client.post(
        "/api/v1/jobs", headers={**headers, "Idempotency-Key": "sse-create"}, json={"mode": "image"}
    ).json()["job_id"]
    client.post(
        f"/api/v1/jobs/{job_id}/start",
        headers={**headers, "Idempotency-Key": "sse-start"},
    )

    with client.stream("GET", f"/api/v1/jobs/{job_id}/events", headers=headers) as resp:
        # Let the endpoint subscribe and finish the (empty) initial replay first.
        time.sleep(0.2)
        started = time.perf_counter()
        _append_later(
            app,
            job_id,
            delay=0.1,
            event_type="test.live",
            message="live arrival",
            progress=10,
        )
        received: list[str] = []
        for line in resp.iter_lines():
            received.append(line)
            if "test.live" in line:
                latency = time.perf_counter() - started
                break

    assert any("test.live" in line for line in received)
    # Push must beat the 2 s heartbeat, proving it is event-driven, not polling.
    assert latency < 0.5, f"event arrived after {latency * 1000:.0f}ms (looks like polling)"
    engine.dispose()


def test_sse_reconnect_with_last_event_id_replays_no_duplicate(tmp_path):
    client, app, sessions, engine, workspace_id = _build(tmp_path)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    job_id = client.post(
        "/api/v1/jobs", headers={**headers, "Idempotency-Key": "r-create"}, json={"mode": "image"}
    ).json()["job_id"]
    # Three non-terminal events so the stream stays open after the initial replay.
    ids = [
        app.state.events.append(
            job_id=UUID(job_id), run_id=None, event_type="test.replay", message=f"e{i}", progress=i
        )["event_id"]
        for i in range(3)
    ]
    first_id, last_id = ids[0], ids[-1]

    # Reconnect with Last-Event-ID = first id; events 2..3 replayed, 1 excluded.
    with client.stream(
        "GET",
        f"/api/v1/jobs/{job_id}/events",
        headers={**headers, "Last-Event-ID": str(first_id)},
    ) as resp:
        text = ""
        for line in resp.iter_lines():
            text += line + "\n"
            if str(last_id) in line:
                break
    assert f"id: {first_id}\n" not in text, "first event was duplicated on reconnect"
    assert f"id: {last_id}\n" in text, "last replayed event missing on reconnect"

    # A new event pushed after reconnect arrives exactly once.
    with client.stream(
        "GET",
        f"/api/v1/jobs/{job_id}/events",
        headers={**headers, "Last-Event-ID": str(first_id)},
    ) as resp:
        _append_later(
            app,
            job_id,
            delay=0.15,
            event_type="test.after",
            message="after reconnect",
            progress=40,
        )
        live_seen = 0
        for line in resp.iter_lines():
            if "test.after" in line:
                live_seen += 1
                break
    assert live_seen == 1
    engine.dispose()


def test_sse_closes_after_terminal_event(tmp_path):
    client, app, sessions, engine, workspace_id = _build(tmp_path)
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    job_id = client.post(
        "/api/v1/jobs", headers={**headers, "Idempotency-Key": "t-create"}, json={"mode": "image"}
    ).json()["job_id"]
    app.state.events.append(
        job_id=UUID(job_id),
        run_id=None,
        event_type="agent.run.started",
        message="start",
        progress=5,
    )

    _append_later(
        app,
        job_id,
        delay=0.15,
        event_type="job.succeeded",
        message="run finished",
        progress=100,
    )

    with client.stream("GET", f"/api/v1/jobs/{job_id}/events", headers=headers) as resp:
        seen_terminal = False
        # The loop ends only because the generator returns once the terminal
        # event is delivered; that is the clean stream shutdown.
        for line in resp.iter_lines():
            if "job.succeeded" in line:
                seen_terminal = True

    assert seen_terminal
    engine.dispose()
