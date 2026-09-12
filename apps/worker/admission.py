"""Per-workspace admission control so heavy media jobs cannot starve the worker.

A classroom upload can be a 46-minute dual-camera recording, which is orders of
magnitude heavier than a single 1080p frame.  The guard estimates a task weight
from its expected duration, keeps a bounded window of in-flight work per
workspace and globally, and returns a *predictable* verdict — admit, reject with
backpressure, or degrade — instead of letting the queue grow without limit.
"""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import Any, Literal

Resolution = Literal["ADMIT", "REJECT", "DEGRADE"]


@dataclass(frozen=True)
class AdmissionLimits:
    """Caps that keep the worker alive under pressure."""

    max_queued_per_workspace: int = 8
    max_concurrent_per_workspace: int = 3
    max_total_weight: int = 240
    max_task_seconds: int = 3_600
    max_task_memory_mb: int = 4_096
    suggested_wait_seconds: int = 30
    in_flight_ttl_seconds: int = 3_600
    gpu_oom_degrade_batch: int = 2
    gpu_oom_escalation_threshold: int = 2

    def __post_init__(self) -> None:
        if self.max_queued_per_workspace <= 0 or self.max_concurrent_per_workspace <= 0:
            raise ValueError("queue and concurrency caps must be positive")
        if self.max_total_weight <= 0 or self.max_task_seconds <= 0:
            raise ValueError("weight and time caps must be positive")


@dataclass(frozen=True)
class TaskEstimate:
    workspace_id: str
    mode: str
    duration_seconds: int
    weight: int
    estimated_seconds: int
    estimated_memory_mb: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    code: str
    resolution: Resolution
    reason: str
    retry_after_seconds: int | None = None
    estimate: TaskEstimate | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class _Entry:
    at: float
    workspace_id: str
    weight: int


