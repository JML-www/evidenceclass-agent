"""Retry, rate-limit, circuit-breaker, timeout-budget, and cost-budget policies."""

from __future__ import annotations

import random
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Generic, Protocol, TypeVar

from .contracts import CapabilityResult, ModelUsage
from .errors import (
    CircuitOpenError,
    LocalRateLimitError,
    ModelBudgetExceededError,
    ModelGatewayError,
    SchemaParseError,
    UnknownCostError,
)


@dataclass(frozen=True)
class BudgetLimits:
    max_model_calls: int
    max_total_tokens: int
    max_cost_usd: float
    max_wall_seconds: float

    def __post_init__(self) -> None:
        if (
            self.max_model_calls <= 0
            or self.max_total_tokens <= 0
            or self.max_cost_usd < 0
            or self.max_wall_seconds <= 0
        ):
            raise ValueError("budget limits must be positive, except cost may be zero")


@dataclass(frozen=True)
class CallEstimate:
    max_total_tokens: int
    max_cost_usd: float | None

    def __post_init__(self) -> None:
        if self.max_total_tokens < 0:
            raise ValueError("estimated tokens cannot be negative")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            raise ValueError("estimated cost cannot be negative")


@dataclass(frozen=True)
class BudgetSnapshot:
    calls: int
    total_tokens: int
    cost_usd: float
    elapsed_seconds: float


class JobModelBudget:
    def __init__(
        self,
        limits: BudgetLimits,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = limits
        self._clock = clock
        self._started = clock()
        self._calls = 0
        self._tokens = 0
        self._cost = 0.0

    def begin_call(self, estimate: CallEstimate) -> None:
        self._check_wall_time()
        if self._calls + 1 > self.limits.max_model_calls:
            raise ModelBudgetExceededError("maximum model-call count reached")
        if self._tokens + estimate.max_total_tokens > self.limits.max_total_tokens:
            raise ModelBudgetExceededError("maximum token reservation would be exceeded")
        if estimate.max_cost_usd is None:
            raise UnknownCostError("hard cost budget requires a configured call-cost ceiling")
        if self._cost + estimate.max_cost_usd > self.limits.max_cost_usd:
            raise ModelBudgetExceededError("maximum cost reservation would be exceeded")
        self._calls += 1

    def settle_call(self, usage: ModelUsage, estimate: CallEstimate) -> None:
        if usage.total_tokens > estimate.max_total_tokens:
            raise ModelBudgetExceededError("provider exceeded the reserved token ceiling")
        if usage.cost_usd is None:
            raise UnknownCostError("provider usage did not include cost")
        if estimate.max_cost_usd is None or usage.cost_usd > estimate.max_cost_usd:
            raise ModelBudgetExceededError("provider exceeded the reserved cost ceiling")
        self._tokens += usage.total_tokens
        self._cost = round(self._cost + usage.cost_usd, 10)
        self._check_wall_time()

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            calls=self._calls,
            total_tokens=self._tokens,
            cost_usd=self._cost,
            elapsed_seconds=max(0.0, self._clock() - self._started),
        )

    def _check_wall_time(self) -> None:
        if self._clock() - self._started > self.limits.max_wall_seconds:
            raise ModelBudgetExceededError("maximum model wall time reached")


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    max_schema_repairs: int = 1
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 4.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_retries < 0 or self.max_schema_repairs < 0:
            raise ValueError("retry counts cannot be negative")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be within 0..1")


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold <= 0 or cooldown_seconds < 0:
            raise ValueError("invalid circuit-breaker configuration")
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._states: dict[str, _CircuitState] = defaultdict(_CircuitState)
        self._lock = RLock()

    def before_call(self, key: str) -> None:
        with self._lock:
            state = self._states[key]
            if state.opened_at is None:
                return
            if self._clock() - state.opened_at < self._cooldown:
                raise CircuitOpenError(f"circuit is open for {key}")
            state.opened_at = None
            state.failures = self._threshold - 1

    def record_success(self, key: str) -> None:
        with self._lock:
            self._states[key] = _CircuitState()

    def record_failure(self, key: str) -> None:
        with self._lock:
            state = self._states[key]
            state.failures += 1
            if state.failures >= self._threshold:
                state.opened_at = self._clock()


