"""SSE notification channel tests.

These prove the event bus (``apps.api.event_bus``) actually pushes newly
appended events to a connected stream instead of relying on a polling interval,
that ``Last-Event-ID`` reconnects replay history without duplication, and that
the stream ends once a terminal event lands.

The stream generator is driven directly rather than through ``TestClient``.
``starlette``'s ``TestClient`` collects the whole response body before returning
(``portal.call(self.app, ...)`` blocks until the ASGI app returns), so reading an
open-ended ``text/event-stream`` response through it deadlocks. Every scenario is
wrapped in ``asyncio.wait_for`` so a regression fails fast instead of hanging CI.
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.auth import hash_password
from apps.api.config import AppSettings
from apps.api.event_bus import NotificationBus, NotifyingJobEventService
from apps.api.main import create_app
from apps.api.sse import stream_job_events
from apps.worker.queue import InProcessTaskQueue
from packages.object_storage.store import InMemoryObjectStore
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import User, Workspace, WorkspaceMember

HEARTBEAT_SECONDS = 2


class _FakeRequest:
    """The slice of a starlette Request the generator polls for disconnects."""

    def __init__(self, disconnected: bool = False) -> None:
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


def _build(tmp_path, *, sse_heartbeat_seconds: int = HEARTBEAT_SECONDS):
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


def _auth(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "api@example.test", "password": "correct horse"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _job(client: TestClient, headers: dict[str, str], key: str) -> UUID:
    """A persisted job row; ``job_events.job_id`` has a foreign key to it."""

    resp = client.post(
        "/api/v1/jobs", headers={**headers, "Idempotency-Key": key}, json={"mode": "image"}
    )
    assert resp.status_code == 201
    return UUID(resp.json()["job_id"])


def _run(coro, timeout: float = 15.0):
    """Drive a coroutine on a fresh loop, failing fast rather than hanging."""

    return asyncio.run(asyncio.wait_for(coro, timeout=timeout))


def test_app_wires_a_notifying_event_service(tmp_path):
    """The wiring under test is real: app.state.events publishes to the bus."""

    _client, app, _sessions, engine, _workspace_id = _build(tmp_path)
    assert isinstance(app.state.events, NotifyingJobEventService)
    assert isinstance(app.state.bus, NotificationBus)
    engine.dispose()


def test_sse_pushes_new_event_without_polling(tmp_path):
    client, app, _sessions, engine, _workspace_id = _build(tmp_path)
    job_id = _job(client, _auth(client), "sse-create")
    events, bus = app.state.events, app.state.bus

    async def scenario() -> float | None:
        stream = stream_job_events(
            job_id=job_id,
            last_event_id=0,
            request=_FakeRequest(),
            events=events,
            bus=bus,
            heartbeat_seconds=HEARTBEAT_SECONDS,
        )

        async def push_later() -> None:
            await asyncio.sleep(0.1)
            events.append(
                job_id=job_id,
                run_id=None,
                event_type="test.live",
                message="live arrival",
                progress=10,
            )

        pusher = asyncio.create_task(push_later())
        started = time.perf_counter()
        try:
            async for chunk in stream:
                if "test.live" in chunk:
                    return time.perf_counter() - started
        finally:
            await stream.aclose()
            await pusher
        return None

    latency = _run(scenario())
    engine.dispose()

    assert latency is not None, "live event never arrived on the stream"
    # Push must beat the 2 s heartbeat, proving it is event-driven, not polling.
    assert latency < 0.5, f"event arrived after {latency * 1000:.0f}ms (looks like polling)"


def test_sse_reconnect_with_last_event_id_replays_no_duplicate(tmp_path):
    client, app, _sessions, engine, _workspace_id = _build(tmp_path)
    job_id = _job(client, _auth(client), "r-create")
    events, bus = app.state.events, app.state.bus
    # Three non-terminal events so the stream stays open after the initial replay.
    ids = [
        events.append(
            job_id=job_id, run_id=None, event_type="test.replay", message=f"e{i}", progress=i
        )["event_id"]
        for i in range(3)
    ]
    first_id, last_id = ids[0], ids[-1]

    async def replay() -> str:
        stream = stream_job_events(
            job_id=job_id,
            last_event_id=first_id,
            request=_FakeRequest(),
            events=events,
            bus=bus,
            heartbeat_seconds=HEARTBEAT_SECONDS,
        )
        text = ""
        try:
            async for chunk in stream:
                text += chunk
                if f"id: {last_id}\n" in chunk:
                    break
        finally:
            await stream.aclose()
        return text

    text = _run(replay())
    engine.dispose()

    assert f"id: {first_id}\n" not in text, "first event was duplicated on reconnect"
    assert f"id: {last_id}\n" in text, "last replayed event missing on reconnect"


def test_sse_closes_after_terminal_event(tmp_path):
    client, app, _sessions, engine, _workspace_id = _build(tmp_path)
    job_id = _job(client, _auth(client), "t-create")
    events, bus = app.state.events, app.state.bus
    events.append(
        job_id=job_id, run_id=None, event_type="agent.run.started", message="start", progress=5
    )

    async def drain() -> list[str]:
        stream = stream_job_events(
            job_id=job_id,
            last_event_id=0,
            request=_FakeRequest(),
            events=events,
            bus=bus,
            heartbeat_seconds=HEARTBEAT_SECONDS,
        )

        async def finish_later() -> None:
            await asyncio.sleep(0.15)
            events.append(
                job_id=job_id,
                run_id=None,
                event_type="job.succeeded",
                message="run finished",
                progress=100,
            )

        pusher = asyncio.create_task(finish_later())
        chunks: list[str] = []
        # The loop ends only because the generator returns once the terminal
        # event is delivered; that is the clean stream shutdown.
        async for chunk in stream:
            chunks.append(chunk)
        await pusher
        return chunks

    chunks = _run(drain())
    assert any("job.succeeded" in chunk for chunk in chunks)

    # A terminal event already persisted means the stream must close on replay
    # rather than tailing a job that can no longer produce anything.
    async def immediate_close() -> list[str]:
        stream = stream_job_events(
            job_id=job_id,
            last_event_id=0,
            request=_FakeRequest(),
            events=events,
            bus=bus,
            heartbeat_seconds=HEARTBEAT_SECONDS,
        )
        return [chunk async for chunk in stream]

    replayed = _run(immediate_close())
    engine.dispose()

    assert any("job.succeeded" in chunk for chunk in replayed)