def estimate_task(
    *,
    workspace_id: str,
    duration_seconds: int = 0,
    mode: str = "video",
    asset_count: int = 1,
) -> TaskEstimate:
    """Estimate weight from duration; longer media is proportionally heavier."""

    duration = max(0, int(duration_seconds))
    per_asset = 10 if mode == "image" else 6
    weight = max(1, 1 + math.ceil(duration / 60.0)) * per_asset + max(1, asset_count)
    return TaskEstimate(
        workspace_id=str(workspace_id),
        mode=mode,
        duration_seconds=duration,
        weight=weight,
        estimated_seconds=duration if duration > 0 else 60,
        estimated_memory_mb=256 + 64 * max(1, asset_count) + (duration // 60) * 8,
    )


class QueueGuard:
    """Bounded, self-pruning admission window with deterministic verdicts."""

    def __init__(
        self,
        limits: AdmissionLimits | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = limits or AdmissionLimits()
        self._clock = clock
        self._entries: deque[_Entry] = deque()
        self._gpu_oom_counts: dict[str, int] = {}
        self._lock = RLock()

    # -- admission ---------------------------------------------------------
    def admit(
        self,
        *,
        workspace_id: str,
        duration_seconds: int = 0,
        mode: str = "video",
        asset_count: int = 1,
    ) -> AdmissionDecision:
        estimate = estimate_task(
            workspace_id=workspace_id,
            duration_seconds=duration_seconds,
            mode=mode,
            asset_count=asset_count,
        )
        with self._lock:
            self._prune()
            if estimate.estimated_seconds > self.limits.max_task_seconds:
                return AdmissionDecision(
                    admitted=False,
                    code="QUEUE_TASK_TOO_LONG",
                    resolution="REJECT",
                    reason=(
                        f"estimated {estimate.estimated_seconds}s exceeds the "
                        f"{self.limits.max_task_seconds}s single-task cap"
                    ),
                    estimate=estimate,
                    details={"limit": self.limits.max_task_seconds},
                )
            if estimate.estimated_memory_mb > self.limits.max_task_memory_mb:
                return AdmissionDecision(
                    admitted=False,
                    code="QUEUE_TASK_TOO_LARGE",
                    resolution="REJECT",
                    reason="estimated peak memory exceeds the single-task cap",
                    estimate=estimate,
                    details={"limit_mb": self.limits.max_task_memory_mb},
                )
            workspace_queued = sum(
                1 for entry in self._entries if entry.workspace_id == estimate.workspace_id
            )
            if workspace_queued >= self.limits.max_queued_per_workspace:
                return AdmissionDecision(
                    admitted=False,
                    code="QUEUE_BACKPRESSURE",
                    resolution="REJECT",
                    reason="this workspace already has the maximum number of in-flight tasks",
                    retry_after_seconds=self.limits.suggested_wait_seconds,
                    estimate=estimate,
                    details={
                        "workspace_queued": workspace_queued,
                        "limit": self.limits.max_queued_per_workspace,
                    },
                )
            total_weight = sum(entry.weight for entry in self._entries)
            if total_weight + estimate.weight > self.limits.max_total_weight:
                return AdmissionDecision(
                    admitted=False,
                    code="QUEUE_BACKPRESSURE",
                    resolution="REJECT",
                    reason="the worker queue is at its weight ceiling; retry shortly",
                    retry_after_seconds=self.limits.suggested_wait_seconds,
                    estimate=estimate,
                    details={
                        "total_weight": total_weight,
                        "incoming_weight": estimate.weight,
                        "limit": self.limits.max_total_weight,
                    },
                )
            self._entries.append(
                _Entry(at=self._clock(), workspace_id=estimate.workspace_id, weight=estimate.weight)
            )
            return AdmissionDecision(
                admitted=True,
                code="QUEUE_ADMITTED",
                resolution="ADMIT",
                reason="admitted within the per-workspace and global weight budget",
                estimate=estimate,
                details={
                    "total_weight": total_weight + estimate.weight,
                    "workspace_queued": workspace_queued + 1,
                },
            )

    def release(self, *, workspace_id: str, weight: int | None = None) -> int:
        """Release in-flight entries for a workspace (early completion)."""

        with self._lock:
            released = 0
            kept: deque[_Entry] = deque()
            for entry in self._entries:
                matches_weight = weight is None or entry.weight == weight
                if entry.workspace_id == workspace_id and matches_weight:
                    released += 1
                    continue
                kept.append(entry)
            self._entries = kept
            return released

    # -- GPU degradation ---------------------------------------------------
    def on_gpu_oom(self, *, workspace_id: str) -> AdmissionDecision:
        """Degrade batch size on the first OOM and escalate after repeated OOMs."""

        with self._lock:
            count = self._gpu_oom_counts.get(workspace_id, 0) + 1
            self._gpu_oom_counts[workspace_id] = count
            if count >= self.limits.gpu_oom_escalation_threshold:
                return AdmissionDecision(
                    admitted=False,
                    code="GPU_OOM_ESCALATED",
                    resolution="REJECT",
                    reason="repeated GPU OOM; stop retrying and escalate to human review",
                    details={"oom_count": count, "action": "NEEDS_REVIEW"},
                )
            return AdmissionDecision(
                admitted=True,
                code="GPU_OOM_DEGRADED",
                resolution="DEGRADE",
                reason="reduce the batch size instead of retrying the same workload",
                details={
                    "oom_count": count,
                    "degraded_batch": self.limits.gpu_oom_degrade_batch,
                },
            )

    def reset_gpu_oom(self, *, workspace_id: str) -> None:
        with self._lock:
            self._gpu_oom_counts.pop(workspace_id, None)

    # -- introspection -----------------------------------------------------
    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            self._prune()
            per_workspace: dict[str, int] = {}
            for entry in self._entries:
                per_workspace[entry.workspace_id] = per_workspace.get(entry.workspace_id, 0) + 1
            return {
                "in_flight": len(self._entries),
                "total_weight": sum(entry.weight for entry in self._entries),
                "per_workspace": per_workspace,
                "limits": asdict(self.limits),
            }

    def _prune(self) -> None:
        cutoff = self._clock() - self.limits.in_flight_ttl_seconds
        while self._entries and self._entries[0].at < cutoff:
            self._entries.popleft()
