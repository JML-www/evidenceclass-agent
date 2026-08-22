"""Durable Agent-run executor used by both Celery and the local test queue."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from packages.agent_runtime import AgentGraph, AgentState, CapabilitySnapshot, RetryBudget
from packages.persistence.agent_runtime import SqlCheckpointStore, SqlReviewService
from packages.persistence.events import JobEventService
from packages.persistence.models import AgentRun, AnalysisJob, MediaAsset


class RuntimeWorker:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory
        self._events = JobEventService(session_factory)

    def run(self, run_id: UUID | str) -> dict[str, Any]:
        run_uuid = UUID(str(run_id))
        claimed = self._claim(run_uuid)
        if claimed is None:
            return {"run_id": str(run_uuid), "status": "SKIPPED"}
        job_id, mode, goal, request = claimed
        self._events.append(
            job_id=job_id,
            run_id=run_uuid,
            event_type="agent.run.started",
            stage="initialize",
            progress=5,
            message="Agent run started",
        )
        try:
            state = self._initial_state(run_uuid, job_id, mode, goal)
            context = self._context(job_id, request)
            graph = AgentGraph(checkpoints=SqlCheckpointStore(self._sessions))
            result = graph.run(state, context=context)
            self._record_trace(job_id, run_uuid, result)
            return self._finish(run_uuid, result)
        except Exception as exc:  # noqa: BLE001 - worker must persist a stable failure
            return self._fail(run_uuid, type(exc).__name__, str(exc))

    def _claim(self, run_id: UUID) -> tuple[UUID, str, str, dict[str, Any]] | None:
        with self._sessions() as session, session.begin():
            run = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
            if run is None or run.active_slot != "active":
                return None
            job = session.get(AnalysisJob, run.job_id)
            if job is None or job.status == "CANCELLED":
                run.status = "ERRORED"
                run.active_slot = None
                if job is not None:
                    job.status = "CANCELLED"
                return None
            if run.status != "INITIALIZING" or job.status != "QUEUED":
                return None
            run.status = "INSPECTING"
            job.status = "RUNNING"
            job.progress = 5
            return (
                job.id,
                job.mode,
                str(job.request_json.get("goal", "analyze classroom evidence")),
                dict(job.request_json),
            )

    def _initial_state(self, run_id: UUID, job_id: UUID, mode: str, goal: str) -> AgentState:
        return AgentState(
            run_id=run_id,
            job_id=job_id,
            user_goal=goal,
            mode=mode,
            capabilities=CapabilitySnapshot(
                available_tools=["inspect_media", "observe_media", "verify_claims"],
                network_allowed=False,
                max_model_calls=8,
            ),
            retry_budget=RetryBudget(remaining_tool_retries=2, remaining_model_retries=1),
        )

    def _context(self, job_id: UUID, request: dict[str, Any]) -> dict[str, Any]:
        with self._sessions() as session:
            assets = session.scalars(select(MediaAsset).where(MediaAsset.job_id == job_id)).all()
        has_audio = any(asset.mime.startswith("audio/") for asset in assets)
        has_audio = has_audio or any(
            asset.mime == "video/mp4" and request.get("has_audio", False) for asset in assets
        )
        return {
            "asset_valid": True,
            "has_audio": has_audio,
            "high_risk": bool(request.get("high_risk", False)),
            "validation_error": bool(request.get("validation_error", False)),
            "numeric_inconsistent": bool(request.get("numeric_inconsistent", False)),
            "persistent_verifier_failure": bool(request.get("persistent_verifier_failure", False)),
            "requested_identity": bool(request.get("requested_identity", False)),
            "requested_full_frame": bool(request.get("requested_full_frame", False)),
            "duration_seconds": int(request.get("duration_seconds", 0)),
            "rubric_available": bool(request.get("rubric_available", False)),
        }

    def _record_trace(self, job_id: UUID, run_id: UUID, state: AgentState) -> None:
        completed = state.completed_nodes
        total = max(1, len(completed))
        for index, node in enumerate(completed, start=1):
            self._events.append(
                job_id=job_id,
                run_id=run_id,
                event_type="agent.step.completed",
                stage=node,
                progress=min(95, 5 + int(index / total * 90)),
                message=f"Completed {node}",
                payload={"trace_index": index},
            )

    def _finish(self, run_id: UUID, state: AgentState) -> dict[str, Any]:
        review_job_id: UUID | None = None
        with self._sessions() as session, session.begin():
            run = session.get(AgentRun, run_id)
            if run is None:
                return {"run_id": str(run_id), "status": "MISSING"}
            job = session.get(AnalysisJob, run.job_id)
            if job is None:
                return {"run_id": str(run_id), "status": "MISSING_JOB"}
            if job.status == "CANCELLED":
                run.status = "ERRORED"
                run.active_slot = None
                self._events.append(
                    job_id=job.id,
                    run_id=run.id,
                    event_type="job.cancelled",
                    stage=state.current_node,
                    progress=job.progress,
                    message="Cancelled run ignored late completion",
                )
                return {"run_id": str(run.id), "status": "CANCELLED"}
            if state.final_status == "SUCCEEDED":
                run.status = "COMPLETED"
                job.status = "SUCCEEDED"
                job.progress = 100
                event_type = "job.succeeded"
            elif state.final_status == "NEEDS_REVIEW" or state.requires_review:
                run.status = "WAITING_HUMAN"
                job.status = "NEEDS_REVIEW"
                job.progress = 80
                review_job_id = job.id
                event_type = "job.needs_review"
            else:
                run.status = "ERRORED"
                job.status = "FAILED"
                job.progress = 100
                job.error_code = state.final_status or "AGENT_RUN_FAILED"
                job.error_message = "Agent run ended without a publishable result"
                event_type = "job.failed"
            run.active_slot = None
            result = {"run_id": str(run.id), "status": run.status, "job_status": job.status}
            job_uuid = job.id
            run_uuid = run.id
            job_progress = job.progress
            job_status = job.status
            event_stage = state.current_node
        self._events.append(
            job_id=job_uuid,
            run_id=run_uuid,
            event_type=event_type,
            stage=event_stage,
            progress=job_progress,
            message=f"Run finished with {job_status}",
        )
        if review_job_id is not None:
            SqlReviewService(self._sessions).create(
                job_id=review_job_id,
                reason="Agent requested human review",
                risk="HIGH",
                observation={"run_id": str(run_id), "node": state.current_node},
            )
        return result

    def _fail(self, run_id: UUID, code: str, message: str) -> dict[str, Any]:
        with self._sessions() as session, session.begin():
            run = session.get(AgentRun, run_id)
            if run is None:
                return {"run_id": str(run_id), "status": "MISSING"}
            job = session.get(AnalysisJob, run.job_id)
            run.status = "ERRORED"
            run.active_slot = None
            if job is not None and job.status != "CANCELLED":
                job.status = "FAILED"
                job.progress = 100
                job.error_code = code
                job.error_message = message[:1_000]
            job_id = job.id if job is not None else None
        if job_id is not None:
            self._events.append(
                job_id=job_id,
                run_id=run_id,
                event_type="job.failed",
                stage="worker",
                progress=100,
                message="Worker failed; see job error fields",
                payload={"code": code},
            )
        return {"run_id": str(run_id), "status": "ERRORED", "error_code": code}
