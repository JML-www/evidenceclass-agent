from __future__ import annotations

import pytest

from apps.worker.admission import AdmissionLimits, QueueGuard, TaskEstimate, estimate_task


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_estimate_weight_grows_with_duration_and_mode():
    short = estimate_task(workspace_id="ws", duration_seconds=60, mode="video")
    long = estimate_task(workspace_id="ws", duration_seconds=2_765, mode="video")
    image = estimate_task(workspace_id="ws", duration_seconds=0, mode="image")
    assert isinstance(short, TaskEstimate)
    assert long.weight > short.weight
    assert long.estimated_memory_mb > image.estimated_memory_mb
    assert image.estimated_seconds == 60


def test_per_workspace_queue_cap_returns_retryable_backpressure():
    guard = QueueGuard(AdmissionLimits(max_queued_per_workspace=2, max_total_weight=10_000))
    assert guard.admit(workspace_id="ws", duration_seconds=0).admitted
    assert guard.admit(workspace_id="ws", duration_seconds=0).admitted
    rejected = guard.admit(workspace_id="ws", duration_seconds=0)
    assert rejected.admitted is False
    assert rejected.code == "QUEUE_BACKPRESSURE"
    assert rejected.resolution == "REJECT"
    assert rejected.retry_after_seconds and rejected.retry_after_seconds > 0


def test_one_workspace_does_not_exhaust_another_workspace_quota():
    guard = QueueGuard(AdmissionLimits(max_queued_per_workspace=1, max_total_weight=10_000))
    assert guard.admit(workspace_id="ws-a", duration_seconds=0).admitted
    assert guard.admit(workspace_id="ws-b", duration_seconds=0).admitted
    assert guard.admit(workspace_id="ws-a", duration_seconds=0).admitted is False


def test_global_weight_ceiling_rejects_even_a_fresh_workspace():
    guard = QueueGuard(
        AdmissionLimits(
            max_queued_per_workspace=99, max_total_weight=100, in_flight_ttl_seconds=10_000
        )
    )
    first = guard.admit(workspace_id="ws-a", duration_seconds=600)
    assert first.admitted
    rejected = guard.admit(workspace_id="ws-b", duration_seconds=600)
    assert rejected.admitted is False
    assert rejected.code == "QUEUE_BACKPRESSURE"
    assert rejected.details["limit"] == 100


def test_tasks_longer_than_the_cap_are_rejected_not_truncated():
    guard = QueueGuard(AdmissionLimits(max_task_seconds=600))
    decision = guard.admit(workspace_id="ws", duration_seconds=3_600)
    assert decision.admitted is False
    assert decision.code == "QUEUE_TASK_TOO_LONG"


def test_oversized_memory_estimate_is_rejected():
    guard = QueueGuard(
        AdmissionLimits(max_queued_per_workspace=99, max_task_memory_mb=64)
    )
    decision = guard.admit(workspace_id="ws", duration_seconds=600, asset_count=4)
    assert decision.admitted is False
    assert decision.code == "QUEUE_TASK_TOO_LARGE"


def test_in_flight_entries_expire_so_the_queue_self_heals():
    clock = FakeClock()
    guard = QueueGuard(
        AdmissionLimits(
            max_queued_per_workspace=1,
            max_total_weight=10_000,
            in_flight_ttl_seconds=30,
        ),
        clock=clock,
    )
    assert guard.admit(workspace_id="ws", duration_seconds=0).admitted
    assert guard.admit(workspace_id="ws", duration_seconds=0).admitted is False
    clock.advance(31)
    assert guard.admit(workspace_id="ws", duration_seconds=0).admitted


def test_release_returns_slots_immediately_after_completion():
    guard = QueueGuard(AdmissionLimits(max_queued_per_workspace=1, max_total_weight=10_000))
    decision = guard.admit(workspace_id="ws", duration_seconds=0)
    assert decision.admitted
    assert guard.release(workspace_id="ws") == 1
    assert guard.admit(workspace_id="ws", duration_seconds=0).admitted


def test_gpu_oom_degrades_first_then_escalates_to_human_review():
    guard = QueueGuard(AdmissionLimits(gpu_oom_escalation_threshold=2))
    first = guard.on_gpu_oom(workspace_id="ws")
    assert first.admitted is True
    assert first.code == "GPU_OOM_DEGRADED"
    assert first.resolution == "DEGRADE"
    second = guard.on_gpu_oom(workspace_id="ws")
    assert second.admitted is False
    assert second.code == "GPU_OOM_ESCALATED"
    assert second.details["action"] == "NEEDS_REVIEW"
    guard.reset_gpu_oom(workspace_id="ws")
    assert guard.on_gpu_oom(workspace_id="ws").code == "GPU_OOM_DEGRADED"


def test_snapshot_reports_per_workspace_and_limit_state():
    guard = QueueGuard(AdmissionLimits(max_queued_per_workspace=4, max_total_weight=10_000))
    guard.admit(workspace_id="ws-a", duration_seconds=0)
    guard.admit(workspace_id="ws-b", duration_seconds=0)
    snapshot = guard.snapshot()
    assert snapshot["in_flight"] == 2
    assert snapshot["per_workspace"] == {"ws-a": 1, "ws-b": 1}
    assert snapshot["limits"]["max_queued_per_workspace"] == 4


@pytest.mark.parametrize("bad", [0, -1])
def test_limits_must_be_positive(bad):
    with pytest.raises(ValueError):
        AdmissionLimits(max_queued_per_workspace=bad)
