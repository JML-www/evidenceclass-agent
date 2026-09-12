"""Process-internal notification bus for job progress events.

The bus decouples event *producers* (the Worker, which appends rows to the
durable event log) from event *consumers* (the SSE endpoint). A producer calls
``publish`` after committing a new event row; a consumer subscribes and receives
a wake-up token that tells it to read the newly appended rows from the
persistent event table and push them over SSE.

The interface is intentionally minimal so the implementation can later be
swapped for a Redis-backed pub/sub without touching the SSE endpoint: the only
contract a backend must satisfy is ``subscribe(job_id) -> Subscriber``,
``unsubscribe(job_id, subscriber)`` and ``publish(job_id)``.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any
from uuid import UUID

from packages.persistence.events import JobEventService

# Event types that close an SSE stream: after one is delivered the job has
# reached a terminal state and the client no longer needs a long-lived stream.
TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "job.succeeded",
        "job.failed",
        "job.cancelled",
        "job.needs_review",
    }
)


# Sentinel placed on a subscriber queue to wake the waiting consumer. It carries
# no data; the consumer re-reads the durable event table to learn what changed.
_WAKEUP = None


class _Subscriber:
    """One SSE connection's view of the bus."""

    __slots__ = ("loop", "queue")

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue: asyncio.Queue[None] = asyncio.Queue()


class NotificationBus:
    """In-process publish/subscribe bus keyed by ``job_id``."""

    def __init__(self) -> None:
        self._subscribers: dict[UUID, list[_Subscriber]] = {}
        self._lock = threading.Lock()

    def subscribe(self, job_id: UUID) -> _Subscriber:
        """Register a new subscriber for ``job_id`` on the running event loop."""

        sub = _Subscriber(asyncio.get_running_loop())
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(sub)
        return sub

    def unsubscribe(self, job_id: UUID, sub: _Subscriber) -> None:
        """Remove a subscriber; safe to call from the SSE cleanup path."""

        with self._lock:
            subs = self._subscribers.get(job_id)
            if subs is not None and sub in subs:
                subs.remove(sub)
                if not subs:
                    self._subscribers.pop(job_id, None)

    def publish(self, job_id: UUID) -> None:
        """Wake every subscriber for ``job_id``.

        Safe to call from a non-event-loop thread (e.g. the Worker's executor
        thread) because the queue put is scheduled on each subscriber's loop via
        ``call_soon_threadsafe``.
        """

        with self._lock:
            targets = list(self._subscribers.get(job_id, []))
        for sub in targets:
            sub.loop.call_soon_threadsafe(sub.queue.put_nowait, _WAKEUP)


class NotifyingJobEventService(JobEventService):
    """``JobEventService`` that notifies the bus after each appended event."""

    def __init__(self, session_factory: Any, bus: NotificationBus) -> None:
        super().__init__(session_factory)
        self._bus = bus

    def append(
        self,
        *,
        job_id: UUID,
        run_id: UUID | None,
        event_type: str,
        message: str,
        stage: str | None = None,
        progress: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = super().append(
            job_id=job_id,
            run_id=run_id,
            event_type=event_type,
            message=message,
            stage=stage,
            progress=progress,
            payload=payload,
        )
        self._bus.publish(job_id)
        return result
