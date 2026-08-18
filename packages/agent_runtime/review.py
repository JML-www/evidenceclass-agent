"""Human-in-the-loop review records with immutable audit history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict


class ReviewError(ValueError):
    code = "REVIEW_REJECTED"


class ReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    review_id: UUID
    job_id: UUID
    reason: str
    risk: str
    status: str = "PENDING"
    original_observation: dict[str, object] = {}
    revised_observation: dict[str, object] | None = None
    reviewer_id: str | None = None
    decision: str | None = None
    decided_at: datetime | None = None
    revision: int = 0
    note: str | None = None


@dataclass(frozen=True)
class ReviewAudit:
    review_id: UUID
    reviewer_id: str
    decision: str
    revision: int
    created_at: datetime


class ReviewService:
    def __init__(self) -> None:
        self._items: dict[UUID, ReviewItem] = {}
        self._audits: list[ReviewAudit] = []

    def create(
        self, *, job_id: UUID, reason: str, risk: str, observation: dict[str, object]
    ) -> ReviewItem:
        item = ReviewItem(
            review_id=uuid4(),
            job_id=job_id,
            reason=reason,
            risk=risk,
            original_observation=dict(observation),
        )
        self._items[item.review_id] = item
        return item

    def get(self, review_id: UUID) -> ReviewItem:
        try:
            return self._items[review_id]
        except KeyError as exc:
            raise ReviewError(f"unknown review item: {review_id}") from exc

    def decide(
        self,
        review_id: UUID,
        *,
        reviewer_id: str,
        role: str,
        decision: str,
        note: str = "",
        revised_observation: dict[str, object] | None = None,
    ) -> ReviewItem:
        item = self.get(review_id)
        if role not in {"reviewer", "admin"}:
            raise ReviewError("reviewer role is required")
        if item.status != "PENDING":
            raise ReviewError("review item already has a decision")
        if decision not in {"APPROVED", "REJECTED", "MODIFIED", "MATERIALS_REQUESTED"}:
            raise ReviewError("unsupported review decision")
        updated = item.model_copy(
            update={
                "status": "DECIDED",
                "reviewer_id": reviewer_id,
                "decision": decision,
                "decided_at": datetime.now(timezone.utc),
                "revision": item.revision + 1,
                "note": note,
                "revised_observation": dict(revised_observation)
                if revised_observation is not None
                else None,
            },
        )
        self._items[review_id] = updated
        self._audits.append(
            ReviewAudit(review_id, reviewer_id, decision, updated.revision, updated.decided_at)
        )
        return updated

    def audits(self) -> tuple[ReviewAudit, ...]:
        return tuple(self._audits)
