"""Minimal, OpenTelemetry-compatible distributed tracing for EvidenceClass Agent.

This is a self-implemented, dependency-free tracing layer (not the official
``opentelemetry-sdk``).  It is compatible with the W3C ``traceparent`` header so a
future OTLP exporter can join the same traces, but it keeps the offline CI and the
single-process acceptance runs free of heavyweight dependencies.

Span kinds mirror the tutorial's request path:

    api → queue → worker → node → tool → model

A span tree is built from parent/child ``span_id`` relationships and propagated
across thread and process boundaries by re-binding the active span context, the
same way :mod:`packages.observability.correlation` already crosses those edges.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from .correlation import CORRELATION_FIELDS, current as current_correlation
from .logging import BLOCKED_CONTENT_KEYS, SENSITIVE_KEY_PATTERN, redact_value

#: The six span categories that make up one request path.
SPAN_KINDS: tuple[str, ...] = ("api", "queue", "worker", "node", "tool", "model")

TRACE_VERSION = "00"
_REMOTE_SPAN_NAME = "(remote-context)"

_TRACEPARENT_RE = re.compile(
    r"^(?P<version>[0-9a-f]{2})-(?P<trace_id>[0-9a-f]{32})-(?P<span_id>[0-9a-f]{16})"
    r"-(?P<flags>[0-9a-f]{2})$"
)


def new_trace_id() -> str:
    """Return a 16-byte (32 hex char) trace id."""

    return uuid4().hex


def new_span_id() -> str:
    """Return an 8-byte (16 hex char) span id."""

    return uuid4().hex[:16]


def format_traceparent(trace_id: str, span_id: str, flags: int = 0) -> str:
    """Serialize a context into the W3C ``traceparent`` form."""

    return f"{TRACE_VERSION}-{trace_id}-{span_id}-{flags & 0xFF:02x}"


def parse_traceparent(value: str | None) -> tuple[str, str, int] | None:
    """Parse a ``traceparent`` value; return ``(trace_id, span_id, flags)`` or ``None``."""

    if not value:
        return None
    match = _TRACEPARENT_RE.match(value.strip())
    if match is None:
        return None
    return (match.group("trace_id"), match.group("span_id"), int(match.group("flags"), 16))


@dataclass(frozen=True)
class SpanContext:
    """The wire identity of a span: enough to parent a child span under it."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    flags: int = 0


class SpanStatus:
    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


