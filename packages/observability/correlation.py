"""Request/run-scoped correlation identifiers propagated across API, queue and worker.

Every log line, metric sample and event should be attributable to the same seven
identifiers so that one user-visible failure can be traced back to a concrete
model call.  The context is stored in a :mod:`contextvars` variable, which is
copied into thread-pool workers and can be serialized into Celery task headers.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from uuid import uuid4

CORRELATION_FIELDS: tuple[str, ...] = (
    "request_id",
    "workspace_id",
    "job_id",
    "run_id",
    "step_id",
    "tool_call_id",
    "model_call_id",
)

#: Canonical HTTP/Celery header names for each correlation field.
HEADER_NAMES: dict[str, str] = {
    "request_id": "X-Request-ID",
    "workspace_id": "X-Workspace-ID",
    "job_id": "X-Job-ID",
    "run_id": "X-Run-ID",
    "step_id": "X-Step-ID",
    "tool_call_id": "X-Tool-Call-ID",
    "model_call_id": "X-Model-Call-ID",
}

_HEADER_LOOKUP: dict[str, str] = {
    header.casefold(): field for field, header in HEADER_NAMES.items()
}


@dataclass(frozen=True)
class CorrelationContext:
    """Immutable correlation scope for one API request or one worker execution."""

    request_id: str
    workspace_id: str | None = None
    job_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    tool_call_id: str | None = None
    model_call_id: str | None = None

    def __post_init__(self) -> None:
        if not str(self.request_id).strip():
            raise ValueError("request_id is required to open a correlation scope")

    @classmethod
    def new(cls, request_id: str | None = None, **values: object) -> CorrelationContext:
        """Create a scope, generating a request id when the caller has none."""

        return cls(request_id=request_id or str(uuid4()), **_clean(values))

    @classmethod
    def from_mapping(cls, values: Mapping[str, object] | None) -> CorrelationContext:
        data = _clean(values or {})
        request_id = data.pop("request_id", None) or str(uuid4())
        return cls(request_id=request_id, **data)

    @classmethod
    def from_headers(cls, headers: Mapping[str, str] | None) -> CorrelationContext:
        """Read identifiers from HTTP headers or Celery task headers."""

        if not headers:
            return cls.new()
        found: dict[str, object] = {}
        for key, value in headers.items():
            field = _HEADER_LOOKUP.get(str(key).casefold())
            if field is not None and value not in (None, ""):
                found[field] = value
        return cls.from_mapping(found)

    def derive(self, **values: object) -> CorrelationContext:
        """Return a child scope with a narrower (or deeper) correlation level."""

        return replace(self, **_clean(values))

    def as_dict(self, *, include_none: bool = False) -> dict[str, str | None]:
        items = {name: getattr(self, name) for name in CORRELATION_FIELDS}
        return {name: value for name, value in items.items() if include_none or value is not None}

    def as_labels(self) -> dict[str, str]:
        """String-only projection safe for metric labels and log fields."""

        return {name: str(value) for name, value in self.as_dict().items() if value is not None}

    def to_headers(self) -> dict[str, str]:
        return {
            HEADER_NAMES[name]: str(value)
            for name in CORRELATION_FIELDS
            if (value := getattr(self, name)) is not None
        }


def _clean(values: Mapping[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for name in CORRELATION_FIELDS:
        value = values.get(name)
        if value is not None:
            cleaned[name] = str(value)
    return cleaned


_current: ContextVar[CorrelationContext | None] = ContextVar(
    "evidenceclass_correlation", default=None
)


def current() -> CorrelationContext | None:
    """Return the active scope, or ``None`` when no scope was ever bound."""

    return _current.get()


def require_current() -> CorrelationContext:
    """Return the active scope, creating a detached one if none is bound."""

    value = _current.get()
    if value is None:
        value = CorrelationContext.new()
        _current.set(value)
    return value


def set_current(context: CorrelationContext) -> Token[CorrelationContext | None]:
    return _current.set(context)


def reset_current(token: Token[CorrelationContext | None]) -> None:
    _current.reset(token)


@contextmanager
def bind(
    context: CorrelationContext | Mapping[str, object] | None = None,
    **values: object,
) -> Iterator[CorrelationContext]:
    """Bind a correlation scope for the duration of the ``with`` block.

    An existing scope is inherited so that nested helpers only need to declare
    the level they change (for example a tool call binding ``tool_call_id``).
    """

    if isinstance(context, CorrelationContext):
        scope = context
    elif isinstance(context, Mapping):
        base = _current.get()
        scope = (base or CorrelationContext.new()).derive(**_clean(context))
    else:
        scope = _current.get() or CorrelationContext.new()
    if values:
        scope = scope.derive(**values)
    token = _current.set(scope)
    try:
        yield scope
    finally:
        _current.reset(token)
