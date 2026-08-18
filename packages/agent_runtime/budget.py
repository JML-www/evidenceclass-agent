"""Deterministic budget accounting for Agent runs.

The runtime checks these limits before work starts.  A model or tool cannot
silently extend its own budget, which makes retries and stopping behaviour
auditable in tests and in production traces.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt


class BudgetExceeded(RuntimeError):
    code = "AGENT_BUDGET_EXCEEDED"


class BudgetLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    max_steps: NonNegativeInt = Field(default=32, le=1000)
    max_model_calls: NonNegativeInt = Field(default=8, le=1000)
    max_tool_retries: NonNegativeInt = Field(default=2, le=1000)
    max_input_tokens: NonNegativeInt = Field(default=40_000)
    max_output_tokens: NonNegativeInt = Field(default=12_000)
    max_cost: NonNegativeFloat = Field(default=10.0)
    max_repair_rounds: NonNegativeInt = Field(default=2, le=100)
    deadline_at: datetime | None = None


@dataclass
class BudgetUsage:
    steps: int = 0
    model_calls: int = 0
    tool_retries: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    repair_rounds: int = 0


class BudgetTracker:
    def __init__(self, limits: BudgetLimits, usage: BudgetUsage | None = None) -> None:
        self.limits = limits
        self.usage = usage or BudgetUsage()

    def _check_deadline(self) -> None:
        deadline = self.limits.deadline_at
        if deadline is not None:
            now = datetime.now(timezone.utc)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if now >= deadline:
                raise BudgetExceeded("agent deadline has passed")

    def check_available(self) -> None:
        """Reject a call when the run can no longer start more work."""

        self._check_deadline()
        if self.usage.steps > self.limits.max_steps:
            raise BudgetExceeded("max_steps exceeded")
        if self.usage.model_calls > self.limits.max_model_calls:
            raise BudgetExceeded("max_model_calls exceeded")
        if self.usage.tool_retries > self.limits.max_tool_retries:
            raise BudgetExceeded("max_tool_retries exceeded")
        if self.usage.cost > self.limits.max_cost:
            raise BudgetExceeded("max_cost exceeded")

    def before_step(self) -> None:
        self._check_deadline()
        if self.usage.steps >= self.limits.max_steps:
            raise BudgetExceeded("max_steps exceeded")
        self.usage.steps += 1

    def before_model_call(self, *, input_tokens: int = 0) -> None:
        if input_tokens < 0:
            raise ValueError("input_tokens cannot be negative")
        self._check_deadline()
        if self.usage.model_calls >= self.limits.max_model_calls:
            raise BudgetExceeded("max_model_calls exceeded")
        if self.usage.input_tokens + input_tokens > self.limits.max_input_tokens:
            raise BudgetExceeded("max_input_tokens exceeded")
        self.usage.model_calls += 1
        self.usage.input_tokens += input_tokens

    def record_model_output(self, *, output_tokens: int = 0, cost: float = 0.0) -> None:
        if output_tokens < 0 or cost < 0:
            raise ValueError("output_tokens and cost cannot be negative")
        if self.usage.output_tokens + output_tokens > self.limits.max_output_tokens:
            raise BudgetExceeded("max_output_tokens exceeded")
        if self.usage.cost + cost > self.limits.max_cost:
            raise BudgetExceeded("max_cost exceeded")
        self.usage.output_tokens += output_tokens
        self.usage.cost += cost

    def before_tool_retry(self) -> None:
        if self.usage.tool_retries >= self.limits.max_tool_retries:
            raise BudgetExceeded("max_tool_retries exceeded")
        self.usage.tool_retries += 1

    def before_repair(self) -> None:
        if self.usage.repair_rounds >= self.limits.max_repair_rounds:
            raise BudgetExceeded("max_repair_rounds exceeded")
        self.usage.repair_rounds += 1

    def snapshot(self) -> dict[str, int | float]:
        return {
            "steps": self.usage.steps,
            "model_calls": self.usage.model_calls,
            "tool_retries": self.usage.tool_retries,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "cost": self.usage.cost,
            "repair_rounds": self.usage.repair_rounds,
        }