@dataclass
class SpanEvent:
    name: str
    timestamp_ns: int
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """One unit of work in the distributed trace tree."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: str
    start_ns: int
    end_ns: int = 0
    status: str = SpanStatus.UNSET
    status_message: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    correlation: dict[str, str] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)
    _remote: bool = False

    def context(self) -> SpanContext:
        return SpanContext(
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            flags=0,
        )

    def duration_ms(self) -> float:
        if self.end_ns <= self.start_ns:
            return 0.0
        return round((self.end_ns - self.start_ns) / 1_000_000.0, 3)

    def add_event(self, name: str, *, attributes: Mapping[str, Any] | None = None) -> None:
        self.events.append(
            SpanEvent(name=name, timestamp_ns=time.perf_counter_ns(),
                      attributes=redact_value(dict(attributes or {})))
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
            "duration_ms": self.duration_ms(),
            "status": self.status,
            "status_message": self.status_message,
            "attributes": self.attributes,
            "correlation": self.correlation,
            "events": [
                {"name": e.name, "timestamp_ns": e.timestamp_ns, "attributes": e.attributes}
                for e in self.events
            ],
        }

    def has_sensitive_attribute(self) -> bool:
        """True when a raw secret/PII key survived redaction (it should not)."""

        return _scan_sensitive(self.attributes)


def _scan_sensitive(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            if SENSITIVE_KEY_PATTERN.search(name) or name.casefold() in BLOCKED_CONTENT_KEYS:
                # A surviving raw value defeats redaction; anything else already redacted.
                if item not in (None, "[redacted]"):
                    return True
            if _scan_sensitive(item):
                return True
        return False
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_scan_sensitive(item) for item in value)
    return False


class TraceStore:
    """Holds finished spans keyed by trace id (in-memory)."""

    def __init__(self) -> None:
        self._traces: dict[str, list[Span]] = {}

    def record(self, span: Span) -> None:
        if span._remote:
            return
        self._traces.setdefault(span.trace_id, []).append(span)

    def get_trace(self, trace_id: str) -> list[Span]:
        return list(self._traces.get(trace_id, []))

    def list_traces(self) -> list[str]:
        return sorted(self._traces)

    def clear(self) -> None:
        self._traces.clear()


class JsonlTraceStore(TraceStore):
    """Persists finished spans as newline-delimited JSON under a directory.

    The default location is ``runs/traces`` (already gitignored) so a real
    deployment can grep/inspect traces without touching the repository.
    """

    def __init__(self, directory: str | os.PathLike[str] | None = None) -> None:
        super().__init__()
        path = Path(directory) if directory is not None else self._default_dir()
        path.mkdir(parents=True, exist_ok=True)
        self._directory = path

    @staticmethod
    def _default_dir() -> Path:
        env = os.getenv("EVIDENCECLASS_TRACE_DIR")
        if env:
            return Path(env)
        return Path(os.getcwd()) / "runs" / "traces"

    def record(self, span: Span) -> None:
        super().record(span)
        if span._remote:
            return
        line = span.to_dict()
        line["_recorded_at"] = time.time()
        with (self._directory / f"{span.trace_id}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")

    def get_trace(self, trace_id: str) -> list[Span]:
        live = super().get_trace(trace_id)
        if live:
            return live
        file = self._directory / f"{trace_id}.jsonl"
        if not file.exists():
            return []
        spans: list[Span] = []
        with file.open("r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                spans.append(_span_from_dict(json.loads(raw)))
        return spans


def _span_from_dict(data: Mapping[str, Any]) -> Span:
    span = Span(
        trace_id=data["trace_id"],
        span_id=data["span_id"],
        parent_span_id=data.get("parent_span_id"),
        name=data["name"],
        kind=data["kind"],
        start_ns=data.get("start_ns", 0),
        end_ns=data.get("end_ns", 0),
        status=data.get("status", SpanStatus.UNSET),
        status_message=data.get("status_message", ""),
        attributes=dict(data.get("attributes", {})),
        correlation=dict(data.get("correlation", {})),
    )
    for event in data.get("events", []):
        span.events.append(
            SpanEvent(
                name=event["name"],
                timestamp_ns=event.get("timestamp_ns", 0),
                attributes=dict(event.get("attributes", {})),
            )
        )
    return span


class Tracer:
    """Creates spans, tracks the active span and renders finished traces."""

    def __init__(self, store: TraceStore | None = None) -> None:
        self._store = store or TraceStore()
        self._current: ContextVar[Span | None] = ContextVar("evidenceclass_span", default=None)

    # -- context ----------------------------------------------------------
    def current(self) -> Span | None:
        return self._current.get()

    def current_context(self) -> SpanContext | None:
        span = self._current.get()
        return span.context() if span is not None else None

    def to_headers(self) -> dict[str, str]:
        ctx = self.current_context()
        if ctx is None:
            return {}
        return {"traceparent": format_traceparent(ctx.trace_id, ctx.span_id, ctx.flags)}

    @contextmanager
    def resume_from_headers(self, headers: Mapping[str, str] | None) -> Iterator[SpanContext | None]:
        ctx = self._context_from_headers(headers)
        with self.resume_from_context(ctx):
            yield ctx

    @contextmanager
    def resume_from_context(self, ctx: SpanContext | None) -> Iterator[SpanContext | None]:
        if ctx is None:
            yield None
            return
        remote = Span(
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            parent_span_id=ctx.parent_span_id,
            name=_REMOTE_SPAN_NAME,
            kind=_REMOTE_SPAN_NAME,
            start_ns=0,
            _remote=True,
        )
        token = self._current.set(remote)
        try:
            yield ctx
        finally:
            self._current.reset(token)

    def _context_from_headers(self, headers: Mapping[str, str] | None) -> SpanContext | None:
        if not headers:
            return None
        traceparent = headers.get("traceparent") or headers.get("Traceparent")
        parsed = parse_traceparent(traceparent)
        if parsed is None:
            return None
        trace_id, span_id, flags = parsed
        return SpanContext(trace_id=trace_id, span_id=span_id, parent_span_id=None, flags=flags)

    # -- span lifecycle ---------------------------------------------------
    @contextmanager
    def span(
        self,
        name: str,
        kind: str,
        *,
        attributes: Mapping[str, Any] | None = None,
        parent: Span | SpanContext | None = None,
    ) -> Iterator[Span]:
        if kind not in SPAN_KINDS:
            raise ValueError(f"unknown span kind: {kind!r} (expected one of {SPAN_KINDS})")
        parent_ctx = self._resolve_parent(parent)
        trace_id = parent_ctx.trace_id if parent_ctx is not None else new_trace_id()
        span = Span(
            trace_id=trace_id,
            span_id=new_span_id(),
            parent_span_id=parent_ctx.span_id if parent_ctx is not None else None,
            name=name,
            kind=kind,
            start_ns=time.perf_counter_ns(),
            attributes=_redact_attributes(attributes),
            correlation=_correlation_snapshot(),
        )
        token = self._current.set(span)
        try:
            yield span
        except Exception as exc:  # noqa: BLE001 - record failure into the span
            span.status = SpanStatus.ERROR
            span.status_message = f"{type(exc).__name__}: {exc}"[:200]
            raise
        finally:
            span.end_ns = time.perf_counter_ns()
            if span.status == SpanStatus.UNSET:
                span.status = SpanStatus.OK
            self._current.reset(token)
            self._store.record(span)

    def _resolve_parent(self, parent: Span | SpanContext | None) -> SpanContext | None:
        if parent is None:
            return self.current_context()
        if isinstance(parent, Span):
            return parent.context()
        return parent

    # -- rendering --------------------------------------------------------
    def render_trace_text(self, trace_id: str) -> str:
        spans = self._store.get_trace(trace_id)
        if not spans:
            return f"(no spans recorded for trace {trace_id})"
        return _render_tree(spans, mode="text")

    def render_trace_markdown(self, trace_id: str) -> str:
        spans = self._store.get_trace(trace_id)
        if not spans:
            return f"*no spans recorded for trace `{trace_id}`*"
        return _render_tree(spans, mode="markdown")

    def export_trace_json(self, trace_id: str) -> dict[str, Any]:
        spans = self._store.get_trace(trace_id)
        return {
            "trace_id": trace_id,
            "span_count": len(spans),
            "kinds": sorted({s.kind for s in spans}),
            "spans": [s.to_dict() for s in spans],
        }


def _redact_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    return redact_value(dict(attributes or {}))


def _correlation_snapshot() -> dict[str, str]:
    scope = current_correlation()
    if scope is None:
        return {}
    return {name: str(value) for name, value in scope.as_dict().items() if value is not None}


def _build_tree(spans: list[Span]) -> dict[str | None, list[Span]]:
    children: dict[str | None, list[Span]] = {}
    for span in spans:
        children.setdefault(span.parent_span_id, []).append(span)
    for bucket in children.values():
        bucket.sort(key=lambda s: s.start_ns)
    return children


def _render_tree(spans: list[Span], *, mode: str) -> str:
    children = _build_tree(spans)
    roots = children.get(None, [])
    if not roots:
        # No explicit root: attach orphans under a synthetic header.
        roots = sorted(spans, key=lambda s: s.start_ns)[:1]
    lines: list[str] = []
    if mode == "markdown":
        lines.append("```text")
    _render_nodes(children, roots, depth=0, lines=lines)
    out = "\n".join(lines)
    if mode == "markdown":
        out += "\n```"
    return out


def _render_nodes(
    children: dict[str | None, list[Span]], nodes: list[Span], *, depth: int, lines: list[str]
) -> None:
    for span in nodes:
        dur = f"{span.duration_ms():.1f}ms" if span.duration_ms() else "-"
        marker = "x" if span.status == SpanStatus.ERROR else "*"
        lines.append(f"{'  ' * depth}{marker} [{span.kind}] {span.name} ({dur})")
        for key, value in span.attributes.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"{'  ' * (depth + 1)}: {key} = {value}")
        _render_nodes(children, children.get(span.span_id, []), depth=depth + 1, lines=lines)


#: Process-wide default tracer used by the API, worker and instrumentation.
TRACER = Tracer()


def tracer() -> Tracer:
    return TRACER
