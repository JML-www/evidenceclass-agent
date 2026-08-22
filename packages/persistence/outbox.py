"""Transactional outbox publisher with explicit claim and retry semantics."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .models import OutboxEvent


class OutboxPublisher:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def publish_pending(
        self, send: Callable[[str, UUID, dict[str, Any]], None], *, limit: int = 50
    ) -> list[UUID]:
        with self._sessions() as session:
            pending = session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.status == "PENDING")
                .order_by(OutboxEvent.created_at.asc())
                .limit(max(1, min(limit, 500)))
            ).all()
            event_ids = [event.id for event in pending]
        published: list[UUID] = []
        for event_id in event_ids:
            with self._sessions() as session, session.begin():
                event = session.get(OutboxEvent, event_id)
                if event is None or event.status != "PENDING":
                    continue
                event.status = "PUBLISHING"
                event.attempts += 1
                topic = event.topic
                aggregate_id = event.aggregate_id
                payload = dict(event.payload_json)
            try:
                send(topic, aggregate_id, payload)
            except Exception as exc:  # noqa: BLE001 - persist retryable publisher failure
                with self._sessions() as session, session.begin():
                    event = session.get(OutboxEvent, event_id)
                    if event is not None:
                        event.status = "PENDING"
                        event.last_error = str(exc)[:1_000]
                continue
            with self._sessions() as session, session.begin():
                event = session.get(OutboxEvent, event_id)
                if event is not None:
                    event.status = "PUBLISHED"
                    event.published_at = datetime.now(timezone.utc)
            published.append(event_id)
        return published
