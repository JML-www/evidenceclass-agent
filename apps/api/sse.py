"""SSE streaming logic for job progress events.

The generator lives here rather than inline in the FastAPI endpoint so that the
push semantics can be exercised directly. This matters because ``starlette``'s
``TestClient`` collects the entire response body before returning
(``portal.call(self.app, ...)`` blocks until the ASGI app returns), so it can
never read an open-ended ``text/event-stream`` response -- driving the async
generator is the only seam that both works offline and actually tests the
behaviour.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, Protocol
from uuid import UUID

from apps.api.event_bus import TERMINAL_EVENT_TYPES, NotificationBus
from packages.persistence.events import JobEventService


class _Disconnectable(Protocol):
    """The slice of ``starlette.requests.Request`` this generator depends on."""

    async def is_disconnected(self) -> bool: ...


def frame(row: dict[str, Any]) -> str:
    """Render one event row as an SSE frame."""

    data = json.dumps(row, ensure_ascii=False)
    return f"id: {row['event_id']}\nevent: {row['type']}\ndata: {data}\n\n"


async def stream_job_events(
    *,
    job_id: UUID,
    last_event_id: int,
    request: _Disconnectable,
    events: JobEventService,
    bus: NotificationBus,
    heartbeat_seconds: int,
) -> AsyncGenerator[str, None]:
    """Yield SSE frames for ``job_id`` until it reaches a terminal state.

    Replays everything already persisted after the client's ``Last-Event-ID``
    cursor, then tails the durable log: a bus wake-up means new rows were
    committed, so the generator re-reads the table and pushes them. That is
    push, not poll -- a heartbeat only fires when the bus stays quiet.
    """

    subscriber = bus.subscribe(job_id)
    try:
        last_id = last_event_id
        rows = events.list_after(job_id=job_id, last_event_id=last_id)
        for row in rows:
            if await request.is_disconnected():
                return
            yield frame(row)
            last_id = max(last_id, int(row["event_id"]))
        if any(row["type"] in TERMINAL_EVENT_TYPES for row in rows):
            return
        while True:
            if await request.is_disconnected():
                return
            try:
                await asyncio.wait_for(subscriber.queue.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue
            new_rows = events.list_after(job_id=job_id, last_event_id=last_id)
            for row in new_rows:
                yield frame(row)
                last_id = max(last_id, int(row["event_id"]))
            if any(row["type"] in TERMINAL_EVENT_TYPES for row in new_rows):
                return
    finally:
        bus.unsubscribe(job_id, subscriber)
