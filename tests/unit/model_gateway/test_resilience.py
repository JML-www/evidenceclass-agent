import random

import pytest

from packages.model_gateway.contracts import (
    ChatMessage,
    ChatRequest,
    InvocationContext,
)
from packages.model_gateway.errors import (
    CircuitOpenError,
    LocalRateLimitError,
    ModelAuthenticationError,
    ModelBudgetExceededError,
    ModelRateLimitError,
    SchemaParseError,
    SemanticValidationError,
    UnknownCostError,
)
from packages.model_gateway.fake import FakeModelGateway
from packages.model_gateway.resilience import (
    AttemptRecord,
    BudgetLimits,
    CallDescriptor,
    CallEstimate,
    CircuitBreaker,
    JobModelBudget,
    ResilientModelExecutor,
    RetryPolicy,
    SlidingWindowRateLimiter,
)


def _request() -> ChatRequest:
    return ChatRequest(
        messages=[ChatMessage(role="user", content="synthetic")],
        response_schema={"type": "object"},
        context=InvocationContext(
            prompt_version="p.v1",
            config_version="c.v1",
            timeout_seconds=1.0,
            max_output_tokens=64,
        ),
    )


def _budget(max_calls=5, max_tokens=500, max_cost=0.01) -> JobModelBudget:
    return JobModelBudget(
        BudgetLimits(
            max_model_calls=max_calls,
            max_total_tokens=max_tokens,
            max_cost_usd=max_cost,
            max_wall_seconds=30.0,
        )
    )


def _descriptor() -> CallDescriptor:
    return CallDescriptor(
        provider="fake",
        model="fake-chat",
        prompt_version="p.v1",
        config_version="c.v1",
    )


class ListRecorder:
    def __init__(self):
        self.items: list[AttemptRecord] = []

    def record(self, attempt: AttemptRecord) -> None:
        self.items.append(attempt)


def test_retryable_429_uses_bounded_exponential_jitter_and_stops_at_success():
    gateway = FakeModelGateway()
    calls = 0
    delays = []
    recorder = ListRecorder()

    def operation(_repair):
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise ModelRateLimitError("synthetic 429")
        return gateway.chat(_request())

    executor = ResilientModelExecutor(
        policy=RetryPolicy(
            max_retries=2,
            base_delay_seconds=1.0,
            max_delay_seconds=4.0,
            jitter_ratio=0.1,
        ),
        sleep=delays.append,
        random_source=random.Random(7),
    )
    budget = _budget(max_calls=3)
    result = executor.execute(
        operation,
        descriptor=_descriptor(),
        budget=budget,
        estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
        recorder=recorder,
    )
    assert result.parsed.structured["decision"] == "continue"
    assert calls == 3
    assert 0.9 <= delays[0] <= 1.1
    assert 1.8 <= delays[1] <= 2.2
    assert budget.snapshot().calls == 3
    assert [item.status for item in recorder.items] == ["FAILED", "FAILED", "SUCCEEDED"]


def test_schema_parse_gets_at_most_one_constrained_repair():
    gateway = FakeModelGateway()
    repair_flags = []

    def operation(repair):
        repair_flags.append(repair)
        if not repair:
            raise SchemaParseError("bad JSON")
        return gateway.chat(_request())

    executor = ResilientModelExecutor(
        policy=RetryPolicy(max_retries=0, max_schema_repairs=1)
    )
    result = executor.execute(
        operation,
        descriptor=_descriptor(),
        budget=_budget(max_calls=2),
        estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
    )
    assert result.parsed.text
    assert repair_flags == [False, True]


@pytest.mark.parametrize("error", [ModelAuthenticationError("auth"), SemanticValidationError("x")])
def test_non_retryable_errors_are_never_replayed(error):
    calls = 0

    def operation(_repair):
        nonlocal calls
        calls += 1
        raise error

    executor = ResilientModelExecutor(policy=RetryPolicy(max_retries=5))
    with pytest.raises(type(error)):
        executor.execute(
            operation,
            descriptor=_descriptor(),
            budget=_budget(),
            estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
        )
    assert calls == 1


def test_hard_cost_and_call_budgets_block_before_an_extra_provider_call():
    gateway = FakeModelGateway()
    calls = 0

    def operation(_repair):
        nonlocal calls
        calls += 1
        return gateway.chat(_request())

    executor = ResilientModelExecutor(policy=RetryPolicy(max_retries=0))
    budget = _budget(max_calls=1, max_cost=0.001)
    executor.execute(
        operation,
        descriptor=_descriptor(),
        budget=budget,
        estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
    )
    with pytest.raises(ModelBudgetExceededError):
        executor.execute(
            operation,
            descriptor=_descriptor(),
            budget=budget,
            estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
        )
    assert calls == 1
    assert budget.snapshot().cost_usd == 0.001


def test_unknown_cost_is_blocked_when_enforcing_a_hard_cost_budget():
    calls = 0

    def operation(_repair):
        nonlocal calls
        calls += 1
        return FakeModelGateway().chat(_request())

    with pytest.raises(UnknownCostError):
        ResilientModelExecutor().execute(
            operation,
            descriptor=_descriptor(),
            budget=_budget(),
            estimate=CallEstimate(max_total_tokens=64, max_cost_usd=None),
        )
    assert calls == 0


def test_circuit_opens_after_threshold_and_prevents_the_next_call():
    calls = 0
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60.0)
    executor = ResilientModelExecutor(
        policy=RetryPolicy(max_retries=0), circuit_breaker=breaker
    )

    def operation(_repair):
        nonlocal calls
        calls += 1
        raise ModelRateLimitError("429")

    for _ in range(2):
        with pytest.raises(ModelRateLimitError):
            executor.execute(
                operation,
                descriptor=_descriptor(),
                budget=_budget(),
                estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
            )
    with pytest.raises(CircuitOpenError):
        executor.execute(
            operation,
            descriptor=_descriptor(),
            budget=_budget(),
            estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
        )
    assert calls == 2


def test_local_rate_limiter_rejects_without_consuming_provider_budget():
    limiter = SlidingWindowRateLimiter(max_calls=1, window_seconds=60.0)
    executor = ResilientModelExecutor(rate_limiter=limiter)
    budget = _budget()
    gateway = FakeModelGateway()
    executor.execute(
        lambda _repair: gateway.chat(_request()),
        descriptor=_descriptor(),
        budget=budget,
        estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
    )
    with pytest.raises(LocalRateLimitError) as error:
        executor.execute(
            lambda _repair: gateway.chat(_request()),
            descriptor=_descriptor(),
            budget=budget,
            estimate=CallEstimate(max_total_tokens=64, max_cost_usd=0.001),
        )
    assert error.value.error_code == "MODEL_LOCAL_RATE_LIMIT"
    assert budget.snapshot().calls == 1
