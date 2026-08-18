"""One policy-aware registry for all Agent tools."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict

from .budget import BudgetTracker

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class ToolRegistryError(ValueError):
    code = "TOOL_REGISTRY_REJECTED"


class ToolTimeoutError(ToolRegistryError):
    code = "TOOL_TIMEOUT"


class ToolContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    workspace_id: str
    allowed_tools: set[str] = set()
    budget: BudgetTracker | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", strict=True)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[BaseModel], BaseModel]
    timeout_seconds: int = 30
    max_attempts: int = 1
    idempotent: bool = True
    workspace_field: str | None = "workspace_id"


@dataclass
class ToolCallResult:
    tool_name: str
    version: str
    output: BaseModel
    cached: bool = False
    attempts: int = 1


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._cache: dict[tuple[str, str], BaseModel] = {}

    def register(
        self,
        *,
        name: str,
        version: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        handler: Callable[[BaseModel], BaseModel],
        timeout_seconds: int = 30,
        max_attempts: int = 1,
        idempotent: bool = True,
    ) -> ToolSpec:
        if name in self._tools:
            raise ToolRegistryError(f"tool already registered: {name}")
        if timeout_seconds <= 0 or max_attempts <= 0:
            raise ToolRegistryError("timeout_seconds and max_attempts must be positive")
        spec = ToolSpec(
            name=name,
            version=version,
            input_model=input_model,
            output_model=output_model,
            handler=handler,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            idempotent=idempotent,
        )
        self._tools[name] = spec
        return spec

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "version": spec.version,
                "timeout_seconds": spec.timeout_seconds,
                "max_attempts": spec.max_attempts,
                "idempotent": spec.idempotent,
            }
            for spec in self._tools.values()
        ]

    def invoke(
        self,
        name: str,
        payload: dict[str, Any] | BaseModel,
        *,
        workspace_id: str,
        allowed_tools: set[str] | frozenset[str] | None = None,
        budget: BudgetTracker | None = None,
        idempotency_key: str | None = None,
    ) -> ToolCallResult:
        spec = self._tools.get(name)
        if spec is None:
            raise ToolRegistryError(f"unregistered tool: {name}")
        if allowed_tools is not None and name not in allowed_tools:
            raise ToolRegistryError(f"tool is not allowed by policy: {name}")
        if budget is not None:
            budget.check_available()
        try:
            model = (
                payload
                if isinstance(payload, spec.input_model)
                else spec.input_model.model_validate(payload)
            )
        except Exception as exc:
            raise ToolRegistryError(f"invalid input for {name}: {exc}") from exc
        workspace_value = getattr(model, "workspace_id", None)
        if workspace_value is not None and str(workspace_value) != workspace_id:
            raise ToolRegistryError("tool input crosses workspace boundary")
        cache_key = (name, idempotency_key) if idempotency_key else None
        if cache_key and spec.idempotent and cache_key in self._cache:
            return ToolCallResult(name, spec.version, self._cache[cache_key], cached=True)
        attempts = 0
        last_error: Exception | None = None
        for attempt in range(spec.max_attempts):
            attempts = attempt + 1
            executor = ThreadPoolExecutor(max_workers=1)
            timed_out = False
            try:
                future = executor.submit(spec.handler, model)
                result = future.result(timeout=spec.timeout_seconds)
                output = (
                    result
                    if isinstance(result, spec.output_model)
                    else spec.output_model.model_validate(result)
                )
                if cache_key and spec.idempotent:
                    self._cache[cache_key] = output
                return ToolCallResult(name, spec.version, output, attempts=attempts)
            except FutureTimeoutError as exc:
                timed_out = True
                last_error = ToolTimeoutError(
                    f"tool {name} timed out after {spec.timeout_seconds}s"
                )
                if attempt + 1 == spec.max_attempts:
                    raise last_error from exc
            except Exception as exc:  # retry policy is deliberately bounded
                last_error = exc
            finally:
                executor.shutdown(wait=not timed_out, cancel_futures=True)
            if budget is not None and attempt + 1 < spec.max_attempts:
                budget.before_tool_retry()
        raise ToolRegistryError(
            f"tool {name} failed after {attempts} attempt(s): {last_error}"
        ) from last_error
