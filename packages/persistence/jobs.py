"""Transactional Job and Agent Run lifecycle services."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from packages.agent_runtime.state_machines import (
    AgentRunEvent,
    AgentRunState,
    JobEvent,
    JobState,
    ReviewDecision,
    transition,
)

from .idempotency import IdempotencyService
from .models import AgentRun, AnalysisJob, ReviewItem


class ResourceNotFound(LookupError):
    error_code = "RESOURCE_NOT_FOUND"
    status_code = 404


class JobLifecycleService:
    """Only this service writes Job and Agent Run state in application code."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory
        self._idempotency = IdempotencyService(session_factory)

    def create_job(
        self,
        *,
        workspace_id: UUID,
        mode: str,
        idempotency_key: str,
        request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if mode not in {"image", "video", "structured"}:
            raise ValueError("mode must be image, video, or structured")
        payload = {"mode": mode, **(request or {})}

        def create(session: Session) -> dict[str, Any]:
            job = AnalysisJob(
                id=uuid4(),
                workspace_id=workspace_id,
                mode=mode,
                status=JobState.CREATED.value,
                idempotency_key=idempotency_key,
            )
            session.add(job)
            session.flush()
            return {"job_id": str(job.id), "status": job.status, "mode": job.mode}

        return self._idempotency.execute(
            workspace_id=workspace_id,
            endpoint="POST /jobs",
            key=idempotency_key,
            payload=payload,
            operation=create,
            response_ref=lambda response: f"job:{response['job_id']}",
        )

    def start_job(
        self,
        *,
        workspace_id: UUID,
        job_id: UUID,
        idempotency_key: str,
        graph_version: str = "agent-graph.v0.1",
    ) -> dict[str, Any]:
        endpoint = f"POST /jobs/{job_id}/start"
        payload = {"job_id": str(job_id), "graph_version": graph_version}

        def start(session: Session) -> dict[str, Any]:
            job = session.scalar(
                select(AnalysisJob).where(
                    AnalysisJob.id == job_id,
                    AnalysisJob.workspace_id == workspace_id,
                    AnalysisJob.deleted_at.is_(None),
                )
            )
            if job is None:
                raise ResourceNotFound("job not found")

            active = session.scalar(
                select(AgentRun).where(
                    AgentRun.job_id == job_id,
                    AgentRun.active_slot == "active",
                )
            )
            if active is not None:
                return {
                    "job_id": str(job.id),
                    "run_id": str(active.id),
                    "job_status": job.status,
                    "run_status": active.status,
                }

            if JobState(job.status) is not JobState.CREATED:
                raise ValueError(f"job in {job.status} cannot be started")

            next_state = transition(JobState(job.status), JobEvent.START)
            claimed = session.execute(
                update(AnalysisJob)
                .where(AnalysisJob.id == job_id, AnalysisJob.status == JobState.CREATED.value)
                .values(status=next_state.value)
            )
            if claimed.rowcount != 1:
                session.expire_all()
                active = session.scalar(
                    select(AgentRun).where(
                        AgentRun.job_id == job_id,
                        AgentRun.active_slot == "active",
                    )
                )
                if active is None:
                    raise ValueError("job start was claimed without an active run")
                return {
                    "job_id": str(job_id),
                    "run_id": str(active.id),
                    "job_status": JobState.QUEUED.value,
                    "run_status": active.status,
                }

            run = AgentRun(
                id=uuid4(),
                job_id=job_id,
                graph_version=graph_version,
                status=AgentRunState.INITIALIZING.value,
                budget_json={},
                active_slot="active",
            )
            session.add(run)
            session.flush()
            return {
                "job_id": str(job_id),
                "run_id": str(run.id),
                "job_status": next_state.value,
                "run_status": run.status,
            }

        return self._idempotency.execute(
            workspace_id=workspace_id,
            endpoint=endpoint,
            key=idempotency_key,
            payload=payload,
            operation=start,
            response_ref=lambda response: f"run:{response['run_id']}",
        )

    def apply_job_event(
        self,
        *,
        workspace_id: UUID,
        job_id: UUID,
        event: JobEvent,
        review_decision: ReviewDecision | None = None,
    ) -> JobState:
        with self._sessions() as session, session.begin():
            job = session.scalar(
                select(AnalysisJob).where(
                    AnalysisJob.id == job_id, AnalysisJob.workspace_id == workspace_id
                )
            )
            if job is None:
                raise ResourceNotFound("job not found")
            if event is JobEvent.REVIEW_APPROVED:
                approved = session.scalar(
                    select(ReviewItem.id).where(
                        ReviewItem.job_id == job_id,
                        ReviewItem.status == "DECIDED",
                        ReviewItem.decision == ReviewDecision.APPROVED.value,
                    )
                )
                review_decision = (
                    ReviewDecision.APPROVED if approved is not None else None
                )
            next_state = transition(
                JobState(job.status), event, review_decision=review_decision
            )
            job.status = next_state.value
            return next_state

    def apply_run_event(
        self,
        *,
        run_id: UUID,
        event: AgentRunEvent,
        review_decision: ReviewDecision | None = None,
    ) -> AgentRunState:
        with self._sessions() as session, session.begin():
            run = session.get(AgentRun, run_id)
            if run is None:
                raise ResourceNotFound("run not found")
            if event is AgentRunEvent.RESUME:
                recorded_decision = session.scalar(
                    select(ReviewItem.decision)
                    .where(
                        ReviewItem.job_id == run.job_id,
                        ReviewItem.status == "DECIDED",
                        ReviewItem.decision.is_not(None),
                    )
                    .order_by(ReviewItem.updated_at.desc())
                    .limit(1)
                )
                review_decision = (
                    ReviewDecision(recorded_decision)
                    if recorded_decision is not None
                    else None
                )
            next_state = transition(
                AgentRunState(run.status), event, review_decision=review_decision
            )
            run.status = next_state.value
            if next_state in {AgentRunState.COMPLETED, AgentRunState.ERRORED}:
                run.active_slot = None
            return next_state
