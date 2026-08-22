"""Offline phase-4 harness proving Fake Job-to-five-artifact integration."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session, sessionmaker

from packages.agent_runtime import AgentRunEvent, JobEvent
from packages.evidence_engine import EngineRunSummary, EvidenceEngineService
from packages.persistence.jobs import JobLifecycleService
from packages.persistence.models import AgentStep, ToolCall

from .contracts import InvocationContext, VisionRequest, vision_output_to_engine_payload
from .fake import FakeModelGateway
from .recording import SqlAlchemyModelCallRecorder
from .resilience import (
    BudgetLimits,
    CallDescriptor,
    CallEstimate,
    JobModelBudget,
    ResilientModelExecutor,
    RetryPolicy,
)


@dataclass(frozen=True)
class FakeE2EResult:
    job_id: UUID
    run_id: UUID
    tool_call_id: UUID
    engine_summary: EngineRunSummary


class FakeStage4AcceptanceHarness:
    """An acceptance harness, not the production Agent graph planned for phase 7."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        gateway: FakeModelGateway | None = None,
    ) -> None:
        self._sessions = session_factory
        self._gateway = gateway or FakeModelGateway()
        self._jobs = JobLifecycleService(session_factory)

    def run(self, *, workspace_id: UUID, output_dir: str | Path) -> FakeE2EResult:
        unique = uuid4().hex
        created = self._jobs.create_job(
            workspace_id=workspace_id,
            mode="image",
            idempotency_key=f"phase4-create-{unique}",
            request={"source": "offline-fake-acceptance"},
        )
        job_id = UUID(created["job_id"])
        started = self._jobs.start_job(
            workspace_id=workspace_id,
            job_id=job_id,
            idempotency_key=f"phase4-start-{unique}",
            graph_version="phase4-acceptance-harness.v0.1",
        )
        run_id = UUID(started["run_id"])
        self._jobs.apply_job_event(
            workspace_id=workspace_id,
            job_id=job_id,
            event=JobEvent.WORKER_STARTED,
        )
        for event in (
            AgentRunEvent.INSPECT,
            AgentRunEvent.PLAN,
            AgentRunEvent.EXECUTE,
        ):
            self._jobs.apply_run_event(run_id=run_id, event=event)

        step_id, tool_call_id = self._begin_trace(run_id)
        recorder = SqlAlchemyModelCallRecorder(self._sessions, tool_call_id=tool_call_id)
        context = InvocationContext(
            prompt_version="fake-vision-prompt.v0.1",
            config_version="fake-vision-config.v0.1",
            timeout_seconds=5.0,
            max_output_tokens=256,
        )
        request = VisionRequest(
            image_refs=["fixture://authorized-synthetic-image/001"],
            instruction="Return only observable synthetic classroom markers.",
            context=context,
        )
        budget = JobModelBudget(
            BudgetLimits(
                max_model_calls=3,
                max_total_tokens=256,
                max_cost_usd=0.01,
                max_wall_seconds=30.0,
            )
        )
        executor = ResilientModelExecutor(policy=RetryPolicy(max_retries=0, max_schema_repairs=0))

        try:
            vision_result = executor.execute(
                lambda _repair: self._gateway.observe(request),
                descriptor=CallDescriptor(
                    provider="fake",
                    model="fake-vision",
                    prompt_version=context.prompt_version,
                    config_version=context.config_version,
                    model_revision="fixture.v0.1",
                ),
                budget=budget,
                estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
                recorder=recorder,
            )
            payload = vision_output_to_engine_payload(vision_result.parsed)
            engine_summary = self._render(payload, output_dir)
        except Exception:
            self._finish_trace(step_id, tool_call_id, succeeded=False)
            self._jobs.apply_run_event(run_id=run_id, event=AgentRunEvent.ERROR)
            self._jobs.apply_job_event(
                workspace_id=workspace_id, job_id=job_id, event=JobEvent.FAIL
            )
            raise

        self._finish_trace(step_id, tool_call_id, succeeded=True)
        self._jobs.apply_run_event(run_id=run_id, event=AgentRunEvent.VERIFY)
        self._jobs.apply_run_event(run_id=run_id, event=AgentRunEvent.COMPLETE)
        self._jobs.apply_job_event(workspace_id=workspace_id, job_id=job_id, event=JobEvent.SUCCEED)
        return FakeE2EResult(
            job_id=job_id,
            run_id=run_id,
            tool_call_id=tool_call_id,
            engine_summary=engine_summary,
        )

    def _begin_trace(self, run_id: UUID) -> tuple[UUID, UUID]:
        step_id, tool_call_id = uuid4(), uuid4()
        with self._sessions() as session, session.begin():
            session.add(
                AgentStep(
                    id=step_id,
                    run_id=run_id,
                    node="observe_media",
                    status="STARTED",
                )
            )
            session.flush()
            session.add(
                ToolCall(
                    id=tool_call_id,
                    step_id=step_id,
                    tool_name="observe_visuals",
                    args_json={"asset_refs": 1, "input_bodies_logged": False},
                    status="STARTED",
                    attempt=1,
                )
            )
        return step_id, tool_call_id

    def _finish_trace(self, step_id: UUID, tool_call_id: UUID, *, succeeded: bool) -> None:
        status = "SUCCEEDED" if succeeded else "FAILED"
        with self._sessions() as session, session.begin():
            step = session.get(AgentStep, step_id)
            tool = session.get(ToolCall, tool_call_id)
            if step is None or tool is None:
                raise RuntimeError("acceptance trace disappeared")
            step.status = status
            tool.status = status

    @staticmethod
    def _render(payload: dict, output_dir: str | Path) -> EngineRunSummary:
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".json",
                delete=False,
            ) as temporary:
                json.dump(payload, temporary, ensure_ascii=False)
                temporary_name = temporary.name
            return EvidenceEngineService().analyze_file(temporary_name, output_dir)
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
