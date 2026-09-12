"""Observability, reliability and performance primitives for EvidenceClass Agent.

This package is the single home for cross-cutting concerns introduced in stage 12:

- :mod:`packages.observability.correlation` — the seven unified correlation ids
- :mod:`packages.observability.logging` — structured JSON logs with redaction
- :mod:`packages.observability.metrics` — counters, gauges and histograms
- :mod:`packages.observability.timing` — per-run stage timeline and memory sampling
- :mod:`packages.observability.reliability` — stable infrastructure failure classification
- :mod:`packages.observability.faults` — the deterministic fault-injection harness
"""

from .correlation import (
    CORRELATION_FIELDS,
    HEADER_NAMES,
    CorrelationContext,
    bind,
    current,
    require_current,
)
from .logging import (
    JsonFormatter,
    configure_logging,
    emit_event,
    get_logger,
    redact_value,
    validate_record,
)
from .metrics import (
    METRIC_MEDIA_PEAK_MEMORY,
    METRIC_MEDIA_REALTIME_FACTOR,
    METRIC_MODEL_429,
    METRIC_MODEL_5XX,
    METRIC_MODEL_COST,
    METRIC_MODEL_TOKENS,
    METRIC_REVIEW_BACKLOG,
    METRIC_REVIEW_DURATION,
    METRIC_TOOL_CALLS,
    METRIC_TOOL_RETRIES,
    METRIC_WORKER_ACTIVE,
    MetricsRegistry,
    metrics,
    record_media_processing,
    record_model_call,
    record_tool_call,
    record_tool_retry,
    set_review_backlog,
    set_worker_active,
)
from .metrics import record_review_duration
from .reliability import ReliabilityVerdict, classify_infrastructure_error
from .timing import STAGE_NAMES, StageTimeline, peak_memory_mb
from .tracing import (
    SPAN_KINDS,
    JsonlTraceStore,
    Span,
    SpanContext,
    SpanStatus,
    TraceStore,
    TRACER,
    Tracer,
    format_traceparent,
    new_span_id,
    new_trace_id,
    parse_traceparent,
    tracer,
)

__all__ = [
    "CORRELATION_FIELDS",
    "HEADER_NAMES",
    "SPAN_KINDS",
    "STAGE_NAMES",
    "CorrelationContext",
    "JsonFormatter",
    "MetricsRegistry",
    "METRIC_MEDIA_PEAK_MEMORY",
    "METRIC_MEDIA_REALTIME_FACTOR",
    "METRIC_MODEL_429",
    "METRIC_MODEL_5XX",
    "METRIC_MODEL_COST",
    "METRIC_MODEL_TOKENS",
    "METRIC_REVIEW_BACKLOG",
    "METRIC_REVIEW_DURATION",
    "METRIC_TOOL_CALLS",
    "METRIC_TOOL_RETRIES",
    "METRIC_WORKER_ACTIVE",
    "ReliabilityVerdict",
    "Span",
    "SpanContext",
    "SpanStatus",
    "StageTimeline",
    "TraceStore",
    "TRACER",
    "Tracer",
    "bind",
    "classify_infrastructure_error",
    "configure_logging",
    "current",
    "emit_event",
    "format_traceparent",
    "get_logger",
    "metrics",
    "new_span_id",
    "new_trace_id",
    "parse_traceparent",
    "peak_memory_mb",
    "record_media_processing",
    "record_model_call",
    "record_review_duration",
    "record_tool_call",
    "record_tool_retry",
    "redact_value",
    "require_current",
    "set_review_backlog",
    "set_worker_active",
    "tracer",
    "validate_record",
]
