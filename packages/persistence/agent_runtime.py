"""Transactional persistence for stage-7 checkpoints, plans, and reviews."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from packages.agent_runtime.checkpoint import Checkpoint
from packages.agent_runtime.review import ReviewError
from packages.agent_runtime.state import AgentState

from .models import AgentRun, AgentStep, ReviewItem


class SqlCheckpointStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    @staticmethod
    def _state_hash(state: AgentState) -> str:
        payload = state.model_dump_json().encode("utf-8")
        return sha256(payload).hexdigest()

    def save_started(self, state: AgentState, node: str) -> Checkpoint:
        with self._sessions() as session, session.begin():
            step = AgentStep(
                run_id=state.run_id,
                node=node,
                status="STARTED",
                input_hash=self._state_hash(state),
            )
            session.add(step)
            session.flush()
            return Checkpoint(
                checkpoint_id=str(step.id),
                run_id=str(state.run_id),
                node=node,
                status="STARTED",
                state=state.model_copy(deep=True),
                output_hash=None,
                created_at=step.created_at or datetime.now(timezone.utc),
            )

    def save_succeeded(self, state: AgentState, node: str, output: Any = None) -> Checkpoint:
        output_hash = (
            sha256(repr(output).encode("utf-8")).hexdigest() if output is not None else None
        )
        with self._sessions() as session, session.begin():
            run = session.get(AgentRun, state.run_id)
            if run is None:
                raise KeyError(f"unknown Agent run: {state.run_id}")
            step = session.scalar(
                select(AgentStep)
                .where(
                    AgentStep.run_id == state.run_id,
                    AgentStep.node == node,
                    AgentStep.status == "STARTED",
                )
                .order_by(AgentStep.created_at.desc())
                .limit(1)
            )
            if step is None:
                step = AgentStep(
                    run_id=state.run_id,
                    node=node,
                    status="SUCCEEDED",
                    input_hash=self._state_hash(state),
                )
                session.add(step)
            else:
                step.status = "SUCCEEDED"
            step.output_hash = output_hash
            session.flush()
            run.checkpoint_id = str(step.id)
            run.graph_version = state.graph_version
            run.checkpoint_state_json = state.model_dump(mode="json")
            if state.plan is not None:
                run.plan_json = state.plan.model_dump(mode="json")
                run.prompt_version = state.plan.prompt_version
            session.flush()
            return Checkpoint(
                checkpoint_id=str(step.id),
                run_id=str(state.run_id),
                node=node,
                status="SUCCEEDED",
                state=state.model_copy(deep=True),
                output_hash=output_hash,
                created_at=step.created_at or datetime.now(timezone.utc),
            )

    def latest_success(self, run_id: str) -> Checkpoint | None:
        with self._sessions() as session:
            run = session.get(AgentRun, UUID(str(run_id)))
            if run is None or run.checkpoint_state_json is None or run.checkpoint_id is None:
                return None
            step = session.get(AgentStep, UUID(run.checkpoint_id))
            if step is None:
                return None
            state = AgentState.model_validate_json(json.dumps(run.checkpoint_state_json))
            return Checkpoint(
                checkpoint_id=run.checkpoint_id,
                run_id=str(run.id),
                node=step.node,
                status="SUCCEEDED",
                state=state,
                output_hash=step.output_hash,
                created_at=step.created_at,
            )

    def restore(self, run_id: str) -> AgentState:
        checkpoint = self.latest_success(run_id)
        if checkpoint is None:
            raise KeyError(f"no successful checkpoint for run {run_id}")
        return checkpoint.state.model_copy(deep=True)


class SqlReviewService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def create(
        self,
        *,
        job_id: UUID,
        reason: str,
        risk: str,
        observation: dict[str, Any],
    ) -> UUID:
        with self._sessions() as session, session.begin():
            item = ReviewItem(
                id=uuid4(),
                job_id=job_id,
                reason=reason,
                risk=risk,
                status="PENDING",
                original_payload_json=dict(observation),
            )
            session.add(item)
            session.flush()
            return item.id

    def decide(
        self,
        review_id: UUID,
        *,
        reviewer_id: str,
        role: str,
        decision: str,
        note: str = "",
        revised_observation: dict[str, Any] | None = None,
    ) -> None:
        if role not in {"reviewer", "admin"}:
            raise ReviewError("reviewer role is required")
        if decision not in {"APPROVED", "REJECTED", "MODIFIED", "MATERIALS_REQUESTED"}:
            raise ReviewError("unsupported review decision")
        with self._sessions() as session, session.begin():
            result = session.execute(
                update(ReviewItem)
                .where(ReviewItem.id == review_id, ReviewItem.status == "PENDING")
                .values(
                    status="DECIDED",
                    reviewer_id=reviewer_id,
                    decision=decision,
                    decided_at=datetime.now(timezone.utc),
                    note=note,
                    revision=ReviewItem.revision + 1,
                    revised_payload_json=(
                        dict(revised_observation) if revised_observation is not None else None
                    ),
                )
            )
            if result.rowcount != 1:
                exists = session.scalar(select(ReviewItem.id).where(ReviewItem.id == review_id))
                if exists is None:
                    raise ReviewError("unknown review item")
                raise ReviewError("review item already has a decision")
