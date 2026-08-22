"""Durable job progress events shared by workers, API, and SSE clients."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .models import JobEventRecord


class JobEventService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

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
        bounded_progress = max(0, min(100, int(progress)))
        with self._sessions() as session, session.begin():
            event = JobEventRecord(
                job_id=job_id,
                run_id=run_id,
                type=event_type,
                stage=stage,
                progress=bounded_progress,
                message=message,
                payload_json=dict(payload or {}),
            )
            session.add(event)
            session.flush()
            return self.serialize(event)

    def list_after(
        self, *, job_id: UUID, last_event_id: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        with self._sessions() as session:
            events = session.scalars(
                select(JobEventRecord)
                .where(JobEventRecord.job_id == job_id, JobEventRecord.id > last_event_id)
                .order_by(JobEventRecord.id.asc())
                .limit(max(1, min(limit, 500)))
            ).all()
            return [self.serialize(event) for event in events]

    def list_all(self, *, job_id: UUID) -> list[dict[str, Any]]:
        return self.list_after(job_id=job_id, last_event_id=0, limit=500)

    @staticmethod
    def serialize(event: JobEventRecord) -> dict[str, Any]:
        return {
            "event_id": event.id,
            "type": event.type,
            "job_id": str(event.job_id),
            "run_id": str(event.run_id) if event.run_id else None,
            "stage": event.stage,
            "progress": event.progress,
            "message": event.message,
            "payload": event.payload_json or {},
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
        }