class SlidingWindowRateLimiter:
    def __init__(
        self,
        *,
        max_calls: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_calls <= 0 or window_seconds <= 0:
            raise ValueError("invalid rate-limit configuration")
        self._max_calls = max_calls
        self._window = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = RLock()

    def acquire(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= self._window:
                events.popleft()
            if len(events) >= self._max_calls:
                raise LocalRateLimitError(f"local rate limit reached for {key}")
            events.append(now)


@dataclass(frozen=True)
class AttemptRecord:
    provider: str
    model: str
    model_revision: str | None
    prompt_version: str
    config_version: str
    attempt: int
    status: str
    error_code: str | None
    usage: ModelUsage | None
    latency_ms: float | None
    raw_response_ref: str | None


class AttemptRecorder(Protocol):
    def record(self, attempt: AttemptRecord) -> None: ...


@dataclass(frozen=True)
class CallDescriptor:
    provider: str
    model: str
    prompt_version: str
    config_version: str
    model_revision: str | None = None


ResultT = TypeVar("ResultT", bound=CapabilityResult)


class ResilientModelExecutor(Generic[ResultT]):
    def __init__(
        self,
        *,
        policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        random_source: random.Random | None = None,
    ) -> None:
        self._policy = policy or RetryPolicy()
        self._breaker = circuit_breaker or CircuitBreaker()
        self._limiter = rate_limiter or SlidingWindowRateLimiter(
            max_calls=60, window_seconds=60.0
        )
        self._sleep = sleep
        self._random = random_source or random.Random()

    def execute(
        self,
        operation: Callable[[bool], ResultT],
        *,
        descriptor: CallDescriptor,
        budget: JobModelBudget,
        estimate: CallEstimate,
        recorder: AttemptRecorder | None = None,
    ) -> ResultT:
        retries = 0
        repairs = 0
        attempt = 0
        key = f"{descriptor.provider}:{descriptor.model}"
        while True:
            self._breaker.before_call(key)
            self._limiter.acquire(key)
            budget.begin_call(estimate)
            attempt += 1
            started = time.perf_counter()
            try:
                result = operation(repairs > 0)
                budget.settle_call(result.metadata.usage, estimate)
            except ModelGatewayError as exc:
                latency_ms = round((time.perf_counter() - started) * 1000, 3)
                self._record(
                    recorder,
                    descriptor,
                    attempt=attempt,
                    status="FAILED",
                    error_code=exc.error_code,
                    latency_ms=latency_ms,
                    raw_response_ref=exc.raw_response_ref,
                )
                if exc.retryable:
                    self._breaker.record_failure(key)
                if isinstance(exc, SchemaParseError) and repairs < self._policy.max_schema_repairs:
                    repairs += 1
                    continue
                if exc.retryable and retries < self._policy.max_retries:
                    self._sleep(self._retry_delay(retries))
                    retries += 1
                    continue
                raise
            self._breaker.record_success(key)
            self._record(
                recorder,
                descriptor,
                attempt=attempt,
                status="SUCCEEDED",
                error_code=None,
                usage=result.metadata.usage,
                latency_ms=result.metadata.latency_ms,
                raw_response_ref=result.metadata.raw_response_ref,
                model_revision=result.metadata.model_revision,
            )
            return result

    def _retry_delay(self, retry_index: int) -> float:
        base = min(
            self._policy.max_delay_seconds,
            self._policy.base_delay_seconds * (2**retry_index),
        )
        jitter = base * self._policy.jitter_ratio
        return max(0.0, base + self._random.uniform(-jitter, jitter))

    @staticmethod
    def _record(
        recorder: AttemptRecorder | None,
        descriptor: CallDescriptor,
        *,
        attempt: int,
        status: str,
        error_code: str | None,
        usage: ModelUsage | None = None,
        latency_ms: float | None = None,
        raw_response_ref: str | None = None,
        model_revision: str | None = None,
    ) -> None:
        if recorder is None:
            return
        recorder.record(
            AttemptRecord(
                provider=descriptor.provider,
                model=descriptor.model,
                model_revision=model_revision or descriptor.model_revision,
                prompt_version=descriptor.prompt_version,
                config_version=descriptor.config_version,
                attempt=attempt,
                status=status,
                error_code=error_code,
                usage=usage,
                latency_ms=latency_ms,
                raw_response_ref=raw_response_ref,
            )
        )
