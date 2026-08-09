"""Explicit, auditable transitions for the three independent lifecycle levels."""

from __future__ import annotations

from enum import Enum
from typing import TypeVar, overload


class InvalidTransition(ValueError):
    """Raised when an event is not legal from the current state."""

    error_code = "INVALID_STATE_TRANSITION"


class JobState(str, Enum):
    CREATED = "CREATED"
    UPLOADING = "UPLOADING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobEvent(str, Enum):
    BEGIN_UPLOAD = "BEGIN_UPLOAD"
    FINISH_UPLOAD = "FINISH_UPLOAD"
    START = "START"
    WORKER_STARTED = "WORKER_STARTED"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    SUCCEED = "SUCCEED"
    FAIL = "FAIL"
    CANCEL = "CANCEL"


class AgentRunState(str, Enum):
    INITIALIZING = "INITIALIZING"
    INSPECTING = "INSPECTING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    WAITING_HUMAN = "WAITING_HUMAN"
    COMPLETED = "COMPLETED"
    ERRORED = "ERRORED"


class AgentRunEvent(str, Enum):
    INSPECT = "INSPECT"
    PLAN = "PLAN"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    REQUEST_REVIEW = "REQUEST_REVIEW"
    RESUME = "RESUME"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class ToolCallState(str, Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class ToolCallEvent(str, Enum):
    START = "START"
    RETRY = "RETRY"
    SUCCEED = "SUCCEED"
    FAIL = "FAIL"
    TIME_OUT = "TIME_OUT"
    CANCEL = "CANCEL"


class ReviewDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


JOB_TRANSITIONS: dict[tuple[JobState, JobEvent], JobState] = {
    (JobState.CREATED, JobEvent.BEGIN_UPLOAD): JobState.UPLOADING,
    (JobState.CREATED, JobEvent.START): JobState.QUEUED,
    (JobState.UPLOADING, JobEvent.FINISH_UPLOAD): JobState.QUEUED,
    (JobState.QUEUED, JobEvent.WORKER_STARTED): JobState.RUNNING,
    (JobState.RUNNING, JobEvent.REQUIRE_REVIEW): JobState.NEEDS_REVIEW,
    (JobState.NEEDS_REVIEW, JobEvent.REVIEW_APPROVED): JobState.RUNNING,
    (JobState.RUNNING, JobEvent.SUCCEED): JobState.SUCCEEDED,
    (JobState.RUNNING, JobEvent.FAIL): JobState.FAILED,
}

AGENT_RUN_TRANSITIONS: dict[tuple[AgentRunState, AgentRunEvent], AgentRunState] = {
    (AgentRunState.INITIALIZING, AgentRunEvent.INSPECT): AgentRunState.INSPECTING,
    (AgentRunState.INSPECTING, AgentRunEvent.PLAN): AgentRunState.PLANNING,
    (AgentRunState.PLANNING, AgentRunEvent.EXECUTE): AgentRunState.EXECUTING,
    (AgentRunState.EXECUTING, AgentRunEvent.VERIFY): AgentRunState.VERIFYING,
    (AgentRunState.EXECUTING, AgentRunEvent.REQUEST_REVIEW): AgentRunState.WAITING_HUMAN,
    (AgentRunState.VERIFYING, AgentRunEvent.REQUEST_REVIEW): AgentRunState.WAITING_HUMAN,
    (AgentRunState.VERIFYING, AgentRunEvent.COMPLETE): AgentRunState.COMPLETED,
}

TOOL_CALL_TRANSITIONS: dict[tuple[ToolCallState, ToolCallEvent], ToolCallState] = {
    (ToolCallState.PENDING, ToolCallEvent.START): ToolCallState.STARTED,
    (ToolCallState.STARTED, ToolCallEvent.RETRY): ToolCallState.RETRYING,
    (ToolCallState.RETRYING, ToolCallEvent.START): ToolCallState.STARTED,
    (ToolCallState.STARTED, ToolCallEvent.SUCCEED): ToolCallState.SUCCEEDED,
    (ToolCallState.STARTED, ToolCallEvent.FAIL): ToolCallState.FAILED,
    (ToolCallState.STARTED, ToolCallEvent.TIME_OUT): ToolCallState.TIMED_OUT,
}

StateT = TypeVar("StateT", JobState, AgentRunState, ToolCallState)


def _invalid(current: Enum, event: Enum) -> InvalidTransition:
    return InvalidTransition(f"{current.value} cannot handle {event.value}")


@overload
def transition(
    current: JobState, event: JobEvent, *, review_decision: ReviewDecision | None = None
) -> JobState: ...


@overload
def transition(
    current: AgentRunState,
    event: AgentRunEvent,
    *,
    review_decision: ReviewDecision | None = None,
) -> AgentRunState: ...


@overload
def transition(
    current: ToolCallState,
    event: ToolCallEvent,
    *,
    review_decision: ReviewDecision | None = None,
) -> ToolCallState: ...


def transition(current, event, *, review_decision=None):
    """Return the next state, rejecting illegal or unaudited transitions."""

    if isinstance(current, JobState) and isinstance(event, JobEvent):
        if event is JobEvent.CANCEL and current not in {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
        }:
            return JobState.CANCELLED
        if current is JobState.CANCELLED and event in {
            JobEvent.WORKER_STARTED,
            JobEvent.REQUIRE_REVIEW,
            JobEvent.SUCCEED,
            JobEvent.FAIL,
        }:
            return JobState.CANCELLED
        if (
            current is JobState.NEEDS_REVIEW
            and event is JobEvent.REVIEW_APPROVED
            and review_decision is not ReviewDecision.APPROVED
        ):
            raise InvalidTransition("NEEDS_REVIEW requires an APPROVED review decision")
        try:
            return JOB_TRANSITIONS[(current, event)]
        except KeyError as exc:
            raise _invalid(current, event) from exc

    if isinstance(current, AgentRunState) and isinstance(event, AgentRunEvent):
        if event is AgentRunEvent.ERROR and current not in {
            AgentRunState.COMPLETED,
            AgentRunState.ERRORED,
        }:
            return AgentRunState.ERRORED
        if current is AgentRunState.WAITING_HUMAN and event is AgentRunEvent.RESUME:
            if review_decision is ReviewDecision.APPROVED:
                return AgentRunState.EXECUTING
            if review_decision is ReviewDecision.REJECTED:
                return AgentRunState.ERRORED
            raise InvalidTransition("WAITING_HUMAN requires a recorded review decision")
        try:
            return AGENT_RUN_TRANSITIONS[(current, event)]
        except KeyError as exc:
            raise _invalid(current, event) from exc

    if isinstance(current, ToolCallState) and isinstance(event, ToolCallEvent):
        if event is ToolCallEvent.CANCEL and current in {
            ToolCallState.PENDING,
            ToolCallState.STARTED,
            ToolCallState.RETRYING,
        }:
            return ToolCallState.CANCELLED
        try:
            return TOOL_CALL_TRANSITIONS[(current, event)]
        except KeyError as exc:
            raise _invalid(current, event) from exc

    raise TypeError("state and event must belong to the same lifecycle")
