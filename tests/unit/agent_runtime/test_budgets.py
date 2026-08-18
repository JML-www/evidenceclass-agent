from datetime import datetime, timedelta, timezone

import pytest

from packages.agent_runtime.budget import BudgetExceeded, BudgetLimits, BudgetTracker


def test_budget_tracker_enforces_every_resource_limit():
    tracker = BudgetTracker(
        BudgetLimits(
            max_steps=1,
            max_model_calls=1,
            max_tool_retries=1,
            max_input_tokens=2,
            max_output_tokens=2,
            max_cost=1.0,
            max_repair_rounds=1,
        )
    )
    tracker.before_step()
    with pytest.raises(BudgetExceeded, match="max_steps"):
        tracker.before_step()
    tracker.before_model_call(input_tokens=2)
    with pytest.raises(BudgetExceeded, match="max_model_calls"):
        tracker.before_model_call()
    tracker.record_model_output(output_tokens=2, cost=1.0)
    with pytest.raises(BudgetExceeded, match="max_output_tokens"):
        tracker.record_model_output(output_tokens=1)
    tracker.before_tool_retry()
    with pytest.raises(BudgetExceeded, match="max_tool_retries"):
        tracker.before_tool_retry()
    tracker.before_repair()
    with pytest.raises(BudgetExceeded, match="max_repair_rounds"):
        tracker.before_repair()
    assert tracker.snapshot()["cost"] == 1.0


def test_budget_tracker_rejects_negative_usage_and_deadline():
    tracker = BudgetTracker(
        BudgetLimits(deadline_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    with pytest.raises(BudgetExceeded, match="deadline"):
        tracker.check_available()
    tracker = BudgetTracker(BudgetLimits())
    with pytest.raises(ValueError, match="negative"):
        tracker.before_model_call(input_tokens=-1)
    with pytest.raises(ValueError, match="negative"):
        tracker.record_model_output(output_tokens=-1)
