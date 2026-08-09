from uuid import uuid4

import pytest
from pydantic import ValidationError

from packages.agent_runtime.state import AgentState, CapabilitySnapshot, RetryBudget
from packages.agent_runtime.state_machines import (
    AGENT_RUN_TRANSITIONS,
    JOB_TRANSITIONS,
    TOOL_CALL_TRANSITIONS,
    AgentRunEvent,
    AgentRunState,
    InvalidTransition,
    JobEvent,
    JobState,
    ReviewDecision,
    ToolCallEvent,
    ToolCallState,
    transition,
)


def test_transition_tables_are_explicit_and_have_unique_state_event_pairs():
    assert len(JOB_TRANSITIONS) == len(set(JOB_TRANSITIONS))
    assert len(AGENT_RUN_TRANSITIONS) == len(set(AGENT_RUN_TRANSITIONS))
    assert len(TOOL_CALL_TRANSITIONS) == len(set(TOOL_CALL_TRANSITIONS))
    assert transition(JobState.CREATED, JobEvent.START) is JobState.QUEUED
    assert transition(ToolCallState.PENDING, ToolCallEvent.START) is ToolCallState.STARTED


@pytest.mark.parametrize(
    ("current", "event", "expected"),
    [(current, event, expected) for (current, event), expected in JOB_TRANSITIONS.items()],
)
def test_every_job_transition_table_row(current, event, expected):
    decision = ReviewDecision.APPROVED if event is JobEvent.REVIEW_APPROVED else None
    assert transition(current, event, review_decision=decision) is expected


@pytest.mark.parametrize(
    ("current", "event", "expected"),
    [
        (current, event, expected)
        for (current, event), expected in AGENT_RUN_TRANSITIONS.items()
    ],
)
def test_every_agent_run_transition_table_row(current, event, expected):
    assert transition(current, event) is expected


@pytest.mark.parametrize(
    ("current", "event", "expected"),
    [
        (current, event, expected)
        for (current, event), expected in TOOL_CALL_TRANSITIONS.items()
    ],
)
def test_every_tool_call_transition_table_row(current, event, expected):
    assert transition(current, event) is expected


def test_succeeded_job_cannot_return_to_running():
    with pytest.raises(InvalidTransition, match="SUCCEEDED cannot handle WORKER_STARTED"):
        transition(JobState.SUCCEEDED, JobEvent.WORKER_STARTED)


def test_late_worker_result_does_not_overwrite_cancelled_job():
    assert transition(JobState.CANCELLED, JobEvent.SUCCEED) is JobState.CANCELLED
    assert transition(JobState.CANCELLED, JobEvent.FAIL) is JobState.CANCELLED


def test_waiting_human_requires_a_recorded_review_decision():
    with pytest.raises(InvalidTransition, match="requires a recorded review decision"):
        transition(AgentRunState.WAITING_HUMAN, AgentRunEvent.RESUME)
    assert (
        transition(
            AgentRunState.WAITING_HUMAN,
            AgentRunEvent.RESUME,
            review_decision=ReviewDecision.APPROVED,
        )
        is AgentRunState.EXECUTING
    )
    assert (
        transition(
            AgentRunState.WAITING_HUMAN,
            AgentRunEvent.RESUME,
            review_decision=ReviewDecision.REJECTED,
        )
        is AgentRunState.ERRORED
    )


def test_agent_state_is_versioned_strict_and_reference_only():
    state = AgentState(
        run_id=uuid4(),
        job_id=uuid4(),
        user_goal="analyze authorized classroom media",
        mode="video",
        capabilities=CapabilitySnapshot(
            available_tools=["inspect_media"], network_allowed=False, max_model_calls=0
        ),
        retry_budget=RetryBudget(remaining_tool_retries=2, remaining_model_retries=0),
    )
    assert state.schema_version == "agent-state.v0.1"
    assert state.asset_ids == []
    with pytest.raises(ValidationError):
        AgentState.model_validate({**state.model_dump(), "raw_video": b"not allowed"})
