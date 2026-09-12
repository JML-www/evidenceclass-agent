"""Durable Agent-run executor used by both Celery and the local test queue."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from packages.agent_runtime import AgentGraph, AgentState, CapabilitySnapshot, RetryBudget
from packages.evidence_engine import EvidenceEngineService
from packages.evidence_engine.renderers import (
    render_actions_csv,
    render_evidence_csv,
    render_html,
    render_json,
    render_markdown,
)
from packages.object_storage import ObjectStorageService
from packages.observability import StageTimeline, bind, emit_event
from packages.observability import metrics as metrics_registry
from packages.persistence.agent_runtime import SqlCheckpointStore, SqlReviewService
from packages.persistence.events import JobEventService
from packages.persistence.models import AgentRun, AnalysisJob, EvidenceItem, MediaAsset


def _elapsed_ms_since(moment: datetime | None) -> float | None:
    """Milliseconds between a stored timestamp and now; ``None`` if unknown."""

    if moment is None:
        return None
    reference = moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - reference).total_seconds() * 1000.0)


class RuntimeWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: ObjectStorageService | None = None,
    ) -> None:
        self._sessions = session_factory
        self._events = JobEventService(session_factory)
        self._storage = storage

    def run(self, run_id: UUID | str) -> dict[str, Any]:
        run_uuid = UUID(str(run_id))
        claimed = self._claim(run_uuid)
        if claimed is None:
            return {"run_id": str(run_uuid), "status": "SKIPPED"}
        job_id, mode, goal, request, created_at = claimed
        workspace_id = self._workspace_of(job_id)
        timeline = StageTimeline()
        queue_wait_ms = _elapsed_ms_since(created_at)
        if queue_wait_ms is not None:
            timeline.record("queue_wait_ms", queue_wait_ms)
        self._events.append(
            job_id=job_id,
            run_id=run_uuid,
            event_type="agent.run.started",
            stage="initialize",
            progress=5,
            message="Agent run started",
        )
        with bind(
            request_id=str(run_uuid),
            workspace_id=str(workspace_id) if workspace_id is not None else None,
            job_id=str(job_id),
            run_id=str(run_uuid),
        ):
            emit_event("agent.run.started", job_id=str(job_id), mode=mode)
            metrics_registry().increment(
                "evidenceclass_agent_runs_total",
                labels={"outcome": "started"},
                help="Agent runs grouped by terminal or started outcome",
            )
            try:
                state = self._initial_state(run_uuid, job_id, mode, goal)
                context = self._context(job_id, request)
                graph = AgentGraph(checkpoints=SqlCheckpointStore(self._sessions))
                result = timeline.measure("agent_overhead_ms", graph.run, state, context=context)
                self._record_trace(job_id, run_uuid, result)
                if result.final_status == "SUCCEEDED":
                    timeline.measure(
                        "artifact_ms", self._publish_structured_result, job_id, run_uuid, mode
                    )
                return self._finish(run_uuid, result, timeline=timeline)
            except Exception as exc:  # noqa: BLE001 - worker must persist a stable failure
                return self._fail(
                    run_uuid, type(exc).__name__, str(exc), timeline=timeline
                )

    def resume(self, run_id: UUID | str, decision: str) -> dict[str, Any]:
        """Continue from the latest successful checkpoint after human review."""

        run_uuid = UUID(str(run_id))
        with self._sessions() as session:
            run = session.get(AgentRun, run_uuid)
            if run is None:
                return {"run_id": str(run_uuid), "status": "MISSING"}
            job = session.get(AnalysisJob, run.job_id)
            if job is None:
                return {"run_id": str(run_uuid), "status": "MISSING_JOB"}
            if run.status != "EXECUTING" or job.status != "RUNNING":
                return {"run_id": str(run_uuid), "status": "SKIPPED"}
            job_id = job.id
            workspace_id = job.workspace_id
        timeline = StageTimeline()
        self._events.append(
            job_id=job_id,
            run_id=run_uuid,
            event_type="agent.run.resumed",
            stage="human_review",
            progress=82,
            message="Agent run resumed after human review",
            payload={"decision": decision},
        )
        with bind(
            request_id=str(run_uuid),
            workspace_id=str(workspace_id),
            job_id=str(job_id),
            run_id=str(run_uuid),
        ):
            emit_event("agent.run.resumed", job_id=str(job_id), decision=decision)
            try:
                checkpoints = SqlCheckpointStore(self._sessions)
                state = checkpoints.restore(str(run_uuid))
                graph = AgentGraph(checkpoints=checkpoints)
                result = timeline.measure(
                    "agent_overhead_ms",
                    graph.run,
                    state,
                    context={"review_decision": decision, "resume_node": "compute_metrics"},
                    resume=True,
                )
                self._record_trace(job_id, run_uuid, result)
                return self._finish(run_uuid, result, timeline=timeline)
            except Exception as exc:  # noqa: BLE001 - persist a stable worker failure
                return self._fail(run_uuid, type(exc).__name__, str(exc), timeline=timeline)

    def _workspace_of(self, job_id: UUID) -> UUID | None:
        with self._sessions() as session:
            job = session.get(AnalysisJob, job_id)
            return job.workspace_id if job is not None else None

    def _publish_structured_result(self, job_id: UUID, run_id: UUID, mode: str) -> None:
        if mode != "structured" or self._storage is None:
            return
        with self._sessions() as session:
            job = session.get(AnalysisJob, job_id)
            asset = session.scalar(
                select(MediaAsset)
                .where(MediaAsset.job_id == job_id, MediaAsset.role == "source")
                .order_by(MediaAsset.created_at.asc())
                .limit(1)
            )
            if job is None or asset is None:
                raise ValueError("structured analysis requires one uploaded source asset")
            workspace_id = job.workspace_id
            asset_id = asset.id
        raw = self._storage.read_asset(workspace_id=workspace_id, asset_id=asset_id)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("structured analysis input must be a JSON object")
        result = EvidenceEngineService().analyze_payload(payload)
        contents = {
            "dashboard": ("text/html", render_html(result).encode("utf-8")),
            "report": ("text/markdown", render_markdown(result).encode("utf-8")),
            "evidence": ("text/csv", render_evidence_csv(result).encode("utf-8")),
            "actions": ("text/csv", render_actions_csv(result).encode("utf-8")),
            "analysis_result": ("application/json", render_json(result).encode("utf-8")),
        }
        self._storage.publish_artifacts(
            workspace_id=workspace_id,
            job_id=job_id,
            version=f"run-{run_id}",
            contents=contents,
        )
        with self._sessions() as session, session.begin():
            existing = set(
                session.scalars(
                    select(EvidenceItem.evidence_id).where(EvidenceItem.job_id == job_id)
                ).all()
            )
            for item in result["evidence"]:
                if item["evidence_id"] not in existing:
                    session.add(
                        EvidenceItem(
                            job_id=job_id,
                            evidence_id=item["evidence_id"],
                            source_ref=item["source_ref"],
                            fact=item["fact"],
                            limitations=item.get("limitations", []),
                        )
                    )
        self._events.append(
            job_id=job_id,
            run_id=run_id,
            event_type="job.artifacts.published",
            stage="publish_report",
            progress=98,
            message="Deterministic evidence and five report artifacts published",
            payload={"artifact_kinds": sorted(contents)},
        )

    def _claim(self, run_id: UUID) -> tuple[UUID, str, str, dict[str, Any], datetime | None] | None:
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
                run.created_at,
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

    def _finalize_observability(self, outcome: str, timeline: StageTimeline | None) -> None:
        """Publish run metrics and one structured completion event."""

        registry = metrics_registry()
        labels = {"outcome": outcome.lower()}
        registry.increment(
            "evidenceclass_agent_runs_total",
            labels=labels,
            help="Agent runs grouped by terminal or started outcome",
        )
        stages: dict[str, float] = {}
        if timeline is not None:
            stages = timeline.finalize()
            for name, value in stages.items():
                registry.observe(
                    f"evidenceclass_stage_{name.removesuffix('_ms')}_milliseconds",
                    value,
                    labels=labels,
                    help="Per-stage duration of one analysis run",
                )
            registry.observe(
                "evidenceclass_agent_run_milliseconds",
                stages.get("end_to_end_ms", 0.0),
                labels=labels,
                help="End-to-end wall time of one agent run",
            )
        emit_event("agent.run.completed", outcome=outcome, stages=sorted(stages))

    def _finish(
        self, run_id: UUID, state: AgentState, *, timeline: StageTimeline | None = None
    ) -> dict[str, Any]:
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
        self._finalize_observability(job_status, timeline)
        return result

    def _fail(
        self, run_id: UUID, code: str, message: str, *, timeline: StageTimeline | None = None
    ) -> dict[str, Any]:
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
        emit_event("agent.run.failed", code=code)
        self._finalize_observability("ERRORED", timeline)
        return {"run_id": str(run_id), "status": "ERRORED", "error_code": code}
