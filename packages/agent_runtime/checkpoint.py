"""Small checkpoint store used by the deterministic runtime and tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from .state import AgentState


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    run_id: str
    node: str
    status: str
    state: AgentState
    output_hash: str | None
    created_at: datetime


class CheckpointStore:
    def __init__(self) -> None:
        self._records: dict[str, list[Checkpoint]] = {}

    @staticmethod
    def _hash(value: Any) -> str:
        return sha256(repr(value).encode("utf-8")).hexdigest()

    def save_started(self, state: AgentState, node: str) -> Checkpoint:
        return self._save(state, node, "STARTED", None)

    def save_succeeded(self, state: AgentState, node: str, output: Any = None) -> Checkpoint:
        output_hash = self._hash(output) if output is not None else None
        return self._save(
            state, node, "SUCCEEDED", output_hash
        )

    def _save(
        self, state: AgentState, node: str, status: str, output_hash: str | None
    ) -> Checkpoint:
        checkpoint = Checkpoint(
            checkpoint_id=f"{state.run_id}:{len(self._records.get(str(state.run_id), [])) + 1}",
            run_id=str(state.run_id),
            node=node,
            status=status,
            state=state.model_copy(deep=True),
            output_hash=output_hash,
            created_at=datetime.now(timezone.utc),
        )
        self._records.setdefault(str(state.run_id), []).append(checkpoint)
        return checkpoint

    def latest_success(self, run_id: str) -> Checkpoint | None:
        records = self._records.get(str(run_id), [])
        for record in reversed(records):
            if record.status == "SUCCEEDED":
                return record
        return None

    def restore(self, run_id: str) -> AgentState:
        checkpoint = self.latest_success(run_id)
        if checkpoint is None:
            raise KeyError(f"no successful checkpoint for run {run_id}")
        return checkpoint.state.model_copy(deep=True)

    def records(self, run_id: str) -> tuple[Checkpoint, ...]:
        return tuple(self._records.get(str(run_id), []))
